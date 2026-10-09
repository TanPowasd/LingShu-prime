"""M3（task 半）：brain-agenda 接管内核 op task——经 MCP 入口与内核原实现逐字一致。"""
import os
import re
import tempfile

import pytest

from lspi import outcome
from conftest import _brain_available, make_brain


def _need():
    if not _brain_available():
        pytest.skip("未提供 dsh-memory（LSPI_BRAIN_SRC）")
    pytest.importorskip("brain_agenda", reason="未安装 brain-agenda")
    pytest.importorskip("lspi_brain", reason="未安装 lspi-brain-host")


def _designer():
    from md_cg.mdcos import MdCGSecure
    from md_cg.security import Principal
    root = tempfile.mkdtemp(prefix="m3_")
    return MdCGSecure(root, principal=Principal(actor="m3", role="designer", can_admin=True,
                                                 session="m3")), root


SEQ = [
    {"op": "task", "action": "open", "name": "拆分 brain agenda", "plan": "先拆 task 半"},
    {"op": "task", "name": "拆分 brain agenda", "change": "goal 半依赖 6 个内核模块，延后"},  # 签名推导 → open
    {"op": "task", "change": "只追加变更", "node_id": "task_拆分-brain-agenda"},             # → plan_add
    {"op": "task", "action": "status", "node_id": "task_拆分-brain-agenda", "task_status": "done"},  # 缺 result → 拒
    {"op": "task", "task_status": "done", "node_id": "task_拆分-brain-agenda", "result": "M3 task 半完成"},
    {"op": "task", "node_id": "task_拆分-brain-agenda"},                                    # → get
    {"op": "task", "action": "open", "name": "第二张  卡", "plan": "空白归一"},
    {"op": "task", "action": "list"},
    {"op": "task"},                                                                       # 缺省 → list
    {"op": "task", "action": "list", "task_status": "done"},
    {"op": "task", "action": "find", "name": "拆分", "k": 3},
    {"op": "task", "action": "session"},
    {"op": "task", "action": "status", "node_id": "task_第二张-卡", "task_status": "bogus"},
    {"op": "task", "action": "nope"},
]
_TS = re.compile(r"^\d{10}(\.\d+)?$|^\d{4}-\d{2}-\d{2}")


def _norm(o, root):
    if isinstance(o, dict):
        return {k: _norm(v, root) for k, v in o.items()
                if k not in ("created_at", "updated_at", "score")}
    if isinstance(o, list):
        return [_norm(v, root) for v in o]
    if isinstance(o, float) and o > 1e9:
        return "<ts>"
    if isinstance(o, str):
        o = o.replace(root, "<root>")
        return re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", o)
    return o


def _run(cg, req):
    from md_cg import mcp_server as M
    try:
        return M._cg_call(cg, dict(req))
    except Exception as e:
        return {"__raised__": type(e).__name__, "msg": str(e)[:80]}


def test_mcp_path_identical_to_kernel():
    _need()
    from md_cg import mcp_server as M
    from brain_agenda import TaskPlugin
    from lspi_brain import attach_brain, install_mcp
    k_cg, k_root = _designer()
    kern = [_norm(_run(k_cg, r), k_root) for r in SEQ]
    p_cg, p_root = _designer()
    attach_brain(p_cg, plugins=[TaskPlugin()], release=["task"])
    install_mcp(M)
    try:
        plug = [_norm(_run(p_cg, r), p_root) for r in SEQ]
    finally:
        M._cg_dispatch = M._cg_dispatch._orig
    for i, (a, b) in enumerate(zip(kern, plug)):
        assert a == b, f"第 {i} 步不一致：{SEQ[i]}"


def test_permission_raises_same_as_kernel():
    _need()
    from md_cg import mcp_server as M
    from brain_agenda import TaskPlugin
    from lspi_brain import attach_brain, install_mcp
    ro = make_brain(ops_allow=("read",))
    k = _run(ro, {"op": "task", "action": "list"})
    ro2 = make_brain(ops_allow=("read",))
    attach_brain(ro2, plugins=[TaskPlugin()], release=["task"])
    install_mcp(M)
    try:
        p = _run(ro2, {"op": "task", "action": "list"})
    finally:
        M._cg_dispatch = M._cg_dispatch._orig
    assert k.get("__raised__") == p.get("__raised__") == "AccessDenied"


def test_released_but_absent_is_not_ready():
    _need()
    from lspi_brain import attach_brain, dispatch
    cg, _ = _designer()
    attach_brain(cg, release=["task"])           # 放给插件，但不装插件
    out = dispatch(cg, {"op": "task", "action": "list"})
    assert outcome(out) == "task_not_ready" and out["ok"] is False


def test_only_delegated_ops_can_be_released():
    _need()
    from lspi_brain import attach_brain
    cg, _ = _designer()
    with pytest.raises(ValueError):
        attach_brain(cg, release=["read"])        # read 是内联 op，不能直接交出


def test_task_status_field_not_clobbered():
    """大脑返回体里 status 是任务状态；信封不得覆盖，outcome() 以 ok 为准。"""
    _need()
    from brain_agenda import TaskPlugin
    from lspi_brain import attach_brain, dispatch
    cg, _ = _designer()
    attach_brain(cg, plugins=[TaskPlugin()], release=["task"])
    out = dispatch(cg, {"op": "task", "action": "open", "name": "x 卡", "plan": "p"})
    assert out["status"] == "active" and outcome(out) == "ok"


def test_action_sigs_derivation():
    _need()
    from brain_agenda import TaskPlugin
    from lspi_brain import attach_brain, dispatch
    cg, _ = _designer()
    attach_brain(cg, plugins=[TaskPlugin()], release=["task"])
    out = dispatch(cg, {"op": "task", "name": "签名推导卡", "plan": "p"})
    assert out["created"] is True and out["action"] == "open" and out["action_source"] == "sig"
