"""门禁：lspi 底座不得 import 任何插件包或 lingshu.world/nn/gen；插件之间不得互相 import。"""
import ast, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "packages"
PLUGINS = {"lspi_voxel", "lspi_trail"}
rules = {
    "lspi-core/lspi": PLUGINS | {"lingshu.world", "lingshu.nn", "lingshu.gen", "lingshu"},
    "lspi-voxel/lspi_voxel": PLUGINS - {"lspi_voxel"},
    "lspi-trail/lspi_trail": (PLUGINS - {"lspi_trail"}) | {"lingshu"},
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
