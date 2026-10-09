"""门禁：底座不得 import 插件、宿主实现（lingshu / md_cg）或宿主适配包；插件之间不得互相 import；
插件不得 import 任何宿主内部（lingshu.core、md_cg、lspi_brain）——只认 lspi 协议。"""
import ast, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "packages"
PLUGINS = {"lspi_voxel", "lspi_trail", "lspi_credibility", "brain_imgskill", "brain_agenda"}
HOST_INTERNALS = {"lingshu.core", "md_cg", "lspi_brain"}
rules = {
    "lspi-core/lspi": PLUGINS | {"lingshu", "md_cg", "lspi_brain"},
    "lspi-brain-host/lspi_brain": PLUGINS | {"lingshu"},
    "lspi-voxel/lspi_voxel": (PLUGINS - {"lspi_voxel"}) | HOST_INTERNALS,
    "lspi-trail/lspi_trail": (PLUGINS - {"lspi_trail"}) | {"lingshu", "md_cg", "lspi_brain"},
    "lspi-credibility/lspi_credibility": (PLUGINS - {"lspi_credibility"}) | HOST_INTERNALS,
    # 拆出的大脑插件：不得回头 import 内核 md_cg（G5 同口径），也不得 import 宿主适配
    "brain-imgskill/brain_imgskill": (PLUGINS - {"brain_imgskill"}) | HOST_INTERNALS | {"lingshu"},
    # 接管内核 op 的大脑插件：可依赖内核**公开模块**（md_cg.nodefile），不得依赖分派层与宿主适配
    "brain-agenda/brain_agenda": (PLUGINS - {"brain_agenda"}) | {"lingshu", "lspi_brain", "md_cg.mcp_server", "md_cg.mdcos", "md_cg.tasks"},
}
violations, scanned = [], 0
for sub, banned in rules.items():
    for f in (ROOT / sub).rglob("*.py"):
        scanned += 1
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                   [n.module or ""] if isinstance(n, ast.ImportFrom) and n.level == 0 else []
            for m in mods:
                if any(m == b or m.startswith(b + ".") for b in banned):
                    violations.append(f"{f.relative_to(ROOT)}:{n.lineno} import {m}")
print(json.dumps({"files_scanned": scanned, "violations": violations}, ensure_ascii=False))
sys.exit(1 if violations else 0)
