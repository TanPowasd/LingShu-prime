import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
for f in ["NotoSansSC-Regular.otf","NotoSansSC-Bold.otf"]: fm.fontManager.addfont(__import__("os").environ.get("CJK_FONT_DIR", ".")+"/"+f)
plt.rcParams["font.family"]="Noto Sans SC"
W,H=12,15.5
fig=plt.figure(figsize=(W,H),dpi=150); ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(0,H); ax.axis("off")
C={"w":"#E8F1FB","q":"#FDF0E3","a":"#EAF6EC","o":"#F3EEF9","e":"#2B3A55"}
def box(x,y,w,h,title,body,col,tc="#1f2937"):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.02,rounding_size=0.15",fc=col,ec="#9aa5b8",lw=1.2))
    ax.text(x+w/2,y+h-0.28,title,ha="center",va="top",fontsize=13,weight="bold",color=tc)
    ax.text(x+w/2,y+h-0.72,body,ha="center",va="top",fontsize=10.2,color="#374151",linespacing=1.45)
def arr(x1,y1,x2,y2,lab=None):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle="-|>",mutation_scale=16,lw=1.6,color="#5b6478",connectionstyle="arc3"))
    if lab: ax.text((x1+x2)/2+0.12,(y1+y2)/2,lab,fontsize=9.5,color="#5b6478",va="center")
ax.text(W/2,H-0.45,"Lex 检索原理图（BM25+ × SDM + 词形归一 + RM3 → AGM）",ha="center",va="top",fontsize=17,weight="bold",color=C["e"])
ax.text(W/2,H-1.0,"零模型 · 零外部数据 · 纯标准库    LingShu-prime 提交 535d9b3",ha="center",va="top",fontsize=10.5,color="#6b7280")
ax.text(3.0,H-1.55,"写入（记忆入库）",ha="center",fontsize=13,weight="bold",color="#2563eb")
ax.text(9.0,H-1.55,"查询（问句检索）",ha="center",fontsize=13,weight="bold",color="#c2410c")
# write column
box(0.5,11.6,5,1.55,"① 对话轮","每轮按行累积，规范化长度满 300 字切成块\n块号 = 写入顺序",C["w"])
box(0.5,9.3,5,1.85,"② 分词","英文：小写词 + 轻量词形归一\n(visited/visiting → visit，复数 -s/-ies)\n中文：字二元组（西湖 / 湖边…），不做归一",C["w"])
box(0.5,6.75,5,2.1,"③ 两套索引","倒排：词 → 块、相邻词对 → 块、词位置\n邻接图（AGM 用）：\n块内 前→后 .5 / 后→前 .25\n上一轮末块 → 本轮首块 .4（问→答）",C["w"])
arr(3,11.6,3,11.15); arr(3,9.3,3,8.85)
# query column
box(6.5,11.6,5,1.55,"④ 问句","与写入同一分词器\n（词形归一 / 中文二元组）",C["q"])
box(6.5,9.0,5,2.15,"⑤ BM25+ × SDM 打分","单词 .85 + 有序相邻对 .10 + 无序窗口对 .05(窗 8)\nBM25+：k1=1.2，b=.75，δ=1（命中即有下界分）\nidf = log((N+1)/df)",C["q"])
box(6.5,6.25,5,2.3,"⑥ RM3 伪相关反馈","取首轮前 10 块，按分数加权的词频\n挑 10 个扩展词（× idf 排序，排除问句词）\n扩展词再走 BM25+ 打分\n块分 = .5·原分/max + .5·扩展分/max",C["q"])
arr(9,11.6,9,11.15); arr(9,9.0,9,8.55)
arr(5.5,8.4,6.5,9.5,None); ax.text(5.6,9.15,"倒排",fontsize=9.5,color="#5b6478")
# AGM
box(1.5,3.0,9,2.65,"⑦ AGM 扩散重排（关联图记忆）","种子：块分前 8 名，激活 = 分/最高分\n沿邻接图扩散 2 步：每步 激活 += 邻居激活 × 边权；非种子衰减 .35\n低于 .05 的丢弃，每步只留前 80 个（k-WTA）\n输出：被激活的块按激活度排在最前，其余块按原分数接在后面",C["a"])
arr(9,6.25,7.2,5.65,"块分数"); arr(3,6.75,4.8,5.65,"邻接图")
box(2.5,0.75,7,1.65,"⑧ 输出","按轮去重（同一轮只留最靠前的块）→ 前 k 轮\n交给阅读器 / 评测 r@10",C["o"])
arr(6,3.0,6,2.4)
ax.text(W/2,0.35,"test r@10：LongMemEval .789（v3 .757）· LoCoMo .632（v3 .618）· 中文 hive@8000 .438（v3 .496，RM3 对中文方向为负，存疑）",ha="center",fontsize=9.8,color="#374151")
fig.savefig(__import__("pathlib").Path(__file__).with_suffix(".png")); print("ok")
