# VSA 正文日期 BD · dev 读数（PREREG_body_date §2）

## E1 VSA 检索 r@10（BD 排序须逐位 ≡ L1）

| 集 | 题数 | L1 | BD | 胜/负/平 | 逐题全等 | L1 ≡ 已提交 long_* |
|---|---:|---:|---:|---|---|---|
| locomo | 257 | 0.5042 | 0.5042 | 0/0/257 | 是 | 是 |
| hive | 46 | 0.4551 | 0.4551 | 0/0/46 | 是 | 是 |
| perltqa | 3956 | 0.9737 | 0.9737 | 0/0/3956 | 是 | 是 |
| crossproj | 41 | 0.6463 | 0.6463 | 0/0/41 | 是 | 是 |

## E2 时间题解绑

| 集 | 题数 | L1 | BD | McNemar BD 胜/负 | p | 预测全等 | BD 来源 |
|---|---:|---:|---:|---|---:|---|---|
| locomo | 50 | 0.5600 | 0.5600 | 0/0 | 1 | 是 | {'TIME': 45, 'SESSION': 5} |
| perltqa | 54 | 0.3333 | 0.3148 | 2/3 | 1 | 否 | {'TIME': 46, 'TIME:bd': 8} |

PerLTQA 时间题按证据单元里金标位置分型（`proposals/body_date_diag.py` 口径）：

| 分型 | 题数 | L1 对 | BD 对 | L1 对→BD 错 |
|---|---:|---:|---:|---|
| absent | 4 | 0 | 0 | 无 |
| body | 4 | 1 | 2 | 徐佳#dialogues#145 |
| first | 20 | 17 | 15 | 冯伟#events#191, 韩刚#events#80 |
| uncanon | 26 | 0 | 0 | 无 |

perltqa 预测改变的题（逐题）：

- `冯伟#events#191`（first；金标 DATE:2022-03-10）：L1 DATE:2022-03-10（对）→ BD YEAR:2019（错，TIME:bd）
- `孙晓明#dialogues#149`（body；金标 YEAR:2019）：L1 DATE:2019-08-15（错）→ BD YEAR:2019（对，TIME:bd）
- `徐佳#dialogues#145`（body；金标 YEAR:2015）：L1 YEAR:2015（对）→ BD YEAR:2020（错，TIME:bd）
- `田洋#dialogues#210`（first；金标 DATE:2022-05-02）：L1 DATE:2021-06-12（错）→ BD DATE:2022-05-03（错，TIME:bd）
- `许慧#dialogues#261`（uncanon；金标 None）：L1 DATE:2022-05-12（错）→ BD DATE:2019-05-06（错，TIME:bd）
- `韩刚#dialogues#198`（body；金标 DATE:2019-05-10）：L1 DATE:2019-05-15（错）→ BD DATE:2022-01-17（错，TIME:bd）
- `韩刚#events#80`（first；金标 DATE:2021-05-12）：L1 DATE:2021-05-12（对）→ BD DATE:2022-01-17（错，TIME:bd）
- `龙美丽#events#47`（body；金标 YEAR:1503）：L1 DATE:2019-06-15（错）→ BD YEAR:1503（对，TIME:bd）

## E3 描述性

| 集 | 单元 | 长单元 | BD 启用单元 | 子痕迹 | 子痕迹最大项数 | 类型 |
|---|---:|---:|---:|---:|---:|---|
| locomo | 5882 | 0 | 0 | 0 | 0 | {} |
| hive | 303 | 0 | 0 | 0 | 0 | {} |
| perltqa | 1042 | 346 | 63 | 1167 | 130 | {'anchor': 159, 'inherit': 978, 'mid': 30} |
| crossproj | 652 | 0 | 0 | 0 | 0 | {} |

## §2 dev 门槛

- 显著倒退：无；E1 四集逐位相同：是；
- PerLTQA first 类：L1 17/20 → BD 15/20；L1 对→BD 错：['冯伟#events#191', '韩刚#events#80']；
- 判定：**dev 不合格 ⇒ 不跑保留集，维持 L1**。
