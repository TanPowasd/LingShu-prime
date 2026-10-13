# -*- coding: utf-8 -*-
"""生成 API 文档附录与公开 API 签名快照（在仓根执行）。

    python tools/ci/gen_api_appendix.py [docs/API_ng.md]   # docs/API_ng.md 附录 A：兼容门面方法支持状态（compat_methods()）
    python tools/ci/gen_api_appendix.py --stability        # docs/STABILITY_ng.md 附录：公开 API 清单（tools/ci/api_surface.py）
    python tools/ci/gen_api_appendix.py --snapshot         # 更新 tests_ng/api_snapshot.json（见 STABILITY_ng §3 的放行规则）

只改各文件标记行之后的部分。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tools", "ci"))
os.environ.pop("LINGSHU_NG_STRICT_UNSUPPORTED", None)
from lingshu_ng.capabilities import compat_methods  # noqa: E402

MARK = "<!-- 以下由 tools/ci/gen_api_appendix.py 生成，勿手改 -->"
SNAPSHOT = os.path.join("tests_ng", "api_snapshot.json")


def _write_after_mark(path, lines):
    head = open(path, encoding="utf-8").read().split(MARK)[0]
    open(path, "w", encoding="utf-8").write(head + "\n".join([MARK, ""] + lines))


def api_appendix(path="docs/API_ng.md"):
    """docs/API_ng.md 附录 A。"""
    tab = compat_methods()
    sup = [n for n, v in tab.items() if v["status"] == "supported"]
    uns = [(n, v) for n, v in tab.items() if v["status"] == "unsupported"]
    out = [f"`SpacetimeMemoryEngine` 公开方法 {len(tab)} 个：supported {len(sup)}、unsupported {len(uns)}。", "",
           "### A.1 unsupported（返回上游缺省；严格模式抛 NotSupportedError）", "",
           "| 方法 | 器官类别 | 上游缺省返回 |", "|---|---|---|"]
    out += [f"| `{n}` | {v['organ']} | `{v['upstream_default']}` |" for n, v in sorted(uns, key=lambda x: (x[1]["organ"], x[0]))]
    out += ["", "### A.2 supported（类上真实实现）", "", ", ".join(f"`{n}`" for n in sup), ""]
    _write_after_mark(path, out)
    print("supported", len(sup), "unsupported", len(uns))


def stability_appendix(path="docs/STABILITY_ng.md"):
    """docs/STABILITY_ng.md 附录：公开 API 清单（按模块 / 类分组；签名不含类型注解）。"""
    import api_surface
    s = api_surface.surface()
    groups = {}
    for k, v in s.items():
        if k.startswith("compat_status."):
            continue
        owner = k
        for mod, names in api_surface.PUBLIC:
            for n in names:
                q = f"{mod}.{n}"
                if k == q or k.startswith(q + "."):
                    owner = q
        groups.setdefault(owner, []).append((k[len(owner):].lstrip(".") or "·", v))
    out = [f"公开名字与签名共 {len(s)} 项（含兼容门面支持状态 {sum(k.startswith('compat_status.') for k in s)} 项，"
           f"见快照 `tests_ng/api_snapshot.json`）。签名只列参数名、种类与缺省值。", ""]
    for owner in sorted(groups):
        items = groups[owner]
        out.append(f"#### `{owner}`")
        out.append("")
        if len(items) > 12:
            out.append(", ".join(f"`{m}{'' if v.startswith(('class', 'property', 'stub', 'attr')) else v}`" for m, v in items))
        else:
            out += [f"- `{m}` {v}" if m == "·" else f"- `{m}`: `{v}`" for m, v in items]
        out.append("")
    _write_after_mark(path, out)
    print("stability items", len(s))


def _version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def snapshot():
    """更新快照。放行规则（STABILITY_ng §3）：有删除 / 改签名 ⇒ 主版本号须升，或当前版本的 CHANGELOG
    逐个点名（「不兼容变更」）；只有新增 ⇒ 版本号须高于快照，或 CHANGELOG 点名。"""
    import api_surface
    import lingshu_ng
    new = api_surface.surface()
    cur = lingshu_ng.__version__
    old = json.load(open(SNAPSHOT, encoding="utf-8")) if os.path.exists(SNAPSHOT) else None
    if old is not None:
        d = api_surface.diff(old["surface"], new)
        mm = ".".join(cur.split(".")[:2])
        cl = f"CHANGELOG_rel-v{mm}.md"
        text = open(cl, encoding="utf-8").read() if os.path.exists(cl) else ""
        unnamed = lambda names: [n for n in names if n.rsplit(".", 1)[-1] not in text]
        breaking = d["removed"] + d["changed"]
        if breaking and _version_tuple(cur)[0] <= _version_tuple(old["version"])[0] and unnamed(breaking):
            sys.exit(f"不兼容变更未放行：{unnamed(breaking)[:20]}——升主版本号，或在 {cl} 逐个点名")
        if d["added"] and _version_tuple(cur) <= _version_tuple(old["version"]) and unnamed(d["added"]):
            sys.exit(f"新增公开 API 未放行：{unnamed(d['added'])[:20]}——升版本号，或在 {cl} 点名")
        print("diff", {k: len(v) for k, v in d.items()})
    json.dump({"version": cur, "surface": new}, open(SNAPSHOT, "w", encoding="utf-8"), ensure_ascii=False, indent=0,
              sort_keys=True)
    open(SNAPSHOT, "a", encoding="utf-8").write("\n")
    print("snapshot", cur, len(new))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--snapshot"]:
        snapshot()
    elif args[:1] == ["--stability"]:
        stability_appendix(*args[1:])
    else:
        api_appendix(*args)
