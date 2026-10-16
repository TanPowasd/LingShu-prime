<!-- 草稿：只写不发。回复 FuRongJun-1999/dsh-memory PR #395；发表须用户点头。 -->

@FuRongJun-1999 @ybyz2 已按两位的意见 rebase 并补齐缓存身份，fork 分支 `feat/qmd-confluence` 已强推。

## 内容
1. **rebase 到最新 main**：基线 `fffa4f2` → `a49fde2`。原提交改写为 `11602d2`，另加一个修订提交 `771e045`（head）。
2. **生成件重渲染，未手改**：冲突只在 `docs/reference/配置参数表_v0.1.md` 的计数行；`md_cg/config_registry_bulk.py` 的两行追加自动并入（与 main 新增登记取并集）。之后用仓内生成器重写两份生成件：`python -X utf8 scripts/gen_config_doc.py`、`python -X utf8 scripts/gen_config_validate.py`。重渲染后「环境面分类登记」是 **115**（ybyz2 指出的那行：main 侧 `MDCG_REPLAY_NEG_MAX_COVERAGE` + 本件 `MDCG_QMD_LLM_*`），`calibrating=21`。相对 main，生成件只多本件的两行登记和随之变化的计数。
3. **缓存身份补两维**（新发现 1 的缺陷 A、B）：`md_cg/qmd_llm.py` · `Cache.identity` 加 `max_tokens`（假值记 `None`，与 `chat` 不传该字段一致）和 `key_sha = sha256(key)`。`call` 把 `max_tokens` 透传给 `Cache.get` / `Cache.put`，命中后仍按完整身份逐项比对（`CacheIdentityError` 不变）。明文 key 不进身份，也不写入任何缓存文件。
4. **守卫补判据和变异**：`md_cg/test_qmd.py` 的 P4 新增三条：
   - `P4 max_tokens 不同 ⇒ 干净 miss`：经 `call` 透传，网关调 2 次，请求体 max_tokens 依次是 100、200；
   - `P4 不同 key 同 base+model ⇒ 干净 miss`；
   - `P4 缓存文件不含 key 明文`。
   新增定点变异三条：M12（身份去掉 max_tokens）、M13（身份去掉 key_sha）、M14（身份改存明文 key，自证上一条判据有牙）。原 38 条断言和 M1–M11 没有删改，也没有放宽。

## 原因
- 维护者 10-16 要求 rebase 后重推。
- ybyz2 对抗复核新发现 1：身份缺 `max_tokens` 会让不同配置命中同一条缓存，导致错答；缺 key 会让同网关的多把密钥共用缓存。新发现 2：配置参数表是生成件，计数行是全局量，只能重渲染，不能手改。

## 位置
- `md_cg/qmd_llm.py` · `Cache.identity` / `Cache.get` / `Cache.put` / `call`（模块头与 `Cache` 文档串同步写明身份字段）
- `md_cg/test_qmd.py` · `p45` 末尾新增块、`MUTATIONS` 末尾 M12–M14、模块头 P4 说明
- `docs/reference/配置参数表_v0.1.md`、`md_cg/config_validate.py`：生成器重渲染

## 验证结论（Linux / Python 3.12，head `771e045`，base `a49fde2`）
```
python -X utf8 -m md_cg.test_qmd                      # 通过 41 / 失败 0（原 38 + 新 3）
python -X utf8 -m md_cg.test_qmd --mutate             # 变异 14 条，未恰好点红 0 条
python -X utf8 tests/test_qmd.py                      # 通过 41 / 失败 0
python -X utf8 -m md_cg.config_registry_guard         # 结果：PASS 7 / FAIL 0
python -X utf8 scripts/check_config_env_registry.py   # 结果：PASS
python -X utf8 scripts/gen_config_doc.py --check      # 生成件最新
python -X utf8 scripts/gen_config_validate.py --check # 生成件最新
```
- 撤掉修订（`qmd_llm.py` 换回 `11602d2` 版）重跑正向：P4-P5 块红（`Cache.get()` 签名不收 max_tokens），说明新判据会对修订红。「缓存文件不含 key 明文」在旧版也成立（旧版身份不含 key），它属于防回归判据，由 M14 自证有牙。
- P14 金标、P15 提示词 sha 未改：排序与提示词都没动。
- `scripts/run_tests.py md_cg --jobs 3`：main `a49fde2` 与 head 的失败名单**逐名相同**（7 条：`test_issue146_frontmatter_quarantine`、`test_issue150_empty_query_terms`、`test_issue404_heal_receipt`、`test_issue409_compact_index_completeness`、`test_p4_freshness`、`test_rank_parity_score_mode`、`test_unify_default_off`），**无新增**。head 汇总 `406/426 通过，18 跳过`；多出的一条是 `md_cg.test_qmd`，PASS。本机缺 Rust 二进制、numpy 等，跳过的项见 SKIP 行。
- gate 子项与 main 逐行对比：`workspace_index --check`、`check_local_paths --selftest`、`check_placeholder_leak`、`check_duplicate_keys`、`cogmap_sync check`、`link_check`（OK=270 BROKEN=0）、`check_config_env_registry`、`config_registry_guard`、`gen_config_doc --check`、`gen_config_validate --check`、`check_guard_coverage` 两侧均过。`check_local_paths`（命中 1，`test_issue405_git_pathspec.py`）、`check_unreachable`（命中 2，`test_issue398` / `test_issue400`）、`check_line_anchors`（红 164，五计数逐位相同）两侧读数相同，都是 main 存量，**本件零新增红**。完整对比表见 PR 草稿：https://github.com/TanPowasd/LingShu-prime/blob/main/TanPowasd/agm/confluence/PR_DRAFT_dsh-memory_qmd.md

## 关于 pr299
本件和 `pr299` 都改 `config_registry_bulk.py` 和同一份生成件。我们这次是重渲染，没有手改。合并顺序由维护者定：**若 pr299 先合，我再 rebase 一次并重渲染两份生成件**，同样跑上面的 `--check` 与 `config_registry_guard` 后重推。
ybyz2 建议「G3 比较时忽略计数行、报错文案提示重渲染」，这是守卫口径的策略选择，不在本 PR 范围内（needs-owner-decision）。

## 仍待维护者
- fork PR 的 4 个工作流（python-tests、workspace-index-check、cogmap-check、publish-artifact-check）处于 `action_required`，需维护者批准后才会跑。
- ybyz2 标的 needs-owner-decision：①新功能是否纳入本轮；②与 pr299 的合并顺序。
