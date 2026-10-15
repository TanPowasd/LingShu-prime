# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""给 dsh-memory md_cg/test_qmd.py 的 P14/P15 生成原型金标：用原型 MultiDim/QMD（英文口径，FROZEN）跑守卫夹具三问，
并给出 SYSTEM 与四个提示词模板的 sha256 前 16 位。用法：python -X utf8 port_golden.py --repo <dsh-memory 仓根>"""
import argparse, hashlib, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "bench"), str(HERE.parent / "tricue")]
import multidim as M, qmd as Q, qx, hive_extract, extract, hive_official as HO  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--repo", required=True); a = ap.parse_args()
sys.path.insert(0, a.repo)
from md_cg.test_qmd import fixture  # noqa: E402
texts, sess, tri, qs, hints, ix = fixture()
ids = [f"{s}:0" for s in sess]
g = Q.QMD(texts, ids, tri, hints, w_v3=3.0, w_qx=3.0)
md = M.MultiDim(texts, ids, tri, w_v3=3.0)
got = {k: g.rank(q)[:12] for k, q in qs.items()}
got.update({"md_" + k: md.rank(q)[:12] for k, q in qs.items()})
got["v3_hub"] = g.base.v3_turns(qs["hub"])[:12]
h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
print(json.dumps({"GOLDEN": got, "SYSTEM_SHA": h(HO.SYSTEM),
                  "PROMPT_SHA": {"Q_ZH": h(qx.P_ZH), "Q_EN": h(qx.P_EN), "G_ZH": h(hive_extract.PROMPT), "G_EN": h(extract.PROMPT)}},
                 ensure_ascii=False))
