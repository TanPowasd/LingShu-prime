# nn/gen 线进度（重启后先读此文件接续）

- [x] 1. 提交未入库 bench_nn.py / bench_parts / legacy_compat_*.json
- [x] 2. tests_ng/nn 按文件分批全绿
- [x] 3. run_legacy_compat 分批 + merge
- [x] 4. bench_nn 分段 + merge + BENCH_NN.md/json
- [x] 5. gen 研究脚本迁移

## 记录
- 步骤2：hexgrid_conv 85、net_train 23、quality_nn 137、text_render_gen 70，共 315 绿（OPENBLAS_NUM_THREADS=1）
- 步骤3：ng 16 文件已重跑提交；test_hex_cnn ng 唯一失败=画幅内晶格有意差异（PR #116，旧测试硬编码越界晶格 cell 下标）
- 步骤3：legacy 14 快速文件已提交；legacy hex_search/hex_hier 需后台跑（setsid nohup，日志 /tmp/lc/*.log），串行（同写 legacy json）
- 步骤3 完成：legacy hier/search 采用同日 18:31 前任完整跑结果（7/7、7/7）；汇总 legacy 用例 119/122=97.54%、ng 121/122=99.18%，子项均 66/67
- 步骤4：determinism/train_step/text_search(ng,legacy)/accuracy ng-ng,ng-legacy 已由前任链 nn_scratch/bench_chain.sh 于 18:21–18:33 跑完；accuracy legacy-legacy 由该链后台进行中（pid 13197），完成后 merge
- 步骤5 完成（提交见 git log）：pack_certify/multi_seed/align_probe + test_gen_research；未迁：黑箱生成、冻结读者 blackbox_reader、自家渲染 head_to_head（依赖 hexgen_c1_real/self_source 与外部语料）
- 步骤4 完成：accuracy legacy-legacy 18:44 跑完，merge → lingshu_ng/nn/BENCH_NN.json，BENCH_NN.md 已写。全部步骤完成。

## 第二轮：gen R2@96 兑现率 + 渲染耗时（2026-10-09 开工）
- [x] A. 诊断 ng R2@96_200 未兑现分类；旧实现严格校验公平对比（脚本 tests_ng/nn/gen_diag.py）
- [x] B. 布局改进（不放宽阈值），目标 R2@96≥0.99、R2@48 不降
- [x] C. 渲染耗时剖析优化（目标 ≤ 旧 2×）
- [ ] D. BENCH_NN.md/json 更新 + 测试全绿
- A 结论：ng R2@96_200 的 14 个未兑现全部是同格两/三件「包围盒不相交无解→叠放」：7 件覆盖率不足（被遮挡 0.20–0.89）、7 件完全不可见（含同色同花纹叠放→改动像素为零）。
  旧实现宽松：不查覆盖率/溢出、形状尺寸恒等回显、花纹读「改动像素是否全在 x%3==0」（0/1 像素空真）。用 ng 严格校验器校验旧输出（旧自身几何/相位作应画掩码）：
  R2@96_200 旧 0.9974→0.9583（16 失败：15 同格遮挡、1 全遮挡）；R2@48_200 0.9655→0.8941；R2@48(30) 0.9219→0.8281；R2@96(30) 1.0→0.9455。
- B 完成：新增 lingshu_ng/gen/cellpack.py（精灵互相关遮挡表 + 合法区域 + 松弛逐级 + 未声明 z 可换层序，验证器整图模拟作证书），layout.plan 在盒搜索无解时调用。
  读数：R2@96_200 1.0（384/384）、R2@48_200 1.0（406/406）、R2@48/96(30) 1.0/1.0、1000 题 48/96 均 1.0；test_text_render_gen+test_gen_research 90 绿。
- B 修正：遮挡表改按实心轮廓计（硬约束），排除“花纹相位错开交织在同一处”骗过像素验证的摆位（首版出现两圆中心相距 1px）。修正后 R2@96_200/R2@48_200/30 题均 1.0；1000 题 48→0.999、96→0.9995（余下为三件同格真放不下，叠放）。
- C 完成：render 解析形状/花纹只在包围盒内求值（part_mask）、众数色打包整数、lattice_points/jitter 向量化、盒搜索向量化（与参考回溯同 DFS 序同预算记账，_search_ref 留作对拍）+ 同格组盒可行性精确预判（无解直接跳过回溯）、cellpack 用局部 FFT 互相关预筛 + 轮廓交表缓存。
  输出逐字节不变（快照哈希 2a77adfa… 前后相同）。render_ms@96（bench 固定 3 件）旧 ~1.4 / ng ~1.9（1.3–1.45×）；R2@96_200 协议逐题均值 旧 1.10 / ng 2.09 ms（p95 5.4，打包题 5–9 ms）；R2@48_200 旧 0.37 / ng 0.81。
