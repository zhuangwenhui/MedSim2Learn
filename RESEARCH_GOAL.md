# Research Goal — Zero-Real-Label Sim→Real Domain Adaptation for Video→Force Prediction

> **本文档是项目的"北极星"(north star),长期回看 + 持续更新。**
> 它的唯一职责:在漫长、反复 compact 的对话中**防止科研目标漂移**。
> 任何一次会话开始、或 compact 之后,**先读本文档**,再决定下一步。
> 详细的外观域差诊断见姊妹文档 `RESEARCH_DIRECTION.md`(2026-06-16,本文不重复)。
>
> **⚠ 生效覆盖(2026-07-03 re-scope):** §11 的 **2026-07-03** 条目**覆盖**本文档与
> `RESEARCH_DIRECTION.md` 中所有更早的"合成增强"(augmentation)框架与渲染环境
> (Linux headless-GL block)措辞。凡本文旧文与该条目冲突处,以该条目为准。
>
> **维护契约(给未来的我):** 每完成一个实验或做出一个方向决定,更新 §7 状态快照
> 与 §9 决策日志;改动 RQ / 假设 / 路线图时同步本文。结论必须有一手证据(命令输出 /
> 生成的 JSON / 图),不得凭记忆断言(见根 `CLAUDE.md` 的 Verification 规则)。
> 用户最终用途:实验结果要有 matplotlib 可视化,可直接进 PPTX 汇报(见 §9)。

Last updated: 2026-07-03 · Owner: WENHUIZ · Status: re-scoped to zero-real-label sim→real UDA (see §11 2026-07-03)

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

**(2026-07-03 re-scope,覆盖旧的"合成增强"框架。)** 核心命题是 **zero-real-label sim→real
transfer**:**只用 FEM 合成数据(带力标注)训练,训练集中不含任何真实力标签**,再通过
**domain adaptation / alignment**(在**输入=图像**与**输出=力**两端同时对齐)把模型迁移到真实域。
之所以坚持"零真实力标签",是**硬约束**:真实人体手术永远无法采集力的 ground-truth(无法在活体
组织里插传感器),所以"合成→真实"不是可选优化,而是唯一可行的落地路径。无标注的真实**图像**
可用于自适应(unlabeled real images OK);真实力标签只作 oracle/评估用,**不进训练**。

**固定 I/O 前提(贯穿全文):** 推理时输入 = 单张/一段**内窥镜图像**,输出 = **3D 力向量**;
任何需要在推理时额外拿深度 / 机器人状态 / 额外传感器的方法都**出局**(见 §2 硬约束)。

**用 FEM 合成数据管线**(ShapeReconstruction → DeformSim → Deform_post)提供力监督主体,
把 sim→real 域差**分解为可组合的因子**(外观/着色、视角多样性、接触点多样性、力真实性)+ 输入/
输出对齐,逐因子隔离测量再组合(见 §4/§5/§8)。

成功判据(本项目意义上的"做成了"):
- **c1(real-scratch)现在是 ceiling / oracle,c2(synth-only zero-shot,无自适应)是 baseline /
  研究起点。** "做成了" = 一个**只用合成数据训练 + 域自适应**、**训练中零真实力标签**的模型,
  **可测量且可复现地**把 c2→c1 的差距缩小(magMAE 从 ~1.357 / 55.4° 朝 c1 的 0.232 / 23.9° 逼近)。
- **主指标 = gap-closed %** = (c2 − method) / (c2 − c1)。序列面板同理(c5=0.234/28.3° 为 ceiling,
  c6=1.542/59.7° 为 baseline)。
- 真实样本数 real-N 仅作**显式标注的 oracle-ceiling 曲线**保留(不是训练旋钮);合成量/多样性可扫。
  **"真实样本数-as-training-knob"与"混合比例"已废弃**(它们隐含真实力标签进训练,违反零标签约束)。
- 全程数值 + 图像结果留痕,权重可复现评估。

---

## 2. Task spec

- **输入:** 内窥镜**视频片段**(时序列已是标配,不再是单帧)。
- **输出:** 连续 **3D 力向量**(幅值 magnitude + 方向 direction)。
- **硬约束——推理 I/O 固定(不可改的 inference contract):** 推理时**只有图像/片段进 → 3D
  力向量出**。任何在测试时改变这一契约的方法(需要深度、机器人状态、额外传感器)**一律出局**。
  自适应可以用无标注真实图像,但**推理输入永远只有图像**。
- **评估面板(原始未归一化力):** magnitude MAE / MRE / Acc@10%、mean angle error、
  angle accuracy@5°、逐轴 x/y/z MAE;序列模型加 temporal RMSE。
- **当前模型:** ConvNeXt-Large(ImageNet 预训练,197M)+ TCN/MLP 力回归头。

---

## 3. Data

- **真实数据:** 猪肾,手术钳施力,内窥镜视频,**稀缺(~31 序列)**;力为传感钳读数(原始值)。
- **合成数据(数字孪生):** CT 重建肾表面 mesh → 四面体化 → 设为弹性体 → 选中顶点附近施加
  力向量 → FEM 求解形变 → 渲染视频。当前是 **31 条真实序列的 1:1 孪生回放**(力 = 真实
  传感力旋转进 mesh 系,**力分布天然匹配真实**),不是大规模随机合成器。
- **孪生不是问题所在(sub-note,2026-07-03):** 数字孪生的力是一个**已被瞥见、且有效的经验
  参考/锚点**(a glimpsed-but-valid empirical reference)——它是真实力分布里的**一个样本,不是
  完整分布**。**完全脱开孪生、随机生成力是危险的**:随机力无法测量 → FEM 会解出错误形变 →
  于是"图像→力"的监督被喂错。**任何力生成器必须仍系在孪生上(tethered to the twin),并对照
  一个参考包络验收**(twin 统计 + 已记录的手术力文献)。见新 §6.6 与 §5-H5、RQ-force。
- **真实力标签不进训练:** 真实力仅用于 c1 oracle-ceiling 与评估;训练**只用合成力标签**,
  真实域侧只用**无标注图像**做自适应(zero-real-label 约束)。
- **数据布局:** 见根 `CLAUDE.md` 的 `DataFlow/Deform_post` 四层结构 + `DataFlow/KiDKNet`。
  KiDKNet 用 ConvNeXt 特征缓存 + 5-fold CV split(`splits/cv5`,seed 42,按 id 配对、防泄漏)。
  服务器现况(2026-07-03 核实):`preprocessed/datasets/{real(31 seq / 52522 samples),
  mixed(62 seq / 105044)}` + `splits/cv5` 在盘;**无 feature_cache**(Track B 需重算 ConvNeXt
  特征);primary 渲染 + `labels.csv` 仅在 Windows 侧。

---

## 4. Research questions

映射用户科研目标,**2026-07-03 起以 zero-real-label sim→real 框架重述**(见 §11):

| RQ | 用户目标 | 一句话问题 | 主战场 |
|---|---|---|---|
| **RQ1** | 目标1 | **输入域对齐(INPUT-domain alignment):** 合成图像与真实图像的外观差如何闭合?§8 逐因子消融:**外观/着色、渲染视角多样性、接触点多样性**。 | 数据侧 §5-H1a/b/c |
| **RQ2** | 目标2 | **输出侧 / 无监督域适应(UDA):** 哪种 UDA 方法(CORAL/DANN 特征对齐、Tent 测试时自适应、在无标注真实帧上 self-training)能把 synth-only 模型迁移到真实**且不用任何真实力标签**(无标注真实图像 OK)? | 训练侧 §6.5 |
| **RQ3** | 目标3 | 是否需要**改造损失函数**(幅值/方向解耦、不确定性加权)提升性能?(框架中性,保留) | 损失侧 §6.5 |
| **RQ4** | 目标4 | 哪种 **transformer-based / VLM 架构**更适合本任务(架构放最后),在 **synth-only + 真实作无标注自适应信号**下最优? | 架构侧 §6.2 |
| **RQ-force** | 新增 | 一条**合理的合成力序列**长什么样(幅值范围、时间轮廓、接触动力学),才不会污染 FEM→图像→力 的监督?如何把生成器**对照孪生参考 + 已记录手术力文献(existence-only)**验收? | 力先验 §6.6 §5-H5 |
| **RQ★** | 附加(降为次要) | 能否拟合**合成数据 scaling law**(error vs **合成量/多样性**)指导"造多少、造什么"数据?**已去掉混合比;只在合成量/多样性维度扫。** | 全局 §8 |

**排序原则(2026-07-03 更新):** 测量整改从**门(gate)降为并行卫生(parallel hygiene)**——
c2→c1 的信号(~1.1 magMAE)约为 fold 噪声(~0.07)的 **~16×**,已不再阻塞关键路径;
可与因子消融并行做。架构(RQ4)仍放最后。

---

## 5. Root-cause hypothesis tree

用户提出"孪生数据不够孪生"的四个环节问题 + 我们补充的测量前置与力真实性问题。每条都需**独立验证**。
**(2026-07-03 起 ROOT 重述为 "c2→c1 gap under zero-real-label transfer"。)**

```
c2→c1 gap under zero-real-label transfer(synth-only 训练 → 真实域,零真实力标签)
├─ H0  测量不可信(val=3序列→best-epoch抖动;无增广→过拟合;力未归一化)  ← 并行卫生(不再是门)
├─ 孪生不够孪生(domain gap,输入侧)
│  ├─ H1a [SR/render] "白模"无纹理颜色/着色 → 外观(appearance/coloring)差(已证:外观差为主因)
│  ├─ H1b [Deform_post] 渲染视角单一 → 视角覆盖(viewpoint-coverage)不足(under-explored)
│  ├─ H1c [annotation]  接触点位置单一 → 接触点覆盖(contact-point-coverage)不足(under-explored)
│  ├─ H2 [DeformSim] FEM 假设过naive(线弹性、无被膜、无粘弹)→ 形变物理失真
│  └─ H3 [Deform_post] Open3D 相机位姿 ≠ 真实术野视角 → 视觉分布偏移
├─ H5 [force realism] 合成力偏离孪生/真实参考 → 不合理 FEM 形变 → 污染监督(在任何"超出孪生"的力生成前必须先设防)
└─ H4 [Architecture/Loss] CNN+TCN 未必最优;损失未针对3D力向量设计
```

各假设当前证据强度(详见 §7):
- **H1(外观差)= 已证、是主因。** 线性探针 100% 可分真假;synth 特征多样性 ~6× 低于真实。
  其中"白模无纹理"(**H1a appearance**)已确证;"mesh 拓扑/四面体病根"**尚未单独验证**(需
  §8 Phase 4 检查 tet 质量)。**H1b 视角覆盖 / H1c 接触点覆盖**是被低估、尚未单独消融的因子
  (§8 因子分解阶段将逐个 isolate-then-combine)。
- **H0(测量噪声)= 已证。** c1 fold std ±0.073(均值的 ~31%)> 所有跨条件差;best-epoch 在
  folds 间跳 1/6/10/25。**但相对 c2→c1 的 ~1.1 信号,它已从"门"降为并行卫生(见 §4/§8)。**
- **H2(FEM naive)= 合理但未验证。** 力分布已匹配真实,故 H2 不是力的问题,而是**形变形态**
  问题(可能影响视觉形变线索);需对照真实形变量化(§8 Phase 4)。
- **H3(相机)= 合理但未验证。** 需对照真实术野相机外参/视角分布(§8 Phase 4)。
- **H5(力真实性)= 新增、尚未验证、是"力生成"的前置门。** 只要不脱开孪生(当前 1:1 回放),
  力分布天然匹配真实、H5 不触发;但**任何超出孪生的力增广**都可能让合成力偏离真实参考,
  解出不合理形变、把"图像→力"监督喂错。**在做任何超出孪生的力生成前,必须先用 §6.6 的
  参考包络 + `is_plausible()` 门设防。** 见 RQ-force。
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
> **硬约束(2026-07-03):** 所有渲染都在**用户控制的 Windows 机器**上执行,**可检视、可中断**
> (inspectable/interruptible);交叉参考已退役的 `sim2vfp.py`(git `ba4501c`,手工可控性保证的
> 记录)。**Linux 容器的 headless-GL/EGL block 已作废(MOOT),绝不再提"修容器 GL"。**
排序(便宜→强):
1. **渲染期域随机化(零外部数据,先做;在 Windows 渲染机上跑):** `Deform_post/dpost/render.py`
   打破"灰白模"捷径——程序化器官材质/顶点色、随机光照、随机背景(代替纯白)、高光+暗角。
   Tobin IROS2017 / Prakash 结构化DR:**靠多样性而非真实感**起效。[ADOPT]
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
> **框架修正(2026-07-03):** 下面"累积而非替换 / 真实+合成混合微调 / ~10% 真实微调"这一整套
> **预设了真实力标签进训练**,与零真实力标签约束冲突。**它们现在只作 oracle-ceiling 语境保留**
> (刻画"如果允许真实标签能到哪"),**不是主线方法**。零标签下的"mix"是 **synth-labeled +
> real-UNLABELED 的 UDA**(见下)。
- **训练配方(oracle-ceiling 语境,非主线):** ~~**累积而非替换**——31 真实序列永远留在池里~~
  (model-collapse 安全区,Gerstgrasser NeurIPS2024);~~合成作为加权 surrogate,用**小范围混合比
  sweep 拟合最优权重**~~(Scaling Laws for Real+Surrogate NeurIPS2024)。~~两阶段:随机化合成上
  预训练 → 真实+合成混合微调("~10% 真实微调"即可追平全真实,arXiv:1907.07061)~~——**以上均需
  真实标签,仅作 ceiling 参照。**
- **训练配方(主线 = zero-real-label UDA,RQ2):** 只在合成(带力标签)上训练,真实域只提供
  **无标注图像**。用 **CORAL(低风险)/ DANN** 做特征对齐、**Tent** 测试时 BN 自适应兜底残余偏移、
  在无标注真实帧上 **self-training**(伪标签/一致性)。**FADA** 属 few-shot 有标注,只在 oracle 语境
  下讨论。[ADOPT/CONSIDER]
- **损失改造(RQ3,正交、可早做):** 力向量**幅值/方向解耦**——log-幅值上 Huber/L1 +
  方向上 **cosine/angular loss**(小数据上优于 L2,WACV2020);幅值项包 **heteroscedastic
  aleatoric**(Kendall&Gal 2017,自动下调噪声标签权重);幅值 vs 方向用 **learned homoscedastic
  uncertainty** 自平衡(Kendall 2018,免手调系数)。若 FEM 暴露接触/平衡约束,加轻量物理一致性残差。
  **每个组件对 plain-L2 做消融。** [ADOPT]

### 6.6 Force-prior / force-realism(H5,RQ-force,力生成的前置门)
一句话:**在做任何"超出孪生"的力生成之前**,先回答"一条合理的手术力长什么样",并设一个能
**拒绝不合理力**的验收门,否则会污染 FEM→图像→力 的监督(见 §5-H5)。
- **合理力的规格(spec):** 从**已记录的手术力数据集 + 文献**总结幅值包络(magnitude envelope)、
  变化率(rate)、驻留时长(dwell)、接触开/关(contact on/off)等应有的量级与时间轮廓。
  **existence-only 规则:** 只登录**确实存在**的来源;找不到就**如实记为"没有"**(不得虚构)。
  running survey 写入 `experiments/2026-07-03_force-prior/LITERATURE.md`。
- **验收度量(acceptance metric):** 一个候选力生成器必须 (a) **落在孪生参考包络内**(twin-reference
  envelope);(b) 其 FEM 形变**对照真实验证**通过;(c) 一旦力**不可测量 / 不合理**即**拒绝**。
- **工具:** `experiments/2026-07-03_force-prior/force_envelope.py`——从 `.pt` 各层读原始力,产出
  经验包络 + `is_plausible()` 验收门。任何超出孪生的力,先过 `is_plausible()` 再进管线。
- 关联:H5(§5)+ RQ-force(§4)。**任何力增广必须仍系在孪生上(tethered),随机脱开的力是危险的
  (§3 sub-note)。**

---

## 7. Status snapshot

### CAMPAIGN RESULTS — autonomous overnight run (2026-06-21 → 06-22)
Three takeaways:
1. **H0 (measurement noise) DOMINATES.** 3-sequence validation → early-stopping never triggers (every c1/c3 run hits the epoch-50 cap); fold std (±0.04-0.07) exceeds nearly every effect. Most A/Bs are 'within noise on the mean'. Fixing measurement is the prerequisite for everything else.
2. **RQ3 learned-uncertainty loss is the most promising lever AND is on-mechanism for H0.** c1: magMAE 0.2316±0.073 (fixed lambda) → 0.1899±0.037 (Kendall uncertainty) = mean -18%, std -49%; it specifically rescues the noisiest folds (down-weights noisy samples). Calibrated: paired t≈-1.80, p≈0.15 (n=5, not yet significant); the variance reduction is the robust part. (c3 generalization check still finishing.)
3. **Synthetic prior is weak-but-positive, only at extreme scarcity.** k-shot (n=3): synt-pretrain beats ImageNet in sign at 4/5 k (k=1 -23%, but ~80% of that is one lucky seed → -4.5% without it; 198x variance), converges to the full-data baseline (0.232) by k=16. Benefit is magnitude-only (angle no better). Gate-1 = HOLD_fix_measurement_first.
Also: **photometric augmentation = mild regularizer** (c1/c3 std -20~27%, mean neutral). **render-DR pilot designed (workflow w7lte239u).** RESOLUTION (2026-07-03): rendering is done on the user-controlled **Windows** render machine **by design** — the earlier "no headless GL/EGL on this Linux container" note is **not a blocker but a settled decision** (MOOT; never propose fixing the container GL). See `sim2vfp.py` (retired at git `ba4501c`) for the controllability record.
Two levers remain: (A) measurement-overhaul — **now demoted from a gate to parallel hygiene** (the c2→c1 signal ~1.1 magMAE dwarfs the ~0.07 fold noise by ~16x), enlarge val + force-norm + multi-fold/init k-shot; (B) render-DR + factor-decomposition on the Windows render machine. GPU note (updated 2026-07-03): **4x NVIDIA A100 80GB PCIe available (idle)** — the earlier "H100 yielded to a colleague ... confined to the 3 Ada since" note is stale and superseded.
Figures (PPTX-ready): kshot/report/kshot_curve.png, cv5_aug/report/aug_ab.png, cv5_unc/report/rq3_loss_ab.png, cv5/report/goal_state_diagnosis.png, Deform_post/feature_cache/domain_gap.png. Commits: 8b5081d adf29a6 493d46c c3ed62f aa11317 48d7817 4d922ad a8e55aa 3eb50ae e87a3d3 40b6e69.


> 每次实验后更新此节。当前数据来自 8-cond×5-fold CV(2026-06-15 完成)+ 4-变体迁移赛马
> (2026-06-15/16 完成)+ 域差量化(2026-06-16)。

### 7.1 主实验结果(real-comparable magnitude MAE,mean±std/5 fold)
> **读表框架(2026-07-03):** **c1(real-scratch)= oracle ceiling;c2(synth-only zero-shot,无自适应)
> = zero-real-label BASELINE** —— 它 1.357 / 55.4° 的差表现是**预期之内的研究起点,不是缺陷**。
> 目标是把 c2 朝 c1 缩小(gap-closed %);序列面板同理(c5=ceiling / c6=baseline)。**表内数值一律
> 不改。**
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
   → 事实不变;**2026-07-03 重述其意义:这不是"证伪"某个增广假设,而是确认了一条研究必须闭合的
   大 adaptation gap**(c2→c1);且已定位为**外观(像素)差**,非物理/力差。
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

**Phase 0 — 测量卫生(2026-07-03:从 GATE 降为 parallel hygiene,可与 Phase 2/因子消融并行)** —
理由:c2→c1 信号 ~1.1 magMAE 是 fold 噪声 ~0.07 的 **~16×**,已不阻塞关键路径;修好能让小效应更可读,
但不再是进入后续阶段的前置门:
- 加**标注安全的光度增广**(KiDKNet `transforms.py`,config 门控,默认行为不变)。
  **[实验已结束——LOSE/reverted;记录见 `experiments/INDEX.md` 的 photometric-augmentation 行、
  `report.md §4.6`,配置在 commit `c3ed62f`]**:A/B 判定为温和正则(std 略降、均值中性),
  **非决定性杠杆**;实现代码已回退,结论保留在实验记录里。(原 `[DONE 2026-06-21]` 标记指的是
  "代码实现完成",与最终 LOSE 处置并不矛盾——此处对齐口径。)
- 扩大/稳定验证集(3-序列 val 是头号噪声源):或改 test-only CV、固定 epoch / EMA 选择,去掉 best-epoch 挑选。
- 力目标归一化/对齐;重跑 c1–c8 基线。
- **(降级说明)** 原 "Gate 0" 已取消;测量整改与因子消融、渲染多样性并行推进即可。

**Phase 1 — 廉价决定性诊断(数小时,复用缓存)** — 先确认上限再砸资源:
- **k-shot 学习曲线**(`scripts/kshot_transfer.py`,需 GPU,现已就绪):synt-pretrain vs ImageNet-scratch
  在 k∈{1,2,4,8,16} 真实序列上微调 → 这才是"合成作为稀缺真实先验"的**真正检验**(主网格从未测过稀缺区)。
- **Gate 1:** 若小 k 处 synt 显著优于 imagenet 且差距随 k 缩小 → 合成先验有效,值得投入 Phase 2/3。

**Phase F(force-prior,EARLY,门控任何"超出孪生"的力生成)** — 在做任何脱开孪生的力增广前**必须先做**:
- 文献 + 已记录手术力数据集调查(**existence-only**,写入 `experiments/2026-07-03_force-prior/LITERATURE.md`;
  找不到就如实记"没有")→ 产出**合理力规格**(幅值包络/rate/dwell/contact on-off)→ 用
  `experiments/2026-07-03_force-prior/force_envelope.py` 的经验包络 + `is_plausible()` 立**验收门**。
- **门:** 只有通过 `is_plausible()`(落在孪生参考包络内 + FEM 形变对真实验证通过)才允许**系在孪生上的
  (twin-tethered)**力增广;随机脱开孪生的力**禁止**。见 §6.6 / §5-H5 / RQ-force。

**Phase 2 — 核心数据杠杆:渲染期域随机化(H1a)—— 在 Windows 渲染机上执行(用户可检视)** — 最便宜最高杠杆:
- `render.py` 最小改动(随机光照+背景+程序化材质/顶点色+暗角),config 门控;**在 Windows 渲染机上**
  重渲孪生集 → 重抽特征 → 重跑 `analyze_domain_gap.py` 验证 separability / separation ratio **下降**。
  **不依赖任何 Linux 容器 GL**(headless-GL block 已作废)。
- **Windows 渲染机 inspectability/robustness 三修:** (F1) 批量渲染前加**形变帧预览+确认门**
  (deformed-frame preview+confirm);(F2) 恢复**逐帧渲染错误隔离 + 日志**(per-frame render-error
  isolation + log);(F3) 序列化时**硬性核对 #PLY == #PNG == #label-row**(不匹配即报错)。

**Phase D(factor-decomposition ablation,isolate-then-combine)** — 逐因子隔离测量再组合,量化各因子 uplift:
- 因子:**外观/着色(H1a)、渲染视角多样性(H1b)、接触点多样性(H1c)、力真实性(H5)**。
- 每个因子单独开/关跑一遍(measure each factor's uplift),再组合已证有益者;报告以 gap-closed % 计。

**Phase 3 — 输出侧 / 无监督域适应(RQ2,zero-real-label)** — 只用合成标签 + 无标注真实图像:
- **CORAL/DANN** 特征对齐、**Tent** 测试时自适应、在无标注真实帧上 self-training;可选无配对 sim→real
  翻译(CUT 优先 → diffusion+ControlNet 几何锁定,在我们自己的真实帧上训)。同步 RQ3 损失改造(正交,可并行)。

**Phase 4 — FEM 物理真实性 + 相机(H2/H3)** — fTetWild 换网格 → corotational/Ogden + 被膜 → DiffPD
  标定;相机外参对照真实术野。量化:仿真 vs 真实表面位移场。

**Phase 5 — 架构(RQ4,放最后)** — 在闭合域差后,跑 §6.2 shortlist(VideoMAE 预训练 / 冻结
  FM+LoRA / TimeSformer 对照),并拟合 **RQ★ scaling law**——**仅在合成量 / 多样性维度**扫
  (error vs 合成量 / 合成多样性;**已去掉混合比与 real-N-as-training-knob**,real-N 只作 oracle-ceiling 曲线)。

**赛马纪律(CLAUDE.md):** 竞争技术方案各自 isolated git worktree(同盘 + 相对 `DataFlow` symlink),只合并
赢家;GPU 与同事共享,遇占用灵活调度(<1500MiB 视为空闲再抢)。资源敏感改动先测资源本身再宣布安全。

---

## 9. Visualization

**用户硬性要求:每个实验用 matplotlib 出 PPTX 可直接用的图。**
- **存放:** 各实验的 `.../report/` 或 `feature_cache/`;图入 §7.4 与下方 roster。
- **规范:** 高 DPI(≥130),白底,英文标注(图进英文论文/PPT),误差棒必带(error bars = fold std),
  基线线(如 c1 scratch)用虚线标注,统一配色(real 蓝 `#378ADD` / synth 红 `#C44E52`)。
- **ceiling/baseline 双线带(2026-07-03):** 每张方法对比图**同时画** c1 oracle-ceiling 线与 c2
  baseline 线两条水平线(构成一条"性能带"),每个方法按 **c2→c1 gap-closed %** 标注(即离 baseline
  多远、离 ceiling 多近),让"缩小了多少差距"一眼可读。
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

### Cluster F — Surgical force-sequence priors / recorded-force datasets
> **existence-only 规则:** 本簇**只登录确实存在**的手术力序列先验 / 已记录力数据集来源;
> **找不到就必须明说"没有"**(report absence as absence),不得虚构。running survey 见
> `experiments/2026-07-03_force-prior/LITERATURE.md`(若一无所获,该文件须明确写"暂无可用来源")。
> 用途:为 §6.6 的合理力规格(幅值包络/rate/dwell/contact on-off)与 `is_plausible()` 验收门提供参考。
- （占位)运行中的文献/数据集调查:`experiments/2026-07-03_force-prior/LITERATURE.md`——**待填**;
  在填入任何来源前,本簇视为"尚无已核实来源"。

---

## 11. Decision & update log

- **2026-06-14/15** — 部署 8-cond×5-fold CV;接 W&B;keep_last=1;commit `8b5081d`(W&B + report_cv.py + keep_last)。
- **2026-06-15/16** — 迁移配方赛马(4 变体×5 fold,isolated worktree);结论:配方全打平,非瓶颈。
- **2026-06-16** — 域差量化:外观差为主因(100% 可分,~6× 多样性差)。写 `RESEARCH_DIRECTION.md`,确立
  "修测量 → 闭外观差(数据侧) → 架构最后"的方向;新增 `analyze_domain_gap.py`/`kshot_transfer.py`。
- **2026-06-21** — 用户用 `/goal` 设定四大科研目标(RQ1–4)+ scaling-law 探问;5 簇文献检索完成;
  建立本北极星文档 `RESEARCH_GOAL.md`(整合技术栈 + 路线图 + 可视化规范);commit `adf29a6`提交文档+诊断脚本。
- **2026-06-21 (Phase 0 起步)** — 实现 train-only 标注安全光度增广(`transforms.py` `PhotometricAugment` + `loader.py` train/eval transform 分离),GPU-free 测试全过(默认禁用、行为不变)。未提交。下一个 GPU-free 单元:RQ3 损失改造(学习式不确定性加权,替代固定 λ)。待 GPU 授权后:启用增广重跑 c1–c4 + 扫验证集扩大/力归一化。
- **2026-06-21 (autonomous run, polls #1-15)** — GPU 恢复后启动全自动 campaign（1h 轮询）。**结果：(a) k-shot 符合假设**：synt-pretrain 在 k=1/2/4 均优于 ImageNet（0.582/0.563/0.309 vs 0.755/0.590/0.340，-23%/-5%/-9%），幅度温和但符号一致（k=8/16 进行中）。**(b) c1 光度增广 A/B**：magMAE 0.2316±0.073 → 0.2283±0.064（均值 -1.5% 在噪声内、std -13% 略稳、角度 23.9→26.0°）→ **光度增广对 real-scratch 近似中性**，非决定性杠杆（与诊断一致：3-序列 val 噪声主导，真正杠杆是闭合外观差）。图：`cv5_aug/report/aug_ab_c1.png`、`kshot/report/kshot_curve.png`。RQ3 损失 ablation（c1 uncertainty）已启动。commits adf29a6/493d46c/c3ed62f/aa11317/48d7817/4d922ad。
- **2026-06-22 (k-shot 30/30 完成 + 校准裁定, workflow wg5f1eew9)** — **Gate-1 = HOLD_fix_measurement_first**。k-shot 终值(n=3, magMAE): synt vs imagenet k=1 0.582±0.211/0.755±0.015, k=2 0.563/0.590, k=4 0.309/0.340, k=8 0.325/0.306, k=16 0.230/0.239。**严谨结论(对抗审查):合成先验方向一致(4/5 k 均值更低)但统计不显著**(各 k 误差带重叠;n=3 置换下限 p=0.25;pooled 9/15 ≈ 抛硬币);**k=1 的 -23% 优势 ~80% 来自单个幸运 draw(rep0=0.284 vs 0.744/0.718),去掉后仅 -4.5%,是 198× 方差故事**;收益仅限幅值,角度反而略差;k=16 收敛到全数据 c1(0.232)。'不显著'=欠功效未定,非无效。**aug A/B**:光度增广=温和正则(std -20~27%,均值中性)。**元结论:测量噪声(H0,3-seq val→epoch-50 永不 early-stop)主导一切,修测量前无法对合成价值定论。** 推荐:先修测量(扩 val、力归一化、多 fold/多 init、k∈{1,2,4} 加到 ≥5-8 draws)再重判 Gate-1;render-DR 小规模 pilot 作低成本探针可并行(验证渲染域随机化是否缩小外观差),但不上 Phase 2 全量管线。RQ3 c1-unc 部分均值 0.201 vs fixed 0.232(有希望,待 5 折齐 + c3-unc)。图:kshot/report/kshot_curve.png、cv5_aug/report/aug_ab.png。
- **2026-06-22 (render-DR pilot DESIGNED but BLOCKED on render env, workflow w7lte239u)** — 设计+对抗审查完成,得到最小、config 门控、标注安全的渲染域随机化规格(详见 task 输出 w7lte239u)。**核心:** 注入点 = `Deform_post/dpost/render.py` 的 `render_fixed_camera_sequence`(调用方 replay.py:186 / main.py:298);新增 `RandomizeConfig(enabled=False)` 到 dpost/config.py(默认关=行为不变)。**可行(legacy Visualizer):** 每帧随机 `opt.background_color` + 器官 `mesh.paint_uniform_color`/vertex_colors(配 `opt.mesh_color_option=Color`)+ 对保存的 PNG buffer 做后处理(亮度/对比/gamma/高斯噪声/暗角,纯 numpy)。**不可行(legacy):** 随机光照方向/强度、PBR 材质 → 需 OffscreenRenderer 重写。**标注安全:** 力标签来自上游 forces CSV、与像素无关,只要相机/几何/尺寸/FOV-crop 不变即安全。**阻塞:** 本 Linux 容器 open3d 0.19 在/opt/venv 可导入,但 legacy Visualizer(OSMesa 缺失)与 OffscreenRenderer(eglInitialize failed)**都无法 headless 渲染** → 渲染需 Windows/GPU 渲染容器(C:/ 路径)。**故 render-DR pilot 无法在此自动跑;需用户在渲染环境执行,或授权容器 EGL/OSMesa 配置。** 未提交未验证渲染代码。
- **2026-06-22 (RQ3 c1 uncertainty-weighting 5/5)** — **最强正向信号(校准):** c1-fixed(λ=0.4) magMAE 0.2316±0.073 → **c1-uncertainty(学习式 Kendall) 0.1899±0.037**:均值 **-18%**、方差 **-49%**、angle 23.9→23.1°。逐折:不确定性加权专门救回 fixed 下最差的 fold1(0.288→0.217)/fold2(0.334→0.210),好折不变 → 既降均值又稳。机制:下调噪声样本权重→对 H0 的 val 噪声更鲁棒。**但 n=5 配对 t≈-1.80,p≈0.15 尚不显著**;降方差是稳健部分。这是 campaign 至今唯一同时改善均值+方差的杠杆,且正好对症 H0。c3-unc(mixed)进行中验证是否泛化。图:cv5_unc/report/rq3_loss_ab.png。绘图器 plot_loss_ab.py。
- **2026-06-23 (RQ3 COMPLETE: c3-unc 5/5)** — uncertainty weighting on MIXED: c3-fixed 0.2041±0.0535 → c3-unc 0.2058±0.0429 (mean +0.8% = NEUTRAL/within-noise, std -20%, angle 24.9→24.1°). **So the uncertainty-weighting MEAN win is specific to the noisiest real-scratch regime (c1 -18%); on mixed (already more data/diversity, less overfit) the mean benefit vanishes, leaving only the variance reduction.** RQ3 verdict: learned uncertainty weighting is a robust STABILIZER (std down in both: c1 -49%, c3 -20%) whose accuracy gain concentrates where noise is worst — reinforces the H0 meta-finding (noise is the binding constraint). Needs the measurement fix + more seeds to confirm the c1 mean win (n=5, p≈0.15). AUTONOMOUS CAMPAIGN COMPLETE — all planned experiments done; loop stopped. Awaiting user on the 2 levers (measurement-overhaul, render-DR env).

- **2026-07-03 (RE-SCOPE — professor + owner; OVERRIDES earlier framing)** — 项目被重新定标为
  **zero-real-label sim→real domain adaptation**。**本条目覆盖本文档与 `RESEARCH_DIRECTION.md`
  中所有更早的"合成增强"(synthetic-as-augmentation)框架与渲染环境(Linux headless-GL block)措辞。**
  - **(a) 教授的方向重定:** 框架不是"用合成放大稀缺真实",而是 **zero-real-label transfer**——
    **只用合成 FEM 数据训练(训练集零真实力标签),再迁移到真实**,因为人体手术永远无法采集力
    ground-truth;无标注真实**图像**可用于自适应。**c2(synth-only zero-shot,无自适应)= baseline /
    研究起点(其差表现是预期,不是缺陷);c1(real-scratch)= ceiling / oracle。** 主指标 =
    **gap-closed %** = (c2 − method)/(c2 − c1)。自适应要在**输入(图像)+ 输出(力)两端**做。
    **此约束不得放松。**
  - **(b) 用户 round-1 更正:** ① 推理 I/O **固定**为图像进→3D 力向量出,任何在推理时需要深度/
    机器人状态/额外传感器的方法**出局**;② 再次确认 c1=ceiling、c2=baseline;③ **数字孪生不是问题**——
    twin 力是一个 glimpsed-but-valid 的经验参考/锚点(真实分布里的一个样本,不是完整分布),
    **force-prior 必须被调查**,**随机脱开孪生的力是危险的**(不可测→错误 FEM 形变→污染"图像→力"监督);
    ④ 外观(appearance)只是**一个**可组合因子;**视角多样性(viewpoint)+ 接触点多样性(contact-point)
    被低估、尚未单独消融**。
  - **(c) 用户 round-2 更正:** ① force-prior 文献调查是 **existence-only**(有就登录、没有就如实记"没有",
    见 §6.6 / Cluster F / `experiments/2026-07-03_force-prior/LITERATURE.md`);② **所有渲染在用户控制的
    Windows 机上执行,不可协商,且可检视/可中断**;**Linux 容器 headless-GL block 已作废(MOOT),
    绝不再提"修容器 GL"**;退役的 `sim2vfp.py`(git `ba4501c`)是手工可控性保证的记录。
  - **本条目落地的文档改动:** 标题/§1 mission/§2 I/O 硬约束/§3 twin-not-the-problem + 真实标签不进训练/
    §4 RQ 重述(RQ1=输入对齐三因子、RQ2=UDA、新增 RQ-force、RQ★去混合比)/§5(ROOT 重述、H1 拆 H1a/b/c、
    新增 H5)/§6.3(Windows 渲染硬约束)/§6.5(去真实标签、改 UDA 主线)/新增 §6.6 force-prior/
    §7 读表框架 + conclusion-1 重述 + render-DR RESOLUTION + GPU 事实更新/§8(force-prior EARLY 门 +
    factor-decomposition + Windows 渲染三修 F1/F2/F3 + Phase 0 降级 + Phase 5 去混合比)/§9(ceiling/baseline
    双线带)/§10 新增 Cluster F。
  - **服务器现况(2026-07-03 核实):** GPU = **4× NVIDIA A100 80GB PCIe(现空闲)**——旧"H100 让给同事、
    此后困在 3 张 Ada"一说**已作废**。盘上数据:`DataFlow/Deform_post/preprocessed/datasets/{real
    (31 seq / 52522 samples),mixed(62 seq / 105044)}` + `KiDKNet/splits/cv5`;**无 feature_cache**
    (Track B 需重算 ConvNeXt 特征);primary 渲染 + `labels.csv` 仅 Windows 侧。已有 Track-A 力包络工具
    `experiments/2026-07-03_force-prior/force_envelope.py`(读 `.pt` 各层原始力 → 经验包络 +
    `is_plausible()` 验收门)。

> **决策待定(需用户拍板的方向选择;渲染环境问题已 DECIDED = Windows,不再列):**
> - **force-prior 调查的排序**:existence-only 文献/数据集调查何时开跑,与因子消融如何排先后?
> - **factor-decomposition 消融的排序**:外观/视角/接触点/力真实性四因子 isolate-then-combine 的先后与预算?
> - **Track B 需要 feature_cache 重算**:盘上无缓存,须先 `precompute_features` 才能跑冻结特征 + UDA。
