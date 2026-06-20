# Research Goal — Sim2Real FEM-Augmented Video→Force Prediction

> **本文档是项目的"北极星"(north star),长期回看 + 持续更新。**
> 它的唯一职责:在漫长、反复 compact 的对话中**防止科研目标漂移**。
> 任何一次会话开始、或 compact 之后,**先读本文档**,再决定下一步。
> 详细的外观域差诊断见姊妹文档 `RESEARCH_DIRECTION.md`(2026-06-16,本文不重复)。
>
> **维护契约(给未来的我):** 每完成一个实验或做出一个方向决定,更新 §7 状态快照
> 与 §9 决策日志;改动 RQ / 假设 / 路线图时同步本文。结论必须有一手证据(命令输出 /
> 生成的 JSON / 图),不得凭记忆断言(见根 `CLAUDE.md` 的 Verification 规则)。
> 用户最终用途:实验结果要有 matplotlib 可视化,可直接进 PPTX 汇报(见 §9)。

Last updated: 2026-06-21 · Owner: WENHUIZ · Status: planning → Phase 0 (measurement fix)

---

## Table of contents
1. [Mission(北极星)](#1-mission)
2. [Task spec(任务定义)](#2-task-spec)
3. [Data(数据现状)](#3-data)
4. [Research questions(RQ1–4,对应用户四目标)](#4-research-questions)
5. [Root-cause hypothesis tree(根因假设树)](#5-root-cause-hypothesis-tree)
6. [Technical stack(文献支撑的技术栈)](#6-technical-stack)
7. [Status snapshot(当前状态 / 已知结论)](#7-status-snapshot)
8. [Experiment roadmap & decision gates(路线图)](#8-experiment-roadmap)
9. [Visualization & reporting convention(可视化规范)](#9-visualization)
10. [Reference library(文献库)](#10-reference-library)
11. [Decision & update log(决策日志)](#11-decision-log)

---

## 1. Mission

用一条 **FEM 合成数据管线**(ShapeReconstruction → DeformSim → Deform_post)放大稀缺的真实
数据,训练出能在**真实内窥镜视频**上准确预测手术钳对肾脏施加的 **3D 力向量**的模型。
终极探问:**能否像 scaling law 那样,通过合成"合适且足量"的 FEM 数据,稳定提升真实域表现?**

成功判据(本项目意义上的"做成了"):
- 在真实测试集上,某个"合成增强"配方**显著且可复现地**优于"仅真实从头训练"(c1)基线;
- 给出 error-vs-(真实样本数 / 合成样本量 / 混合比例)三条曲线,刻画合成数据的价值与饱和点;
- 全程数值 + 图像结果留痕,权重可复现评估。

---

## 2. Task spec

- **输入:** 内窥镜**视频片段**(时序列已是标配,不再是单帧)。
- **输出:** 连续 **3D 力向量**(幅值 magnitude + 方向 direction)。
- **评估面板(原始未归一化力):** magnitude MAE / MRE / Acc@10%、mean angle error、
  angle accuracy@5°、逐轴 x/y/z MAE;序列模型加 temporal RMSE。
- **当前模型:** ConvNeXt-Large(ImageNet 预训练,197M)+ TCN/MLP 力回归头。

---

## 3. Data

- **真实数据:** 猪肾,手术钳施力,内窥镜视频,**稀缺(~31 序列)**;力为传感钳读数(原始值)。
- **合成数据(数字孪生):** CT 重建肾表面 mesh → 四面体化 → 设为弹性体 → 选中顶点附近施加
  力向量 → FEM 求解形变 → 渲染视频。当前是 **31 条真实序列的 1:1 孪生回放**(力 = 真实
  传感力旋转进 mesh 系,**力分布天然匹配真实**),不是大规模随机合成器。
- **数据布局:** 见根 `CLAUDE.md` 的 `DataFlow/Deform_post` 四层结构 + `DataFlow/KiDKNet`。
  KiDKNet 用 ConvNeXt 特征缓存 + 5-fold CV split(`splits/cv5`,seed 42,按 id 配对、防泄漏)。

---

## 4. Research questions

直接映射用户设定的四个科研目标(+ scaling-law 探问):

| RQ | 用户目标 | 一句话问题 | 主战场 |
|---|---|---|---|
| **RQ1** | 目标1 | 合成数据的**多样性**(视觉/形变/相机)能否提升当前架构的真实域表现? | 数据侧 §5-H1/H2/H3 |
| **RQ2** | 目标2 | 什么**训练方式**能最有效联合利用合成管线 + 真实数据? | 训练侧 §6.5 |
| **RQ3** | 目标3 | 是否需要**改造损失函数**(幅值/方向解耦、不确定性加权)提升性能? | 损失侧 §6.5 |
| **RQ4** | 目标4 | 哪种 **transformer-based / VLM 架构**更适合本任务,且最大化利用合成+真实? | 架构侧 §6.2 |
| **RQ★** | 附加 | 能否拟合**合成数据 scaling law**(error vs 合成量/多样性/混合比)指导"造多少、造什么"数据? | 全局 §8 |

**重要排序原则(来自已有实验,见 §7):** 现在测量噪声 > 除域差外的所有效应,
所以 **RQ 的回答必须先建立在"可测量"之上(Phase 0)**;架构(RQ4)放最后做。

---

## 5. Root-cause hypothesis tree

用户提出"孪生数据不够孪生"的四个环节问题 + 我们补充的测量前置问题。每条都需**独立验证**。

```
真实域表现差
├─ H0  测量不可信(val=3序列→best-epoch抖动;无增广→过拟合;力未归一化)  ← 先修
├─ 孪生不够孪生(domain gap)
│  ├─ H1 [SR]  mesh 拓扑/四面体化病根 + "白模"无纹理颜色 → 视觉外观差(已证:外观差为主因)
│  ├─ H2 [DeformSim] FEM 假设过naive(线弹性、无被膜、无粘弹)→ 形变物理失真
│  └─ H3 [Deform_post] Open3D 相机位姿 ≠ 真实术野视角 → 视觉分布偏移
└─ H4 [Architecture/Loss] CNN+TCN 未必最优;损失未针对3D力向量设计
```

各假设当前证据强度(详见 §7):
- **H1(外观差)= 已证、是主因。** 线性探针 100% 可分真假;synth 特征多样性 ~6× 低于真实。
  其中"白模无纹理"已确证;"mesh 拓扑/四面体病根"**尚未单独验证**(需 §8 Phase 4 检查 tet 质量)。
- **H0(测量噪声)= 已证。** c1 fold std ±0.073(均值的 ~31%)> 所有跨条件差;best-epoch 在
  folds 间跳 1/6/10/25。
- **H2(FEM naive)= 合理但未验证。** 力分布已匹配真实,故 H2 不是力的问题,而是**形变形态**
  问题(可能影响视觉形变线索);需对照真实形变量化(§8 Phase 4)。
- **H3(相机)= 合理但未验证。** 需对照真实术野相机外参/视角分布(§8 Phase 4)。
- **H4(架构/损失)= 暂不是瓶颈。** 两个差异极大的架构(端到端 ConvNeXt-L vs 冻结特征+TCN)
  给出**相同**真实分数(0.234 vs 0.232)与**相同** sim2real 悬崖(1.542 vs 1.357)→ 架构族不是
  约束。**但损失(RQ3)是低成本、可早做的正交改进。**

---

## 6. Technical stack

文献支撑(完整引用见 §10)。每个决策标注首选方案与 [ADOPT/CONSIDER] 来源。

### 6.1 任务基线与定位(必引对照)
- **必比基线:** 同器官同设置的 **Scientific Reports 2024 猪肾力预测**(VGG-16,单帧,3D力,传感钳标注)。
  我们的差异化卖点:**3D 向量 + 视频时序 + sim2real**。
- **视频→力时序基线:** Marban 2019(CNN+LSTM)、**DaFoEs ICRA2024**(混合多数据集→相对误差降到~5%,
  backbone/时序头消融模板)、2026 small-bowel benchmark(**小数据上 3D-ResNet/TCN 胜过 video
  transformer**,佐证我们当前"CNN+TCN 高度"是合理的)。
- **合成→力先例:** simulation-trained force classifier(IJCARS2019)、neural force manifold(2023)
  → 用仿真/FEM 提供力标注主体,正是我们的核心思路。

### 6.2 架构候选(RQ4,架构放最后,但先定 shortlist)
- **首选 A(合成预训练故事):** **VideoMAE / VideoMAE-V2** ViT-B/L backbone + 均值池化 token 回归头
  (非 CLS);先在合成视频上 tube-masking 自监督预训练,再 PEFT 微调真实。[ADOPT]
- **首选 B(稀缺标注故事):** 冻结领域 backbone(**Endo-FM** 视频 / DINOv2 / EndoViT 单帧)+
  **ST-Adapter/AIM/LoRA** + 小回归头(对标 **Surgical-DINO**:冻结 FM + LoRA 做**连续**回归,
  <1% 可训参数,内窥镜域已验证)。[ADOPT]
- **对照 C(隔离时序注意力贡献):** TimeSformer(divided attention)/ Video Swin,作为受控 baseline。
- **VLM:** SurgVLP/HecVL/PeskaVLP、InternVideo2 仅作 frozen-feature 探针,优先级低于 masked-video 预训练。

### 6.3 外观域差闭合(H1,核心数据杠杆,详见 RESEARCH_DIRECTION.md)
排序(便宜→强):
1. **渲染期域随机化(零外部数据,先做):** `Deform_post/dpost/render.py` 打破"灰白模"捷径——程序化
   器官材质/顶点色、随机光照、随机背景(代替纯白)、高光+暗角。Tobin IROS2017 / Prakash 结构化DR:
   **靠多样性而非真实感**起效。[ADOPT]
2. **标注安全的光度增广(训练期):** color jitter / gamma / blur / noise / vignette——纯像素操作,
   **不动几何**(几何会改 3D 力方向标签,绝不可做几何增广)。[ADOPT]
3. **无配对 sim→real 翻译(在我们自己的真实帧上训练):** **CUT/FastCUT**(优于 CycleGAN,单向+内容
   保持)→ 进阶 **diffusion + ControlNet,用 render 的 depth/normal/PPS 条件锁住几何**(SimuScope /
   Tomasini / PPS-Ctrl 的标注完整性设计)。可加 **force/geometry-consistency loss**(RetinaGAN 模式)。[ADOPT]
4. **神经渲染真实外观:** Rivoir ICCV2021 可学习纹理 / SurgicalGaussian 重建真实组织外观再贴回 FEM mesh。[CONSIDER]
- **外部外观池(仅 T1+T2 plateau 后):** DSAD(最接近公开**肾**视图)、SCARED/EndoVis(**猪**腹腔+深度)、
  Cholec80/CholecT45、Hamlyn、Kvasir。仅作纹理/背景/光照来源,**不提供力标签**,注意 license。

### 6.4 FEM 物理真实性(H2 + mesh 病根,详见 §10-cluster4)
1. **先换网格(高回报低成本):** TetGen-on-raw → **fTetWild**(对自交/非流形/重复tet 鲁棒,ε-envelope
   保证有效 tet),直接治"四面体病根";用 min dihedral / aspect-ratio 验收。[ADOPT]
2. **本构升级:** 线弹性 → **corotational(warped-stiffness)** 先消旋转伪影 → 近不可压 **Ogden/Neo-Hookean**
   parenchyma(ν≈0.49),参数取自 PLOS ONE 2024 / Farshad 1999 肾数据。[ADOPT]
3. **加被膜(capsule):** 薄壳/膜,E≈7–16 MPa(比 parenchyma 硬 ~1000×)——**主导表面形变线索**,是渲染
   视频里最可见的 cue。[ADOPT]
4. **粘弹(viscoelastic):** 1–2 项 Prony,匹配秒级持续施力下的应力松弛。[CONSIDER]
5. **标定而非猜:** **DiffPD / 可微 FEM** 反演拟合 E/Ogden/被膜刚度,使仿真形变贴合真实序列。[ADOPT]
6. **量化验收:** 仿真 vs 真实表面位移场对比 + 拟合模量落在 §10 肾参数表区间内,再批量产数据。
- 框架可选 **SOFA**(开源手术 FEM,自带 corotational/hyperelastic + 接触 + 钳交互)。

### 6.5 训练配方(RQ2)与损失(RQ3)
- **训练配方:** **累积而非替换**——31 真实序列永远留在池里(model-collapse 安全区,Gerstgrasser
  NeurIPS2024);合成作为加权 surrogate,用**小范围混合比 sweep 拟合最优权重**(Scaling Laws for
  Real+Surrogate NeurIPS2024,给出最优权重闭式预测)。两阶段:随机化合成上预训练 → 真实+合成混合
  微调("~10% 真实微调"即可追平全真实,arXiv:1907.07061)。可加 **CORAL(低风险)/ DANN** 特征对齐、
  **FADA** few-shot 对齐;末端 **Tent** 测试时 BN 自适应兜底残余偏移。[ADOPT/CONSIDER]
- **损失改造(RQ3,正交、可早做):** 力向量**幅值/方向解耦**——log-幅值上 Huber/L1 +
  方向上 **cosine/angular loss**(小数据上优于 L2,WACV2020);幅值项包 **heteroscedastic
  aleatoric**(Kendall&Gal 2017,自动下调噪声标签权重);幅值 vs 方向用 **learned homoscedastic
  uncertainty** 自平衡(Kendall 2018,免手调系数)。若 FEM 暴露接触/平衡约束,加轻量物理一致性残差。
  **每个组件对 plain-L2 做消融。** [ADOPT]

---

## 7. Status snapshot

> 每次实验后更新此节。当前数据来自 8-cond×5-fold CV(2026-06-15 完成)+ 4-变体迁移赛马
> (2026-06-15/16 完成)+ 域差量化(2026-06-16)。

### 7.1 主实验结果(real-comparable magnitude MAE,mean±std/5 fold)
| cond | setup | magMAE | angle |
|---|---|---|---|
| c1 | real scratch (single) | 0.232±0.073 | 23.9° |
| c2 | synt→real zero-shot (single) | **1.357±0.456** | 55.4° |
| c3 | mixed real_only (single) | 0.204±0.054 | 24.9° |
| c4 | transfer LP-FT (single) | 0.209±0.035 | 26.1° |
| c5 | real scratch (sequence) | 0.234±0.023 | 28.3° |
| c6 | synt→real zero-shot (sequence) | **1.542±0.097** | 59.7° |
| c7 | mixed real_only (sequence) | 0.222±0.040 | 28.1° |
| c8 | transfer (sequence) | 0.240±0.037 | 29.0° |

### 7.2 迁移配方赛马(c4 变体,5 fold,均 init 自同 fold c2 best)
| 变体 | 策略 | magMAE | angle |
|---|---|---|---|
| c1 | scratch(基线) | 0.232±0.073 | 23.9° |
| c4 | LP-FT(原基线) | 0.209±0.035 | 26.1° |
| c4ft | full-FT | 0.216±0.032 | 26.1° |
| c4dl | disc-LR | 0.211±0.039 | 25.2° |
| c4sg | surgical | **0.207±0.029** | 26.9° |
| c4fz | frozen-head | 0.208±0.033 | 26.3° |

### 7.3 已确立结论
1. **大且稳健的 synth→real 域差**(唯一超出噪声的信号):zero-shot 差 ~6×,angle 55–60°(方向几乎无用)。
   → **证伪假设"FEM-synth ≈ real"**,且是**外观(像素)差**,非物理/力差。
2. **域差是外观差:** 线性探针 100% 可分真假(chance 50%),separation ratio 3.7,synth 多样性 ~6× 低
   (RMS 1.25 vs 7.64)。图:`DataFlow/Deform_post/feature_cache/domain_gap.png`。
3. **迁移配方不是瓶颈:** 5 种配方(full/disc-LR/surgical/frozen/LP-FT)统计上**全部打平**(0.207–0.216,
   极差 0.009 « ±0.03 std),仅边际优于 scratch(0.232)且在噪声内;唯一真实收益是**方差更小(更稳)**。
4. **架构不是瓶颈**(见 §5-H4)。
5. **测量不可信**(见 §5-H0)——一切小效应的解读都被 3-序列 val 噪声淹没。

### 7.4 关键产物位置
- CV/赛马报告表+图:`DataFlow/KiDKNet/outputs/cv5/report/`(`report_cv_*` / `report_race_*`)。
- 域差图+点:`DataFlow/Deform_post/feature_cache/domain_gap.{png,json}`。
- 北极星汇总图:`DataFlow/KiDKNet/outputs/cv5/report/goal_state_*.png`(§9 生成)。
- W&B:`kidknet-cv5`(主)/ `kidknet-xferrace`(赛马),entity `zwhdiscovery-kyoto-university`。
- 诊断脚本:`KiDKNet/scripts/{analyze_domain_gap,kshot_transfer,report_cv}.py`。

---

## 8. Experiment roadmap

**严格分阶段、设决策门(gate),不要"一次全上"。** 每阶段产出数值 + 图(§9)。

**Phase 0 — 修测量仪器(前置,~数天,无 GPU 风险)** — 没有它后续比较都不可信:
- 加**标注安全的光度增广**(KiDKNet `transforms.py`,config 门控,默认行为不变)。 **[DONE 2026-06-21]** `PhotometricAugment` + `loader.py` train/eval transform 分离;GPU-free 测试全过(默认禁用→行为不变、标注安全无几何改动、bf16 round-trip);未提交;待 GPU 启用。
- 扩大/稳定验证集(3-序列 val 是头号噪声源):或改 test-only CV、固定 epoch / EMA 选择,去掉 best-epoch 挑选。
- 力目标归一化/对齐;重跑 c1–c8 基线。
- **Gate 0:** c1 fold std 明显下降、跨 fold best-epoch 收敛 → 进入 Phase 1。

**Phase 1 — 廉价决定性诊断(数小时,复用缓存)** — 先确认上限再砸资源:
- **k-shot 学习曲线**(`scripts/kshot_transfer.py`,需 GPU,现已就绪):synt-pretrain vs ImageNet-scratch
  在 k∈{1,2,4,8,16} 真实序列上微调 → 这才是"合成作为稀缺真实先验"的**真正检验**(主网格从未测过稀缺区)。
- **Gate 1:** 若小 k 处 synt 显著优于 imagenet 且差距随 k 缩小 → 合成先验有效,值得投入 Phase 2/3。

**Phase 2 — 核心数据杠杆:渲染期域随机化(H1)** — 最便宜最高杠杆:
- `render.py` 最小改动(随机光照+背景+程序化材质/顶点色+暗角),config 门控;重渲孪生集 → 重抽特征 →
  重跑 `analyze_domain_gap.py` 验证 separability / separation ratio **下降**。
- **Gate 2:** 域差指标下降 + k-shot 曲线上移 → 进入 Phase 3。

**Phase 3 — 无配对 sim→real 翻译(H1 强化)** — 用我们自己的真实帧:CUT 优先 → diffusion+ControlNet
  几何锁定;同步 RQ3 损失改造(可与 Phase 0/2 并行,损失正交)。

**Phase 4 — FEM 物理真实性 + 相机(H2/H3)** — fTetWild 换网格 → corotational/Ogden + 被膜 → DiffPD
  标定;相机外参对照真实术野。量化:仿真 vs 真实表面位移场。

**Phase 5 — 架构(RQ4,放最后)** — 在干净测量 + 闭合域差后,跑 §6.2 shortlist(VideoMAE 预训练 / 冻结
  FM+LoRA / TimeSformer 对照),并拟合 **RQ★ scaling law** 三曲线(error vs 真实N / 合成量 / 混合比)。

**赛马纪律(CLAUDE.md):** 竞争技术方案各自 isolated git worktree(同盘 + 相对 `DataFlow` symlink),只合并
赢家;GPU 与同事共享,遇占用灵活调度(<1500MiB 视为空闲再抢)。资源敏感改动先测资源本身再宣布安全。

---

## 9. Visualization

**用户硬性要求:每个实验用 matplotlib 出 PPTX 可直接用的图。**
- **存放:** 各实验的 `.../report/` 或 `feature_cache/`;图入 §7.4 与下方 roster。
- **规范:** 高 DPI(≥130),白底,英文标注(图进英文论文/PPT),误差棒必带(error bars = fold std),
  基线线(如 c1 scratch)用虚线标注,统一配色(real 蓝 `#378ADD` / synth 红 `#C44E52`)。
- **现有脚本:** `report_cv.py`(跨条件表+柱状图)、`analyze_domain_gap.py`(PCA散点+多样性柱)。

### Figures & artifacts roster(验证产物登记,CLAUDE.md 要求)
| path | purpose | owner | cleanup |
|---|---|---|---|
| `DataFlow/KiDKNet/outputs/cv5/report/report_cv_*.png` | 8/12-cond CV 对照图 | report_cv.py | keep(汇报用) |
| `DataFlow/KiDKNet/outputs/cv5/report/report_race_*.png` | 迁移赛马对照图 | report_cv.py | keep |
| `DataFlow/Deform_post/feature_cache/domain_gap.png` | 域差 PCA+多样性 | analyze_domain_gap.py | keep |
| `DataFlow/KiDKNet/outputs/cv5/report/goal_state_*.png` | 北极星汇总图(诊断三联) | scripts/plot_goal_state.py | keep |

---

## 10. Reference library

按技术栈分簇;标签 [ADOPT]=拟采用 / [CONSIDER]=候选 / [CITE]=对照或必引。

### Cluster A — Vision→force estimation in surgery
- **Vision-based force estimation, porcine excised kidney** (Sci. Rep. 2024) — VGG-16 单帧回归 3D 力,传感钳标注。**必比基线(同器官同设置)。** [CITE] https://www.nature.com/articles/s41598-024-60574-w
- **Recurrent CNN for sensorless force estimation** (Marban, BSPC 2019) — CNN+LSTM,视频+钳运动融合。[CITE] arXiv:1805.08545
- **DaFoEs** (ICRA 2024) — 混合多数据集→相对误差~5%;backbone/时序头消融模板。[ADOPT] arXiv:2401.09239
- **Video models for small-bowel retraction force** (IJCARS 2026) — **小数据上 3D-ResNet/TCN 胜过 video transformer。** [ADOPT] (SPIE 2025 13408)
- **Force estimation w/ vision+robot state** (2020) — 辅助状态(钳位姿/接触)有用。[CONSIDER] arXiv:2011.02112
- **Dim-reduction for force estimation** (EAAI 2023) — 特征瓶颈降过拟合 ~10%。[CONSIDER]
- **Contact-detection + local stiffness force** (JMRR 2024) — 物理接地、接触门控。[CONSIDER] arXiv:2403.18172
- **Simulation-trained force classification** (IJCARS 2019) — **仿真图像供力标注主体**,sim→real 先例。[ADOPT]
- **Image-to-Force via structured light** (2025) — 形变几何是力信号载体;可加深度 cue。[CONSIDER] arXiv:2501.08593
- **Neural force manifold sim2real (paper folding)** (2023) — 纯仿真训练零样本部署。[CITE] arXiv:2301.01968

### Cluster B — Video transformers / VLM for regression
- **VideoMAE** (NeurIPS 2022) — tube-masking,数据高效,3–4k clip 即可。[ADOPT] arXiv:2203.12602
- **VideoMAE V2** (CVPR 2023) — dual-masking,公开 ViT-S/B/L/g 权重。[ADOPT] arXiv:2303.16727
- **V-JEPA / V-JEPA 2** (2024–25) — 潜空间预测,适合物理量;强 frozen 特征。[CONSIDER] arXiv:2506.09985
- **ViViT** (ICCV 2021) — 因子化时空注意力。[CITE] arXiv:2103.15691
- **TimeSformer** (ICML 2021) — divided space-time attention,对照 baseline。[CITE] arXiv:2102.05095
- **Video Swin** (CVPR 2022) — 层级局部 3D 注意力,ImageNet 可初始化,样本高效。[CONSIDER] arXiv:2106.13230
- **MViTv2** (CVPR 2022) — 多尺度,利于定位小钳尖接触区。[CITE] arXiv:2112.01526
- **AIM / ST-Adapter** (ICLR/NeurIPS 2022–23) — 冻结图像 ViT + 时空 adapter,PEFT。[ADOPT] arXiv:2302.03024
- **Surgical-DINO** (IJCARS 2024) — 冻结 DINOv2 + LoRA 做**连续**深度回归,0.17% 参数。**回归头模板。** [ADOPT] arXiv:2401.06013
- **Endo-FM** (MICCAI 2023) — 33K 内窥镜 clip 自监督视频 backbone。[CONSIDER] arXiv:2306.16741
- **EndoViT** (IJCARS 2023) — Endo700k MAE 预训练单帧 ViT。[CITE] arXiv:2303.17636
- **SurgVLP/HecVL/PeskaVLP, InternVideo2** — 手术 VLM,仅 frozen 探针,优先级低。[CONSIDER] arXiv:2403.15377

### Cluster C — Sim2real appearance gap (medical/endoscopic)
- **Long-Term Temporally Consistent Unpaired Video Translation from Sim 3D** (Rivoir, ICCV 2021) — 可学习纹理贴 mesh + 视图一致性,**最接近我们白模→真实**(视频级)。[ADOPT] arXiv:2103.17204
- **SimuScope** (WACV 2025) — SD+LoRA i2i,**保留 simulator 标注**(姿态/形变)。[ADOPT] arXiv:2412.02332
- **Sim2Real structure-aware translation** (Tomasini, MICCAI-W 2024) — 给 sim 图加纹理、锁定布局,几乎我们的设置。[ADOPT] arXiv:2505.02654
- **PPS-Ctrl** (2025) — SD+ControlNet 用 Per-Pixel-Shading 条件,**强几何锁定 → 标注安全**。[ADOPT] arXiv:2504.17067
- **CUT/FastCUT** (ECCV 2020) — 单向对比无配对翻译,内容保持优于 CycleGAN,**首选 GAN baseline**。[ADOPT] arXiv:2007.15651
- **CycleGAN** (ICCV 2017) — 无配对翻译鼻祖,必引历史 baseline。[CITE] arXiv:1703.10593
- **Domain Randomization** (Tobin, IROS 2017) — 随机纹理/光照/相机,**最便宜标注安全杠杆**。[ADOPT] arXiv:1703.06907
- **Structured Domain Randomization** (ICRA 2019) — 在合理结构内随机,胜过朴素 DR。[CONSIDER] arXiv:1810.10093
- **RetinaGAN** (ICRA 2021) — task-consistency loss 锁任务内容,**对应我们 force-consistency loss**。[CONSIDER] arXiv:2011.03148
- **SurgicalGaussian** (MICCAI 2024) — 可变形 3DGS 重建真实组织外观,再贴回 FEM mesh。[CONSIDER]
- **Endora** (MICCAI 2024) — 内窥镜视频生成,realism 先验。[CITE]
- **公开真实数据集:** Cholec80/CholecT45(CC BY-NC-SA,style源)、**SCARED**(猪腹腔+深度,最接近猪肾域)、
  Hamlyn(大量无标注真实)、**DSAD**(CC BY,最接近公开肾视图)、EndoVis、AutoLaparo、Kvasir/HyperKvasir。

### Cluster D — Soft-tissue FEM realism & meshing
- **Pig kidney material characterization** (Farshad, J. Biomech 1999) — parenchyma 单位数 kPa + 硬被膜。[CITE]
- **Kidney capsule strain-rate properties** (Snedeker 2005) — 被膜 E≈7→16 MPa,rate-dependent。[ADOPT]
- **Porcine kidney mechanical evaluation** (PLOS ONE 2024) — Ogden 3-term + viscoelastic + damage,**现代可引参数集**。[ADOPT]
- **Abdominal organ constitutive modelling** (J. Biomech 2000) — 肝/肾/脾 hyperelastic+viscoelastic。[CITE]
- **Liver visco-hyperelastic indentation** (JMBBM 2019) — 加载-卸载滞回。[CONSIDER]
- **Hyperelastic models for soft tissue** (J.R.Soc.Interface 2015) — Ogden 对大应变最佳。[CONSIDER]
- **Interactive Virtual Materials (corotational FEM)** (Müller, GI 2004) — **线弹性→corotational 最小升级**。[ADOPT]
- **Nonlinear FEM in SOFA / GPU** (ISVC 2008) — SOFA 自带 corotational/hyperelastic+接触。[CONSIDER]
- **Real-time soft-tissue simulation survey** (IEEE Access 2020) — 选型地图。[CITE]
- **DiffPD** (ACM TOG 2022) — 可微 soft-body,**反演标定 E/Ogden/被膜**,real2sim。[ADOPT] arXiv:2101.05917
- **Equivariant GNN tissue+force** (2024–25) — FEM-synthetic+real 混训预测形变+力。[CONSIDER] arXiv:2509.10125
- **fTetWild** (ACM TOG 2020) — 鲁棒四面体化(自交/非流形/triangle soup),**治四面体病根**。[ADOPT] arXiv:1908.03581
- **TetGen** (ACM TOMS 2015) — Delaunay 质量 tet,但需 watertight 输入(病根来源)。[CITE]
- **肾/软组织力学参数表:** parenchyma ~3.5–4.4 kPa(SWE,健康)/ 单位数 kPa(离体);capsule 7–16 MPa;
  ν≈0.45–0.499(近不可压);whole kidney Ogden+viscoelastic+damage(PLOS 2024)。

### Cluster E — Synthetic scaling laws, training recipes, losses
- **Scaling Laws for Learning with Real and Surrogate Data** (NeurIPS 2024) — 真实+surrogate 混合**最优权重闭式**。[ADOPT] arXiv:2402.04376
- **How Much Real Data Do We Need** (ICML-W 2019) — sim 预训练+~10% 真实微调 ≈ 全真实。[ADOPT] arXiv:1907.07061
- **Scaling Laws of Synthetic Images** (CVPR 2024) — 合成遵循 scaling law,常数更差,域差大时合成胜。[CONSIDER] arXiv:2312.04567
- **Scaling Laws of Synthetic Data for LM** (COLM 2025) — 明确**饱和点**。[CITE] arXiv:2503.19551
- **Is Model Collapse Inevitable? (Accumulate)** (NeurIPS 2024) — **累积**真实+合成可避免崩溃,误差有界。[CITE] arXiv:2404.01413
- **Curse of Recursion** (Nature 2024) — 递归训自身输出会崩溃(我们 FEM 渲染非自生,安全)。[CITE] arXiv:2305.17493
- **DANN** (JMLR 2016) — 梯度反转域不变特征。[CONSIDER] arXiv:1505.07818
- **Deep CORAL** (ECCV-W 2016) — 二阶统计对齐,轻量低风险。[CONSIDER] arXiv:1607.01719
- **FADA** (NeurIPS 2017) — few-shot 对抗域适应,契合稀缺真实标注。[CONSIDER]
- **Tent** (ICLR 2021) — 测试时 BN 自适应,兜底残余偏移。[CONSIDER] arXiv:2006.10726
- **Uncertainty to Weigh Losses** (Kendall, CVPR 2018) — **自平衡幅值 vs 方向多任务**。[ADOPT] arXiv:1705.07115
- **What Uncertainties (aleatoric)** (Kendall&Gal, NeurIPS 2017) — **heteroscedastic 回归损失**下调噪声标签。[ADOPT] arXiv:1703.04977
- **Cosine Loss for Small Datasets** (WACV 2020) — 小数据上**方向 cosine loss** 优于 L2。[ADOPT] arXiv:1901.09054

---

## 11. Decision & update log

- **2026-06-14/15** — 部署 8-cond×5-fold CV;接 W&B;keep_last=1;commit `8b5081d`(W&B + report_cv.py + keep_last)。
- **2026-06-15/16** — 迁移配方赛马(4 变体×5 fold,isolated worktree);结论:配方全打平,非瓶颈。
- **2026-06-16** — 域差量化:外观差为主因(100% 可分,~6× 多样性差)。写 `RESEARCH_DIRECTION.md`,确立
  "修测量 → 闭外观差(数据侧) → 架构最后"的方向;新增 `analyze_domain_gap.py`/`kshot_transfer.py`。
- **2026-06-21** — 用户用 `/goal` 设定四大科研目标(RQ1–4)+ scaling-law 探问;5 簇文献检索完成;
  建立本北极星文档 `RESEARCH_GOAL.md`(整合技术栈 + 路线图 + 可视化规范);commit `adf29a6`提交文档+诊断脚本。
- **2026-06-21 (Phase 0 起步)** — 实现 train-only 标注安全光度增广(`transforms.py` `PhotometricAugment` + `loader.py` train/eval transform 分离),GPU-free 测试全过(默认禁用、行为不变)。未提交。下一个 GPU-free 单元:RQ3 损失改造(学习式不确定性加权,替代固定 λ)。待 GPU 授权后:启用增广重跑 c1–c4 + 扫验证集扩大/力归一化。

> **决策待定(需用户拍板的方向选择):**
> - Phase 0 与 Phase 1 是否现在就开跑(需 GPU,与同事共享)?
> - RQ3 损失改造可与 Phase 0 并行(正交、低成本),是否一并启动?
> - 诊断脚本(analyze_domain_gap / kshot_transfer / report_cv 扩展)是否提交入库?
