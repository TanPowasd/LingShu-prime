"""M2：大脑库第一个拆出的插件 brain-imgskill——经 cg(op=imgskill) 调用与上游 md_cg.imgskill.run 等价。"""
import os
import tempfile

import pytest

from lspi import call
from conftest import _brain_available, make_brain

S_up = None


def _need():
    global S_up
    if not _brain_available():
        pytest.skip("未提供 dsh-memory（LSPI_BRAIN_SRC）")
    pytest.importorskip("brain_imgskill", reason="未安装 brain-imgskill")
    pytest.importorskip("lspi_brain", reason="未安装 lspi-brain-host")
    Image = pytest.importorskip("PIL.Image", reason="无 Pillow，造不了测试图")
    from md_cg import imgskill as up
    S_up = up
    return Image


def _sandbox(Image):
    root = tempfile.mkdtemp(prefix="imgsb_")
    img = Image.new("RGB", (40, 30), (200, 60, 30))
    for x in range(10):
        img.putpixel((x, x), (0, 0, 255))
    img.save(os.path.join(root, "src.png"))
    Image.new("L", (40, 30), 128).save(os.path.join(root, "mask.png"))
    Image.new("RGB", (10, 10), (0, 255, 0)).save(os.path.join(root, "over.png"))
    return root


CASES = [
    ("inspect", {}),
    ("resize", {"width": 20, "height": 15}),
    ("convert", {"format": "jpg"}),
    ("thumbnail", {"max_edge": 20}),
    ("crop", {"x": 5, "y": 5, "width": 10, "height": 8}),
    ("crop", {"x": 35, "y": 25, "width": 10, "height": 10}),     # 越窗 → E_BAD_PARAM
    ("rotate", {"degrees": 90}),
    ("flip", {}), ("flop", {}),
    ("adjust", {"brightness": 20, "contrast": 10, "gamma": 1.2}),
    ("blur", {"sigma": 1.5}), ("sharpen", {"sigma": 1.0}),
    ("composite", {"over_path": "over.png", "gravity": "center", "opacity": 0.5}),
    ("mask", {"mask_path": "mask.png", "mode": "set"}),
    ("mask", {"mask_path": "mask.png", "mode": "mul"}),           # 范围外 → E_UNSUPPORTED_OP
]


def _norm(out, root):
    """去掉每次都变的字段（audit_id、绝对路径），留可比的语义面。"""
    err = out.get("error") or {}
    meta = dict(out.get("meta") or {})
    asset = out.get("asset")
    art = out.get("artifact_path")
    return {"ok": out.get("ok"), "err": err.get("code"), "meta": meta,
            "artifact": os.path.relpath(art, root) if art and os.path.isabs(art) else art,
            "asset": asset,
            "backend": (out.get("backend") or {}).get("name") if isinstance(out.get("backend"), dict) else out.get("backend")}


@pytest.mark.parametrize("op,params", CASES, ids=[f"{o}-{i}" for i, (o, _) in enumerate(CASES)])
def test_plugin_equals_upstream(op, params):
    Image = _need()
    from brain_imgskill import ImgSkillPlugin
    from lspi_brain import attach_brain, dispatch
    r_up, r_pl = _sandbox(Image), _sandbox(Image)
    up = S_up.run({"op": op, "src": "src.png", "params": params, "sandbox_root": r_up,
                   "caller": "plugin://imgskill@0.1.0"})
    cg = make_brain(ops_allow=("read", "write"))
    attach_brain(cg, plugins=[ImgSkillPlugin()])
    pl = dispatch(cg, {"op": "imgskill", "action": op, "src": "src.png", "params": params,
                       "sandbox_root": r_pl})
    assert pl["status"] == ("ok" if up["ok"] else "error")
    assert _norm(pl, r_pl) == _norm(up, r_up)


def test_no_sandbox_root_not_defaulted():
    Image = _need()
    from brain_imgskill import ImgSkillPlugin
    from lspi_brain import attach_brain
    cg = make_brain(); attach_brain(cg, plugins=[ImgSkillPlugin()])
    out = call(cg, "imgskill", "inspect", src="src.png")
    up = S_up.run({"op": "inspect", "src": "src.png", "caller": "x"})
    assert out["status"] == "error" and out["error"]["code"] == up["error"]["code"]


def test_ops_listing_and_default_action():
    _need()
    from brain_imgskill import ImgSkillPlugin
    from lspi_brain import attach_brain
    cg = make_brain(); attach_brain(cg, plugins=[ImgSkillPlugin()])
    out = call(cg, "imgskill")                   # action 缺省 → ops
    assert out["status"] == "ok" and out["ops"] == sorted(S_up._OPS) and len(out["ops"]) == 13


def test_readonly_token_denied():
    Image = _need()
    from brain_imgskill import ImgSkillPlugin
    from lspi_brain import attach_brain
    cg = make_brain(ops_allow=("read",)); attach_brain(cg, plugins=[ImgSkillPlugin()])
    out = call(cg, "imgskill", "resize", src="src.png", params={"width": 4, "height": 3},
               sandbox_root=_sandbox(Image))
    assert out["status"] == "denied"


def test_brain_only_plugin_refused_by_body(engine):
    _need()
    from brain_imgskill import ImgSkillPlugin
    from lspi import Registry
    reg = Registry(engine); reg.add(ImgSkillPlugin())
    assert reg.report()["imgskill"]["state"] == "wrong_host"


def test_absent_plugin_same_fallback_shape():
    _need()
    from lspi_brain import attach_brain, dispatch
    cg = make_brain(); attach_brain(cg)          # 不装 imgskill
    out = dispatch(cg, {"op": "imgskill", "action": "inspect"})
    assert out["status"] == "imgskill_not_ready"
