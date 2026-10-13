# -*- coding: utf-8 -*-
"""stab-r1：环境无关的确定性 + 可见的退回。

- 时钟：:func:`lingshu_ng.types.now` 可注入；冻结 / 粗粒度时钟下帧链与「最新帧」按写入序断开，不再落到随机 id 上；
- 退回可见：sem_v4fb 退回打且只打一次 WARNING；``capabilities()`` 报出生效档位与不可用原因；
- 损坏的 onnxruntime（装了但导入抛 ImportError）不打断收集，也不让打分件构造抛错。
"""
import logging
import os
import subprocess
import sys

import pytest

from lingshu_ng import assoc as ax
from lingshu_ng import diag, semrank, types
from lingshu_ng.capabilities import capabilities, semantic_tier
from lingshu_ng.compat import SpacetimeMemoryEngine
from lingshu_ng.engine import MemoryEngine
from lingshu_ng.types import EdgeType
from tests_ng._optdeps import plugin, require

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = ["丰巢快递柜取件码忘了，可以在丰巢微信公众号里查看取件码。", "西红柿炒鸡蛋要先炒鸡蛋，盛出后再炒西红柿。",
       "快递柜的取件码也会通过短信发送，短信删了可以联系快递员重发。", "红烧肉先焯水去血沫，再小火慢炖一小时。",
       "丰巢柜子超时取件会收取保管费，会员可以免费延长。", "台风天出门注意远离广告牌和临时搭建物。"]


# ------------------------------------------------------------------ 时钟
def test_now_follows_injected_and_patched_clock(monkeypatch):
    """now() 缺省每次读 time.time()（评测 clockshim 钉住 time.time 照常生效）；set_clock 注入优先，None 恢复。"""
    monkeypatch.setattr(types.time, "time", lambda: 123.0)
    assert types.now() == 123.0
    prev = types.set_clock(lambda: 7.0)
    try:
        assert types.now() == 7.0
    finally:
        types.set_clock(prev)
    assert types.now() == 123.0


def test_frame_chain_survives_reopen_with_tied_clock(tmp_path, frozen_clock):
    """Windows 粗时钟同形：三帧同一墙钟读数写入、重开库后续帧仍接在最后一帧之后
    （此前同分按随机 id 断开，20 次里约 14 次接错；现在按写入序 rowid 断开）。"""
    db = str(tmp_path / "f.db")
    e = SpacetimeMemoryEngine(db)
    a = e.ingest_frame({"caption": "红色杯子"}, entity_hint="杯子", state_hint={"颜色": "红"})
    b = e.ingest_frame({"caption": "红色杯子"}, entity_hint="杯子", state_hint={"颜色": "红"})
    c = e.ingest_frame({"caption": "蓝色杯子"}, entity_hint="杯子", state_hint={"颜色": "蓝"})
    assert a.created_at == b.created_at == c.created_at          # 冻结时钟：三帧同一读数
    rels = {(x.source_id, x.target_id): EdgeType.coerce(x.relation_type)
            for x in e.ng.store.edges.outgoing(a.id) + e.ng.store.edges.outgoing(b.id)}
    assert rels == {(a.id, b.id): EdgeType.SEQUENTIAL, (b.id, c.id): EdgeType.CAUSAL}
    e.close()
    e2 = SpacetimeMemoryEngine(db)
    d = e2.ingest_frame({"caption": "蓝色杯子"}, entity_hint="杯子", state_hint={"颜色": "蓝"})
    assert [x.source_id for x in e2.ng.store.edges.incoming(d.id)] == [c.id]
    e2.close()


def test_world_rebuild_latest_frame_with_tied_clock(tmp_path, frozen_clock):
    """上游 #282 同形 + 粗时钟：同一读数写入的多帧，重建世界取最后写入的一帧。"""
    require("numpy")  # 最小环境（不装 numpy）下 skip，见 tests_ng/_optdeps.py
    from lingshu_ng.world import compat as wc
    sm = wc._derived_module("scene_model")

    class _Agent:
        def __init__(self, engine):
            self.engine, self.store = engine, engine.store

    ag = _Agent(SpacetimeMemoryEngine(str(tmp_path / "w.db")))
    for pos, st in [("0,0.85,5", "shy"), ("3,0.85,8", "happy"), ("5,0.85,9", "angry"), ("8,0.85,2", "sleepy")]:
        sm.ingest_scene(ag, f"肥鱼|fatfish|{pos}|{st}")
        f = sm.load_world_from_memory(ag).entities["肥鱼"]
        assert tuple(f.pos) == tuple(float(v) for v in pos.split(",")) and f.state == st


# ------------------------------------------------------------------ 退回可见
def _eng(tmp_path):
    e = MemoryEngine(str(tmp_path / "m.db"))
    for d in WEB:
        e.perceive(d)
    e.retriever.assoc = ax.AssocConfig(lc_head=2, tp_coh=0.0)
    return e


def test_v4_fallback_warns_exactly_once(tmp_path, no_models, caplog):
    diag.reset()
    e = _eng(tmp_path)
    with caplog.at_level(logging.WARNING, logger="lingshu_ng"):
        for q in ("丰巢取件码忘了怎么办", "红烧肉怎么做", "取件码"):
            e.retriever.recall(q, 6)
    recs = [r for r in caplog.records if r.name == "lingshu_ng" and "sem_v4fb" in r.getMessage()]
    assert len(recs) == 1 and recs[0].levelno == logging.WARNING
    assert "sem_v4fb" in diag.fallbacks()
    diag.reset()


def test_v4_fallback_behaviour_unchanged(tmp_path, no_models, frozen_clock):
    """退回可见只加日志：交付默认（sem_v4fb 1）与显式 v4 配置逐位相同（同 test_semrank 的 v4 断言，此处在冻结时钟下复核）。"""
    e = _eng(tmp_path)
    for q, k in (("丰巢取件码忘了怎么办", 6), ("取件码", 2)):
        e.retriever.assoc = ax.AssocConfig(lc_head=2, tp_coh=0.0)
        x = [(n.content, s) for n, s in e.retriever.recall(q, k)]
        e.retriever.assoc = ax.AssocConfig(lc_head=2, tp_coh=0.0, tp_head=0, sem_n=0)
        y = [(n.content, s) for n, s in e.retriever.recall(q, k)]
        assert x == y


def test_capabilities_reports_tier_without_models(tmp_path, no_models):
    c = MemoryEngine(str(tmp_path / "c.db")).capabilities()
    assert c["semantic_tier"] == "v4"
    # 1.24 起只列已装插件声明的依赖（纯核心环境为空）；装了 lingshu-ng-embed 时至少含其三项
    assert set(c["dependencies"]) <= {"numpy", "onnxruntime", "tokenizers", "PIL"}
    if "embed" in c["plugins"] and c["plugins"]["embed"]["error"] is None:
        assert {"numpy", "onnxruntime", "tokenizers"} <= set(c["dependencies"])
    assert all(set(d) == {"available", "version", "error"} for d in c["dependencies"].values())
    assert c["models"]["cross_scorer"]["available"] is False
    assert c["engine"]["semantic_provider"] is False
    assert SpacetimeMemoryEngine(str(tmp_path / "d.db")).capabilities()["semantic_tier"] == "v4"


def test_semantic_tier_table():
    cfg = ax.AssocConfig()
    assert semantic_tier(cfg, None, None, None) == "v4"
    assert semantic_tier(cfg, object(), None, None) == "v7.1"
    assert semantic_tier(cfg, object(), object(), None) == "v11c"
    assert semantic_tier(ax.AssocConfig(sem_casc=3), object(), object(), object()) == "v13"
    assert semantic_tier(ax.AssocConfig(sem_n=0), object(), object(), object()) == "off"


def test_broken_onnxruntime_records_reason(tmp_path, monkeypatch):
    """装了但导入失败（sys.modules 屏蔽 → ImportError）：打分件 / 稠密件构造不抛错，返回 None 并记原因。"""
    plugin("cross_backend")   # split-r3：模型件在插件 lingshu-ng-embed；纯核心环境下原因是「未安装插件」（test_plugins 覆盖），此处 skip
    for m in ("bge-reranker-base", "bge-small-zh-v1.5"):
        (tmp_path / m / "onnx").mkdir(parents=True)
        (tmp_path / m / "tokenizer.json").write_text("{}", encoding="utf-8")
        for f in ("model_quantized.onnx", "model.onnx"):
            (tmp_path / m / "onnx" / f).write_bytes(b"")
    monkeypatch.setenv("LINGSHU_NG_SEM", str(tmp_path))
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    semrank._SCORERS.clear()
    semrank._EMBEDDERS.clear()
    assert semrank.get_scorer() is None and semrank.get_embedder() is None
    assert semrank.unavailable_reason("scorer").startswith("加载失败 ")
    assert semrank.unavailable_reason("dense").startswith("加载失败 ")
    c = capabilities()
    assert c["dependencies"]["onnxruntime"]["available"] is False and c["semantic_tier"] == "v4"


def test_sem_off_reason(monkeypatch):
    monkeypatch.setenv("LINGSHU_NG_SEM", "off")
    semrank._SCORERS.clear()
    assert semrank.get_scorer() is None and "off" in semrank.unavailable_reason("scorer")


@pytest.mark.parametrize("sim", ["ort_broken", "no_ort"])
def test_collection_survives_unusable_onnxruntime(sim):
    """子进程：把模拟包放到 PYTHONPATH 最前（DLL 加载失败 / 未安装），依赖 onnxruntime 的测试文件被 skip 而非收集报错。"""
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "tests_ng", "_envsim", sim) + os.pathsep + ROOT,
               PYTHONDONTWRITEBYTECODE="1")
    # 1.24：该文件随 OnnxEmbedder 移到插件 lingshu-ng-embed 的测试目录；-p tests_ng.conftest 带上本套件的档位报告头
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-p", "tests_ng.conftest",
                        os.path.join("plugins", "lingshu-ng-embed", "tests_embed", "test_tokvec_pre.py")],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=110)
    assert r.returncode in (0, 5), r.stdout[-2000:] + r.stderr[-2000:]   # 5 = 整个文件在收集期被 skip（无用例可跑）
    assert "1 skipped" in r.stdout and " error" not in r.stdout
    assert "semantic tier (zh long requests): v4" in r.stdout
