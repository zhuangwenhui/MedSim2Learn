# C1 外观域随机化设计（Track C / H1a，试点先行）

日期：2026-08-10
上游依据（均为已提交裁定，本文只做实例化）：`95b765f` 的
`experiments/2026-07-03_windows-render-diversity/PLAN.md` §2-C1 与
`DATA_SIDE_HANDOFF.md` §3/§4/§6-C1；2026-06-22 渲染 DR 规格（legacy 可行域）；
R25 路线结果（`9c74cf0`，程序化多尺度顶点色场，ELIGIBLE）。
前置：F1/F2/F3 三修已在本分支落地并通过 seq01 全序列字节校验。

## 1. 目标与验收

打破"灰白模"捷径：仅随机化外观（C1 单因子隔离），其余一切不动。基线对照
（2026-08-10 新鲜缓存实测）：线性可分性 1.0000、分离比 3.708、合成 RMS 1.249
（真实 7.642）、质心距 16.484。验收阶梯：
1. 机械：OFF 时字节级不变（沿 F 修的 parity 关卡）；ON 时 F1 空白守卫、F3 对账、
   `.pt` 契约全数通过；种子全记录。
2. 服务器度量：DR 变体数据集重抽特征后 `analyze_domain_gap.py` 的可分性 < 1.0000
   且合成 RMS > 1.249（方向性要求，无数值承诺）。
3. 训练级（后续独立步骤）：c2 式 synth-only 训练在真实测试上的 gap-closed %。
主张边界：可分性下降不等于迁移收益；任何 gap-closed 声明只能来自第 3 级。

## 2. 随机化域（legacy Visualizer 可行集，逐项 config 门控）

`DiversityConfig.appearance`（新增 dataclass 段，默认 enabled=False，OFF 即旧行为）：

| 旋钮 | 定义 | 范围（工程适配，冻结） |
|---|---|---|
| organ_mode | `uniform` 或 `r25_field` 二选一（按序列随机） | 概率 uniform 0.3 / r25_field 0.7 |
| uniform 色 | 肾样 albedo RGB | R∈[0.45,0.62], G∈[0.28,0.42], B∈[0.30,0.44] |
| r25_field | R25 场族逐顶点色（candidate-1/2/3 等概率），基色取 uniform 色域随机样 | 振幅 a∈[0.15,0.30] |
| background | 远离纯白的腔体色 | R∈[0.10,0.35], G∈[0.04,0.22], B∈[0.05,0.24] |
| 后处理链 | 捕获后、写盘前的 numpy 逐帧处理：亮度×[0.85,1.15]、对比×[0.85,1.15]、gamma∈[0.8,1.25]、暗角强度∈[0,0.35]、高斯噪声 σ∈[0,0.012] | 逐帧种子抖动 |
| 光照 | **不随机**（legacy 无法随机方向/强度，2026-06-22 已裁定不可行；light_on=True 原样） | — |

- R25 场求值：序列首帧顶点做 bbox-center/max-extent 归一化后求值一次，同拓扑
  逐帧复用同一组颜色字节（同一性契约，纹理不"游泳"）；模块复用 `9c74cf0` 的
  `dpost/c1_r25_procedural_microtexture.py`（本分支已并入），不复制代码。
- 标签安全：只动像素。相机、几何、力、SampleID、配对链零接触；几何增广禁止。

## 3. 种子与溯源

每序列主种子 `seed_seq = SeedSequence([diversity.seed, seq 序号])`；spawn 出
organ/background/后处理三条子流。全部抽样值（模式、颜色、a、变体名、逐帧后处理
参数的种子）写入该序列 `replay_meta.json` 的 `appearance` 段（PLAN §4 溯源要求）。

## 4. 试点先行（本轮范围）

1. 实现 + 测试（TDD；OFF-parity 用既有 F 套件模式）。
2. 试点渲染：仅 seq01，三个不同主种子各出一版（800px 全序列 + 256px 序列化到
   scratch），产出 3×6 帧蒙太奇对比页（含基线白模一行）供人工检视。
3. **人工检视门（用户）通过前，不做 31 序列全量、不上传服务器。**
   全量与上传按 DATA_SIDE_HANDOFF §8 合格数据五关 + PLAN §4 清单执行，
   目标域名 `preprocessed/sources/synt/dr-c1-v1/`。

## 5. 排除与不做

不做 C2 视角、C3 接触点（后续单独隔离）；不做 OffscreenRenderer/PBR 迁移（仅当
C1 平坦着色的隔离增益证明不足时再议）；不做训练期光度增广（已判 LOSE）；不做
任何力生成；不改 `.pt` 契约。
