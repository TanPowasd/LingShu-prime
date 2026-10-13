# CHANGELOG rel-v1.19（stab-r4：semrank 缺省模型目录）

- 版本号：**rel-v1.19**（`lingshu_ng.__version__ == "1.19.0"`）；base sha：LingShu-prime main **8795d266**（= rel-v1.18）；发布树 wt-rel rel-v1 = rel-v1.18 + stab-v1（475fed6e）。
- 本版只修可用性问题，不含检索 / 版本链调优；检索与版本链指标只作持平门。

## 改了什么

- **`lingshu_ng.semrank` 缺省模型目录不再是作者开发机路径**。新函数 `semrank.model_root()`：
  1. 设了 `LINGSHU_NG_SEM` 就用它（`off` / `0` / `none` / 空串 = 关闭，与旧版一致）；
  2. 未设 → 退到 `~/.cache/lingshu_ng/models`（`semrank.default_model_dir()`，调用时按当前用户主目录展开），
     并在进程内打 **一次 WARNING**（logger `lingshu_ng`），同时登记 `diag.fallbacks()["sem_model_dir_default"]`：写明所用目录、目录是否存在、怎样启用或关闭。
     目录不存在 ⇒ 语义件不可用，逐位退回无模型路径；`capabilities()` 的不可用原因里能看到该路径。
  `DEFAULT_DIR` 仍保留为模块属性（导入时展开的同一路径）。rel-v1.18 及以前未设时缺省为 `/workspace/work/ls/_shared/models`，
  在别的机器上不存在，语义件**静默**退回 v4。
- 新增 `tests_ng/test_semrank_model_root.py`（5 条：env 优先且无警告；off / 空串 = 关闭；未设退到用户缓存目录且只警告一次、目录不存在时退回无模型；
  缺省目录存在时被使用；包内 .py 不含开发机路径）。`tests_ng/_optdeps.model_dir` 改用 `model_root(warn=False)`。
- `docs/API_ng.md` §8 / §9 同步。

## 行为变更

- 未设 `LINGSHU_NG_SEM` 的进程会多一条 WARNING（只一条）；不想看到就显式设置 `LINGSHU_NG_SEM=<目录>` 或 `off`。
- 若有人依赖旧的开发机缺省路径，需改设 `LINGSHU_NG_SEM` 或把模型放到 `~/.cache/lingshu_ng/models`。

## 回归门（对 rel-v1.18 / stab3a）

开发沙箱里 `~/.cache/lingshu_ng/models` 软链到原共享模型目录（`env_reinstall.sh` 已加），所以门在「未设 `LINGSHU_NG_SEM`」时走的是新缺省路径、读到同一批模型件。读数存 wt-stab `_stab/r4/`。

- tests_ng（3.12.15，onnxruntime + 模型件）：**3202 passed**（= 3197 + 新增 5）。
- 验收矩阵（全部 exit 0）：随机序 seed 61 / 62 各 3202 passed；无 onnxruntime、DLL 损坏、无模型各 3196 passed 3 skipped；最小 venv 2028 passed 51 skipped；Python 3.11.17 / 3.13.5 各 3196 passed 3 skipped。
- 打包（`pkg_check.sh`）：3.12 `full` / `embed`、3.11.17、3.13.5 全部 PKG_OK，版本 1.19.0。另在空 HOME、未设 `LINGSHU_NG_SEM` 的干净 venv（embed）里实测：打出一条 `sem_model_dir_default` WARNING，档位 v4（`_stab/r4/clean_home_demo.txt`）。
- gate_rel 四段 cn / chainzh / t2r / hmbzh：与 rel-v1.18（stab-r3）读数逐项相同；t2r r1test 380 题名次逐题相同。
- gen 无模型 stab4a 对 stab3a：loc_dev 383/383、LME dev 83/83 逐题名次相同。
- 版本链 h100 / h50：对 `_stab/r3/det/fix_*_1` 逐字段相同。误登记逐条对照：99 个文件 0 处不同。

## 未解决项（照实）

- Windows 真机未测（`~` 在 Windows 上展开为 `%USERPROFILE%`，未实测）。
- 占位 45 个、扩展面 28 项未完成。
- 未支持 `XDG_CACHE_HOME`（固定用 `~/.cache`）。

## 推送记录

（待填）
