# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""拓展 AGM（Lex+RA，角色感知扩散）原理图。CJK_FONT_DIR=字体目录 python agm_ra_schematic.py"""
import os, pathlib
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
for f in ["NotoSansSC-Regular.otf", "NotoSansSC-Bold.otf"]:
    fm.fontManager.addfont(os.environ.get("CJK_FONT_DIR", ".") + "/" + f)
plt.rcParams["font.family"] = "Noto Sans SC"
W, H = 12, 17
fig = plt.figure(figsize=(W, H), dpi=150); ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
G, GR, U, A, X = "#EAF6EC", "#F3F4F6", "#DBEAFE", "#FDE2E2", "#2B3A55"


def box(x, y, w, h, title, body, col, fs=10.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=col, ec="#9aa5b8", lw=1.2))
    ax.text(x + w / 2, y + h - 0.25, title, ha="center", va="top", fontsize=12.5, weight="bold", color="#1f2937")
    ax.text(x + w / 2, y + h - 0.68, body, ha="center", va="top", fontsize=fs, color="#374151", linespacing=1.5)


def arr(x1, y1, x2, y2, lab=None, col="#5b6478", ls="-", rad=0.0, lw=1.6):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=15, lw=lw, color=col, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}"))
    if lab:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.17, lab, fontsize=9, color=col, ha="center")


ax.text(W / 2, H - 0.4, "拓展 AGM 原理图：角色感知扩散（Lex + RA）", ha="center", va="top", fontsize=18, weight="bold", color=X)
ax.text(W / 2, H - 0.95, "零模型 · 白箱 · 只改扩散的一条规则    LingShu-prime 37b3cc8 · PREREG_role.md", ha="center", va="top", fontsize=10.5, color="#6b7280")

# 流程
box(0.5, 13.6, 3.4, 1.9, "① Lex 打分", "BM25+ × SDM\n词形归一 + RM3\n得到每块分数 s", GR)
box(4.3, 13.6, 3.4, 1.9, "② 选种子", "s 的前 8 名\n激活 x = s / max(s)\n种子保留原角色", GR)
box(8.1, 13.6, 3.4, 1.9, "③ 关联图", "块内 前→后 .5 / 后→前 .25\n上一轮末块→本轮首块 .4\n每块带角色 user / assistant", GR)
arr(3.9, 14.55, 4.3, 14.55); arr(7.7, 14.55, 8.1, 14.55)
box(0.5, 10.75, 11, 2.35, "④ 扩散 2 步（新增：角色闸门）",
    "每一步：激活 a(j) += a(i) × 边权 w(i→j)；非种子乘 (1 − .35)；低于 .05 丢弃；只留前 80（k-WTA）\n"
    "角色闸门：j 是「非种子的助手块」→ 这条边直接作废\n"
    "        不进激活段（不插队）· 也不当中继（激活不经它再往外传）\n"
    "种子助手块（被 Lex 直接命中的助手回复）不受影响，照常排在前面\n"
    "没有角色的记忆（两人对话、中文 hive）闸门永远不触发，与原 AGM 逐位相同", G, fs=10.6)
arr(6, 13.6, 6, 13.1)
box(0.5, 9.05, 11, 1.2, "⑤ 输出",
    "激活段（按激活度）排最前，其余块按 Lex 分接在后面 → 按轮去重 → 前 10 轮", "#F3EEF9")
arr(6, 10.75, 6, 10.25)

# 示意图
ax.text(W / 2, 8.35, "示意：问「我那只比格犬叫什么？」（一段用户—助手对话的邻接链）", ha="center", fontsize=12.5, weight="bold", color=X)
rows = [(6.6, "原 AGM", False), (4.0, "拓展 AGM（RA，R2）", True)]
names = [("U1a", "我领养了一只\n比格犬", U), ("U1b", "名字叫 Max，\n去年春天", U), ("A1", "恭喜！比格犬\n活泼友好", A), ("U2", "我还报了\n陶艺课", U)]
xs = [1.6, 4.4, 7.2, 10.0]
for y, title, blocked in rows:
    ax.text(0.5, y + 1.15, title, fontsize=11.5, weight="bold", color="#374151")
    for k, ((n, t, c), x) in enumerate(zip(names, xs)):
        rc = "#2563eb" if n.startswith("U") else "#dc2626"
        seed = k == 0
        ax.add_patch(Circle((x, y), 0.68, fc=c, ec=rc, lw=2.4 if seed else 1.2))
        ax.text(x, y + 0.2, n, ha="center", fontsize=10, weight="bold", color=rc)
        ax.text(x, y - 0.22, t, ha="center", va="center", fontsize=7.6, color="#374151", linespacing=1.2)
        if seed:
            ax.text(x, y + 0.85, "种子", ha="center", fontsize=9, weight="bold", color="#2563eb")
    labs = ["同轮 .5", "跨轮 问→答 .4", "跨轮 .4"]
    for k in range(3):
        x1, x2 = xs[k] + 0.7, xs[k + 1] - 0.7
        if not blocked:
            arr(x1, y, x2, y, labs[k], "#16a34a")
        elif k == 0:
            arr(x1, y, x2, y, labs[k], "#16a34a")
        elif k == 1:
            arr(x1, y, x2, y, labs[k], "#dc2626", "--")
            ax.text((x1 + x2) / 2, y - 0.03, "×", ha="center", va="center", fontsize=20, color="#dc2626", weight="bold")
        else:
            arr(x1, y, x2, y, "无中继", "#9ca3af", ":")
    sub = ("激活段 = U1a, U1b, A1, U2 …：助手套话和不相关的下一轮一起插队" if not blocked else
           "激活段 = U1a, U1b：同轮上下文照常扩散；A1 不插队，也不把激活传给 U2")
    ax.text(W / 2, y - 0.95, sub, ha="center", va="top", fontsize=10, color="#b91c1c" if not blocked else "#15803d")
ax.text(W / 2, 2.0, "两人对话里每轮都是「信息源」，闸门不触发，原 AGM 把邻轮尾部送进前 10 的作用完整保留",
        ha="center", va="top", fontsize=9.8, color="#6b7280")

# 读数
ax.add_patch(FancyBboxPatch((0.5, 0.25), 11, 1.15, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#FFFBEB", ec="#f59e0b", lw=1.2))
ax.text(W / 2, 1.18, "病因：LME 上原 AGM 把前 10 轮里助手轮占比从 36% 推到 45%（diag，LME dev 前 30 题）",
        ha="center", va="top", fontsize=10.2, color="#374151")
ax.text(W / 2, 0.72, "test r@10：LongMemEval .789 → .810（16 胜 2 负，p=.0013）· LoCoMo .632 不变 · 中文 hive .438 不变",
        ha="center", va="top", fontsize=10.2, weight="bold", color="#92400e")
fig.savefig(pathlib.Path(__file__).with_suffix(".png")); print("ok")
