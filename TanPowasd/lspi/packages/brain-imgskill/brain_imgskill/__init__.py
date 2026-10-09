"""brain-imgskill：从大脑库 dsh-memory 拆出的第一个内核插件（任务书 v0.3 · M2）。

`imgskill.py` 与上游 md_cg/imgskill.py 逐字节相同（见 NOTICE.md），本文件只做 LSPI 适配：
    cg(op="imgskill", action="resize", src=..., params={...}, sandbox_root=..., ...)
  → imgskill.run({"op": "resize", ...})
  → 返回体在原样保留 ok/artifact_path/asset/meta/audit_id/backend/error 的基础上，补统一信封的 status。

不替调用方补沙箱根：契约 §九-#8「调用方必须显式给根」，缺即原样返回 imgskill 的拒绝。
caller 缺省填插件溯源 plugin://imgskill@<版本>，用于 imgskill 台账归因。
"""
from __future__ import annotations

from lspi import PluginManifest

from . import imgskill as _S

ACTIONS = tuple(sorted(_S._OPS)) + ("ops",)


class ImgSkillPlugin:
    manifest = PluginManifest(
        name="imgskill", version="0.1.0", lspi=">=1,<2",
        actions=ACTIONS, default_action="ops",
        reads=(), writes=(),            # 不写认知图；产物只落调用方给的沙箱根
        permission="write",             # 会在沙箱根写文件与台账 → 按写类 op 授权（保守）
        hosts=("brain",),
        extras=("magick|Pillow",),
        summary="图像 Skill（L1）13 op：inspect/resize/convert/thumbnail/crop/rotate/flip/flop/adjust/blur/sharpen/composite/mask",
    )

    def activate(self, ctx):
        self.ctx = ctx

    def deactivate(self):
        pass

    def call(self, action, p):
        if action == "ops":
            return {"status": "ok", "ops": sorted(_S._OPS), "backend": _probe()}
        req = {"op": action,
               "src": p.get("src"), "dst": p.get("dst"),
               "params": p.get("params") or {},
               "sandbox_root": p.get("sandbox_root"),
               "caller": p.get("caller") or self.manifest.provenance}
        for k in ("declared_level", "idempotency_key"):
            if k in p:
                req[k] = p[k]
        out = _S.run(req)
        return {"status": "ok" if out.get("ok") else "error", **out}


def _probe():
    try:
        name, _exe, version, note = _S.resolve_backend()
        return {"name": name, "version": version, "note": note}
    except Exception as e:  # 后端缺失不影响插件激活
        return {"error": getattr(e, "code", repr(e))}
