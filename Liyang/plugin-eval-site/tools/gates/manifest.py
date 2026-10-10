"""validation/_gates/manifest.json：本批验证的身份（文档哈希、代码版本、工具哈希、范围）与 review.json（复核状态）。"""
from __future__ import annotations
import json
from pathlib import Path

from tools.gates.common import ROOT, VAL, HMB, sha256_file, wjson, git_head, now_cst


def main():
    docs = {p.name: sha256_file(p) for p in sorted((ROOT / "docs/v3").glob("*.md"))}
    sums = {}
    for line in (ROOT / "docs/v3/SHA256SUMS").read_text(encoding="utf-8").splitlines():
        h, n = line.split(None, 1); sums[n.strip()] = h
    tools = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in sorted((ROOT / "tools/gates").glob("*.py"))}
    man = {"validation_id": "_gates", "scope": "端到端验证计划 v0 门槛 2–6（受控夹具、公平性、安全案例、追根与失效、故障注入）；门槛 1 不在本批",
           "created": now_cst(), "executor": "pes-e2e-gates（代理）", "independent_reviewer": None,
           "docs_sha256": docs, "docs_match_SHA256SUMS": all(docs.get(k) == v for k, v in sums.items()), "docs_not_in_SHA256SUMS": sorted(k for k in docs if k not in sums),
           "harness_git_head": git_head(), "hmb_git": git_head(HMB),
           "judge_py_sha256": sha256_file(ROOT / "harness/judge.py"), "examA_py_sha256": sha256_file(ROOT / "harness/examA.py"),
           "upstream_hmb_judge_sha256": sha256_file(HMB / "judge.py"), "tools_sha256": tools,
           "model": "cline-pass/deepseek-v4.1-flash（经 harness/llm.py 匀速闸）",
           "outputs": {"gate2": "validation/_gates/gate2/", "regression": "validation/_gates/regression/", "gate3": "validation/_gates/gate3/",
                       "gate4": "validation/_gates/gate4/", "gate5+6③": "validation/_gates/gate5_6_evidence/",
                       "gate6①": "validation/_gates/gate6/judge_fault/", "gate6②": "validation/_gates/gate6/state_restore/",
                       "replicas(可销毁, 不入 git)": "validation/_gates/replica/"}}
    wjson(VAL / "manifest.json", man)
    wjson(VAL / "review.json", {"status": "未复核", "reviewer": None,
                                "note": "计划 §8 通过规则要求独立复核完成；本批无独立复核人 ⇒ 任何门槛最多记为「本批检测通过（待独立复核）」，不能记为正式通过。",
                                "at": now_cst()})
    print(json.dumps({k: man[k] for k in ("docs_match_SHA256SUMS", "harness_git_head")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
