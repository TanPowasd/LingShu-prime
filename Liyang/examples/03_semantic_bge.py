"""最小示例 3：带 bge 模型件的语义档（中文长请求的交叉编码重排 v7.1 / 稠密补入 v11c）。

前置：
    pip install "lingshu_ng[embed]"          # numpy + onnxruntime + tokenizers
    模型目录（任选其一）：
      - 设 LINGSHU_NG_SEM=<模型根目录>
      - 或放在 $XDG_CACHE_HOME/lingshu_ng/models（未设 XDG_CACHE_HOME 时 ~/.cache/lingshu_ng/models）
    目录下需有 bge-reranker-base/{tokenizer.json, onnx/model_quantized.onnx}，
    以及（可选，稠密补入）bge-small-zh-v1.5/{tokenizer.json, onnx/model_quantized.onnx}。
    ONNX 版可从 Hugging Face 上 BAAI/bge-reranker-base、BAAI/bge-small-zh-v1.5 的 ONNX 导出获得（权重不随本包发布）。

    python examples/03_semantic_bge.py

缺依赖或缺模型时不报错：打印当前实际档位与缺什么，然后照常以零模型路径（v4）运行——这就是「缺了逐位退回」。
"""
import os
import tempfile

from lingshu_ng.engine import MemoryEngine

DOCS = ["灵枢的写入路径零 LLM，去重按字符二元组 Jaccard。",
        "中文长请求会先经词面通路取候选，再由交叉编码模型重排并自适应截断。",
        "版本链把同一事物的多次取值按写入序串起来，回答现值与历史。",
        "今天食堂的午饭是番茄炒蛋和米饭。",
        "模型权重不随包发布，需要自行放到模型目录。",
        "明天下午三点在三号会议室开评审会。", "白鹭项目的预算截止日期是十月底。",
        "写入去重命中时合并标签并取较大的重要度。", "缺依赖时语义件逐位退回零模型路径。"]


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        e = MemoryEngine(os.path.join(d, "sem.db"))
        caps = e.capabilities()
        tier = caps["semantic_tier"]
        print("semantic_tier:", tier)
        for name, m in caps["models"].items():
            if not m["available"]:
                print(f"  {name}: 不可用 —— {m['reason']}")
        for t in DOCS:
            e.perceive(t)
        e.prefetch_dense()                               # 有稠密件时预算向量（只省冷查询时延，不改名次）；无模型返回 0
        hits = e.recall("系统怎样对中文的长问题做语义排序", limit=20)["hits"]   # limit > 15 = 长请求，才走语义重排
        for node, score in hits[:3]:
            print(f"{score:.3f}  {node.content}")
        if tier in ("v4", "v4-equivalent", "off"):
            print("当前为零模型档；按上方前置说明装好依赖与模型后再运行即为 v7.1 / v11c。")
        e.close()


if __name__ == "__main__":
    main()
