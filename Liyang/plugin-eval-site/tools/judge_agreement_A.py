"""考卷 A 判官一致性细读（不改判）：pass/fail 二值一致在"几乎全 fail"时会尺度塌缩（上游 判分可靠性 §一 批次二的教训），
故另报 采分点级三档一致率、覆盖率分逐题差值。  python -m tools.judge_agreement_A runs/A_bm25 runs/A_dsh"""
import json, sys
from pathlib import Path

def main(argv):
    out = {}
    for d in argv:
        for jp in sorted((Path(d) / "judge").glob("s?.json")):
            j = json.loads(jp.read_text(encoding="utf-8"))
            pts = same = 0; diffs = []; both_pass = one_pass = 0
            for r in j["items"]:
                s = r.get("sem")
                if not s:
                    continue
                f1, f2 = s["fin1"], s["fin2"]
                def lab(f):
                    m = {}
                    for k in ("strict", "paraphrase", "miss"):
                        for p in f.get(k) or []:
                            m[p] = k
                    return m
                a, b = lab(f1), lab(f2)
                for p in set(a) | set(b):
                    pts += 1; same += a.get(p) == b.get(p)
                diffs.append(abs(s["s1"] - s["s2"]))
                both_pass += (s["s1"] >= 0.7 and s["s2"] >= 0.7); one_pass += ((s["s1"] >= 0.7) != (s["s2"] >= 0.7))
            n = len(diffs)
            out[f"{Path(d).name}/{jp.stem}"] = {"sem_items": n, "point_level_identical": round(same / pts, 3) if pts else None, "n_points": pts,
                                                "score_absdiff_mean": round(sum(diffs) / n, 3) if n else None,
                                                "score_absdiff_gt_0.3": sum(x > 0.3 for x in diffs), "both_pass": both_pass, "split_pass": one_pass}
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main(sys.argv[1:])
