# -*- coding: utf-8 -*-
"""dsh-auto-memory × 考卷 B · 预注册 B0/P 配对执行器（端到端验证计划 v0 §3 真实链路）。

  python plugins/dsh-auto-memory/run_pairs.py --vdir validation/dam-20261010T1045 [--max-runs N] [--limit-cards N --tag smoke]

按 preregistration.json 的 execution_order 逐个运行（前一个结束才开始下一个），逐卡落盘、可断点续跑。
B0：harness 考卷 B 底子臂同款作答（系统提示 = examB.GEN_SYSTEM；用户消息 = examB.gen_messages(card, [])）。
P ：同上，唯一差别 = 系统提示后追加插件真实注入段（memory:index，宿主仿真 host_emu.mjs 渲染）。
    记忆状态按预注册：其它 15 份语料各自固化一次（阶段 A，真实 LLM）→ 每卡在空记忆根上依固定顺序回放
    阶段 A 的固化输出（插件真实写入/去重/更新/索引代码）→ 再固化本卡语料断点前部分（真实 LLM）→ 渲染注入段。
判分：harness.judge.judge_batch（双判官 + 48 锚混入，未过闸整批作废重批 ≤3 次）。
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from harness import examB, judge as J, llm  # noqa: E402
from harness.recorder import Recorder, render_timeline  # noqa: E402
import emu  # noqa: E402

GEN_T, GEN_MAX = 0.7, 1500
JUDGE_MAX = 600
CWD = "/home/user/hmb-e2e-history"   # 仿真会话 cwd：16 份语料视为同一工作区（同一位使用者的同一段协作史）
VERIFY = HERE / "verify_state.py"
MARKS = (examB.MARK_USER, examB.MARK_AI)


def wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"); os.replace(tmp, p)


def rjson(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def verify(*args) -> dict:
    p = subprocess.run([sys.executable, str(VERIFY), *map(str, args)], capture_output=True, text=True)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        r = {"pass": False, "fails": [f"verifier 输出不可解析 rc={p.returncode}: {p.stdout[-300:]} {p.stderr[-300:]}"]}
    r["rc"] = p.returncode
    return r


# ---------------- 语料 → 宿主事件 ----------------
def session_turns(fname: str, before_line: int | None = None) -> list[dict]:
    out = []
    for t in examB.sessionize(fname)["turns"]:
        if t["role"] not in ("user", "assistant"):
            continue
        s, e = t["start_line"], t["end_line"]
        if before_line is not None:
            if s >= before_line:
                break
            e = min(e, before_line - 1)
        L = examB.corpus_lines(fname)[s - 1:e]
        if L and L[0].strip() in MARKS:      # 说话人标记行 → role 字段（纯格式转换）
            L = L[1:]
        text = "\n".join(L).strip()
        if text:
            out.append({"role": t["role"], "text": text})
    return out


# ---------------- 生成与判分 ----------------
def gen_one(card, system_extra: str | None, seed: int, client, rec, outp: Path, tag: str):
    if outp.exists():
        return
    msgs = examB.gen_messages(card, [])
    if system_extra:
        msgs[0] = {"role": "system", "content": examB.GEN_SYSTEM + "\n\n" + system_extra}
    try:
        res = client.chat(msgs, rec, tag=f"gen|{tag}|{card['id']}|s{seed}", seed=seed)
    except llm.LLMError as e:
        rec.event("gen.error", qid=card["id"], error=str(e)[:300]); return
    ans = examB.parse_answer(res["content"], card["id"])
    ev = rec.event("gen.answer", qid=card["id"], seed=seed, parse_err=ans["parse_err"], prediction=ans["prediction"],
                   usage=res["usage"], system_chars=len(msgs[0]["content"]))
    wjson(outp, {"qid": card["id"], "seed": seed, "raw": res["content"], "answer": ans, "usage": res["usage"],
                 "cost_usd": res["cost_usd"], "finish_reason": res["finish_reason"],
                 "system_sha256": hashlib.sha256(msgs[0]["content"].encode()).hexdigest(),
                 "user_sha256": hashlib.sha256(msgs[1]["content"].encode()).hexdigest(), "ev": [ev["seq"], ev["t"]]})


def judge_run(rdir: Path, cards, seed, rec, run_id, conc):
    jp = rdir / "judge" / "batch.json"
    if jp.exists() and rjson(jp).get("status") == "valid":
        return rjson(jp)
    all_cards = examB.load_cards()
    anchors = J.build_anchors(all_cards)
    by_id = {c["id"]: c for c in all_cards}
    items = []
    for c in cards:
        g = rjson(rdir / "gen" / f"{c['id']}.json")
        items.append({"key": f"{c['id']}.{run_id}", "card": c["id"], "prediction": g["answer"]["prediction"],
                      "auto": "parse_err" if g["answer"]["parse_err"] else None, "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
    (rdir / "judge").mkdir(exist_ok=True)
    res = J.judge_batch(by_id, items, anchors, rec,
                        make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=JUDGE_MAX),
                        concurrency=conc, batch_tag=run_id, cache_path=str(rdir / "judge" / "verdicts.jsonl"))
    wjson(jp, res)
    return res


# ---------------- P：宿主仿真记忆构建 ----------------
def phase_a(rdir: Path, files, rec, conc, run_id) -> dict:
    """每份语料在空记忆根上固化一次（真实 LLM），缓存插件收到的原始输出。"""
    client = emu.consolidation_client()
    outd = rdir / "state" / "phaseA"

    def one(f):
        p = outd / f"{hashlib.sha1(f.encode()).hexdigest()[:10]}.json"
        if p.exists():
            return f, rjson(p)
        mem = outd / (p.stem + ".mem")
        if mem.exists():
            shutil.rmtree(mem)
        pre = verify("card-pre", "--mem", mem)
        job = {"memoryDir": str(mem), "cwd": CWD, "sessions": [{"id": f, "turns": session_turns(f)}]}
        r = emu.run_job(job, rec=rec, client=client, tag=f"{run_id}|A")
        ok = bool(r["done"]) and "fatal" not in (r["done"] or {}) and len(r["calls"]) == 1 and r["calls"][0]["ok"]
        if r["done"] and "manifest" in r["done"]:
            wjson(outd / (p.stem + ".reported_manifest.json"), r["done"]["manifest"])
            post = verify("card-post", "--mem", mem, "--reported", outd / (p.stem + ".reported_manifest.json"))
        else:
            post = {"pass": False, "fails": ["无 manifest"]}
        res = {"file": f, "ok": ok, "check_pre": pre, "check_post": post, "calls": r["calls"], "done": r["done"],
               "stderr": r["stderr"], "rc": r["rc"]}
        rec.event("plugin.consolidate.phaseA", file=f, ok=ok, n_files=len((r["done"] or {}).get("manifest", [])),
                  check_pre=pre["pass"], check_post=post["pass"])
        if ok:
            wjson(p, res)
        return f, res

    with ThreadPoolExecutor(conc) as ex:
        got = dict(ex.map(one, files))
    return got


def phase_b(rdir: Path, cards, files, A: dict, rec, conc, run_id) -> dict:
    client = emu.consolidation_client()
    outd = rdir / "state" / "cards"

    def one(c):
        p = outd / f"{c['id']}.json"
        if p.exists():
            return c["id"], rjson(p)
        mem = outd / f"{c['id']}.mem"
        if mem.exists():
            shutil.rmtree(mem)       # 恢复 = 回到空基线（恢复代码在这里；检查在 verify_state.py）
        pre = verify("card-pre", "--mem", mem)
        cut = int(c["answer"]["human"]["line"])
        sess = []
        for f in files:
            if f == c["file"]:
                continue
            txt = A[f]["calls"][0]["text"]
            sess.append({"id": f, "turns": session_turns(f), "replay": txt})
        sess.append({"id": f"{c['file']}#<L{cut}", "turns": session_turns(c["file"], before_line=cut)})
        job = {"memoryDir": str(mem), "cwd": CWD, "sessions": sess}
        r = emu.run_job(job, rec=rec, client=client, tag=f"{run_id}|B|{c['id']}")
        d = r["done"] or {}
        ok = bool(d) and "fatal" not in d and len(r["calls"]) <= 1 and all(x["ok"] for x in r["calls"])
        if "manifest" in d:
            wjson(outd / f"{c['id']}.reported_manifest.json", d["manifest"])
            post = verify("card-post", "--mem", mem, "--reported", outd / f"{c['id']}.reported_manifest.json")
        else:
            post = {"pass": False, "fails": ["无 manifest"]}
        res = {"qid": c["id"], "ok": ok, "check_pre": pre, "check_post": post, "calls": r["calls"],
               "replay_events": r["events"], "sessions": d.get("sessions"), "section": d.get("section"),
               "section_bytes": d.get("section_bytes"), "all_sections": d.get("all_sections"), "tools": d.get("tools"),
               "manifest": d.get("manifest"), "stderr": r["stderr"], "rc": r["rc"], "fatal": d.get("fatal")}
        ev = rec.event("plugin.inject", qid=c["id"], ok=ok, section_bytes=d.get("section_bytes"),
                       n_mem_files=len(d.get("manifest") or []), check_pre=pre["pass"], check_post=post["pass"])
        res["ev"] = [ev["seq"], ev["t"]]
        if ok:
            wjson(p, res)
        return c["id"], res

    with ThreadPoolExecutor(conc) as ex:
        got = dict(ex.map(one, cards))
    return got


# ---------------- 一次运行 ----------------
def run_one(vdir: Path, prereg: dict, entry: dict, cards, conc: int) -> dict:
    run_id = entry["run_id"]; cond = entry["condition"]; seed = entry["gen_seed"]
    rdir = vdir / "raw" / run_id
    resume = (rdir / "recording.jsonl").exists()
    if not resume:
        pre = verify("run-pre", "--state-root", rdir / "state", "--emu-home", emu.EMU / "home",
                     "--plugin-lib", emu.EMU / "node_modules/dsh-auto-memory/lib/index.js", "--expect-lib-sha", emu.TARBALL_LIB_SHA256)
    rdir.mkdir(parents=True, exist_ok=True)
    rec = Recorder(rdir / "recording.jsonl", run_id, resume=resume)
    if not resume:
        wjson(rdir / "snapshot-check.run-pre.json", pre)
        rec.event("snapshot.check", stage="run-pre", **{k: pre[k] for k in ("pass", "fails")})
    meta = {"run_id": run_id, "pair_id": entry["pair_id"], "scenario_id": entry["scenario_id"], "condition": cond,
            "gen_seed": seed, "order_index": entry["order_index"], "prereg_sha256": prereg["_sha256"],
            "emu": emu.prepare(), "generator": {"model": llm.MODEL, "temperature": GEN_T, "max_tokens": GEN_MAX},
            "judge": {"model": llm.MODEL, "temperature": 0.0, "max_tokens": JUDGE_MAX, "n_judges": 2},
            "prompt_sha": {"gen_system": hashlib.sha256(examB.GEN_SYSTEM.encode()).hexdigest(),
                           "contract": hashlib.sha256(examB.CONTRACT.encode()).hexdigest(),
                           "judge_system": hashlib.sha256(J.JUDGE_SYSTEM.encode()).hexdigest()},
            "cards_sha256": hashlib.sha256(examB.CARDS_JSON.read_bytes()).hexdigest(), "n_cards": len(cards)}
    if not (rdir / "run.json").exists():
        meta["started_wall"] = time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.gmtime(time.time() + 8 * 3600))
        wjson(rdir / "run.json", meta)
    rec.event("run.config", **meta)
    pre = rjson(rdir / "snapshot-check.run-pre.json")
    validity = {"valid": True, "reasons": []}
    if not pre["pass"]:
        validity = {"valid": False, "reasons": ["run-pre 快照检查未通过"] + pre["fails"]}
        wjson(rdir / "validity.json", validity); rec.close(); return validity

    gen = llm.Client("generator", temperature=GEN_T, max_tokens=GEN_MAX)
    inject = {}
    if cond == "P":
        files = examB.corpus_files()
        need_files = sorted({f for f in files})   # 阶段 A：16 份全部（每卡排除本卡语料时取其余 15 份）
        A = phase_a(rdir, need_files, rec, conc, run_id)
        badA = [f for f, r in A.items() if not r.get("ok")]
        if badA:
            validity = {"valid": False, "reasons": [f"阶段A固化失败 {len(badA)} 份"], "files": badA}
            wjson(rdir / "validity.json", validity); rec.close(); return validity
        inject = phase_b(rdir, cards, files, A, rec, conc, run_id)
        bad = [q for q, r in inject.items() if not (r.get("ok") and r["check_pre"]["pass"] and r["check_post"]["pass"])]
        if bad:
            validity = {"valid": False, "reasons": [f"阶段B 记忆构建或快照检查失败 {len(bad)} 卡"], "cards": bad}
            wjson(rdir / "validity.json", validity); rec.close(); return validity
    else:
        b0 = verify("b0", "--state-root", rdir)
        wjson(rdir / "snapshot-check.b0.json", b0)
        if not b0["pass"]:
            validity = {"valid": False, "reasons": ["B0 出现记忆目录"] + b0["fails"]}
            wjson(rdir / "validity.json", validity); rec.close(); return validity

    def g(c):
        extra = (inject[c["id"]]["section"] or None) if cond == "P" else None
        gen_one(c, extra, seed, gen, rec, rdir / "gen" / f"{c['id']}.json", run_id)
    with ThreadPoolExecutor(conc) as ex:
        list(ex.map(g, cards))
    miss = [c["id"] for c in cards if not (rdir / "gen" / f"{c['id']}.json").exists()]
    if miss:
        rec.event("gen.incomplete", missing=miss); rec.close()
        return {"valid": None, "reasons": [f"作答未完成 {len(miss)}，续跑"]}
    if os.environ.get("DAM_SKIP_JUDGE"):
        rec.close(); return {"valid": True, "reasons": ["smoke: 跳过判分"]}
    jr = judge_run(rdir, cards, seed, rec, run_id, conc)
    if jr["status"] != "valid":
        validity = {"valid": False, "reasons": ["判官上岗考 3 次未过（判分器故障，实验无效）"]}
    scores = {r["card"]: J.WEIGHT[r["final"]] for r in jr["items"]}
    wjson(rdir / "scores.json", {"run_id": run_id, "condition": cond, "item_scores": scores,
                                 "score_0_100": round(100 * sum(scores.values()) / len(cards), 4),
                                 "counts": {k: sum(1 for r in jr["items"] if r["final"] == k) for k in J.VERDICTS},
                                 "parse_err": sum(rjson(rdir / "gen" / f"{c['id']}.json")["answer"]["parse_err"] for c in cards),
                                 "judge_attempt": jr["attempt"], "judge_gate": jr["gate"]})
    wjson(rdir / "validity.json", validity)
    rec.event("run.done", validity=validity)
    rec.close(); render_timeline(rdir / "recording.jsonl", rdir / "timeline.md")
    return validity


def _scan_recording(p: Path) -> tuple[int, float]:
    calls = cost = 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            if '"llm.response"' in line:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                calls += 1; cost += float(e.get("cost_usd") or 0)
    return calls, cost


def _readable_prefix(p: Path) -> bytes:
    """逐块读到第一个 EIO 为止（沙箱重启后工作区盘可能出现读不出的尾段）。"""
    out = bytearray()
    fd = os.open(p, os.O_RDONLY)
    try:
        while True:
            try:
                b = os.read(fd, 65536)
            except OSError:
                break
            if not b:
                break
            out += b
    finally:
        os.close(fd)
    return bytes(out)


def _artifact_spend(rdir: Path) -> tuple[int, float]:
    """录像不可读时的下界：按逐题落盘的产物（作答/固化调用）累计；判官缓存不含成本，不计。"""
    calls = cost = 0
    for g in list((rdir / "gen").glob("*.json")) + list((rdir / "state").glob("*/*.json")):
        if "manifest" in g.name:
            continue
        try:
            d = json.loads(g.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "cost_usd" in d and "raw" in d:
            calls += 1; cost += float(d.get("cost_usd") or 0)
        for c in d.get("calls") or []:
            if isinstance(c, dict) and "cost_usd" in c:
                calls += 1; cost += float(c.get("cost_usd") or 0)
    return calls, cost


def budget(vdir: Path, retries: int = 4, wait: float = 2.0) -> dict:
    """预算读数（只读录像统计 llm.response；判定逻辑不在这里）。
    I/O 错误（沙箱重启后的 EIO）：每文件重试 retries 次、间隔 wait 秒；仍失败则取
    max(可读前缀统计, 产物下界) 并在 degraded 中留痕，不再让续跑外壳崩溃。"""
    calls = cost = 0
    degraded = []
    for p in sorted((vdir / "raw").glob("*/recording.jsonl")):
        got = None
        for k in range(retries):
            try:
                got = _scan_recording(p); break
            except OSError as e:
                last = e; time.sleep(wait * (k + 1))
        if got is None:
            c1 = c2 = 0; k1 = k2 = 0.0
            try:
                for line in _readable_prefix(p).decode("utf-8", "ignore").splitlines():
                    if '"llm.response"' in line:
                        try:
                            e = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        c1 += 1; k1 += float(e.get("cost_usd") or 0)
            except OSError:
                pass
            c2, k2 = _artifact_spend(p.parent)
            got = (c1, k1) if k1 >= k2 else (c2, k2)
            degraded.append({"file": str(p.relative_to(vdir)), "error": repr(last)[:120],
                             "prefix": [c1, round(k1, 4)], "artifacts": [c2, round(k2, 4)], "used": [got[0], round(got[1], 4)]})
        calls += got[0]; cost += got[1]
    r = {"calls": calls, "cost_usd": round(cost, 4)}
    if degraded:
        r["degraded"] = degraded
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vdir", required=True)
    ap.add_argument("--max-runs", type=int, default=99)
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    vdir = Path(a.vdir).resolve()
    pp = vdir / "preregistration.json"
    prereg = rjson(pp); prereg["_sha256"] = hashlib.sha256(pp.read_bytes()).hexdigest()
    examB.set_root(prereg["taskset"]["hmb_path"])
    cards = examB.load_cards()
    lim = prereg["sample_plan"].get("limit_cards")
    if lim:
        cards = cards[:lim]
    statusp = vdir / "raw" / "_status.json"
    status = rjson(statusp) if statusp.exists() else {"runs": {}}
    done = 0
    order = list(prereg["execution_order"]) + list(status.get("appended_reruns", []))
    for entry in order:
        rid = entry["run_id"]
        if status["runs"].get(rid, {}).get("final"):
            continue
        if entry["pair_id"] in {x["pair_id"] for x in status.get("invalidated_pairs", [])}:
            status["runs"][rid] = {"final": True, "valid": False, "skipped": "所属配对已整对作废，本侧不运行、不计入"}
            wjson(statusp, status); continue
        b = budget(vdir)
        if b["calls"] > prereg["budget"]["max_llm_calls"] or b["cost_usd"] > prereg["budget"]["max_cost_usd"]:
            status["halt"] = {"reason": "预算上限", **b}; wjson(statusp, status); print("预算上限，停止"); return 4
        print(f"== {rid} ({entry['condition']}) 开始", flush=True)
        try:
            v = run_one(vdir, prereg, entry, cards, a.concurrency)
        except Exception as e:
            v = {"valid": None, "reasons": [f"异常：{e!r}"], "tb": traceback.format_exc()[-3000:]}
        print(f"== {rid} → {v}", flush=True)
        if v.get("valid") is None:
            status["runs"][rid] = {"final": False, "last": v}; wjson(statusp, status); return 3   # 续跑
        status["runs"][rid] = {"final": True, "valid": v["valid"], "validity": v, "budget_after": budget(vdir)}
        if v["valid"] is False:
            # 无效运行留痕，整对重跑（两边都重跑），重跑上限 prereg.rerun_cap_per_pair
            pid = entry["pair_id"]
            nre = sum(1 for e in status.get("appended_reruns", []) if e["orig_pair_id"] == pid and e["condition"] == entry["condition"])
            if nre < prereg["sample_plan"]["rerun_cap_per_pair"]:
                sides = [e for e in prereg["execution_order"] if e["pair_id"] == pid]
                for e in sides:
                    ne = dict(e); ne["run_id"] = f"{e['run_id']}-r{nre + 1}"; ne["pair_id"] = f"{pid}-r{nre + 1}"
                    ne["orig_pair_id"] = pid; ne["reason"] = f"{rid} 无效：{v['reasons'][:2]}"
                    status.setdefault("appended_reruns", []).append(ne)
                status.setdefault("invalidated_pairs", []).append({"pair_id": pid, "by_run": rid, "reasons": v["reasons"]})
                order.extend(status["appended_reruns"][-len(sides):])
        wjson(statusp, status)
        done += 1
        if done >= a.max_runs:
            return 0
    status["all_done"] = True; wjson(statusp, status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
