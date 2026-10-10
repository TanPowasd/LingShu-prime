"""考场运行器：一个插件臂 × 考卷 B × 多种子。逐题落盘，支持 --resume。

  python -m harness.run --plugin null  --seeds 1,2,3 --out runs/B_null
  python -m harness.run --plugin bm25  --seeds 1,2,3 --out runs/B_bm25 --resume
  python -m harness.run --plugin plugins/dsh-memory/adapter.py:DshMemoryPlugin --seeds 1,2,3 --out runs/B_dsh

阶段：① 插件期（沙箱 → install → 快照 → ingest → 逐题 recall → uninstall → 残留 diff）
     ② 作答期（每种子 × 每题：生成器作答，同提示词模板/同参数，唯一变量 = 插件给的材料）
     ③ 判分期（每种子一批：双判官 + 混入 48 锚上岗考；不达标整批作废重批）
     ④ 汇总（summary.json）+ 渲染时间轴
"""
from __future__ import annotations
import argparse, hashlib, importlib, importlib.util, json, os, subprocess, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import examB, judge as J, llm
from .adapter import Plugin
from .plugins_builtin import BM25Plugin, NullPlugin
from .recorder import Recorder, render_timeline
from .sandbox import Sandbox

GEN_TEMPERATURE = 0.7     # 种子 = 独立重复采样（温度>0 才有种子间方差）；判官恒 0
GEN_MAX_TOKENS = 1500
JUDGE_MAX_TOKENS = 600


def load_plugin(spec: str) -> Plugin:
    if spec == "null":
        return NullPlugin()
    if spec == "bm25":
        return BM25Plugin()
    path, _, cls = spec.partition(":")
    if path.endswith(".py"):
        sp = importlib.util.spec_from_file_location("pes_plugin_" + hashlib.md5(path.encode()).hexdigest()[:6], path)
        mod = importlib.util.module_from_spec(sp); sys.modules[sp.name] = mod; sp.loader.exec_module(mod)
    else:
        mod = importlib.import_module(path)
    return getattr(mod, cls)()


def git_sha(d) -> str:
    try:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return "?"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def wjson(p: Path, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def rjson(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=examB.DEFAULT_K)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 卡（冒烟）")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--hmb", default=str(examB.HMB))
    ap.add_argument("--skip-judge", action="store_true")
    a = ap.parse_args(argv)

    examB.set_root(a.hmb)
    out = Path(a.out); (out / "q").mkdir(parents=True, exist_ok=True); (out / "judge").mkdir(exist_ok=True)
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    plugin = load_plugin(a.plugin)
    run_id = out.name
    rec = Recorder(out / "recording.jsonl", run_id, resume=a.resume)
    cards = examB.load_cards()
    if a.limit:
        cards = cards[:a.limit]
    by_id = {c["id"]: c for c in cards}
    cfg = {"exam": "B/e2e-C v0.1", "plugin": a.plugin, "plugin_name": plugin.name, "plugin_version": plugin.version,
           "plugin_kind": getattr(plugin, "kind", "python"),
           "generator": {"model": llm.MODEL, "temperature": GEN_TEMPERATURE, "max_tokens": GEN_MAX_TOKENS, "thinking": "off"},
           "judge": {"model": llm.MODEL, "temperature": 0.0, "max_tokens": JUDGE_MAX_TOKENS, "thinking": "off", "n_judges": 2},
           "seeds": seeds, "k": a.k, "material_cap": examB.MATERIAL_CAP, "n_cards": len(cards),
           "prompt_sha": {"gen_system": sha(examB.GEN_SYSTEM), "contract": sha(examB.CONTRACT), "judge_system": sha(J.JUDGE_SYSTEM)},
           "cards_sha": examB.file_sha(examB.CARDS_JSON), "hmb_git": git_sha(examB.HMB),
           "harness_git": git_sha(Path(__file__).resolve().parent.parent), "anchor_seed": J.ANCHOR_SEED}
    cfgp = out / "config.json"
    if cfgp.exists() and a.resume:
        old = rjson(cfgp)
        for key in ("plugin", "generator", "judge", "seeds", "k", "material_cap", "prompt_sha", "cards_sha"):
            if old.get(key) != cfg.get(key):
                raise SystemExit(f"--resume 配置不一致：{key}（旧 {old.get(key)} vs 新 {cfg.get(key)}）")
    wjson(cfgp, cfg)
    rec.event("run.config", **cfg)
    statep = out / "state.json"
    state = rjson(statep) if statep.exists() else {}

    # ---------- ① 插件期 ----------
    need = [c for c in cards if not (out / "q" / f"{c['id']}.recall.json").exists()]
    if need:
        sbx = Sandbox(run_id, fresh=True)
        plugin.sandbox = sbx
        rec.event("sandbox.create", root=str(sbx.root), env_keys=sorted(sbx.env))
        snap0 = sbx.snapshot()
        t0 = time.monotonic()
        try:
            ir = plugin.install(rec)
        except Exception as e:
            ir = type("IR", (), {"ok": False, "steps": 0, "errors": [repr(e)]})()
            rec.event("plugin.install.exception", tb=traceback.format_exc()[-4000:])
        ev = rec.event("plugin.install.result", ok=ir.ok, steps=ir.steps, errors=ir.errors, dur_s=round(time.monotonic() - t0, 3))
        state["install"] = {"ok": ir.ok, "steps": ir.steps, "errors": ir.errors, "dur_s": ev["dur_s"], "ev": [ev["seq"], ev["t"]]}
        snap1 = sbx.snapshot()
        state["install"]["footprint"] = Sandbox.diff(snap0, snap1)
        wjson(statep, state)
        if not ir.ok:
            rec.event("run.abort", reason="安装失败 → 🚧 没法测（只出好不好用单）")
            state["aborted"] = "install_failed"; wjson(statep, state); rec.close()
            render_timeline(out / "recording.jsonl", out / "timeline.md"); return 2
        sessions = examB.all_sessions()
        t0 = time.monotonic()
        ingest_err = None
        try:
            restored = bool(getattr(plugin, "restore", lambda r: False)(rec)) if a.resume else False
            if not restored:
                plugin.ingest(sessions, rec)
        except Exception as e:
            ingest_err = repr(e)
            rec.event("plugin.ingest.exception", tb=traceback.format_exc()[-4000:])
        ev = rec.event("plugin.ingest.result", ok=ingest_err is None, error=ingest_err, dur_s=round(time.monotonic() - t0, 3),
                       turns=sum(len(s["turns"]) for s in sessions), chars=sum(len(t["text"]) for s in sessions for t in s["turns"]))
        state["ingest"] = {"ok": ingest_err is None, "error": ingest_err, "dur_s": ev["dur_s"], "turns": ev["turns"], "ev": [ev["seq"], ev["t"]]}
        lat = []
        for c in need:
            q = examB.query_of(c)
            t1 = time.monotonic(); err = None
            try:
                items = plugin.recall(q, a.k, rec) if ingest_err is None else []
            except Exception as e:
                items, err = [], repr(e)
                rec.event("plugin.recall.exception", qid=c["id"], tb=traceback.format_exc()[-3000:])
            dt = time.monotonic() - t1; lat.append(dt)
            items = [{"text": str(i.get("text", "")), "source": i.get("source")} for i in (items or [])][:a.k]
            kept, audit = examB.leak_filter(items, c)
            mat = examB.assemble_material(kept, q)
            ev = rec.event("plugin.recall", qid=c["id"], query=q, k=a.k, latency_s=round(dt, 3), error=err,
                           sources=[i["source"] for i in items], leak_audit=audit,
                           material=[{"source": m["source"], "chars": len(m["text"])} for m in mat])
            wjson(out / "q" / f"{c['id']}.recall.json", {"qid": c["id"], "error": err or (ingest_err and "ingest_failed"),
                  "latency_s": dt, "raw_sources": [i["source"] for i in items], "leak_audit": audit,
                  "material": [{k: m[k] for k in ("text", "source", "file", "start", "end")} for m in mat],
                  "ev": [ev["seq"], ev["t"]]})
        state.setdefault("recall_latency_s", []).extend(round(x, 4) for x in lat)
        t0 = time.monotonic()
        try:
            un = plugin.uninstall(rec) or {}
        except Exception as e:
            un = {"residue_paths": [], "error": repr(e)}
        snap2 = sbx.snapshot()
        residue = Sandbox.diff(snap0, snap2)
        ev = rec.event("plugin.uninstall.result", reported=un, residue=residue, dur_s=round(time.monotonic() - t0, 3))
        state["uninstall"] = {"reported": un, "residue": residue, "ev": [ev["seq"], ev["t"]]}
        state["permissions"] = getattr(plugin, "permissions", None)
        state["sandbox_env_has_api_key"] = "CLINE_API_KEY" in sbx.env
        wjson(statep, state)

    # ---------- ② 作答期 ----------
    gen = llm.Client("generator", temperature=GEN_TEMPERATURE, max_tokens=GEN_MAX_TOKENS)

    def answer(job):
        seed, c = job
        p = out / "q" / f"{c['id']}.s{seed}.gen.json"
        if p.exists():
            return
        r = rjson(out / "q" / f"{c['id']}.recall.json")
        msgs = examB.gen_messages(c, r["material"])
        try:
            res = gen.chat(msgs, rec, tag=f"gen|{c['id']}|s{seed}", seed=seed)
        except llm.LLMError as e:
            rec.event("gen.error", qid=c["id"], seed=seed, error=str(e)[:300]); return
        ans = examB.parse_answer(res["content"], c["id"])
        bc = examB.check_basis(ans["basis"])
        ev = rec.event("gen.answer", qid=c["id"], seed=seed, parse_err=ans["parse_err"], prediction=ans["prediction"],
                       basis_check=bc, usage=res["usage"])
        wjson(p, {"qid": c["id"], "seed": seed, "raw": res["content"], "answer": ans, "basis_check": bc,
                  "usage": res["usage"], "finish_reason": res["finish_reason"], "ev": [ev["seq"], ev["t"]]})

    jobs = [(s, c) for s in seeds for c in cards]
    with ThreadPoolExecutor(a.concurrency) as ex:
        list(ex.map(answer, jobs))
    missing = [(s, c["id"]) for s, c in jobs if not (out / "q" / f"{c['id']}.s{s}.gen.json").exists()]
    if missing:
        rec.event("gen.incomplete", missing=len(missing))
        rec.close(); render_timeline(out / "recording.jsonl", out / "timeline.md")
        print(f"作答未完成 {len(missing)} 条，请 --resume 续跑"); return 3

    # ---------- ③ 判分期 ----------
    if not a.skip_judge:
        anchors = J.build_anchors(examB.load_cards())
        all_by_id = {c["id"]: c for c in examB.load_cards()}
        for s in seeds:
            jp = out / "judge" / f"s{s}.json"
            if jp.exists() and rjson(jp).get("status") == "valid":
                continue
            items = []
            for c in cards:
                g = rjson(out / "q" / f"{c['id']}.s{s}.gen.json")
                items.append({"key": f"{c['id']}.s{s}", "card": c["id"], "prediction": g["answer"]["prediction"],
                              "auto": "parse_err" if g["answer"]["parse_err"] else None,
                              "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
            res = J.judge_batch(all_by_id, items, anchors, rec,
                                make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=JUDGE_MAX_TOKENS),
                                concurrency=a.concurrency, batch_tag=f"{run_id}|s{s}",
                                cache_path=str(out / "judge" / f"s{s}.verdicts.jsonl"))
            wjson(jp, res)

    # ---------- ④ 汇总 ----------
    summ = summarize(out, cards, seeds, state)
    wjson(out / "summary.json", summ)
    rec.event("run.summary", **{k: v for k, v in summ.items() if k != "per_item"}, llm_totals_this_process=dict(llm.TOTALS))
    rec.close()
    render_timeline(out / "recording.jsonl", out / "timeline.md")
    print(json.dumps({k: v for k, v in summ.items() if k not in ("per_item",)}, ensure_ascii=False, indent=1))
    return 0


def summarize(out: Path, cards, seeds, state) -> dict:
    per_item = {}
    seed_stats = {}
    basis = {"n": 0, "verbatim": 0, "line_pm3": 0, "cards_with_basis": 0}
    tok = {"gen_prompt": 0, "gen_completion": 0}
    parse_err = 0
    for s in seeds:
        jp = out / "judge" / f"s{s}.json"
        j = rjson(jp) if jp.exists() else None
        cnt = {"strict": 0, "paraphrase": 0, "miss": 0}
        rows = {r["card"]: r for r in (j["items"] if j else [])}
        for c in cards:
            g = rjson(out / "q" / f"{c['id']}.s{s}.gen.json")
            parse_err += g["answer"]["parse_err"]
            tok["gen_prompt"] += g["usage"].get("prompt_tokens") or 0
            tok["gen_completion"] += g["usage"].get("completion_tokens") or 0
            bc = g["basis_check"]
            basis["n"] += len(bc); basis["verbatim"] += sum(b["verbatim"] for b in bc)
            basis["line_pm3"] += sum(b["line_pm3"] for b in bc); basis["cards_with_basis"] += bool(bc)
            r = rows.get(c["id"])
            if r:
                cnt[r["final"]] += 1
                per_item.setdefault(c["id"], {})[str(s)] = {"final": r["final"], "final_strict": r["final_strict"],
                                                           "score": r["score"], "v1": r["v1"], "v2": r["v2"]}
        n = len(cards)
        seed_stats[str(s)] = {**cnt, "n": n, "weighted": round((cnt["strict"] + 0.5 * cnt["paraphrase"]) / n, 4) if j else None,
                              "judge_status": j["status"] if j else "missing", "judge_attempts": j["attempt"] if j else 0,
                              "voided_batches": j.get("voided", 0) if j else 0, "gate": j["gate"] if j else None}
    recall_err = sum(1 for c in cards if rjson(out / "q" / f"{c['id']}.recall.json").get("error"))
    mat_chars = [sum(len(m["text"]) for m in rjson(out / "q" / f"{c['id']}.recall.json")["material"]) for c in cards]
    return {"n_cards": len(cards), "seeds": seeds, "per_seed": seed_stats, "parse_err": parse_err,
            "recall_errors": recall_err, "material_chars_mean": round(sum(mat_chars) / len(mat_chars)),
            "cards_with_material": sum(1 for x in mat_chars if x), "basis": basis, "gen_tokens": tok,
            "install": state.get("install"), "ingest": state.get("ingest"), "per_item": per_item}


if __name__ == "__main__":
    sys.exit(main())
