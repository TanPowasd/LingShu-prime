# TE 默认管线流程图。字体：环境变量 CJK_FONT_DIR（含 NotoSansSC-Regular/Bold.otf）。python3 agm_te_flow.py
import os
from PIL import Image, ImageDraw, ImageFont
_D=os.environ.get('CJK_FONT_DIR','.'); R=os.path.join(_D,'NotoSansSC-Regular.otf'); B=os.path.join(_D,'NotoSansSC-Bold.otf')
W=1080; f_t=ImageFont.truetype(B,46); f_h=ImageFont.truetype(B,34); f_b=ImageFont.truetype(R,27); f_s=ImageFont.truetype(R,24)
steps=[
 ("输入","对话按轮切块（带角色、会话号）+ 问题",(236,240,247),(70,90,130)),
 ("① Lex 词法打分","BM25+（δ=1）+ 拉丁轻词干\n每块得到 Lex 分 s(i)；s(i)>0 的块是种子\n（中文走 RA-AGM_zh：去功能词二元组、不用 RM3）",(225,239,255),(30,90,180)),
 ("② RA 角色闸门","非种子的助手块：不接收扩散、不中继\n（防止助手长回复挤占前排）",(255,240,222),(190,110,20)),
 ("③ TR-TE 建图","回复/邻接边（原 AGM）\n+ 实体边：两块共享专名（出现 2–30 块），权 .3 均分\n+ 更新边：跨会话 早→晚 再加 .1\n每行出边和 > 1.15 时等比缩放",(228,246,232),(40,140,70)),
 ("④ FD F1 激活扩散","从种子出发幂迭代，激活 a(i) < θ=.01 截断\n行和上限保证收敛",(243,232,250),(120,60,160)),
 ("⑤ 单分数融合","f(i) = s(i) / max s + β·a(i)   （β = 1）\n一个分数、一次排序，不投票、不 RRF",(255,230,232),(180,40,60)),
 ("输出","按 f 排序 → 按轮去重 → 取前 k（r@10 计分）",(236,240,247),(70,90,130)),
]
def wrap_h(t): return len(t.split("\n"))
H=210+sum(120+44*wrap_h(b) for _,b,_,_ in steps)+60*(len(steps)-1)+330
im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
d.text((W//2,70),"灵枢 AGM 默认检索管线（TE）",font=f_t,fill=(20,20,30),anchor="mm")
d.text((W//2,128),"零模型 · 标准库 · 白箱    Lex → RA → FD F1 → TR-TE",font=f_s,fill=(90,90,100),anchor="mm")
y=180
for k,(h,b,bg,fg) in enumerate(steps):
    bh=100+44*wrap_h(b)
    d.rounded_rectangle((70,y,W-70,y+bh),radius=26,fill=bg,outline=fg,width=4)
    d.text((110,y+24),h,font=f_h,fill=fg)
    d.multiline_text((110,y+78),b,font=f_b,fill=(40,40,50),spacing=11)
    y+=bh
    if k<len(steps)-1:
        cx=W//2; d.line((cx,y+6,cx,y+48),fill=(120,120,130),width=6); d.polygon([(cx-16,y+38),(cx+16,y+38),(cx,y+58)],fill=(120,120,130)); y+=66
y+=30
d.rounded_rectangle((70,y,W-70,y+250),radius=22,fill=(248,248,248),outline=(180,180,180),width=2)
d.text((110,y+20),"读数（r@10）",font=f_h,fill=(60,60,70))
d.multiline_text((110,y+74),"LME test .8065 · LoCoMo test .6426 · ConvoMem .7716\nMemBench A .7182 / B .7135 · REALTALK .5153 · hive .5197\n已试未采纳：层级 H2E/HS、补位 BF、代词共指 CP",font=f_b,fill=(60,60,70),spacing=12)
im=im.crop((0,0,W,y+290)); im.save("agm_te_flow.png")
print(im.size)
