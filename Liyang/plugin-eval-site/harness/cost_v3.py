"""v3 成本口径（方案 v3.0 §10 / 手册 v1.1 §5）。纯标准库。

- 每干成一件花多少（总单位成功成本）= 全部成本 ÷ 成功任务数
- 多干成一件多花多少（增量单位成功成本）=（插件总成本 − 基线总成本）÷ 插件多带来的成功数
分母规矩：成功数=0 → "不适用：没有成功任务"（仍展示实际总花费）；增量成功数 ≤0 → "不适用：没有多干成任务"
（分别报告成本差和成功数差，不给负比值）。测不到写"没测到"，有依据的估算写"估算值 + 误差来源"，绝不填 0。

API（稳定 v1）
    CostItem(name, value=None, status="measured"|"estimated"|"unmeasured", unit="USD", error_source=None, included=True, note=None)
    total_cost(items) -> dict           {value|None, display, status, components:[...], unmeasured:[...]}
    unit_success_cost(items_or_total, successes) -> dict
    incremental_success_cost(plug_items, base_items, plug_successes, base_successes) -> dict
    cost_sheet(arm_plug, arm_base) -> dict   两臂一张单子（含失败任务成本、机器等待/人工分列、缓存冷热）
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

NA_NO_SUCCESS = "不适用：没有成功任务"
NA_NO_GAIN = "不适用：没有多干成任务"
NOT_MEASURED = "没测到"
STATUSES = ("measured", "estimated", "unmeasured")


class CostError(ValueError):
    pass


@dataclass
class CostItem:
    name: str
    value: float | None = None
    status: str = "measured"
    unit: str = "USD"
    error_source: str | None = None
    included: bool = True          # 是否计入总成本（订阅费/固定部署费/人工费须逐项说明）
    note: str | None = None

    def __post_init__(self):
        if self.status not in STATUSES:
            raise CostError(f"{self.name}: status 须为 {STATUSES}")
        if self.status == "unmeasured":
            if self.value is not None:
                raise CostError(f"{self.name}: 没测到的项不得给数值（禁止填 0）")
        else:
            if self.value is None or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
                raise CostError(f"{self.name}: {self.status} 项须有有限数值")
            if self.value < 0:
                raise CostError(f"{self.name}: 成本不得为负")
            if self.status == "estimated" and not self.error_source:
                raise CostError(f"{self.name}: 估算值须写误差来源")

    def display(self) -> str:
        if self.status == "unmeasured":
            return NOT_MEASURED
        s = f"{self.value:g} {self.unit}"
        return s + (f"（估算；误差来源：{self.error_source}）" if self.status == "estimated" else "")


def _items(x) -> list[CostItem]:
    out = []
    for it in x:
        out.append(it if isinstance(it, CostItem) else CostItem(**it))
    units = {i.unit for i in out if i.included}
    if len(units) > 1:
        raise CostError(f"计入项单位不一致：{units}")
    return out


def total_cost(items) -> dict:
    items = _items(items)
    inc = [i for i in items if i.included]
    unmeasured = [i.name for i in inc if i.status == "unmeasured"]
    est = [i.name for i in inc if i.status == "estimated"]
    comp = [{**asdict(i), "display": i.display()} for i in items]
    if not inc:
        return {"value": None, "display": NOT_MEASURED, "status": "unmeasured", "components": comp, "unmeasured": []}
    if unmeasured:
        # 有计入项没测到：总额不能当完整值，只给"已测部分"并明写缺口
        part = sum(i.value for i in inc if i.status != "unmeasured")
        return {"value": None, "partial_value": part, "status": "incomplete",
                "display": f"{NOT_MEASURED}（已测部分 {part:g}；缺：{'、'.join(unmeasured)}）",
                "components": comp, "unmeasured": unmeasured, "estimated": est}
    v = sum(i.value for i in inc)
    st = "estimated" if est else "measured"
    unit = inc[0].unit
    disp = f"{v:g} {unit}" + (f"（含估算项：{'、'.join(est)}）" if est else "")
    return {"value": v, "status": st, "display": disp, "components": comp, "unmeasured": [], "estimated": est, "unit": unit}


def _check_count(n, name):
    if isinstance(n, bool) or not isinstance(n, int):
        raise CostError(f"{name} 须为整数：{n!r}")
    if n < 0:
        raise CostError(f"{name} 不得为负：{n}")


def unit_success_cost(items_or_total, successes: int) -> dict:
    _check_count(successes, "成功数")
    tot = items_or_total if isinstance(items_or_total, dict) and "status" in items_or_total else total_cost(items_or_total)
    out = {"total": tot["display"], "successes": successes}
    if successes == 0:
        out.update(value=None, display=f"{NA_NO_SUCCESS}（实际总花费 {tot['display']}）")
    elif tot["value"] is None:
        out.update(value=None, display=f"{NOT_MEASURED}（总成本不完整：{tot['display']}）")
    else:
        v = tot["value"] / successes
        out.update(value=v, display=f"{v:g} {tot.get('unit','')}/件".strip() + ("（估算）" if tot["status"] == "estimated" else ""))
    return out


def incremental_success_cost(plug_items, base_items, plug_successes: int, base_successes: int) -> dict:
    _check_count(plug_successes, "插件成功数"); _check_count(base_successes, "基线成功数")
    tp = plug_items if isinstance(plug_items, dict) and "status" in plug_items else total_cost(plug_items)
    tb = base_items if isinstance(base_items, dict) and "status" in base_items else total_cost(base_items)
    gain = plug_successes - base_successes
    dcost = None if (tp["value"] is None or tb["value"] is None) else tp["value"] - tb["value"]
    out = {"success_diff": gain, "cost_diff": dcost,
           "cost_diff_display": NOT_MEASURED if dcost is None else f"{dcost:+g}",
           "plug_total": tp["display"], "base_total": tb["display"]}
    if gain <= 0:
        out.update(value=None, display=f"{NA_NO_GAIN}（成本差 {out['cost_diff_display']}；成功数差 {gain:+d}）")
    elif dcost is None:
        out.update(value=None, display=f"{NOT_MEASURED}（成本差无法计算；成功数差 {gain:+d}）")
    else:
        v = dcost / gain
        out.update(value=v, display=f"{v:g}/多干成一件")
    return out


def cost_sheet(arm_plug: dict, arm_base: dict) -> dict:
    """arm = {items:[CostItem|dict], successes:int, failed_cost_included:bool, cache:"冷"|"热"|None,
              machine_wait_s: float|None, human_ops_s: float|None}"""
    def side(a):
        if a.get("failed_cost_included") is not True:
            raise CostError("失败任务成本必须计入（failed_cost_included=True）")
        t = total_cost(a["items"])
        return {"total": t, "unit": unit_success_cost(t, a["successes"]),
                "cache": a.get("cache") or "未标注",
                "machine_wait": NOT_MEASURED if a.get("machine_wait_s") is None else f"{a['machine_wait_s']:g} s",
                "human_ops": NOT_MEASURED if a.get("human_ops_s") is None else f"{a['human_ops_s']:g} s"}
    sp, sb = side(arm_plug), side(arm_base)
    inc = incremental_success_cost(sp["total"], sb["total"], arm_plug["successes"], arm_base["successes"])
    return {"plug": sp, "base": sb, "incremental": inc}
