# -*- coding: utf-8 -*-
"""全量臂停止后的只读核对（不调模型、不改记忆根）。录像续写 runs/everos_checks。
C5 profile 抽取提示词随写入增长（转发器逐次记账，无提示词正文）
C6 user.md 何时最后写回、profile_timestamp_ms
C7 服务日志里 extract_user_profile 的重试 / 非 stop 结束
C8 EverOS 1.4.1 源码事实（Tier 1 直连路径的 profile 触发与选材规则）
C9 吞吐分段（录像 plugin.flush 每分钟计数）与停止时快照
"""
import collections, hashlib, json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline  # noqa

ST = os.path.join(ROOT, "runs/B_everos/everos_state")
SBX = os.path.join(ROOT, "runs/sbx/B_everos")
rec = Recorder(os.path.join(ROOT, "runs/everos_checks/recording.jsonl"), "everos_checks", resume=True)
cite = {}

calls = [json.loads(l) for l in open(os.path.join(ST, "everos_llm_calls.jsonl"), encoding="utf-8") if l.strip()]
big = [c for c in calls if c["prompt_chars"] > 100_000]
rows = [{"wall": c["wall"], "prompt_chars": c["prompt_chars"], "prompt_tokens": c.get("prompt_tokens"),
         "completion_tokens": c.get("completion_tokens"), "finish_reason": c.get("finish_reason"),
         "cost_usd": round(c.get("cost_usd") or 0, 4)} for c in big]
e = rec.event("check.profile_prompt_growth", n_calls_total=len(calls), n_big=len(big),
              big_cost_usd=round(sum(c.get("cost_usd") or 0 for c in big), 4),
              total_cost_usd=round(sum(c.get("cost_usd") or 0 for c in calls), 4),
              big_finish_length=sum(1 for c in big if c.get("finish_reason") == "length"),
              max_prompt_tokens_accepted=max(c.get("prompt_tokens") or 0 for c in big), rows=rows,
              note="提示词 >10 万字的调用（服务日志确认为 extract_user_profile 策略）；最后一次成功返回 09:18，之后该策略的请求全部重试/失败")
cite["C5"] = e

um = os.path.join(ST, "root/dsh/pes-examb/users/pes-user/user.md")
txt = open(um, encoding="utf-8").read()
ts = re.search(r"profile_timestamp_ms:\s*(\d+)", txt)
e = rec.event("check.user_profile_frozen", path=os.path.relpath(um, ROOT), bytes=len(txt.encode()),
              mtime_cst=time.strftime("%H:%M:%S", time.gmtime(os.stat(um).st_mtime + 8 * 3600)),
              profile_timestamp_ms=int(ts.group(1)) if ts else None,
              episode_md_bytes={f: os.path.getsize(os.path.join(os.path.dirname(um), "episodes", f))
                                for f in os.listdir(os.path.join(os.path.dirname(um), "episodes"))})
cite["C6"] = e

log = re.sub(r"\x1b\[[0-9;]*m", "", open(os.path.join(SBX, "server.log"), errors="replace").read())
retry = [l for l in log.splitlines() if "Retrying request to /chat/completions" in l]
retry_prof = [l for l in retry if "strategy_name=extract_user_profile" in l]
nonstop = [l for l in log.splitlines() if "llm_non_stop_finish" in l]
hm = lambda l: (re.search(r"(\d{1,2}:\d\d) [AP]M", l) or re.search(r"T(\d\d:\d\d)", l)).group(1)
e = rec.event("check.profile_strategy_retries", retry_total=len(retry), retry_profile=len(retry_prof),
              retry_profile_first=hm(retry_prof[0]) if retry_prof else None, retry_profile_last=hm(retry_prof[-1]) if retry_prof else None,
              retry_other_first=hm([l for l in retry if l not in retry_prof][0]) if len(retry) > len(retry_prof) else None,
              non_stop_finish=len(nonstop), log=os.path.relpath(os.path.join(SBX, "server.log"), ROOT),
              note="EverOS 侧 openai 客户端超时重试（每个 run_id 2 次后放弃，策略 max_retries=2 再整体重跑）；本站转发器在客户端放弃后仍按 harness/llm.py 重试并置全局冷却，波及其它调用（retry_other）")
cite["C7"] = e

src = os.path.join(SBX, "venv/lib/python3.12/site-packages/everos/memory/strategies/extract_user_profile.py")
s = open(src, encoding="utf-8").read().splitlines()
pick = {n: s[n - 1].strip() for n in (74, 79, 212, 233, 200, 201, 202)}
e = rec.event("check.profile_source_facts", file="everos/memory/strategies/extract_user_profile.py (everos==1.4.1)",
              sha256_16=hashlib.sha256("\n".join(s).encode()).hexdigest()[:16], lines=pick,
              reading="Tier 1（无嵌入）走直连路径：每个 EpisodeExtracted 都触发（INTERVAL=1、MIN_MEMCELLS=1），"
                      "选材＝该用户 profile_timestamp_ms 之后的全部 memcell（list_by_owner_after_ts），按用户串行（partition lock）；"
                      "抽取失败则 profile 不写回、时间戳不前进，下次选材更大。未设 max_tokens。")
cite["C8"] = e

E = [json.loads(l) for l in open(os.path.join(ROOT, "runs/B_everos/recording.jsonl"), encoding="utf-8")]
fl = [x for x in E if x["type"] == "plugin.flush"]
def mins(w):
    m = re.search(r"(\d{1,2}):(\d\d)", w.split("2026-10-10")[1]); return int(m.group(1)) * 60 + int(m.group(2))
per = collections.Counter(mins(x["wall"]) for x in fl)
seg = lambda a, b: sum(v for k, v in per.items() if a <= k <= b)
fin = json.load(open(os.path.join(ST, "final_status_at_stop.json"), encoding="utf-8"))
prog = json.load(open(os.path.join(ST, "ingest_progress.json"), encoding="utf-8"))
e = rec.event("check.throughput_and_stop", per_minute={f"{k // 60}:{k % 60:02d}": v for k, v in sorted(per.items()) if k >= 9 * 60},
              flush_0909_0920=seg(549, 560), flush_0921_0928=seg(561, 568),
              batches_done=fin["batches_done"], batches_total=698, files_started=len(prog), files_total=16,
              progress=prog, llm_calls=fin["llm_calls"], prompt_tokens=fin["prompt_tokens"],
              completion_tokens=fin["completion_tokens"], cost_usd=fin["cost_usd"], n_flush_failed=fin["n_flush_failed"],
              stopped_cst="09:28:57", stop_note="tools/stop_everos_arm.sh 发 SIGTERM；everos server 进程 20 s 内未退出，改发 SIGKILL")
cite["C9"] = e

render_timeline(os.path.join(ROOT, "runs/everos_checks/recording.jsonl"), os.path.join(ROOT, "runs/everos_checks/timeline.md"))
for k, v in cite.items():
    print(k, v["seq"], v["t"])
