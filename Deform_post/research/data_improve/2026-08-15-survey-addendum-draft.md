# 方法空间补充调研(按管线位置重扫):零真实标签 Sim-to-Real 力回归

- 日期:2026-08-15(草案,交业主审阅)
- 前置文档:`2026-08-13-next-methods-survey.md`(按技术家族组织的主调研,引用总表 R1–R21 继续有效)、`2026-08-13-fda-training-manifest.md` §5.2(FDA 阴性关闭回执)、`2026-08-14-cut-design-manifest.md` §5(CUT 试点结构幻觉回执)。
- 载体准入(硬约束,沿主调研):仅 CCF-A / CCF-B 会议期刊、JCR Q2 及以上期刊、或 TMLR;ICLR/NeurIPS/ICML 按任务认可清单收入;MDPI 一律排除;预印本仅作次级注记,不作候选锚点。本轮全部新增引用均经检索引擎与官方页面(ACM DL / CVF Open Access / OpenReview / dblp / 官方仓库)逐条核实,核实方式随表标注;无法核实处显式标记"未核实"。

## 前言

主调研(2026-08-13)按技术家族组织,其 Top-3 推荐中的方向一(FDA)已以干净阴性关闭(隔离 -39.1% 有害),方向二(CUT)试点暴露结构幻觉与场景记忆,均属图像空间方法在本任务上的系统性失败;业主随之立下新约束:**生成的外观必须落在三维网格上(UV 纹理/顶点色),帧永远由经典渲染器经内镜相机产出,任何学习模型不得直接输出帧**。当前主线据此定为 T-B(Texture-Bake,网格 UV 纹理烘焙)方案:预训练 Stable Diffusion + 深度 ControlNet 在肾网格 UV 纹理上作画(TEXTure/Text2Tex/FlashTex/Paint3D 家族),辅以 IP-Adapter/LoRA 从真实帧个性化。本补充调研的任务不是重议该决策,而是:(1) 以**管线位置**为主分类轴(技术家族降为副标签)重扫一遍方法空间,查漏;(2) 逐条核实 T-B 主线依赖的 tier-1 文献的载体、代码与许可;(3) 在下一轮五折训练启动前,回答"是否存在压倒 T-B 的方法族"。另一关键事实约束贯穿全文:真实与孪生序列**仅在力值层面配对**,接触点与相机位姿两侧不同,凡要求帧级几何/光度对应的方法一律不适用。

---

## 1. 模型/网格空间(mesh texture / material / geometry)

T-B 方案的本位。外观被写进网格资产(UV 纹理、PBR 材质),帧由经典渲染器产出,天然满足业主约束;纹理按对象生成而非按帧生成,31 段序列共享少量纹理变体,成本与帧数解耦。

### 1.1 主线 tier-1 支撑核实表(本轮逐条核实)

| 条目 | 载体/年份(核实结果) | 官方代码 | 许可 | 备注 |
|---|---|---|---|---|
| TEXTure | SIGGRAPH 2023(核实:ACM DL 10.1145/3588432.3591503) | github.com/TEXTurePaper/TEXTurePaper | MIT(核实:仓库徽章) | 迭代式深度条件绘制 UV 纹理,官方实现 |
| Text2Tex | ICCV 2023(核实:官方仓库与项目页标注) | github.com/daveredrum/Text2Tex | CC BY-NC-SA 3.0(核实:仓库声明;**非商用**) | 深度感知 inpainting 逐视角合成纹理 |
| TexFusion | ICCV 2023 Oral(核实:CVF Open Access) | **未见官方代码仓库**(截至 2026-08-15 检索,仅 NVIDIA 项目页) | 不适用 | 无代码即不可作实施候选,仅作方法参照 |
| Paint3D | CVPR 2024(核实:CVF Open Access + 会议页) | github.com/OpenTexture/Paint3D | Apache-2.0(核实:仓库声明) | 粗到细生成 2K **无光照烘焙** UV 纹理,支持图像条件 |
| FlashTex | ECCV 2024 Oral(核实:ECVA 论文页 + 会议页) | github.com/Roblox/FlashTex | Apache-2.0(核实:仓库徽章) | LightControlNet 光照条件蒸馏,产出可重光照 PBR 材质 |
| ControlNet | ICCV 2023,Marr Prize(沿主调研 R6;本轮复核许可) | github.com/lllyasviel/ControlNet | Apache-2.0(核实:仓库 LICENSE) | 深度条件为 T-B 结构锁定件 |
| IP-Adapter | **仅 arXiv 预印本 2308.06721,无同行评审载体**(核实:检索无会议/期刊版本) | github.com/tencent-ailab/IP-Adapter | Apache-2.0(核实:仓库 LICENSE/pyproject) | 按规则降为工程组件与次级注记;其论文主张不作为证据引用 |
| LoRA | ICLR 2022(核实:OpenReview nZeVKeeFYf9) | github.com/microsoft/LoRA | MIT(核实:LICENSE.md) | 真实帧个性化微调件 |

要点:实施栈许可干净(MIT/Apache 为主),唯 Text2Tex 为**非商用许可**——学术论文可用,但若成果日后涉商用需在候选间改选 Paint3D/FlashTex/SyncMVD 实现;TexFusion 无官方代码,从实施清单剔除;IP-Adapter 载体不合格,以组件身份使用并在论文中如实标注出处性质。

### 1.2 补充候选(同族查漏,2026-08-13 调研未覆盖)

| 候选 | 机制一句话 | 载体/年份(核实) | 代码/许可 | 适用性判定 | 成本档 |
|---|---|---|---|---|---|
| SyncMVD | 多视角潜空间同步去噪,一次性生成全网格一致 UV 纹理,免逐视角迭代接缝 | SIGGRAPH Asia 2024(核实:ACM DL 10.1145/3680528.3687621) | github.com/LIU-Yuxin/SyncMVD,MIT(核实:仓库) | 与 TEXTure 同接口(网格+深度条件+文本/图像),多视角一致性更强,直接可为 T-B 备选实现;合规(纹理落网格) | days-1GPU |
| DreamMat | 几何与光照感知的扩散蒸馏,生成**去光照纠缠**的 PBR 材质(albedo/roughness/metallic) | SIGGRAPH 2024 / TOG(核实:仓库标注 + 项目页) | github.com/zzzyuqing/DreamMat,MIT(核实:仓库) | 产出材质而非烘焙色,须配可消费 BRDF 的着色环节:现行 Open3D 平面着色只能吃 albedo,完整价值依赖 M4 G-buffer 离线延迟着色或渲染器升级;合规 | days-1GPU(含 Blender 预渲染) |
| Material Palette | 从单张真实图像的掩膜区域提取 PBR 材质(albedo/normal/roughness),LoRA 概念抽取 + SVBRDF 分解 | CVPR 2024(核实:CVF Open Access) | github.com/astra-vision/MaterialPalette,MIT,扩散权重 CreativeML Open RAIL-M(核实:仓库) | **与 T-B 互补的反向路径**:不靠文本先验,直接从真实肾帧掩膜区提取组织材质再铺 UV;仅需单帧掩膜,无对应性要求;合规 | days-1GPU |

### 1.3 几何增强(geometry augmentation)

肾网格几何多样化(统计形状模型采样、笼形变形等)会改变接触力学,力标签必须经 FEM 重放重算,属"新数据生产"而非增强,成本为 weeks 级且撞上"接触点多样性已弥合 60.6%"的既有条件——**本轮不立候选**,仅记录:若日后数据扩容,几何轴应与现行方案 A 解剖缩放线合并规划,避免与 c3 条件重复计账。

---

## 2. 渲染空间(lighting / camera / material randomization,经典渲染纪律内)

| 候选 | 机制一句话 | 载体/年份(核实) | 代码/许可 | 适用性判定 | 成本档 |
|---|---|---|---|---|---|
| 结构化域随机化(SDR) | 随机化参数锚定真实场景统计分布而非均匀撒点 | ICRA 2019,CCF-B(沿主调研 R10) | 无官方开源(思想级方法) | 已是现行 DR 的隐含做法;查漏结论:光照/光学维(高光、暗角、景深)仍未随机化,与 M4 G-buffer 路线同一缺口;完全合规 | days-CPU |
| nvdiffrast | 高性能**可微光栅化**原语:仍是经典光栅化管线,只是参数可求梯度 | ACM TOG 2020(核实:ACM DL 10.1145/3414685.3417861) | github.com/NVlabs/nvdiffrast,NVIDIA Source Code License(核实:LICENSE;**非商用研究限定**) | 合规性辨析:它是经典渲染器而非学习模型出帧,可作 (a) 未来渲染器升级件、(b) 以分布级损失(如特征统计距离)对真实语料**拟合光照/材质参数**——分布对分布,无需帧对应;但等于换渲染栈 | weeks(渲染器迁移) |
| nvdiffrecmc | 可微蒙特卡洛渲染 + 去噪,从多视角图像反演形状/材质/HDR 环境光 | NeurIPS 2022(核实:OpenReview VAeAUWHNrty) | github.com/NVlabs/nvdiffrecmc,NVIDIA Source Code License(核实:仓库) | **基本不适用**:需已知位姿的静态多视角采集;真实内镜帧无位姿、软组织非刚性,SfM 补位姿在此场景脆弱。仅当日后能截取准静态片段估位姿时,才可用于"从真实帧反演组织 BRDF+光照先验"喂给第 1 节材质生成 | weeks,低优先 |

小结:渲染空间没有被遗漏的独立方法族;真正缺口(光照/光学维随机化)已由主调研 M4/M5 占位,且与 DreamMat/FlashTex 的 PBR 产物构成"材质生成(第 1 节)→ 着色消费(本节)"的配套关系。

---

## 3. 图像空间(仅记录未试过的新子族,依约不扩写)

本项目已实证关闭两个子族:频谱/统计对齐(FDA,-39.1%)与无配对 GAN 翻译(CUT,结构幻觉)。查漏仅得两个未试子族,均**不建议投入**:

1. 结构条件扩散翻译(depth-ControlNet img2img / SDEdit 系,即主调研 M2):机制上比 GAN 结构保持更强,但产物是学习模型直接输出的帧,**违反业主新约束**,仅存档;其火力已由 T-B 方案在网格空间合规吸收(同一扩散先验,改写纹理而非帧)。
2. 经典确定性色彩传递(Reinhard 均值-方差匹配一族;载体为 IEEE CG&A 2001,**级别未核实**):非学习像素运算,但与 FDA 同属"全局统计移植"机制族,FDA 阴性结果构成直接反证据;且外观仍落在帧上而非网格上,与约束精神不符。记录在案,不立候选。

---

## 4. 表征空间(domain-robust features for sim2real regression)

机制定位:不改数据、不改帧,换掉"对外观差敏感"的特征本身。与 T-B 正交,可叠加,也是唯一有潜力以极低成本改变格局的位置(见第 7 节)。

| 候选/证据 | 机制一句话 | 载体/年份(核实) | 代码/许可 | 适用性判定 | 成本档 |
|---|---|---|---|---|---|
| DINOv2(候选) | 大规模自监督蒸馏 ViT,冻结特征即含强稠密几何信息 | **TMLR 2024**(核实:论文扉页"Published in TMLR (01/2024)"+ TMLR 官方 Outstanding Finalist 通告) | github.com/facebookresearch/dinov2,代码与权重 Apache-2.0(核实:README;附属 XRay/Cell 模型另属非商用许可,与本项目无关) | 冻结骨干 + 浅回归头替换 ConvNeXt-L 通路;原文以**冻结特征线性探针完成单目深度估计**(稠密度量回归)且跨域稳健——是"基础特征可用于细粒度回归"的直接一手证据;零标签、零帧生成、无对应性要求,输入侧需适配 ViT patch 网格(如 224px) | days-1GPU |
| AM-RADIO(候选) | 将 DINOv2/CLIP/SAM 聚合蒸馏为单一骨干,兼得稠密与语义特征 | CVPR 2024(核实:CVF 会议页 + 官方仓库) | github.com/NVlabs/RADIO,NVIDIA Source Code License-**NC**(核实:README;非商用) | 同上通路的备选骨干;许可非商用,论文可用;优先级低于 DINOv2(证据链短) | days-1GPU |
| DINOv3(次级注记) | DINOv2 的 70 亿参数级后继,Gram 锚定稳定稠密特征 | **预印本/技术报告(Meta,2025),无合格载体**——按规则仅作次级注记,不作候选锚点 | github.com/facebookresearch/dinov3;**DINOv3 License(自定义)**:允许商用与衍生、发表须致谢声明、权重申请-审核制下载;自定义许可需自行法务复核(核实:仓库 LICENSE.md + Meta 官方博客) | 若 DINOv2 探针给出阳性信号,可平替升级;载体不合格故不得作为论文方法锚点 | days-1GPU |
| LP-FT(证据) | 分布偏移大时,全量微调**扭曲**预训练特征,OOD 上不敌"先线性探针后微调" | ICLR 2022 Oral(核实:OpenReview UYneFzXSJWh + 会议页) | github.com/AnanyaKumar/transfer_learning(许可**未核实**) | 对本项目的含义:合成域上微调整个骨干可能正是"把特征拉向合成外观"的机制;支持"冻结骨干/LP-FT 两段式"训练法作为单变量条件 | 训练策略,零额外成本 |
| Probe3D(证据) | 系统探针测量各视觉基础模型冻结特征的深度/法线等三维感知 | CVPR 2024(核实:CVF Open Access) | github.com/mbanani/probe3d(许可**未核实**) | 证据方向:DINOv2 系单视角深度/法线探针表现居首——支撑其特征承载"形变几何"信息的假设;同时提示多视角一致性弱,但本任务为单视角回归,不受此短板影响 | 仅证据 |

风险如实记录:项目内特征级方法有零效前科(CORAL),且"合成/真实 100% 线性可分"是在 ConvNeXt-L(ImageNet 监督预训练)特征上测得——DINOv2 特征下该探针结果未知,必须先测后押注;另有业主在案经验:ImageNet 归一化对合成数据未必适用(record-only,另 session 处理),换骨干时输入归一化须一并纳入单变量清单。

---

## 5. 训练环空间(UDA / 自训练 / 一致性,回归适用、零目标标签)

主调研 M7(PnP-GA/RegDA 自训练)与 M8(SSA 回归 TTA)已占位,是业主"三方向按序全试"的方向三,此处不重复;本轮仅补齐"回归专用特征对齐"子族与一致性子族:

| 候选 | 机制一句话 | 载体/年份(核实) | 代码/许可 | 适用性判定 | 成本档 |
|---|---|---|---|---|---|
| RSD | 以 Grassmann 流形上的表示子空间距离对齐两域特征,专为**回归**设计(证明尺度敏感性使分类式对齐伤回归) | ICML 2021(核实:PMLR v139 pp.1749-1759 + 会议页) | github.com/thuml/Domain-Adaptation-Regression,**仓库无 LICENSE 文件(已核实缺失;默认保留权利,使用前需联系作者)** | 训练损失级改动,消费未标注真实帧,零标签合规、无对应性要求;与 CORAL 的差异(子空间几何 vs 二阶矩)真实存在,但 CORAL 零效前科要求以严苛预注册门槛对待 | days-1GPU |
| DARE-GRAM | 对齐两域特征**逆 Gram 矩阵**(伪逆角度),显式面向 UDA 回归的最小二乘几何 | CVPR 2023(核实:CVF Open Access) | github.com/ismailnejjar/DARE-GRAM,MIT(核实:仓库) | 同上;是回归 UDA 子族中载体最硬、许可最干净的代表,若开训练环支线应以其为首选锚点 | days-1GPU |
| Mean Teacher 一致性(改造) | 师生 EMA 一致性:同一未标注真实帧的不同光度视图间强制预测一致 | NeurIPS 2017(沿主调研 R18) | 多方实现,原始仓库 Apache-2.0(**本轮未复核**,标注沿用) | 与自训练 M7 不同:不产伪标签,只约束一致性,确认偏误风险更低;噪声源可用增强而非帧对应,**不依赖真实-孪生配对**,合规;但光度增强在本项目有负效前科,噪声设计须避开该轴(如仅裁剪/遮挡) | days-1GPU |

---

## 6. 边界外相邻(业主应知,不在本轮委托范围)

1. **视触觉传感 sim2real 力回归**:与本任务同构("图像 → 接触力",零/少真实标签)且文献成熟——Ding, Lepora, Johns, "Sim-to-Real Transfer for Optical Tactile Sensing",ICRA 2020,CCF-B(核实:论文集页码 1639-1645);Sferrazza 等,"Sim-to-Real for High-Resolution Optical Tactile Sensing: From Images to Three-Dimensional Contact Force Distributions",Soft Robotics 2022,JCR Q1(核实:出版社页 + PMC;分区未逐年核验)。其"仿真侧特征工程 + 真实统计标定"套路值得引为论文相关工作与技巧来源。
2. **内镜单目深度自监督估计**:同成像域的稠密回归先例(几何自监督信号在真实内镜帧上成立)——Liu 等,IEEE TMI 39(5):1438-1447, 2020,JCR Q1(核实:PubMed/JHU 页 + 官方仓库)。可为"真实帧免标签几何信号"提供借鉴(如深度一致性作自训练过滤器)。
3. **DreamBooth 主体驱动个性化**:CVPR 2023(核实:dblp + CVF Open Access)。IP-Adapter/LoRA 之外的第三条个性化路线,且载体合格——若论文写作需要"个性化"环节的合格锚点,应引 DreamBooth + LoRA 而非仅 IP-Adapter。
4. **组织光学特性/BRDF 实测文献**(生物医学光学方向):可为材质生成提供物理参数先验(散射、镜面叶瓣);本轮未核实具体锚点,仅提示该文献带存在。
5. **手术机器人有监督视觉力估计**:使用真实力标签训练,不合本任务设定,但构成审稿人必比的性能语境,投稿前需专项摸底。

---

## 7. 压倒性判定:是否存在压倒当前 T-B 方案的方法族

**判定:否。** 理由:(1) 模型/网格空间的全部新候选(SyncMVD/DreamMat/Material Palette)与 T-B 同族,是实现件与增强件而非替代族;(2) 渲染空间与 T-B 是"材质生产-着色消费"的配套关系,且渲染器迁移(nvdiffrast)成本 weeks 级、不解决纹理内容问题;(3) 图像空间被业主约束与两次阴性实证双重关闭;(4) 训练环空间(RSD/DARE-GRAM/一致性)均为叠加件,不与外观改造争位,且背负 CORAL 零效前科,无压倒性证据;(5) 唯一具备"改变格局"潜质的是**表征空间**——DINOv2 冻结特征 + 浅回归头机制上绕开外观改造本身(特征不敏感则无需修数据),成本仅 days-1GPU,并有 TMLR 2024 原文深度线性探针与 LP-FT(ICLR 2022 Oral)两条合格证据链;但它缺"内镜 sim2real 力回归"的直接证据,项目内特征级方法又有零效前科,故构成**必须对冲的例外**而非压倒。

**建议动作(不改变 T-B 排程,作为廉价保险预注册):** 在下一轮五折训练启动前,插入一个一天级单变量条件——对现有 twin/real 数据抽取 DINOv2 冻结特征,(a) 复跑合成/真实线性可分性探针,(b) 冻结特征 + 线性头按冻结 c2/c1 协议跑一折哨兵。若 (a) 可分性显著下降或 (b) 哨兵 gap-closed 优于现行同协议水平,则将表征空间升格为与 T-B 并行的正式赛马臂(独立 worktree,按 2026-08-10 胜利门槛记账);否则归档,T-B 独进。

---

## 8. 术语表(新增项;前序调研与清单术语表继续有效)

| 术语 | 解释 | 来路 |
|---|---|---|
| UV 纹理烘焙(texture baking) | 将外观写入网格 UV 展开的贴图,渲染时经典采样,不经学习模型出帧 | T-B 方案定义;TEXTure SIGGRAPH 2023 |
| PBR 材质 | 物理基着色参数组(albedo/roughness/metallic 等),与光照解耦 | DreamMat SIGGRAPH 2024;FlashTex ECCV 2024 |
| SVBRDF | 空间变化的双向反射分布函数,即逐像素 BRDF 贴图 | Material Palette CVPR 2024 |
| 无光照纹理(lighting-less texture) | 去除烘焙光影的反照率纹理,避免与渲染光照二次叠加 | Paint3D CVPR 2024 |
| 多视角同步去噪 | 各视角扩散潜变量在每步去噪间融合共识,保全网格纹理一致 | SyncMVD SIGGRAPH Asia 2024 |
| 可微光栅化 | 经典光栅化管线的梯度可传版本,属渲染器而非生成模型 | nvdiffrast ACM TOG 2020 |
| 逆渲染(inverse rendering) | 从图像反演形状/材质/光照参数的优化过程 | nvdiffrecmc NeurIPS 2022 |
| 冻结特征线性探针回归 | 骨干冻结,仅训线性/浅层头做回归,测特征本身的任务承载力 | DINOv2 TMLR 2024(深度估计探针) |
| LP-FT | 先线性探针后微调的两段式训练,防止微调扭曲预训练特征 | Kumar 等 ICLR 2022 Oral |
| 逆 Gram 矩阵对齐 | 对齐两域特征逆 Gram 矩阵以稳住回归最小二乘解的几何 | DARE-GRAM CVPR 2023 |
| 表示子空间距离(RSD) | Grassmann 流形上特征主子空间夹角距离,回归专用对齐目标 | RSD ICML 2021 |
| 门控下载(gated download) | 权重需接受许可协议并经申请审核方可获取 | DINOv3 License(Meta 2025,预印本注记) |

---

## 附:本轮核实留痕说明

新增引用核实途径:ACM DL(TEXTure/SyncMVD/nvdiffrast)、CVF Open Access(TexFusion/Paint3D/Material Palette/DARE-GRAM/Probe3D/DreamBooth)、ECVA(FlashTex)、OpenReview(LoRA/LP-FT/nvdiffrecmc)、PMLR(RSD)、TMLR 官方通告与论文扉页(DINOv2)、PubMed(Liu TMI 2020)、各官方 GitHub 仓库 LICENSE 页(全部许可结论)。未核实项已在正文逐处标记:probe3d 仓库许可、AnanyaKumar/transfer_learning 仓库许可、Mean Teacher 原始仓库许可(沿用标注)、Reinhard 2001 载体级别、Soft Robotics 逐年分区、第 6 节第 4 条(仅提示文献带,无锚点)。IP-Adapter 与 DINOv3 为预印本,已按规则降级标注。
