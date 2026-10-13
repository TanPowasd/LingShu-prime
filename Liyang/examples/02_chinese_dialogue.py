"""最小示例 2：中文对话记忆——逐轮写入情境层与知识层，按问句召回；开启版本链后回答「现在是哪天」类问题。

    python examples/02_chinese_dialogue.py        # 只需本包（零模型）
"""
import os
import tempfile

os.environ.setdefault("LINGSHU_NG_SEM", "off")

from lingshu_ng.engine import MemoryEngine          # noqa: E402

DIALOGUE = [
    ("用户", "青鸾项目 的周会时间首次确立为 周三上午十点。"),
    ("助手", "好的，已记下青鸾周会时间。"),
    ("用户", "张三负责白鹭项目的预算，截止日期是十月三十一日。"),
    ("用户", "青鸾项目 的周会时间调整为 周四下午三点，起因是会议室冲突。"),
    ("用户", "我对花生过敏，订餐时请避开。"),
]
# 版本链认「<主体> 的<属性>首次确立为 / 调整为 <值>」这类陈述（写入路径零 LLM，规则抽取）；口语改期句只进普通召回。


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        e = MemoryEngine(os.path.join(d, "chat.db"))
        e.enable_chain()                               # 版本链：同一事物的值变化按写入序成链（缺省关）
        for who, text in DIALOGUE:
            e.add_context(f"{who}：{text}")             # 情境层：原话、短期、容量先进先出
            if who == "用户":
                e.perceive(text, tags=["对话"])          # 知识层：长期、近重复去重
        for q in ["青鸾的周会时间现在是什么", "谁负责白鹭项目的预算", "我对什么过敏"]:
            hits = e.recall(q, limit=2)["hits"]
            print(q, "→", hits[0][0].content if hits else "（无）")
        ans = e.chain_answer("青鸾项目的周会时间现在是什么")
        assert ans and ans["value"] == "周四下午三点", ans
        print("版本链现值：", ans["value"], "| 状态：", ans["state"], "| 依据：", ans["basis"][0]["quote"])
        e.close()


if __name__ == "__main__":
    main()
