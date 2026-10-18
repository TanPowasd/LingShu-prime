# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""ng_arm 守卫（需 $UMB_NG 指向 lingshu-ng 克隆；未设 ⇒ 打印"跳过"并以 0 退出，不算通过的读数）。
  T1 零模型：semantic / neural / chain 均为 None，LINGSHU_NG_SEM=off。
  T2 去重映射：重复正文并入同一节点 ⇒ merged=1、multi_nodes=1，召回把该节点展开为两个单元序号（写入序），无重复。
     定点变异自证：同语料 skip_dedup=True（去重关）⇒ 无 merged，T2 的计数断言在该变异下必红。
  T3 补尾：结果是 0..n-1 的一个排列（ng 未返回的单元按写入序补尾）。
  T4 钉钟可复现：两个独立引擎同语料同题，名次逐位相同；created_at 恒为 CLOCK。"""
import os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def main():
    if not os.environ.get("UMB_NG"):
        print("跳过：未设 UMB_NG"); return
    import ng_arm as N
    texts = ["Alice moved to Paris in May 2023.", "Bob adopted a grey cat named Miso.",
             "Alice moved to Paris in May 2023.", "我昨天去北京看了长城。", "The weather in Paris was rainy all week."]
    x = N.NgIndex(texts)
    assert os.environ.get("LINGSHU_NG_SEM") == "off"
    N._check(x.e)                                                       # T1
    assert x.stats["merged"] == 1 and x.stats["multi_nodes"] == 1 and x.stats["nodes"] == 4, x.stats   # T2
    o, nh, amb = x.rank("Where did Alice move?", 10)
    assert o[:2] == [0, 2] and amb == 1, (o, amb)
    assert sorted(o) == list(range(len(texts))), o                      # T3
    # 定点变异：去重关 ⇒ 不再合并（证明 T2 断言能分辨"去重开/关"）
    e = N.setup()["ME"](":memory:")
    acts = [e.perceive(t, skip_dedup=True).action for t in texts]
    assert acts.count("merged") == 0, acts
    e.close()
    y = N.NgIndex(texts)                                               # T4
    for q in ("Alice Paris", "北京长城", "cat"):
        assert x.rank(q, 10) == y.rank(q, 10), q
    n = y.e.store.nodes.get(next(iter(y.of)))
    assert n.created_at == N.CLOCK, n.created_at
    x.close(); y.close()
    print("test_ng_arm: T1–T4 通过")


if __name__ == "__main__":
    main()
