# C1-R25 程序化多尺度组织微纹理设计

日期：2026-08-09（任务 T-002）
基线：R19 干净基底（branch `codex/dataimprove-c1-r19-triplanar-continuity`，commit `80bdd8c74dece2a514be8485868e7b6a3ae59495`，F-GIT-005）
文献：`R25-LITERATURE.md`（同目录；条目引用记为 R25-LIT-XX）
语言契约：本文与后续 R25 报告一律中文；代码注释与标识符一律英文（C-F010 事故教训）。

## 1. 目标与假设

R24 已证明：精选真实样本源在连续性上可过关，但其空间多样性受限（60 个注册视图内 3 对近重复，masked MAE 6.2–6.9；数值出自 D-004 工件，状态项 F-EXP-011 与 C-F009 指向该工件）。R25 检验与其正交的下一代假设：

> 以三维 canonical 物体空间中的连续程序化多尺度场（R25-LIT-01/02/04/08）替代真实像素来源作为逐顶点颜色生成器，能否在完全不依赖真实像素的前提下，得到连续、有多尺度结构、且候选间可区分的组织样表面外观。

动机（仅动机，非结论）：ImageNet 训练的分类 CNN 主要依赖纹理统计（R25-LIT-11，证据域即此、措辞限"提示"）；域随机化表明非写实参数化纹理族可支撑迁移（R25-LIT-12/13）；腹腔镜合成数据路线成立，但在该论文的演示中朴素渲染外观单独不足、需额外增真步骤（R25-LIT-15）；自然纹理的本质是跨尺度相关结构而非单带噪声（R25-LIT-16）。

R25 与 R23（血管专精）、R24（真实样本专精）互为 R19 的并列兄弟路线（F-GIT-008），不继承二者任何专精化改动。"组织样（tissue-like）"在全文中只是工程描述词，不构成任何生理学或医学真实性主张。

## 2. 单变量契约

**唯一变量：逐顶点颜色的生成函数。** R19 用"三平面投影采样真实 atlas"；R25 用"连续程序化多尺度场直接求值"。其余一切冻结（见第 3 节）。四个变体共享同一渲染与序列化路径，仅生成函数的参数不同；`base` 变体即振幅为零的退化情形。

**明确排除**（违反即终止）：
- patch/exemplar 拼贴（quilting 等）与任何真实像素的空间映射（C-F004、C-F009 教训；T-005 禁令 patch_tiling / real_pixel_spatial_mapping）；真实数据只允许以冻结聚合统计形式出现（仅第 3.6 节的基色均值）。
- R23 血管要素（add_r23_vessels 禁令）。
- UV 参数化（C-F003；R25-LIT-08 支撑物体空间路线）。
- 逐顶点表示之外的第二变量（网格细分、逐像素 shader、采样密度变更——R19 结果文档已把采样密度列为日后独立变量）。

## 3. 冻结项（逐项锚定）

继承 R19 screen-v1 已验收契约（`D:\MedSim2Learn-C1-verification\r19-triplanar-continuity\screen-v1\`，receipt/inputs/validation 与 artifact-hashes.json 为锚）：

| 冻结项 | 取值 | 锚定证据 |
|---|---|---|
| 几何 canonical | 2,005 vertices / 4,006 faces | inputs.json `canonical_file_sha256 = f0a301cf143fcb12b4a92ef6ca8ce326b45a71e393d7f18c806cc4802c5e3e2d` |
| 几何 deformed | 同拓扑冻结实例 `deformed-s0521-v0000` | inputs.json `deformed_file_sha256 = 82915fe9e0eb1f7e7dec6f29c195fb7ec361fbace55d32f21a80ef601e099493` |
| 相机 | R19 五机位注册表不动；预览取子集 `z-plus`、`iso-plus` | inputs.json `camera_names` |
| 渲染器与光照 | Open3D legacy renderer，无光照（unlit），R19 同路径同参数 | R19 设计文档"无光照 renderer"；C-F007（R23 光照不回流 R25） |
| 背景与深度 mask | 与 R19 逐像素一致 | mask 哈希四联：canonical/z-plus `5cdcfe8f818de089018a95fe50730d41923a8ee26755dc827c84429016d5e33d`、canonical/iso-plus `8d4f75d71240cbb56ff1e99da76cd9d95ef2288f7fa1f03d581ac5323bdece30`、deformed/z-plus `7ef2dea7d1725b6fdf537d217c3ae351b4406c593642c3a045e4b4e2dcb76b48`、deformed/iso-plus `1f87171958c394beb44a2b2add57afeb8b55334b24eaef58fde35d3758c123ad` |
| 分辨率 | 512×512 PNG | R19 renders/masks 实测 IHDR |
| 映射路径 | 逐顶点颜色场 + 三角形线性插值；deformed 逐字节复用 canonical 颜色（`reuse_exact_canonical_bytes`） | inputs.json `mapping_space=canonical` |
| 归一化坐标系 | 包围盒中心 + 单一最大边长等比缩放（R19 同式） | R19 设计文档第"方法"节 |
| 并行度 | 串行，worker_count = 1 | R19 契约 + C-F011 |
| 基色 base_rgb | 冻结常量；派生规则见 3.6 | vertex-colors.npy `af2c92d61b73cf34e3802beef7b85f95cd63b4b47e2d3fb5242dd0d17b20474b` |

### 3.6 基色派生规则（冻结聚合统计，非空间映射）

`base_rgb = round(mean_{v=1..2005}(R19 vertex-colors.npy))`（逐通道，8-bit）。该 npy 是 R19 已验收工件（哈希如上）；均值是聚合统计，符合 `fable5_policy.allowed_default_data` 的 frozen_aggregate_statistics，不构成真实像素空间映射。数值在 T-005 实现时计算一次，写入 receipt 与 manifest；四个变体共用同一 base_rgb，整轮不得更改（change_base_colour 禁令）。

## 4. 方法定义（诚实命名）

方法名：**per-vertex sampled procedural volumetric microtexture field**（CPU、canonical 归一化空间逐顶点求值）。它不是逐像素 shader 求值的 solid texture，也不是 Gabor 噪声实现（R25-LIT-06 仅作原理引用）；命名在代码与报告中保持一致，不得夸大（R19 命名纪律的延续）。

### 4.1 场构造

基元：改进型梯度噪声（R25-LIT-01/02；quintic 淡入为其标准实现形式，作为实现惯例采用），fBm 逐倍频程求和（结构依 R25-LIT-04）。**数值参数 lacunarity = 2、gain = 0.5 与振幅 a = 0.20 均为本项目工程适配（adaptation）之冻结值：R25-LIT-04 仅在目录级支撑 fBm 逐倍频程结构本身，不为任何具体数值背书。** 纯 NumPy 哈希置换表实现，不引入新依赖。对每个 canonical 顶点归一化坐标 p 求标量场 n(p)，随后：

1. 去均值：n ← n − mean(n)（在 2,005 个顶点上）；
2. 归幅：n ← n / max|n|，使 n 张满 [−1, 1]（逐变体、确定性）；
3. 上色：`colour(v) = clip(round(base_rgb · (1 + a·n(v))), 0, 255)`，振幅 **a = 0.20** 三个候选共用；
4. deformed 网格逐字节复用 canonical 颜色（同一性契约与 R19 相同，由构造保证）。

`base` 变体：a = 0，即全部顶点恰为 base_rgb。

### 4.2 频带约束（采样密度的诚实上限）

网格仅 2,005 个顶点采样，可表示的最细波长受限。硬约束：**受检尺度集合内所有 λ ≥ λ_floor = 2 × median(canonical 边长，归一化)**。受检尺度集合逐项写死：candidate-1 {0.64, 0.32, 0.16}；candidate-2 主场 {0.48, 0.24, 0.12} 与扭曲场 {0.50, 0.25}；candidate-3 fBm {0.64, 0.32, 0.16} 与细胞尺度 d_cell = 0.09。λ_floor 在实现时实测并写入 receipt（预估约 0.06，须以实测为准）；集合内任一元素违反即机械门失败。诚实注记（同样写入 receipt）：域扭曲复合会抬高有效带宽，λ 记账仅指成分尺度，最终由 λ_floor 与视觉门共同约束。更细颗粒超出本轮范围——与 R19 结果文档"采样密度是日后独立变量"的裁定一致。

### 4.3 三个候选（参数即冻结值；数值属工程适配，标注为 adaptation）

| 变体 | 构造 | 倍频程波长（归一化） | 种子 |
|---|---|---|---|
| candidate-1 粗斑驳 | fBm，3 octaves | {0.64, 0.32, 0.16} | 20260809 |
| candidate-2 域扭曲多尺度 | fBm，3 octaves，单步域扭曲 f(p + h(p))，h 为 2-octave 向量 fBm（λ {0.50, 0.25}），扭曲强度 0.08（归一化单位） | {0.48, 0.24, 0.12} | 主场 20260810 / 扭曲场 20260812 |
| candidate-3 颗粒混合 | 0.65·fBm{0.64, 0.32, 0.16} + 0.35·W；W = 2·(1 − min(F1/d_cell, 1)) − 1，Worley F1 特征点按 d_cell 网格哈希抖动布点，d_cell = 0.09 | 见构造 | 20260811 |

依据：fBm 结构 R25-LIT-04；域扭曲存在性 R25-LIT-04（目录级 "Domain Distortion" 小节）、具体构造 R25-LIT-09（`[TECH-REF]`，非同行评审，已在台账如实标注）；细胞基元 R25-LIT-05。三候选共用同一振幅与同一上色式，可区分性只能来自谱结构差异——这保证比较是单变量族内比较。所有种子、波长、权重为冻结值（数值均属工程适配）；实现不得调参（调参 = 新版本 + 新设计文档）。

## 5. 十六图预览契约（精确）

输出根：`<verification>/r25-procedural-tissue-microtexture/development-preview-v1/`（verification 根按 STATE.yaml `roots.verification` 解析）。

**clean/ 目录恰好 16 张 512×512 PNG，公式 4 变体 × 2 网格 × 2 视图，全名枚举：**

```
clean/base__canonical__z-plus.png
clean/base__canonical__iso-plus.png
clean/base__deformed-s0521-v0000__z-plus.png
clean/base__deformed-s0521-v0000__iso-plus.png
clean/candidate-1__canonical__z-plus.png
clean/candidate-1__canonical__iso-plus.png
clean/candidate-1__deformed-s0521-v0000__z-plus.png
clean/candidate-1__deformed-s0521-v0000__iso-plus.png
clean/candidate-2__canonical__z-plus.png
clean/candidate-2__canonical__iso-plus.png
clean/candidate-2__deformed-s0521-v0000__z-plus.png
clean/candidate-2__deformed-s0521-v0000__iso-plus.png
clean/candidate-3__canonical__z-plus.png
clean/candidate-3__canonical__iso-plus.png
clean/candidate-3__deformed-s0521-v0000__z-plus.png
clean/candidate-3__deformed-s0521-v0000__iso-plus.png
```

计数规则：**只有 `clean/` 下的文件计入 16**。`fields/`（逐变体标量场与顶点颜色 npy）、`masks/`、`controls/`、`diagnostics/`（对比页、径向功率谱图、MAE 表）均不计入。验收 token 映射：`z_plus↔z-plus`、`iso_plus↔iso-plus`、`candidate_1↔candidate-1`（余类推）；`base` 即对照变体。

闭合与写序：`receipt.json`（schema `c1-r25-preview-v1`）记录全部冻结参数与种子、base_rgb 及其派生输入哈希、λ_floor 实测值、受检尺度集合、输入网格/相机锚定哈希、Open3D 版本串、RSS 峰值、串行时序，先行写入；`manifest.json` 最后写入，覆盖输出树内除其自身外全部文件的 sha256（manifest 不含自身哈希）。no-clobber：目标路径已存在即拒绝写入；诊断后重跑只允许新建 `development-preview-v2`（C-F010 纪律）。

## 6. 机械门（T-005 自验 + T-006 复验）

- M1 计数与命名：clean/ 恰 16 文件且逐名等于第 5 节枚举；全部可在原始分辨率解码。
- M2 网格守恒：两网格 2,005 vertices / 4,006 faces；输入哈希等于第 3 节锚定值。
- M3 同一性契约：canonical/deformed 逐拓扑对应顶点颜色逐字节一致（4 变体各自成立）。
- M4 连续性（继承 R19）：全部 6,009 条共享边端点颜色零失配。
- M5 mask 冻结证明：(a) R25 每 (网格,视图) 深度 mask 与第 3 节四个 R19 mask 哈希逐一相等；(b) 真背景一致性——以 mask 经 1 像素 8-邻域膨胀后的补集为真背景区，真背景区内所有像素等于渲染路径固定清屏色（实测 (5,5,5)，rerun receipt 复记）且与 R19 对应渲染逐像素一致；(c) 1 像素轮廓圈（膨胀区减 mask 前景）不参与背景比较——legacy 渲染器在轮廓处以前景色覆盖 RGB 而深度为 0，R19 自身四视图渲染在该圈内各有 89/82/86/85 个前景色像素，其取值随顶点色场变化，属渲染器固有行为而非受试变量（v4 修订，一手证据见修订记录）。
- M6 base 精确性：base 变体所有顶点恰为 base_rgb。
- M7 均值保持：每候选渲染前顶点颜色逐通道 |mean(colour) − base_rgb| ≤ 2.0（单位：8-bit 灰度级）。
- M8 振幅界：每候选逐顶点 |colour − base_rgb| ≤ ceil(0.20·base_rgb) 逐通道。
- M9 确定性重放：同种子重算场与顶点颜色，npy 哈希逐字节复现。
- M10 频带下限：§4.2 受检尺度集合（含 candidate-2 扭曲场尺度与 candidate-3 的 d_cell）内所有 λ ≥ λ_floor（实测记录于 receipt）。
- M11 资源门：串行；psutil 进程树 RSS 采样峰值 < 500,000,000 字节（C-F011；R19 先例 232.6 MB，须实测不得引用先例充当证据）。
- M12 可区分性预门（工程适配，最终裁定权在视觉门 V3）：对 6 个变体对（3 个候选互对 + 3 个候选对 base），在 4 个 (网格,视图) 组合上**各自**计算 masked MAE——前景像素集取第 3 节对应冻结 mask；逐像素三通道绝对差先对通道取均值、再对前景像素取均值；单位 8-bit 灰度级——共 24 个数值，要求全部 > 4.0（等价表述：每对在 4 个组合上的最小值 > 4.0）。阈值 4.0 的依据（设计自估，同属 adaptation）：一方面高出量化/重渲噪声地板（同图重渲 MAE ≈ 0）一个数量级以上；另一方面低于设计期望值——按 a = 0.20、max 归一 fBm 的 E|n| ≈ 0.25–0.35 估算，base-对-候选期望 MAE ≈ 5.5–6.9、候选互对 ≈ 7.8–9.7（插值渲染略降），留有余量，实测 24 值全部写入 diagnostics 供 T-006 与期望对照。R24 近重复带 6.2–6.9（D-004）仅作叙事背景：跨渲染管线的绝对数值不可移植，不构成本阈值依据。
- M13 闭合：manifest 全覆盖、receipt 字段齐全、无覆写事件。

## 7. 视觉门（T-006 执行，T-007 独立复核；一律原始分辨率）

- V1 连续性：16 图无接缝、条带、砖块/chart 边界、孤岛色块、断裂污渍（R19 判词表）。
- V2 结构保持：器官整体形态不被纹理破坏（mask 相等已保证轮廓；此处审内部结构）。
- V3 可区分性：三候选彼此、以及与 base，肉眼可分。
- V4 多尺度连贯性：候选呈现 ≥2 个尺度的连贯结构而非无结构噪声（判据为视觉;`diagnostics/` 的径向功率谱仅作辅助诊断,不作为通过判据——R25-LIT-16 边界）。
- V5 组织样性（工程语义）：斑驳/颗粒观感处于组织样范围，不得出现明显人工周期性或轴向伪影。

## 8. TDD 契约（T-005 强制）

先写红测试并存档 junit，再实现转绿；红/绿 junit 均入 `<verification>/r25-procedural-tissue-microtexture/tests/`（命名沿用 r25-core-red-v1-junit.xml / r25-core-green-v1-junit.xml 等既有式样）。红测试至少覆盖：M3/M4/M6/M7/M8/M9/M10 的纯函数层、M1 命名公式、no-clobber 拒绝行为、RSS 采样接线。实现代码只进 r25 worktree 的 `Deform_post` 研究工具区（复用 R19 c1 渲染/序列化 harness，仅替换颜色源阶段——AGENTS 复用纪律），不触碰 dpost 产品包。

## 9. 停止条件（显式；触发即停，按 C-F010 纪律记录检查点后待人裁）

1. 机械门 M1–M11、M13 任一失败 → 终态 `R25_INVALID_OR_FAILED`（M12 不适用本条，其归属见第 3 条）。
2. V1 或 V5 失败（接缝/条带/砖块/孤岛/断裂污渍，或明显人工周期性/轴向伪影）→ `R25_CONTINUITY_FAILED`。
3. V3 失败，或 M12 预门未达且 V3 原始分辨率复核确认同质 → `R25_DIVERSITY_LIMITED`（对应 R24 式受限关闭）；若 M12 未达而 V3 判定可分，如实记录分歧并以 V3 为准（预门定位即止于预门）。
4. V2 或 V4 失败（器官整体结构被破坏，或呈无结构噪声）→ `R25_STRUCTURE_UNSTRUCTURED_FAILED`。
5. 运行中进程树 RSS ≥ 500,000,000 字节 → 立即中止运行，记录资源检查点（C-F011 同类），终态 `R25_INVALID_OR_FAILED`；不得改并行度重试。
6. 安全路由/拒绝事件 → 按 C-H003 序列处理并保存为过程检查点，禁止任何规避性改写；本条不单独构成 R25_* 终态。
7. 未诊断根因不得重跑；所有失败工件 no-clobber 保留（C-F010 纪律；过程检查点，不单独构成终态）。

唯一成功终态：`R25_MICROTEXTURE_ELIGIBLE`（M1–M11、M13 与 V1–V5 全过，且 M12 通过，或 M12 未达但已按第 3 条如实记录分歧且 V3 原始分辨率判定可分）。

## 10. 主张边界（本轮成立与不成立的话）

即使全部通过，R25 也**只**支持："在冻结的 R19 几何/相机/背景/光照/基色与当前 2,005 顶点采样密度下，程序化多尺度微纹理三候选在两个注册视图内连续、具多尺度结构、且彼此及与对照可区分。"

**不支持且不得声称**（对齐 STATE.yaml claim_boundary.unsupported 与 F-EXP-012/013）：
- 外观差距（appearance gap）缩小；
- 任何训练收益；
- 医学或生理学真实性（"tissue-like" 仅为工程描述词）；
- 超出两个注册视图与当前采样密度的泛化。

本轮不做 gap 比较、不做训练、不做数据集生成；那些属于后续任务并各有人工闸门。

## 11. 角色、路径与后续闸门

- 本设计（T-002）→ 独立反幻觉评审（T-003，review 角色）→ **人工批准 T-004**（设计 + 同盘兄弟 worktree + 分支/基点冻结：`codex/dataimprove-c1-r25-procedural-tissue-microtexture` @ `80bdd8c74dece2a514be8485868e7b6a3ae59495`，目录按 STATE.yaml `roots.r25`）→ 实现 T-005（仅 r25 worktree）→ 验证 T-006 → 独立终审 T-007 → **人工提交闸门 T-008** → 收口 T-009。
- T-004 之前不存在任何 worktree/分支创建；设计批准不等于提交批准（T-008 独立）。
- 全程 git 写操作人工独占；本设计文档自身不构成任何 git 授权。

## 12. 修订记录

- v1（2026-08-09T18:45 前后）：初版。
- v2（2026-08-09，响应 T-003 评审 NEEDS_REVISION）：
  1. M7 阈值改为明确的 8-bit 灰度级表述（≤ 2.0 灰度级）——修复 Important-1。
  2. M12 写死"每对 × 每组合共 24 项、全部 > 阈值"的口径——修复 Important-2；并在复核可行性时发现原 8.0 阈值在本管线期望量级（a=0.16 时 base-对-候选期望 MAE ≈ 5.5）下会误杀健康结果：振幅调整为 a = 0.20、阈值调整为 4.0，依据改为管线自估期望与噪声地板（附推导数字），R24 数值降级为叙事背景。此为实质性参数变更，已提交 T-003 复审。
  3. §4.1 为 lacunarity/gain/振幅落 adaptation 标注，R25-LIT-04 引注限定为结构级——修复 Important-3。
  4. 自查修复：原停止条件 1 与 3 对 M12 归属矛盾（1 兜底"任一机械门失败→INVALID"与 3 的"预门失败→受限终态"冲突），现将 M12 移出条件 1；V2/V5 原无终态映射，现并入条件 2/4，使全部视觉门显式闭合到终态。
  5. Minor 修复：§1 补"ImageNet 训练的"限定与"在该论文演示中"限定、R24 数值改注 D-004；§4.2 写死 M10 受检尺度集合并加带宽诚实注记；§5 写死 receipt/manifest 写序与自指排除；§4.3 域扭曲补 R25-LIT-04 目录级存在性依据。
- v4（2026-08-09，响应 T-005 实现停机报告）：M5 原第二子句"背景像素与 R19 渲染逐像素一致"被证明结构性不可满足——T-005 三重一手证据：(i) 实现方渲染的深度 mask 与四个 R19 冻结 mask 逐字节相同（几何/相机/渲染路径/环境复现无误）；(ii) 差异像素恰全部位于轮廓 1 像素圈内（canonical/z-plus 为 89 个），取值随前景色场变化；(iii) R19 自身四张冻结渲染在同一圈内本就各有 89/82/86/85 个非清屏色像素——legacy 渲染器在轮廓处覆盖 RGB 而深度为 0，故该子句对任何颜色场不等于 R19 的变体（含 base）恒假。v4 将 M5 改写为 (a) mask 哈希相等 + (b) 真背景区（mask 1 像素膨胀之补集，共 234,537 像素与 R19 完全一致的区域）等于清屏色且与 R19 逐像素一致 + (c) 轮廓圈豁免。实验变量、冻结项、参数、16 图契约与主张边界零变化；本修订经 T-003 评审确认后 T-005 方可续跑。
- v3（2026-08-09，响应 T-003 复审 v2）：
  1. 修复 v2-I1：成功终态公式与停止条件 3 的 V3 覆写条款同步——`R25_MICROTEXTURE_ELIGIBLE` 改为"M1–M11、M13 与 V1–V5 全过，且 M12 通过，或 M12 未达但已记录分歧且 V3 判定可分"，消除"M12 未达且 V3 可分"状态的终态真空。
  2. 修复 v2-M3：§6 M10 措辞同步为"§4.2 受检尺度集合"。
  3. v2-M1/M2（M12 推导中 max/σ 归因与区间传播的两处注记）按复审意见 record-only，正文不动，以 R25-DESIGN-REVIEW.md 第 9 节为准。
