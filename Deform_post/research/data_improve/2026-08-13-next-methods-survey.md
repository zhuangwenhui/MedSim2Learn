# 数据侧下一步方法调研：零真实标签 Sim-to-Real 力回归迁移

- 日期：2026-08-13
- 任务背景：腹腔镜肾脏视频帧 → 三维接触力向量回归（image-to-force regression）；训练仅使用合成 FEM 渲染数据，真实标签（labels）绝不进入训练环节；未标注真实图像可用。
- 现状基线（冻结协议 c2-baseline / c1-ceiling）：纯合成训练 magMAE 1.357 N，真实监督上限 0.232 N；白渲染基线弥合率 0%；外观域随机化（domain randomization，域随机化）弥合 39.6%；叠加接触点多样性弥合 60.6%。
- 已实证排除（本项目内）：CORAL 训练损失（零效果）、光度学训练时增强（photometric train-time augmentation，负效果）、Tent（ConvNeXt 无 BatchNorm，不适用）。
- 残余差距画像：镜面/湿润高光（specular/wet highlights）、光学模糊（optical blur）、传感器噪声（sensor noise）、更丰富的颜色异质性（紫斑/脂肪）、致密毛细血管层；合成/真实特征线性可分性（linear separability）仍为 100%。
- 渲染栈约束：Windows / Open3D 旧版可视化器（legacy visualizer，平面着色，无可编程光照）；Linux 训练服务器无 headless GL；离线数据生产可接受；回归网络为 ConvNeXt-L（LayerNorm 归一化）。
- 载体准入规则（硬约束）：仅 JCR Q2 及以上期刊，或 CCF-A / CCF-B 级会议与期刊（含任务指定认可的 ICRA / IROS / RA-L / ICLR 等）；MDPI、Hindawi、Frontiers 系一律排除。每条引用均标注 载体+年份+级别；无法核实者不计入。

---

## 摘要

围绕"离线数据改造 + 无标签利用"两条主线，本调研筛得 9 个通过载体审查的候选方法，覆盖六类：(a) 无配对图像翻译、(b) 物理化外观/镜面高光建模、(c) 域随机化扩展（含光照的屏幕空间补救）、(d) 无标签真实帧的回归自训练、(e) 兼容 LayerNorm 的免源/测试时适应、(f) 离线频域对齐。

**Top-3 推荐（按建议实施顺序排列）：**

1. **M3 — FDA 傅里叶域适应（Fourier Domain Adaptation）**（CVPR 2020，CCF-A）。零训练、纯离线的低频幅值谱替换，一至两天即可完成数据生产并跑通冻结协议门槛。它直接攻击全局颜色/光照统计——正是线性可分性 100% 的最可能来源——且与其余一切方法可叠加。作为"快速试金石"应最先执行：若廉价的一阶/二阶统计对齐即可显著弥合差距，则后续昂贵方法的预期收益需重新估计。
2. **M1 — 无配对图像翻译（CUT/CycleGAN 系）**（CUT，ECCV 2020，CCF-B；外科同场景先例 Pfeiffer 等，MICCAI 2019，CCF-B；Rivoir 等，ICCV 2021，CCF-A）。这是与本项目场景重合度最高的路线：Pfeiffer/Rivoir 两工作正是"腹腔镜合成渲染 → 真实腹腔镜外观"的迁移，且证明了平面着色级合成输入即可训练。一次翻译同时注入颜色异质性、毛细血管纹理与高光统计，是主力押注。
3. **M7 — 面向回归的自训练/伪标签（self-training / pseudo-labeling）**（PnP-GA，ICCV 2021，CCF-A；RegDA，CVPR 2021，CCF-A）。唯一直接消费未标注真实帧的正交路线：以合成训练的模型集成在真实帧上产生伪力标签，用集成分歧与时序物理约束过滤后回灌训练。它不与外观改造竞争，可叠加于 M1/M3 之上，并且是把"未标注真实图像可用"这一被闲置的资源变现的唯一 Top 级手段。

次优待命：M4（屏幕空间重打光与镜面高光合成，域随机化线内的定向补丁）、M6（ConvNeXt V2 FCMAE 无标签预训练，基础设施级押注）。

---

## 候选方法明细

### M1 · 无配对图像翻译（GAN 系）：合成帧的离线真实化

类别：(a) 无配对图像到图像翻译（unpaired image-to-image translation）

**1) 文献锚点（载体均已逐条核实）**
- Zhu et al., "Unpaired Image-to-Image Translation using Cycle-Consistent Adversarial Networks" (CycleGAN) — **ICCV 2017，CCF-A**。
- Park et al., "Contrastive Learning for Unpaired Image-to-Image Translation" (CUT) — **ECCV 2020，CCF-B**。
- Pfeiffer et al., "Generating Large Labeled Data Sets for Laparoscopic Image Processing Tasks Using Unpaired Image-to-Image Translation" — **MICCAI 2019，CCF-B**。外科同场景先例：合成肝脏腹腔镜渲染 → 真实腹腔镜外观，全标签保留。
- Rivoir et al., "Long-Term Temporally Consistent Unpaired Video Translation from Simulated Surgical 3D Data" — **ICCV 2021，CCF-A**。外科视频级先例：利用仿真几何实现跨视角长期一致翻译。
- 辅证：Lin et al., "LC-GAN: Image-to-image Translation Based on GAN for Endoscopic Images" — **IROS 2020（任务指定认可会议；注：CCF 官方目录中 IROS 为 C 类，故仅作辅证，不作主锚）**。

**2) 机制与针对残差的理由**
生成器学习"合成渲染分布 → 真实帧分布"的映射，判别器以真实语料为参照施压；CUT 以补丁级对比学习（patchwise contrastive learning）替代循环一致性，训练更轻且结构保持更强。翻译在像素域一次性注入真实语料的颜色异质性（紫斑/脂肪）、毛细血管纹理、湿润高光统计与整体色调——恰好覆盖我们四项残余差距中的三项。力标签绑定于几何/接触状态而非外观，翻译不触碰标签，与零真实标签约束完全兼容；Pfeiffer 工作证明平面着色级合成输入（与我们 Open3D 旧版渲染同档）足以支撑翻译训练。

**3) 对本栈的适配性与工程成本：中**
- 完全离线：twin_full 渲染帧与 real_full 真实帧（均可取 256px）即为两侧训练语料，无需改动渲染器。
- CUT 官方 PyTorch 实现成熟，单卡数日内可训练；翻译 5 万余帧为一次性批处理，H100 服务器过夜可完成。
- 产物落位为新数据域（见"落地路线建议"），完全符合 DataFlow 分层规约。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：内容幻觉——生成器可能改写与力相关的形变/接触视觉线索（判别器只关心"像真的"，不关心"力对不对"）。缓解：优先 CUT（结构保持强于 CycleGAN），并对翻译前后帧做结构一致性抽检（边缘图/SSIM 阈值）。
- 风险二：真实语料量偏小导致判别器过拟合、模式坍缩。
- 预注册门槛：冻结 c2/c1 协议下的 gap-closed %（magMAE）为唯一胜负判据；前置观测指标（线性可分性探针下降、FID）仅作诊断，依业主裁定不构成胜利证据。结构一致性抽检作为数据准入前置门（不达标的翻译批次不得进入训练集）。

---

### M2 · 结构条件扩散翻译（ControlNet / SDEdit 系）

类别：(a) 扩散模型（diffusion model）路线的 sim-to-real 翻译

**1) 文献锚点**
- Zhang, Rao, Agrawala, "Adding Conditional Control to Text-to-Image Diffusion Models" (ControlNet) — **ICCV 2023，CCF-A（Marr Prize 最佳论文）**。
- Meng et al., "SDEdit: Guided Image Synthesis and Editing with Stochastic Differential Equations" — **ICLR 2022（任务认可清单内顶级会议；CCF 目录未收录，与 NeurIPS/ICML 同档对待）**。
- 注：外科专用扩散先例（SimuScope、IJCARS 上的 Stable Diffusion 内镜生成等）均因载体不达标被排除，见"排除记录"；本候选仅以上述两个通用方法锚点成立。

**2) 机制与针对残差的理由**
在真实肾脏帧语料上以 LoRA 微调 Stable Diffusion 获得"真实腹腔镜外观先验"，再以 ControlNet 施加空间条件（深度图/法线图/边缘图，均可由我们的 FEM 网格离线导出）锁定几何结构，对每张合成帧做条件重生成；或以 SDEdit 方式对合成帧加噪至中等强度后逆向去噪，"外观重刷、结构保留"。扩散先验对高频纹理（毛细血管层）、局部高光与颜色异质性的生成质量普遍高于 GAN 系，是对残余差距中"最难的两项"（毛细血管、丰富颜色异质）的最强火力。

**3) 对本栈的适配性与工程成本：高**
- 完全离线，与渲染器解耦；深度/法线条件图可在 Windows 侧随渲染一并导出。
- 成本在于：LoRA 微调 + ControlNet 训练 + 5 万帧批量采样（即便用加速采样器也数倍于 GAN 推理）；工程链条长（SD 权重管理、条件图对齐、批处理管线）。
- 建议定位为 M1 的升级备选：若 M1 出现"翻译质量不足以弥合毛细血管/颜色异质"的明确证据，再启动。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：结构幻觉比 GAN 更隐蔽（生成先验强，可能"想象"出不存在的器械/组织边界），直接污染力—外观对应关系。缓解：条件图一致性核查（生成帧重估深度/边缘与条件图比对）作为准入前置门。
- 风险二：吞吐与算力成本高，迭代周期长，failed-fast 特性差。
- 预注册门槛：与 M1 相同的冻结协议 gap-closed % 判据；另加逐批结构一致性通过率阈值（预先定值，如 ≥95% 帧通过边缘一致性检查方可入库）。

---

### M3 · FDA：离线傅里叶域低频幅值替换

类别：(f) 频域/特征统计对齐（离线数据操作）

**1) 文献锚点**
- Yang, Soatto, "FDA: Fourier Domain Adaptation for Semantic Segmentation" — **CVPR 2020，CCF-A**。

**2) 机制与针对残差的理由**
对每张合成帧做二维 FFT，将其幅值谱（amplitude spectrum）的低频窗口替换为随机抽取的一张真实帧的对应低频幅值，相位谱（phase spectrum，承载结构/语义）原样保留，逆变换即得"真实风格化"合成帧。零训练、零参数（仅窗口比例 β 一个超参）。低频幅值恰好编码全局色调、光照分布与低频颜色异质——这正是"线性可分性 100%"最廉价的解释源；对紫斑/脂肪等低频色块有直接注入能力。原论文即在"合成 → 真实"语义分割迁移上验证（GTA5→Cityscapes）。

**3) 对本栈的适配性与工程成本：低（全候选中最低）**
- NumPy/PyTorch 数十行代码；对 256px 序列化前的帧批量处理，CPU 亦可承受，一天内完成数据生产。
- 每张合成帧可与多张真实帧配对生成多个风格化副本，兼具扩增作用。
- 完全不触碰标签与渲染器。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：β 过大产生振铃伪影（ringing artifacts）与"鬼影"叠加；需在小 β（0.01–0.09，原文量级)网格上扫。
- 风险二：只对齐低频统计，无法注入毛细血管高频纹理与锐利镜面高光——预期弥合有限，属"快速摘取低垂果实"而非终局方案。
- 预注册门槛：冻结协议下 β∈{0.01, 0.05, 0.09} 三点小网格各训一次，任一点 gap-closed % 相对 60.6% 基线取得预定增量（建议 ≥5 个百分点）方视为有效；线性可分性探针下降仅作旁证记录。

---

### M4 · 屏幕空间重打光与镜面高光合成（G-buffer 延迟着色的离线补救）

类别：(b) 物理化外观/高光建模 +（c) 域随机化的光照维度补救

**1) 文献锚点**
- Tobin et al., "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World" — **IROS 2017（任务指定认可会议；注：CCF 官方目录中 IROS 为 C 类）**。域随机化奠基工作，光照随机化为其核心维度之一。
- Prakash et al., "Structured Domain Randomization: Bridging the Reality Gap by Context-Aware Synthetic Data" — **ICRA 2019，CCF-B**。将随机化参数锚定到真实场景统计分布（与我们"颜色锚定真实语料经验支撑"的既有做法同构）。
- Daher, Vasconcelos, Stoyanov, "A Temporal Learning Approach to Inpainting Endoscopic Specularities and Its Effect on Image Correspondence" — **Medical Image Analysis (MedIA) 2023，JCR Q1**。提供内镜镜面高光的检测/掩膜方法与统计画像来源，可反向用于"从真实语料采集高光统计"。

**2) 机制与针对残差的理由**
Open3D 旧版可视化器虽无可编程光照，但可分通道导出 G-buffer（几何缓冲）：反照率通道（现行彩色渲染）、法线通道（将网格法线编码为顶点色渲染一遍）、深度通道（`capture_depth_float_buffer`）。此后在 NumPy/PyTorch 中做离线延迟着色（deferred shading）：随机化光源位置/强度，按 Blinn-Phong 或 Cook-Torrance BRDF 叠加漫反射调制与镜面高光叶瓣，并以"湿润度贴图"控制高光锐度。用 Daher 等的高光检测在真实语料上统计高光的面积/强度/空间频率分布，将随机化参数锚定其上（结构化域随机化思想）。该路线定向补齐两项残差：镜面/湿润高光缺失，以及旧版渲染器"光照无法随机化"的既知盲区。

**3) 对本栈的适配性与工程成本：中**
- 全部在自有栈内完成，无新训练框架；法线/深度通道导出仅需在现有渲染脚本上加一遍 pass。
- 着色计算为纯数组运算，5 万帧批处理数小时级。
- 与既有纹理烘焙域随机化管线自然衔接（同为"渲染后处理"層），可作为其新维度并入 8 条件实验框架。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：合成高光"假"——形状/运动与真实湿润高光不符时，可能反而放大域差（判别性捷径）。缓解：参数分布严格锚定真实统计，且以线性可分性探针做前置筛查。
- 风险二：FEM 网格法线偏粗，屏幕空间高光的几何细节上限受限。
- 预注册门槛：先以探针（合成/真实特征线性可分性）做廉价前置门——若加高光后可分性不降反升，立即止损；通过者进入冻结协议评测，以 gap-closed % 定胜负。

---

### M5 · 相机管线退化建模：标定化模糊 + 泊松-高斯噪声注入

类别：(b)/(c) 物理化成像模型（离线数据生产，非训练时随机增强）

**1) 文献锚点**
- Brooks et al., "Unprocessing Images for Learned Raw Denoising" — **CVPR 2019，CCF-A**。逆 ISP（图像信号处理器）管线合成真实分布的传感器退化。
- Foi et al., "Practical Poissonian-Gaussian Noise Modeling and Fitting for Single-Image Raw-Data" — **IEEE TIP 2008，CCF-A 期刊 / JCR Q1**。单图估计信号相关噪声参数（泊松光子项 + 高斯读出项）。

**2) 机制与针对残差的理由**
用 Foi 方法直接从真实肾脏帧估计该内镜相机的泊松-高斯噪声参数，再按 Brooks 的"unprocess → 加噪 → reprocess"路径将合成帧退化到与真实语料同一成像分布；同时以标定化的点扩散函数（PSF，离焦/运动模糊核，可由真实帧频谱包络估计）注入光学模糊。直接针对"光学模糊 + 传感器噪声"两项残差。关键区别于已判负的光度学训练时增强：这里是一次性、参数标定于真实语料的离线数据生产，不是训练循环内的随机抖动——分布是"对准的"而非"撑宽的"。

**3) 对本栈的适配性与工程成本：低**
- 纯后处理脚本，无训练；噪声/模糊参数估计与批量注入合计数日内完成。
- 可与 M3/M4 在同一离线后处理管线串联（先风格/高光、后模糊/噪声，符合成像物理顺序）。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：与光度学增强判负同源的风险——若域差主因不在噪声/模糊，此项收益趋零；其价值在于廉价且可与他法串联。
- 风险二：真实帧已过 ISP（非 raw），Foi 估计存在偏差；退化参数估错会引入新偏移。
- 预注册门槛：作为独立单变量条件跑冻结协议（尊重"一次隔离一个变量"的项目规约）；预定增量不达（建议 ≥3 个百分点 gap-closed）则记为无效并归档，不与其他方法捆绑上车。

---

### M6 · 未标注真实帧上的掩码自编码预训练（FCMAE 域自适应预训练）

类别：(d)/(f) 无标签真实数据利用（特征空间层面，与数据侧紧耦合）

**1) 文献锚点**
- Woo et al., "ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders" — **CVPR 2023，CCF-A**。FCMAE（全卷积掩码自编码器）使 ConvNeXt 系可直接做 MAE 式自监督预训练。
- Tian et al., "Designing BERT for Convolutional Networks: Sparse and Hierarchical Masked Modeling" (SparK) — **ICLR 2023 Spotlight（任务认可清单内顶级会议；CCF 目录未收录）**。任意卷积网络的稀疏掩码建模，同类可替换实现。

**2) 机制与针对残差的理由**
以 ImageNet FCMAE 预训练权重为起点，在"未标注真实帧 + 合成帧"混合语料上继续掩码自编码预训练（domain-adaptive pretraining，域自适应预训练），迫使骨干在同一重建任务下同时编码两域外观，从表征层面压缩域距离；随后照常在合成标签上微调回归头。它不逐项修补外观残差，而是让骨干对"高光/噪声/颜色异质"等表面统计不再敏感——是对"线性可分性 100%"的釜底抽薪式攻击，且严格零标签。

**3) 对本栈的适配性与工程成本：中偏高**
- 训练在 H100 服务器进行，无渲染侧改动；FCMAE 官方实现可直接用于 ConvNeXt-L。
- 成本在预训练算力与调度（数万帧继续预训练，数日 GPU 时）；数据侧仅需把真实帧（无标签）打包为预训练语料，注意管线上物理隔离 labels.csv。
- 风险点：真实帧约 5 万量级，从头 MAE 不可行，必须走"继续预训练"路径。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：继续预训练可能灾难性遗忘 ImageNet 通用特征，反伤回归微调起点。缓解：低学习率、短程预训练 + 与基线权重的插值消融。
- 风险二：重建任务与力回归目标错位，特征改善不传导到 magMAE。
- 预注册门槛：冻结协议 gap-closed % 为判据；同时预注册"预训练不得读取任何标签文件"的管线审计（脚本级 assert 真实域输入不含标签列）。

---

### M7 · 面向回归的自训练/伪标签：集成分歧过滤 + 时序物理约束

类别：(d) 无标签真实图像的自训练（self-training / pseudo-labeling，伪标签）

**1) 文献锚点**
- Liu et al., "Generalizing Gaze Estimation with Outlier-guided Collaborative Adaptation" (PnP-GA) — **ICCV 2021，CCF-A**。纯回归任务（视线角回归）上、仅用未标注目标域数据、以网络集成的离群引导协同学习完成域适应，即插即用。
- Jiang et al., "Regressive Domain Adaptation for Unsupervised Keypoint Detection" (RegDA) — **CVPR 2021，CCF-A**。系统论证分类式域适应在回归上失效的原因，并给出回归专用的对抗回归器方案。
- 辅证：Tarvainen, Valpola, "Mean Teachers are Better Role Models" — **NeurIPS 2017，CCF-A**。师生一致性自训练的奠基工作。

**2) 机制与针对残差的理由**
用已有的合成训练模型（或 8 条件框架中的多个变体）组成集成，在未标注真实帧上前向产生伪力标签；以集成方差（回归任务的天然不确定度替身）与时序约束（力波形在视频内应平滑、幅值应落于物理可行域）双重过滤，仅保留高置信伪标签帧回灌训练学生模型，迭代一至两轮。该路线不修改外观，而是让模型直接在真实外观分布上"见过并拟合过"——对全部四项残差一并生效，且是消费未标注真实图像这一闲置资源的最直接方式。PnP-GA 证明该范式在纯回归、零目标域标签设定下成立。

**3) 对本栈的适配性与工程成本：中**
- 零渲染侧改动；伪标签生产即批量推理，服务器侧数小时。
- 与 KiDKNet 现有训练循环兼容（加一个混合数据加载与损失加权即可）。
- 必须的管线防火墙：伪标签产线与 real_full/labels.csv 物理隔离，评测方可读真实标签——建议以独立脚本 + 审计断言实现，杜绝标签泄漏嫌疑。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：确认偏误（confirmation bias）——初始模型 magMAE 尚有 ~0.7 N 级误差（60.6% 弥合后），伪标签系统性偏移会被放大固化。缓解：高阈值过滤（只取集成方差最低分位，如前 20%）、单轮起步、伪标签损失降权。
- 风险二：过滤后样本分布偏向"容易帧"（轻接触/小力），标签支撑收窄，magMAE 在大力段反而恶化。缓解：按力幅分桶配额采样。
- 预注册门槛：两级门——前置门：伪标签在真实评测集上的诊断性 magMAE（此处允许用真实标签做只读评测，不进训练）必须显著优于随机/常数基线且时序平滑度达标；主门：冻结协议 gap-closed % 增量。两门与过滤阈值均在启动前写死。

---

### M8 · 兼容 LayerNorm 的回归专用测试时适应：显著子空间对齐（SSA）

类别：(e) 免源域 / 测试时适应（source-free / test-time adaptation, TTA），无 BatchNorm 依赖

**1) 文献锚点**
- Adachi et al., "Test-time Adaptation for Regression by Subspace Alignment" (SSA) — **ICLR 2025（任务认可清单内顶级会议；CCF 目录未收录）**。回归专用 TTA：检出对输出显著的特征子空间，在子空间内做源/目标统计对齐并按显著性加权。
- Niu et al., "Towards Stable Test-time Adaptation in Dynamic Wild World" (SAR) — **ICLR 2023 Oral（同上）**。系统证据：TTA 的不稳定主因是 BatchNorm，batch 无关归一化（LayerNorm/GroupNorm）下更稳——为 ConvNeXt-L 栈上做 TTA 的可行性背书（其熵最小化目标本身为分类专用，不直接采用）。

**2) 机制与针对残差的理由**
Tent 因无 BN 而出局后，SSA 是现存最贴合我们设定的替代：训练侧缓存合成域特征的子空间统计（一次性、离线），部署/评测侧仅用未标注真实帧把骨干特征在"对输出显著"的低维子空间内拉回源统计。回归专用设计规避了熵最小化类方法对类别概率输出的假设；全程零标签。它不改数据本身，但与数据侧改进共享同一评测协议，且能吃掉外观方法清不掉的最后一段特征级偏移。

**3) 对本栈的适配性与工程成本：低偏中**
- 无渲染改动、无数据再生产；在 KiDKNet 推理侧加特征统计钩子与轻量适应步。
- 我们的评测为离线数据集而非在线流，可将 SSA 以"免源域适应"（source-free adaptation）方式在整个未标注真实集上一次性跑完，避开在线不稳定性。
- 注意与冻结协议的关系：TTA 修改的是"评测时的模型"，需在预注册中明确其作为独立条件（c-TTA）与数据侧条件分开记账，避免混淆归因。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险一：子空间统计由合成域估计，若合成特征本身偏斜（可分性 100% 即警号），"拉回源统计"未必拉向正确回归面。
- 风险二：按项目裁定，特征级方法（CORAL）已有零效果前科；SSA 与 CORAL 的差异（显著性加权 + 子空间限定 + 测试时机）需被明确验证而非默认成立。
- 预注册门槛：冻结协议下与不加 TTA 的同权重模型严格对照；预定增量不达即止损。作为"数据侧主线之外的独立支线"记账，不占用数据改进线的胜利判据。

---

### M9 · C-Mixup：标签相似度加权的回归混合增强

类别：(d)/(f) 回归感知的数据侧增强（与数据生产紧耦合的训练侧轻量件）

**1) 文献锚点**
- Yao et al., "C-Mixup: Improving Generalization in Regression" — **NeurIPS 2022，CCF-A**。

**2) 机制与针对残差的理由**
经典 mixup 在回归上会因均匀配对制造标签语义错误的插值样本；C-Mixup 按力标签相似度加权采样配对（相近力值的帧才互混），在保持标签一致性的前提下平滑特征—标签流形，实证改善回归的分布外（OOD）稳健性。对我们而言另有一层针对性：可跨渲染域配对（twin 帧与 FDA/翻译风格化帧互混），在合成数据内部制造外观连续体，钝化模型对单一渲染风格的过拟合——间接攻击线性可分性。

**3) 对本栈的适配性与工程成本：低**
- 数据加载器层数十行改动；与任何数据条件正交可叠加。
- 无渲染、无新数据生产。

**4) 风险 / 失效模式 / 预注册门槛**
- 风险：像素级混合可能糊化接触区形变线索（力的视觉证据），对小力段回归有害；带宽超参敏感。
- 预注册门槛：作为单变量条件在冻结协议下评测；增量微弱（<2 个百分点）即不并入主线，避免复杂度积债。

---

## 落地路线建议（映射到现行管线）

现行管线：FEM 冻结/接触标注（inputs/annotations）→ Open3D 旧版渲染（primary/twin_full，800px）→ 256px 序列化 `.pt`（preprocessed/sources/synt/twin）→ 数据集装配（preprocessed/datasets，硬链接）→ `author_cv_splits.py` 授权切分 → KiDKNet（ConvNeXt-L@256²，圆形遮罩）训练于 H100 服务器。序列 04 依业主裁定永久排除。

**阶段一（本周可完成，Windows 本地）：M3 FDA 试金石**
1. 新增离线脚本：对 twin 渲染帧做 FDA 风格化（β 三点网格），真实参照帧从 real_full 图像目录随机抽样（只读图像，不触 labels.csv）。
2. 产物按 DataFlow 规约落位新域：`preprocessed/sources/synt/fda_b{β}/` → 装配 `datasets/synt/fda_b{β}/` → 以 `author_cv_splits.py` 重新授权切分（遵守"三处一致、宁重授权不搬移"规则）→ 新 KiDKNet 配置。
3. 服务器按冻结 c2/c1 协议训练评测，记录 gap-closed %。此结果同时为 M1/M2 的预期收益提供标定。

**阶段二（1–3 周）：M1 无配对翻译主线（建议独立 worktree 赛马位）**
1. 以 twin 256px 帧与 real_full 256px 帧为两侧语料训练 CUT；翻译全量合成帧，结构一致性抽检达标后落位 `preprocessed/sources/synt/cut/`。
2. 与阶段一同协议评测。若毛细血管/颜色异质仍是明显短板且 CUT 增量不足，再评估升级 M2（ControlNet/LoRA，需先导出深度/法线条件图）。
3. 依 2026-08-10 业主裁定：该线任何分支在拿到实证 gap-closed 增量前，严格本地，不并 master、不推远端。

**阶段三（与阶段二并行，服务器侧）：M7 回归自训练**
1. 用现有最优条件模型组集成，产伪标签 → 集成方差 + 时序平滑 + 力幅配额三重过滤 → 混合回灌训练。
2. 管线防火墙与两级门槛先行预注册（含"伪标签产线不可读 labels.csv"的脚本级审计）。
3. 该线与外观线正交，最终可在各自过门后做一次组合条件确认（仍遵守单变量先行、组合后验的项目规约）。

**机会性补丁（低成本、随主线穿插）：**
- M4 高光合成：渲染脚本加法线/深度 pass 后，作为 8 条件框架的新随机化维度，先过可分性探针前置门。
- M5 噪声/模糊标定注入与 M9 C-Mixup：各作为独立单变量条件小步验证，增量不达即归档。
- M6 FCMAE 预训练与 M8 SSA：分别作为"表征层"与"评测时"支线独立记账，不占数据改进线判据。

**统一胜负判据（全部候选共享）：** 冻结 c2-baseline / c1-ceiling 协议下的 magMAE gap-closed %。线性可分性下降、FID、目视验收均为诊断性旁证，依业主裁定不构成胜利证据。

---

## 排除记录（因载体质量或既有实证而剔除）

以下方法/文献在调研中出现且与主题相关，但按硬约束剔除，不计入候选与推荐：

1. **Kaleta et al., "Minimal data requirement for realistic endoscopic image generation with Stable Diffusion"** — 载体为 Int. J. Computer Assisted Radiology and Surgery（IJCARS，CCF-C，JCR 约 Q2/Q3 边缘）。方法本身（LoRA 微调 SD 做内镜翻译）已被 M2 以 ControlNet/SDEdit（ICCV 2023 / ICLR 2022）为合格锚点吸收。
2. **Martyniak (Kaleta) et al., "SimuScope: Realistic Endoscopic Synthetic Dataset Generation through Surgical Simulation and Diffusion Models"** — 载体为 WACV 2025（不在 CCF A/B 及任务认可清单内）。思路同上，作背景参考不作锚点。
3. **"Interactive Generation of Laparoscopic Videos with Diffusion Models"** — 载体为 DGM4MICCAI 2024 研讨会（workshop 卷，非 MICCAI 主会），不达标。
4. **内镜高光检测/去除类 MDPI 文献**（如 Sensors 等所载多篇镜面反射去除工作）— 按出版商排除规则整体剔除；高光统计采集改以 Daher 等 MedIA 2023（JCR Q1）为锚。
5. **胶囊内镜高光去除、亮度分类去高光等仅见于 arXiv/低档载体的工作** — 无合格载体版本可核实，剔除。
6. **既有实证排除项（非载体原因，为完整性重列）：** CORAL 训练损失（本项目零效果）；光度学训练时随机增强（本项目负效果；注意与 M5 的"标定化离线退化"在机制上的区别已在 M5 节说明）；Tent（ICLR 2021，依赖 BatchNorm，ConvNeXt 无 BN，不适用——其"免源 TTA"生态位由 M8 SSA 承接）。
7. **载体级别备注：** LC-GAN（IROS 2020）与 Tobin et al.（IROS 2017）按任务指定认可清单收入，但 CCF 官方目录中 IROS 为 C 类，故仅作辅证/背景锚点，未作任何候选的唯一主锚；两处均已在正文标注。

---

## 引用总表（载体逐条核实记录）

| 编号 | 文献 | 载体 / 年份 / 级别 | 核实方式 |
|---|---|---|---|
| R1 | Zhu et al., CycleGAN | ICCV 2017，CCF-A | 公开会议论文集（周知条目） |
| R2 | Park et al., CUT | ECCV 2020，CCF-B | Springer LNCS 12354 + 官方仓库 |
| R3 | Pfeiffer et al., 腹腔镜无配对翻译 | MICCAI 2019，CCF-B | dblp + Springer LNCS 11768 |
| R4 | Rivoir et al., 手术视频长期一致翻译 | ICCV 2021，CCF-A | ICCV Open Access + dblp |
| R5 | Lin et al., LC-GAN | IROS 2020（任务认可；CCF-C） | IEEE Xplore/ACM DL |
| R6 | Zhang et al., ControlNet | ICCV 2023，CCF-A（Marr Prize） | ICCV Open Access |
| R7 | Meng et al., SDEdit | ICLR 2022（任务认可顶会） | ICLR 官方虚拟会议页 |
| R8 | Yang & Soatto, FDA | CVPR 2020，CCF-A | CVPR Open Access |
| R9 | Tobin et al., 域随机化 | IROS 2017（任务认可；CCF-C） | dblp + ACM DL |
| R10 | Prakash et al., 结构化域随机化 | ICRA 2019，CCF-B | ACM DL（ICRA 2019 论文集） |
| R11 | Daher et al., 内镜高光时序修复 | MedIA 2023，JCR Q1 | ScienceDirect（Vol. 90, 102994）+ PMC |
| R12 | Brooks et al., Unprocessing | CVPR 2019，CCF-A | CVPR Open Access + dblp |
| R13 | Foi et al., 泊松-高斯噪声建模 | IEEE TIP 2008，CCF-A 期刊/JCR Q1 | dblp + IEEE Xplore |
| R14 | Woo et al., ConvNeXt V2 (FCMAE) | CVPR 2023，CCF-A | CVPR Open Access |
| R15 | Tian et al., SparK | ICLR 2023 Spotlight（任务认可顶会） | ICLR 官方虚拟会议页 |
| R16 | Jiang et al., RegDA | CVPR 2021，CCF-A | CVPR Open Access |
| R17 | Liu et al., PnP-GA | ICCV 2021，CCF-A | ICCV Open Access + IEEE Xplore |
| R18 | Tarvainen & Valpola, Mean Teacher | NeurIPS 2017，CCF-A | 公开会议论文集（周知条目） |
| R19 | Adachi et al., SSA（回归 TTA） | ICLR 2025（任务认可顶会） | arXiv 2410.03263 正式版扉页标注 "Published as a conference paper at ICLR 2025" + OpenReview |
| R20 | Niu et al., SAR | ICLR 2023 Oral（任务认可顶会） | OpenReview + 官方仓库 |
| R21 | Yao et al., C-Mixup | NeurIPS 2022，CCF-A | NeurIPS Proceedings 官方页 |

注：R1、R18 为学界周知的奠基条目，本轮未单独二次检索，其载体归属无争议；其余各条均在本次调研中经检索引擎与官方论文集页面逐一核实。
