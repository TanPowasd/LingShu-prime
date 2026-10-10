"""考卷 A 检索面机械读数（不进结论）：插件交来的材料里，含多少条答案键「认可依据」（evidence_pool / supporting_evidence）原文。
  python -m tools.retrieval_face_A runs/A_bm25 runs/A_dsh
判据：认可依据引文（去空白标点归一化，上游 judge.norm）是材料某条片段（同章）的子串 ⇒ 命中。"""
import json, sys
from pathlib import Path
from harness import examA as A

def main(argv):
    J, _ = A.upstream(); C = A.cards()
    out = {}
    for d in argv:
        hit_q = tot_ev = hit_ev = 0
        for qid, card in C.items():
            r = json.loads((Path(d) / "q" / f"{qid}.recall.json").read_text(encoding="utf-8"))
            pool = card.get("supporting_evidence") or card.get("evidence_pool") or []
            mats = [(m["file"], J.norm(m["text"])) for m in r["material"]]
            h = 0
            for e in pool:
                q = J.norm(e.get("quote") or "")
                if q and any(f == e.get("cid") and q in t for f, t in mats):
                    h += 1
            tot_ev += len(pool); hit_ev += h; hit_q += h > 0
        out[Path(d).name] = {"questions_with_any_key_quote": hit_q, "n_questions": len(C), "key_quotes_hit": hit_ev, "key_quotes_total": tot_ev}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out

if __name__ == "__main__":
    main(sys.argv[1:])
