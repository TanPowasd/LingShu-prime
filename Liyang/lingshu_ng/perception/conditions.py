# -*- coding: utf-8 -*-
"""conditions · 图像条件归一化 / cond_hash（重写旧 lingshu.core.condition_normalize）

旧实现的问题类别：
  * 「未声明」有三种写法（缺键 / ``None`` / ``__UNASSERTED__``），下游各自解释——verdict 曾把
    UNASSERTED 当「有遮挡」（core-rest-05），同一张图规范化前后结论不同；
  * 取值不做类型检查：列表/字典取值在同义词表查找时抛 ``TypeError``，数值被 ``str`` 隐式比较；
  * ``part_cond_hash`` 用 ``%d`` 格式化：``1.9`` 被静默截成 1、``True`` 当 1，不同部件撞 hash。

不变量：
  C1 :func:`value_of` 是「读一个域值」的唯一入口：缺键、``None``、空串、非字符串、非法枚举值
     一律归一为 :data:`UNASSERTED`（P2-001：未声明无可校验）。verdict 与校验边都只经它读值。
  C2 :func:`canonical_condition` 只含 :data:`IMAGE_DOMAINS` 的键、键有序、值 ∈ 枚举 ∪ {UNASSERTED}；
     幂等（canonical(canonical(d)) == canonical(d)）；cond_hash 只依赖 canonical 结果。
  C3 ``part_idx`` 必须是非负 int（拒 bool/float），``part_type``/``image_hash`` 必须是非空 str。
纯函数、确定性、零依赖；输出与旧实现在合法输入上逐值相同（同 hash 前缀算法）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional

__all__ = ["IMAGE_DOMAINS", "UNASSERTED", "DOMAIN_SOURCE", "ASSERTED_BY_DEFAULT", "SYNONYMS",
           "value_of", "is_asserted", "canonical_condition", "canonical_sourced", "validate_edges",
           "cond_hash", "part_cond_hash", "img0_domains", "invalid_values", "INVALID_KEY"]

#: cond_hash 载荷里登记「声明了但不合法」的域（#138：非法值不得与未声明同桶）
INVALID_KEY = "__INVALID__"

IMAGE_DOMAINS: Dict[str, list] = {
    "subject": ["人物", "景色", "物品", "动物"],
    "count": ["单体", "双体", "群像"],
    "subject_priority": ["主体", "配角", "环境"],
    "composition": ["居中", "三分", "偏移", "留白", "对称构图"],
    "era_theme": ["现代", "古风", "未来", "赛博", "奇幻", "日常"],
    "pose": ["静止", "站姿", "坐姿", "躺姿", "行走", "奔跑", "回眸"],
    "view_distance": ["特写", "半身", "全身", "远景"],
    "view_dir": ["正视图", "侧视", "俯视", "仰视", "背影"],
    "frame": ["竖幅", "横幅", "方形", "全景", "宽幅"],
    "background": ["白", "黑", "简单纯色", "透明", "景色"],
    "dof": ["浅景深", "深景深", "前景模糊"],
    "style": ["动漫", "写实", "水彩", "扁平", "3D"],
    "line_edge": ["粗线稿", "淡线稿", "无线稿", "硬边", "描边", "软边"],
    "color": ["黑白", "柔和", "丰富", "多彩", "霓虹"],
    "lighting": ["暗", "柔和", "明亮", "逆光", "霓虹光"],
    "contrast": ["模糊", "清晰", "高对比", "低对比"],
    "material": ["光滑", "粗糙", "金属", "玻璃", "布料", "蕾丝"],
    "detail": ["高清", "低清", "噪点", "精细", "极简"],
    "abstraction": ["符号化", "简化", "拟真", "写实化"],
    "occlusion": ["无遮挡", "部分遮挡", "全遮挡"],
    "symmetry": ["对称", "部分对称", "不对称", "镜像"],
    "clothing": ["无", "泳装", "常服", "铠甲", "制服"],
    "input_modality": ["彩色立绘", "线稿", "mask", "PSD分层"],
}
UNASSERTED = "__UNASSERTED__"

#: evaluated = 求值器可从像素判定（强验证）；asserted = 声明来源（弱验证，可被求值域反驳）
DOMAIN_SOURCE: Dict[str, str] = {
    "subject": "asserted", "count": "evaluated", "subject_priority": "evaluated",
    "composition": "evaluated", "era_theme": "asserted", "pose": "evaluated",
    "view_distance": "evaluated", "view_dir": "evaluated", "frame": "evaluated",
    "background": "evaluated", "dof": "evaluated", "style": "asserted",
    "line_edge": "evaluated", "color": "asserted", "lighting": "asserted",
    "contrast": "evaluated", "material": "asserted", "detail": "evaluated",
    "abstraction": "asserted", "occlusion": "evaluated", "symmetry": "evaluated",
    "clothing": "asserted", "input_modality": "asserted",
}
ASSERTED_BY_DEFAULT: Dict[str, str] = {
    "style": "人工标注", "era_theme": "人工标注", "material": "人工标注",
    "lighting": "人工标注", "clothing": "人工标注", "color": "枚举档声明",
    "subject": "人工标注", "input_modality": "输入声明", "abstraction": "人工标注",
}
SYNONYMS: Dict[str, str] = {
    "可爱动漫": "动漫", "日系动漫": "动漫", "二次元": "动漫", "少女漫画": "动漫",
    "全身立绘": "全身", "立绘": "全身", "正面": "正视图", "正立": "正视图",
    "纯白": "白", "白底": "白", "浅色底": "白", "平涂": "扁平",
}


def _mapping(domains: Any) -> Mapping:
    if domains is None:
        return {}
    if not isinstance(domains, Mapping):
        raise TypeError(f"domains 必须是映射，得到 {type(domains).__name__}")
    return domains


def value_of(domains: Any, key: str) -> str:
    """C1：读一个域的规范值（同义词归一；任何「未声明/非法」⇒ UNASSERTED）。"""
    v = _mapping(domains).get(key)
    if not isinstance(v, str) or not v.strip():
        return UNASSERTED
    v = SYNONYMS.get(v.strip(), v.strip())
    allowed = IMAGE_DOMAINS.get(key)
    if allowed is not None and v not in allowed:
        return UNASSERTED
    return v


def invalid_values(domains: Any) -> Dict[str, str]:
    """声明了却不合法的域 → 原值（规范化前 strip 后的文本 / 非字符串取 repr）。

    缺键、None、空白串、显式 UNASSERTED 是「未声明」，不算非法。判据层（value_of）仍把非法值
    视作未声明（不参与校验），但条件身份（cond_hash）与来源表（canonical_sourced）必须把它区分出来。
    """
    d = _mapping(domains)
    out: Dict[str, str] = {}
    for k in sorted(IMAGE_DOMAINS):
        raw = d.get(k)
        if raw is None or raw == UNASSERTED or (isinstance(raw, str) and not raw.strip()):
            continue
        if value_of(d, k) == UNASSERTED:
            out[k] = raw.strip() if isinstance(raw, str) else repr(raw)
    return out


def is_asserted(domains: Any, key: str) -> bool:
    """该域是否有合法声明值。"""
    return value_of(domains, key) != UNASSERTED


def canonical_condition(domains: Any) -> Dict[str, str]:
    """C2：域取值 → 同义词归一 → canonical dict（仅合法枚举值，未知→UNASSERTED，键排序）。"""
    d = _mapping(domains)
    return {k: value_of(d, k) for k in sorted(IMAGE_DOMAINS)}


def canonical_sourced(domains: Any, asserted_by: Optional[Mapping[str, str]] = None) -> Dict:
    """canonical + source/asserted_by/validate 三字段（不参与 cond_hash）。"""
    canon = canonical_condition(domains)
    bad = invalid_values(domains)
    by = dict(ASSERTED_BY_DEFAULT)
    by.update(_mapping(asserted_by))
    out = {}
    for k in sorted(IMAGE_DOMAINS):
        src = DOMAIN_SOURCE[k]
        out[k] = {"value": canon[k], "source": src,
                  "asserted_by": by.get(k) if src == "asserted" else None,
                  "validate": "强验证" if src == "evaluated" else "弱验证"}
        if k in bad:
            out[k]["invalid"] = bad[k]
    return out


def validate_edges(domains: Any) -> Dict:
    """校验边：E1 声明=线稿 但 色彩求值=色块档；E2 运动姿态 × 对称求值。UNASSERTED 不参与。"""
    c = canonical_condition(domains)
    violations = []
    if c["input_modality"] == "线稿" and c["color"] in ("柔和", "丰富", "多彩", "霓虹"):
        violations.append({"edge": "E1", "note": "声明=线稿 但 求值色彩=色块档",
                           "domains": {"input_modality": c["input_modality"], "color": c["color"]}})
    if c["pose"] in ("行走", "奔跑", "回眸") and c["symmetry"] == "对称":
        violations.append({"edge": "E2", "note": "运动姿态与对称求值矛盾",
                           "domains": {"pose": c["pose"], "symmetry": c["symmetry"]}})
    return {"state": "DEFER_REVIEW" if violations else "consistent", "violations": violations}


def cond_hash(domains: Any, salt: str = "") -> str:
    """canonical condition set → sha256 前 16 hex（只与域取值有关，与描述串无关）。"""
    if not isinstance(salt, str):
        raise TypeError("salt 必须是 str")
    canon: Dict[str, Any] = dict(canonical_condition(domains))
    bad = invalid_values(domains)
    if bad:                      # 合法输入的载荷与旧实现逐字节相同；仅非法声明多一个登记键
        canon[INVALID_KEY] = bad
    payload = json.dumps(canon, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((salt + payload).encode("utf-8")).hexdigest()[:16]


def part_cond_hash(part_type: str, image_hash: str, part_idx: int) -> str:
    """C3：部件级 cond_hash = sha256(image_hash|part_type|part_idx) 前 16 hex。"""
    if isinstance(part_idx, bool) or not isinstance(part_idx, int) or part_idx < 0:
        raise ValueError(f"part_idx 必须是非负整数，得到 {part_idx!r}")
    for name, v in (("part_type", part_type), ("image_hash", image_hash)):
        if not isinstance(v, str) or not v:
            raise ValueError(f"{name} 必须是非空字符串")
    return hashlib.sha256(f"{image_hash}|{part_type}|{part_idx}".encode("utf-8")).hexdigest()[:16]


def img0_domains() -> Dict[str, str]:
    """演示图 img0 的原始域描述（含同义词变体）。"""
    return {"subject": "人物", "count": "单体", "pose": "站姿", "view_distance": "全身",
            "view_dir": "正视图", "frame": "竖幅", "background": "白", "style": "可爱动漫",
            "line_edge": "淡线稿", "color": "柔和", "lighting": "柔和", "contrast": "清晰",
            "symmetry": "对称", "clothing": "常服", "input_modality": "彩色立绘"}
