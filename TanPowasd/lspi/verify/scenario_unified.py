"""E 场景：同一插件、同一信封、两个宿主——读数并排。用法：python scenario_unified.py <dsh-memory 仓根>"""
import json, sys, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, sys.argv[1])
from lspi import Registry, call
from lspi_credibility import CredibilityPlugin
from lspi_brain import attach_brain, dispatch
from lingshu.core.core import SpacetimeMemoryEngine
from md_cg.mdcos import MdCGSecure
from md_cg.security import Principal

SEQ = [("hit", 1.0, False), ("miss", 0.6, True), ("hit", 0.8, True)]
out = {}
eng = SpacetimeMemoryEngine(":memory:"); r = Registry(eng); r.add(CredibilityPlugin()); r.activate_all(); eng.plugins = r
cg = MdCGSecure(tempfile.mkdtemp(), principal=Principal(actor="E", role="recorder", ops_allow=("read", "write"), session="E"))
attach_brain(cg, plugins=[CredibilityPlugin()])
for name, t in (("body", eng), ("brain", cg)):
    for a, c, s in SEQ:
        last = call(t, "credibility", a, channel="tactile", conf=c, strong=s)
    com = call(t, "credibility", "commit", channel="tactile")
    out[name] = {"credibility": last["credibility"], "a": last["a"], "b": last["b"],
                 "commit_status": com["status"], "node_written": bool(com.get("node_id"))}
fm = dispatch(cg, {"op": "read", "node_id": call(cg, "credibility", "commit", channel="tactile")["node_id"]}).get("frontmatter", {})
out["brain_node"] = {"layer": fm.get("layer"), "tags": [x for x in fm.get("tags", []) if x.startswith(("kind:", "provenance:"))]}
ro = MdCGSecure(tempfile.mkdtemp(), principal=Principal(actor="E", role="recorder", ops_allow=("read",), session="E2"))
attach_brain(ro, plugins=[CredibilityPlugin()])
out["brain_readonly_commit"] = call(ro, "credibility", "commit", channel="tactile")["status"]
out["same_readings"] = out["body"]["credibility"] == out["brain"]["credibility"] and out["body"]["a"] == out["brain"]["a"]
print(json.dumps(out, ensure_ascii=False))
