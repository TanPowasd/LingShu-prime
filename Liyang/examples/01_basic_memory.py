"""最小示例 1：基础记忆——写入、召回、去重、维护、落盘重开。

    python examples/01_basic_memory.py            # 只需本包（零第三方依赖、零模型）

库文件写在临时目录，运行完即删。"""
import os
import tempfile

os.environ.setdefault("LINGSHU_NG_SEM", "off")      # 本例不用模型件；也免去「未设模型目录」的一次性提示

from lingshu_ng.engine import MemoryEngine          # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "mem.db")
        e = MemoryEngine(path)
        for text in ["The quarterly report is due next Friday.",
                     "Alice prefers oat milk in her coffee.",
                     "The office Wi-Fi password was rotated on Monday.",
                     "Alice prefers oat milk in her coffee."]:         # 第 4 条与第 2 条重复 → merged
            w = e.perceive(text, importance=0.6)
            print(f"{w.action:8s} {w.node_id}")
        for node, score in e.recall("what milk does Alice like", limit=3)["hits"]:
            print(f"{score:.3f}  {node.content}")
        print("maintenance:", e.run_maintenance())                       # 提升 → 巩固 → 衰减 → 遗忘（确定性顺序）
        e.close()

        e = MemoryEngine(path)                                            # 落盘：重开后仍在
        hits = e.recall("quarterly report", limit=1)["hits"]
        assert hits and "quarterly" in hits[0][0].content
        print("reopened:", hits[0][0].content)
        e.close()


if __name__ == "__main__":
    main()
