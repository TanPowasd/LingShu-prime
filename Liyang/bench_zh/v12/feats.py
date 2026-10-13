# zh-v12 零模型信号 S3（实体/数字对齐）、S5（答案句型，句级）+ φ（修订 7b，作参照）；S4 冗余见 redund.py
import json, os, sys, re, math
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(HERE))
from lingshu_ng import anstype
D = os.path.join(HERE, "runs", "t2r2", "v12"); P = json.load(open(os.path.join(D, "pairs.json")))
STOPC = set("的了吗呢啊吧么是在有和与或及什怎如何哪谁为几多少个一这那些请问一下")
def nz(s): return re.sub(r"\s+", "", s)
def bg(s): s = nz(s); return [s[i:i + 2] for i in range(len(s) - 1)]
NUM = re.compile(r"\d+(?:\.\d+)?|[一二三四五六七八九十百千万两]+(?=[年月日天个岁次元块倍号])")
ENT = re.compile(r"[《“\"「](.+?)[》”\"」]|[A-Za-z][A-Za-z0-9\-\.\+]+")
INT = [("how", r"怎么|如何|怎样|方法|步骤|教程|攻略|技巧|办法", r"(^|[。\n；;])\s*(\d[\.、)]|[一二三四五六七八九]、|第[一二三四五]步|首先|然后|接着|最后|步骤|点击|打开|进入|选择|输入|设置)"),
       ("num", r"多少|几[个年天岁米斤度次种号点月]|多大|多高|多长|多重|多久|多远|比例|率|价格|多钱|费用", r"\d"),
       ("what", r"是什么|什么意思|指什么|含义|定义|什么是|是啥|啥意思", r"是指|指的是|是一种|是一个|即|也就是|意思是|又称|简称|是.{1,12}的(总称|统称)"),
       ("why", r"为什么|为何|原因|怎么回事|咋回事", r"因为|由于|原因|导致|所以|引起|造成|是因"),
       ("when", r"什么时候|何时|几月|哪一?年|哪天|日期|多久", r"\d{2,4}年|\d{1,2}月|\d{1,2}日|[春夏秋冬]季|周[一二三四五六日]|星期|早上|晚上|小时|分钟|天"),
       ("where", r"哪里|在哪|哪儿|什么地方|地址|位置", r"[省市区县路街镇村]|位于|地址|坐落"),
       ("yn", r"吗$|吗[?？]|能不能|可不可以|是否|会不会|有没有|好不好|能否|可以吗", r"可以|不能|不可以|能够|不会|会的|是的|不是|没有|不行|建议|不建议|最好"),
       ("who", r"谁|哪位|什么人", r"[\u4e00-\u9fa5]{2,3}(先生|女士|教授|导演|作者|主演)|由.{1,10}(创作|演唱|导演|主演|发明|提出)")]
INT = [(k, re.compile(a), re.compile(b)) for k, a, b in INT]
def sents(p): return [s for s in re.split(r"(?<=[。！？!?；;\n])", p) if nz(s)]
def feats(q, p, idf):
    qb = [b for b in dict.fromkeys(bg(q)) if not (b[0] in STOPC and b[1] in STOPC)]; W = sum(idf.get(b, 1) for b in qb) or 1
    pz = nz(p); cov = sum(idf.get(b, 1) for b in qb if b in pz) / W
    qn = set(NUM.findall(q)); pn = set(NUM.findall(p)); numal = len(qn & pn) / len(qn) if qn else -1
    qe = {(a or b).lower() for a, b in ((m.group(1), m.group(0)) for m in ENT.finditer(q))}; ental = sum(e in p.lower() for e in qe) / len(qe) if qe else -1
    # 最短覆盖窗：段内含问句 IDF 权重 ≥ 60% 二元组的最短跨度（字）
    pos = sorted((i, b) for b in qb for i in [m.start() for m in re.finditer(re.escape(b), pz)])
    best = len(pz) + 1; tgt = .6 * W
    for a in range(len(pos)):
        got = {}; 
        for c in range(a, len(pos)):
            got[pos[c][1]] = 1
            if sum(idf.get(b, 1) for b in got) >= tgt: best = min(best, pos[c][0] - pos[a][0] + 2); break
    win = math.log1p(best) if best <= len(pz) else math.log1p(len(pz)) + 1
    ints = [k for k, a, _ in INT if a.search(q)]
    ss = sents(p); sc = []
    for s in ss:
        sz = nz(s); c = sum(idf.get(b, 1) for b in qb if b in sz) / W
        pat = any(b.search(s) for k, a, b in INT if k in ints) if ints else False
        sc.append((c, pat))
    best_s = max(sc, key=lambda x: x[0]) if sc else (0, False)
    ans_any = max([c for c, pt in sc if pt], default=0.0)          # 含答语形的句子中最高覆盖
    nxt = 0.0                                                       # 覆盖最高句的后一句是否答语形（答案常在问句复述之后）
    if sc:
        j = max(range(len(sc)), key=lambda k: sc[k][0])
        nxt = 1.0 if j + 1 < len(sc) and sc[j + 1][1] else 0.0
    phi = anstype.score(q, [p])[0]
    return {"cov": cov, "win": -win, "numal": numal, "ental": ental, "s_best": best_s[0], "s_bestpat": float(best_s[1]),
            "ans_any": ans_any, "ans_next": nxt, "ans_pat": float(any(pt for _, pt in sc)), "len": -math.log1p(len(pz)), "phi": phi}
out = {}
for q, v in P.items():
    df = {}
    for x in v["items"]:
        for b in set(bg(x["t"])): df[b] = df.get(b, 0) + 1
    N = len(v["items"]); idf = {b: math.log((N + 1) / (c + .5)) for b, c in df.items()}
    out[q] = {str(x["i"]): feats(v["q"], x["t"], idf) for x in v["items"] if x["lab"] in "EM"}
json.dump(out, open(os.path.join(D, "feat_z.json"), "w")); print("DONE", len(out))
