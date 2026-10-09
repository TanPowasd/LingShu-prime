# -*- coding: utf-8 -*-
"""reflect · 3.12 递归验证反思（recursive_reflect 的 ng 实现）

旧实现的问题类别：
  * #154 自我证实：归档写成 ``[反思链] <claim>`` 记忆节点，下次一级验证以 ``recall(claim)`` 是否为空
    判偏差——归档必被召回，第二次起偏差恒 False，隐藏前提也把自己的归档当前提；
  * #154 可逆性按子串判、无否定处理：「不删除」判不可逆并升级设计者，「清空/drop」反而不触发；
  * #130 判出 needs_designer 后只返回一句指向不存在函数的字符串，升级点（check_escalation）零调用。

不变量：
  R1 证据集 = 召回结果去掉 ``reflection_chain`` 标签节点（自己的归档永不作证据/前提）。
  R2 关键词判定逐个检查「最近的前置否定」（不/没/未/无/别/勿/非/不会/不得/not/no/never/don't），
     被否定的危险词不计；危险词表含中英常见同义写法。
  R3 needs_designer=True ⇒ 调用宿主的 ``check_escalation('结构威胁')``，命中的升级点写进 verdict。
  R4 depth ≥ max_depth ⇒ structural_blindspot（不再递归）。归档进行为日志 + reflection_chain 节点。
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

__all__ = ["reflect", "negated_hit", "IRREVERSIBLE", "REVERSIBLE", "IMPACT"]

IRREVERSIBLE = ("删除", "清空", "终止", "覆盖", "格式化", "不可逆", "销毁", "抹除", "drop", "delete",
                "truncate", "wipe", "rm -rf", "overwrite")
REVERSIBLE = ("查询", "读取", "检测", "观察", "预览", "只读", "read", "query", "inspect", "preview")
IMPACT = (("崩溃", "存在"), ("终止", "存在"), ("泄露", "存在"), ("删除", "结构"), ("清空", "结构"),
          ("破坏", "结构"), ("覆盖", "结构"), ("drop", "结构"), ("delete", "结构"))
_NEG = re.compile(r"(不会|不得|不要|不|没有|没|未|无|别|勿|非|\bnot\b|\bno\b|\bnever\b|n't)\s*$", re.I)
CHAIN_TAG = "reflection_chain"


def negated_hit(text: str, word: str) -> bool:
    """R2：``word`` 在文本中至少有一次**未被紧前否定**的出现。"""
    low, w = text.lower(), word.lower()
    start = 0
    while True:
        i = low.find(w, start)
        if i < 0:
            return False
        if not _NEG.search(low[max(0, i - 6):i]):
            return True
        start = i + len(w)


def _any(text: str, words) -> Optional[str]:
    return next((w for w in words if negated_hit(text, w)), None)


def _evidence(recall: Callable[[str, int], List], claim: str, k: int) -> List:
    """R1：召回结果中排除反思归档节点。"""
    return [(n, s) for n, s in recall(claim, k + 8) if CHAIN_TAG not in (n.tags or [])][:k]


def _verify(recall: Callable, claim: str, expected: Optional[str], actual: Optional[str]) -> Dict:
    if expected and actual:
        dev = str(expected) != str(actual)
        return {"deviation": dev, "detail": f"预期[{expected}] vs 实际[{actual}]", "trigger_reflection": dev,
                "memory_hits": None}
    hits = [{"content": (n.content or "")[:80], "similarity": round(s, 3)} for n, s in _evidence(recall, claim, 3)]
    dev = not hits
    return {"deviation": dev, "trigger_reflection": dev, "memory_hits": hits,
            "detail": "记忆对照：" + ("无相关记忆（信息差信号）" if dev else f"{len(hits)} 条相关记忆")}


def _premises(recall: Callable, claim: str) -> Dict:
    premises, spaces = [], []
    for n, s in _evidence(recall, claim, 5):
        tool = (n.condition_space.observation_tool if n.condition_space else "") or ""
        if tool and tool[:60] not in spaces:
            spaces.append(tool[:60])
        if s > 0.35:
            premises.append({"premise": (n.content or "")[:100], "source": n.id[:24], "similarity": round(s, 3)})
    if not premises:
        premises.append({"premise": "该判断缺少记忆支撑（可能基于未言明的默认假设）", "source": "recall 空"})
    return {"premises": premises[:5], "condition_space_boundary": spaces[:3] or ["未锚定（默认假设域）"],
            "question": "这件事有什么隐藏前提？"}


def _impact(claim: str) -> Dict:
    level = next((lv for w, lv in IMPACT if negated_hit(claim, w)), "协作")
    return {"routes": [{"route": ["（预测引擎未装配或无路线）"], "confidence": 0.0}], "impact_level": level,
            "question": "这件事会有什么影响？"}


def _judge(claim: str, impact: Dict, escalate: Callable[[str], List]) -> Dict:
    if _any(claim, IRREVERSIBLE):
        rev = "不可逆"
    elif _any(claim, REVERSIBLE):
        rev = "可逆"
    else:
        rev = "半可逆（需评估）"
    needs = rev == "不可逆" and impact["impact_level"] in ("结构", "存在")
    points = escalate("结构威胁") if needs else []     # 命中协议升级点 ESC-002（P0保护触发：结构威胁/信任崩溃）
    return {"principle": "可逆性优先 + 结构一致性（3.12 三级）", "reversibility": rev, "needs_designer": needs,
            "escalation": [{"code": p.get("code"), "action": p.get("action")} for p in points],
            "action": ("已触发升级点，等待设计者终裁" if points else "需设计者终裁（无启用的升级点）")
            if needs else "本次反思范围内可处理（可逆/半可逆）"}


def reflect(host: Any, claim: str, expected: Optional[str] = None, actual: Optional[str] = None,
            context: Optional[str] = None, depth: int = 0, max_depth: int = 3) -> Dict:
    """R1–R4。``host`` 需提供 recall(q, limit) / check_escalation(trigger) / ng（MemoryEngine）。"""
    if depth >= max_depth:
        return {"status": "structural_blindspot", "claim": claim,
                "note": f"递归深度已达上限 {max_depth}（3.12 运行约束：超出=结构性盲区）",
                "chain": getattr(host, "_last_reflection_chain", None)}
    recall = host.recall
    report: Dict = {"claim": claim, "depth": depth, "max_depth": max_depth, "protocol": "3.12+1.6.7",
                    "meta_reflection": {"standards": [{"standard": "反射层优先（可逆性/确定性）",
                                                       "condition": "先验证后反思，先反思后终裁；递归 ≤ 3 层"}],
                                        "note": "元反思 = 结构性后退：审视反思过程的前提与边界"}}
    report["verification"] = _verify(recall, claim, expected, actual)
    impact = _impact(claim)
    report["reflection"] = {"hidden_premises": _premises(recall, claim), "impact": impact}
    report["verdict"] = _judge(claim, impact, host.check_escalation)
    report["status"] = "reflected"
    text = (f"[反思链] {claim[:60]} | 偏差={report['verification']['deviation']} | "
            f"可逆性={report['verdict']['reversibility']} | 深度={depth}")
    host.ng.perceive(text, importance=0.6, tags=[CHAIN_TAG], skip_dedup=True)
    host.ng.store.meta.log_action("reflection", f"claim={claim[:80]}",
                                  outcome={"verdict": report["verdict"]["reversibility"]})
    host._last_reflection_chain = text
    return report
