# 校验：本台用 conf_arms 取到的三臂排序，按队友 HR.evaluate/take 在 hive 全 92 卡上复算，与其发布的 results/*.json 逐项对照。
import json
import zh_eval as Z
from conf_arms import CONF
HR = Z.HR; d = Z.data(); ch = d["tc"]; cards = d["tcards"]
pub_md = json.load(open(CONF / "results" / "hive_md_zerokey.json", encoding="utf-8"))
pub_ls = json.load(open(CONF / "results" / "hive_lingshu_zerokey.json", encoding="utf-8"))
R = {a: json.load(open(f"runs/conf/{a}_hive_tcards.json"))["rank"] for a in ("md_heur", "md_llm", "tricue")}
res = {"md_heur vs hive_md_zerokey[多维v3×3]": [], "tricue vs hive_md_zerokey[v3]": [], "md_llm vs hive_lingshu[汇流多维 v3×3(LLM)]": [],
       "tricue vs hive_lingshu[TriCue v3]": []}
for B in HR.BUDGETS:
    ev = {a: HR.evaluate(cards, lambda c, o=o: HR.take(o[c["qid"]], ch, B)) for a, o in R.items()}
    res["md_heur vs hive_md_zerokey[多维v3×3]"].append(ev["md_heur"] == pub_md[f"预算{B}"]["多维v3×3"])
    res["tricue vs hive_md_zerokey[v3]"].append(ev["tricue"] == pub_md[f"预算{B}"]["v3"])
    res["md_llm vs hive_lingshu[汇流多维 v3×3(LLM)]"].append(ev["md_llm"] == pub_ls[str(B)]["汇流多维 v3×3(LLM)"])
    res["tricue vs hive_lingshu[TriCue v3]"].append(ev["tricue"] == pub_ls[str(B)]["TriCue v3"])
    if B == 8000:
        for a in ev:
            print(a, {k: v for k, v in ev[a].items() if k != "_n"})
print(json.dumps(res, ensure_ascii=False))
json.dump(res, open("runs/conf/check.json", "w"), ensure_ascii=False, indent=1)
