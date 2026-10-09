# -*- coding: utf-8 -*-
"""主轮判分：score_sut.py 规则层 → semantic.py 语义层（两判官盲混）+ L2 依据契合判官 → judge_audit 锚自证/一致率。

  python judge_main.py prep     # 规则层 build + 锚集构造 + 两个判官目录各自 prepare（同材料同判据）
  python judge_main.py judge    # 全部请求（真实答卷 + 锚，五臂混合、随机打乱、不含臂名/标签）交两判官
  python judge_main.py final    # finalize + score_sut report（逐判官）+ judge_audit check
判官：J1/J2＝cline-pass/deepseek-v4.1-flash 的两个独立实例（thinking off；J1 t=0 seed11，J2 t=0.6 seed29；各自打乱题序）。
同模型双实例判官，独立性弱于异模型。
"""
import glob
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402
import llm  # noqa: E402

ARMS = H.arms()
J1 = os.path.join(H.OUT, "_hmbrun")
JD = {"J1": J1, "J2": os.path.join(H.OUT, "_hmbrun_J2")}
SEED = 20261009
PY = [sys.executable, "-X", "utf8"]


def sh(args, cwd):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def make_anchors():
    """48 锚（与作者 e2e 锚同构：24 正 / 12 跨卡负 / 12 无关负），机械构造、seed 固定。
    正锚＝该卡全部必答采分点的 point 文本（＋客观题 necessary_conclusion）逐条断言；
    跨卡负锚＝另一张卡的正锚文本；无关负锚＝与小说无关的说明文字。case 名为哈希，不泄露标签。"""
    cards = H.load_cards()
    rnd = random.Random(SEED)
    ids = sorted(cards)
    pos = rnd.sample(ids, 24)
    unrelated = ["明天多云转晴，气温十八到二十四度，适合外出活动。", "这台咖啡机需要每周除垢一次，建议使用柠檬酸溶液。",
                 "本季度销售额同比增长百分之十二，主要来自华东地区。", "猫咪每天需要十二到十六小时的睡眠，属于正常现象。"]

    def pos_text(c):
        t = "；".join(p["point"] for p in H.card_points(c))
        if c.get("necessary_conclusion"):
            t = c["necessary_conclusion"] + "。" + t
        return t
    rows = []
    for q in pos:
        rows.append((q, pos_text(cards[q]), "pass"))
    others = [q for q in ids if q not in pos]
    for i in range(12):
        q = others[i * 3 % len(others)]
        donor = pos[(i * 5 + 7) % 24]
        rows.append((q, pos_text(cards[donor]), "fail"))
    for i in range(12):
        q = others[(i * 3 + 1) % len(others)]
        rows.append((q, unrelated[i % 4] + unrelated[(i + 1) % 4], "fail"))
    root = os.path.join(J1, "anc_main")
    shutil.rmtree(root, ignore_errors=True)
    for q, text, exp in rows:
        case = "x" + hashlib.sha1(f"{q}|{text}".encode()).hexdigest()[:8]
        H.dump(os.path.join(root, q, f"{case}.json"),
               {"qid": q, "case": case, "expected": exp, "desc": "锚",
                "response": {"qid": q, "conclusion": text[:80], "answer": text, "evidence": [],
                             "confidence": "probable"}})
    return rows


def prep():
    log = {}
    for a in ARMS:
        rc, out = sh(PY + ["score_sut.py", "build", f"{a}_main", f"real_{a}"], J1)
        log[a] = out[-600:]
        print(a, out.strip().splitlines()[-2:])
    make_anchors()
    # J2 目录：代码与数据同源（符号链接），只有 semantic/ 独立
    d2 = JD["J2"]
    os.makedirs(d2, exist_ok=True)
    for f in glob.glob(os.path.join(J1, "*.py")):
        shutil.copy(f, d2)
    for name in ["cards", "corpus", "questions", "sut", "anc_main"] + [f"real_{a}" for a in ARMS]:
        dst = os.path.join(d2, name)
        if not os.path.lexists(dst):
            os.symlink(os.path.join(J1, name), dst)
    for j, d in JD.items():
        for a in ARMS:
            sh(PY + ["semantic.py", "prepare", f"real_{a}", "--select", "semantic"], d)
            sh(PY + ["semantic.py", "prepare", "--task", "cite", f"real_{a}"], d)
        rc, out = sh(PY + ["semantic.py", "prepare", "anc_main", "--select", "all"], d)
        print(j, out.strip().splitlines()[:2])
    H.dump(os.path.join(H.WORK, "rule_build_log.json"), log)


def _reqs(d):
    out = []
    for f in glob.glob(os.path.join(d, "semantic", "req", "*", "*.md")):
        root, name = f.split(os.sep)[-2], os.path.basename(f)[:-3]
        out.append((f, os.path.join(d, "semantic", "out", root, name + ".json")))
    for f in glob.glob(os.path.join(d, "semantic", "cite_req", "*", "*.cite.md")):
        root, name = f.split(os.sep)[-2], os.path.basename(f)[:-8]
        out.append((f, os.path.join(d, "semantic", "cite_out", root, name + ".json")))
    return out


def judge():
    jobs = []
    for j, d in JD.items():
        for req, outp in _reqs(d):
            if not os.path.exists(outp):
                jobs.append((j, req, outp))
    # 盲混：五臂 + 锚随机交错；两判官实例各自独立打乱题序（种子不同），再交替合并
    per = {j: [x for x in jobs if x[0] == j] for j in JD}
    for i, j in enumerate(sorted(per)):
        random.Random(SEED + 1000 * (i + 1)).shuffle(per[j])
    jobs = [x for pair in __import__("itertools").zip_longest(*per.values()) for x in pair if x]
    print("待判", len(jobs))

    def one(job):
        j, req, outp = job
        txt = open(req, encoding="utf-8").read()
        txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S).strip()
        r = llm.call([{"role": "user", "content": txt}], model=llm.JUDGES[j], max_tokens=2000,
                     thinking=False, tag=f"judge_main:{j}", **llm.JUDGE_PARAMS[j])
        if r.get("content"):
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            open(outp, "w", encoding="utf-8").write(r["content"])
            return "ok"
        return "err"
    from collections import Counter
    print(Counter(llm.pmap(one, jobs)), "累计 $%.4f" % llm.total_cost())


def final():
    res = {"boards": {}, "audit": None}
    anc_v = {}
    for j, d in JD.items():
        for a in ARMS:
            sh(PY + ["semantic.py", "finalize", f"real_{a}"], d)
            sh(PY + ["semantic.py", "finalize", "--task", "cite", f"real_{a}"], d)
            rc, out = sh(PY + ["score_sut.py", "report", f"{a}_main", f"real_{a}"], d)
            b = json.load(open(os.path.join(d, f"real_{a}", "board.json"), encoding="utf-8"))
            res["boards"].setdefault(a, {})[j] = b
        sh(PY + ["semantic.py", "finalize", "anc_main"], d)
        fin = json.load(open(os.path.join(d, "semantic", "final_anc_main.json"), encoding="utf-8"))
        anc_v[j] = {r["name"]: ("correct" if (r.get("sem") or {}).get("verdict") == "pass" else "incorrect")
                    for r in fin}
        anc_exp = {r["name"]: ("correct" if r["expected"] == "pass" else "incorrect") for r in fin}
    job = {"round": "HMB主轮·语义层（evalsuite_hmb r2）", "stratum": "机械构造锚 48（24正/12跨卡负/12无关负）",
           "anchors": [{"qid": k, "expected": v} for k, v in sorted(anc_exp.items())], "judges": anc_v}
    jp = os.path.join(H.WORK, "audit_main_job.json")
    H.dump(jp, job)
    rc, out = sh(PY + [os.path.join(H.HMB, "judge_audit.py"), "check", jp, "--out",
                       os.path.join(H.WORK, "audit_main_rec.json")], H.HERE)
    res["audit"] = {"rc": rc, "stdout": out[-2000:], "record": H.load(os.path.join(H.WORK, "audit_main_rec.json"))}
    # 真实答卷上的判官一致率（逐题终判 pass/非 pass）
    xs, ys = [], []
    for a in ARMS:
        d1 = {r["qid"]: r["verdict"] for r in res["boards"][a]["J1"]["detail"]}
        d2 = {r["qid"]: r["verdict"] for r in res["boards"][a]["J2"]["detail"]}
        for q in d1:
            if q in d2:
                xs.append(d1[q] == "pass"); ys.append(d2[q] == "pass")
    sys.path.insert(0, H.HMB)
    import judge_audit as JA
    res["real_agreement"] = {"n": len(xs), "identical": sum(x == y for x, y in zip(xs, ys)) / max(1, len(xs)),
                             "kappa": JA.cohen_kappa([str(x) for x in xs], [str(y) for y in ys])}
    H.dump(os.path.join(H.WORK, "judge_main_final.json"), res)
    print(res["audit"]["stdout"])
    print("real agreement", res["real_agreement"])
    for a in ARMS:
        print(a, {j: res["boards"][a][j]["board"] for j in JD})


if __name__ == "__main__":
    {"prep": prep, "judge": judge, "final": final}[sys.argv[1]]()
