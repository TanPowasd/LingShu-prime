# -*- coding: utf-8 -*-
"""生成 docs/API_ng.md 附录 A（兼容门面方法支持状态），数据来自 lingshu_ng.capabilities.compat_methods()。
用法：python tools/ci/gen_api_appendix.py [docs/API_ng.md]（在仓根执行；只改标记行之后的部分）"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.pop("LINGSHU_NG_STRICT_UNSUPPORTED", None)
from lingshu_ng.capabilities import compat_methods  # noqa: E402

MARK = "<!-- 以下由 tools/ci/gen_api_appendix.py 生成，勿手改 -->"
path = sys.argv[1] if len(sys.argv) > 1 else "docs/API_ng.md"
head = open(path, encoding="utf-8").read().split(MARK)[0]
tab = compat_methods()
sup = [n for n, v in tab.items() if v["status"] == "supported"]
uns = [(n, v) for n, v in tab.items() if v["status"] == "unsupported"]
out = [MARK, "", f"`SpacetimeMemoryEngine` 公开方法 {len(tab)} 个：supported {len(sup)}、unsupported {len(uns)}。", "",
       "### A.1 unsupported（返回上游缺省；严格模式抛 NotSupportedError）", "",
       "| 方法 | 器官类别 | 上游缺省返回 |", "|---|---|---|"]
out += [f"| `{n}` | {v['organ']} | `{v['upstream_default']}` |" for n, v in sorted(uns, key=lambda x: (x[1]["organ"], x[0]))]
out += ["", "### A.2 supported（类上真实实现）", "", ", ".join(f"`{n}`" for n in sup), ""]
open(path, "w", encoding="utf-8").write(head + "\n".join(out))
print("supported", len(sup), "unsupported", len(uns))
