"""场景读数：在当前 venv 里挂载 LSPI，打印一行 JSON。"""
import json, sys, warnings
warnings.filterwarnings("ignore")
from importlib.util import find_spec
from lingshu.core.core import SpacetimeMemoryEngine
from lspi import attach, install_shims

e = SpacetimeMemoryEngine(":memory:")
reg = attach(e)
install_shims(e, {"voxel_world": "voxel"})
out = {
    "scenario": sys.argv[1],
    "numpy_installed": find_spec("numpy") is not None,
    "plugins_active": reg.list(),
    "report": {k: v["state"] for k, v in reg.report().items()},
    "engine.voxel_world(state)": e.voxel_world("state")["status"],
    "cap(voxel) is None": e.cap("voxel") is None,
}
if "voxel" in reg.list():
    eid = e.voxel_world("spawn", {"pos": [1, 1, 1], "velocity": [1, 0, 0]})["entity_id"]
    e.voxel_world("simulate", {"steps": 2})
    c = e.voxel_world("commit", {"entity_id": eid})
    out["commit"] = c["status"]
    out["commit_tags"] = e.store.get_node(c["node_id"]).tags[-2:]
if "trail_reason" in reg.list():
    out["trail.tracked"] = len(reg.call("trail_reason", "tracked")["tracked"])
out["trail_reason.displacement"] = reg.call("trail_reason", "displacement", {"entity_id": "x"})["status"]
out["gate_log"] = [(r.plugin, r.kind, r.accepted) for r in reg.gate.log]
print(json.dumps(out, ensure_ascii=False))
