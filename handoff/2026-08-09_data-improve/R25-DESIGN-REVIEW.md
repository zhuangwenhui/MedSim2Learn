# C1-R25 设计与文献台账独立评审（T-003）

- 评审时间戳：2026-08-09T19:03:39+09:00
- 评审者身份：独立评审子代理（T-003，review 角色；与 T-002 执行者无共享上下文，一切主张按一手证据重验，不信任被审文档的自述）
- 被审对象：`handoff/2026-08-09_data-improve/R25-DESIGN.md`、`handoff/2026-08-09_data-improve/R25-LITERATURE.md`（均未改动）
- 结论预告：v1 评审 **NEEDS_REVISION**（Critical 0 / Important 3 / Minor 11）→ v2 增量复审（第 9 节）**NEEDS_REVISION**（Critical 0 / Important 1 / 新 Minor 3）→ v3 终审（第 10 节）**APPROVED** → v4 增量评审（第 11 节，M5 修订）**APPROVED**（Critical 0 / Important 0；record-only 注记累计 5 条：v2-M1/M2 见第 9 节，v4-m1/m2/m3 见第 11 节，均不构成阻塞）

## 1. 评审范围与方法（实际执行清单）

只读范围：handoff 目录、`D:\MedSim2Learn-C1-R19-Triplanar-Continuity\Deform_post`（R19 worktree）、`D:\MedSim2Learn-C1-verification\r19-triplanar-continuity`、公开网络。R23/R24 验证目录不在本任务允许路径内（见第 6 节"范围内无法核验项"）。

实际执行的核验动作：

1. 本地文件读取：STATE.yaml、HANDOFF.md、两份被审文档；R19 `screen-v1` 下 `inputs.json`、`artifact-hashes.json`、`validation.json`、`telemetry.json`、`receipt.json`、`vertex-colors-receipt.json`；R19 设计/结果文档（`2026-08-07-c1-r19-triplanar-continuity-design.md` / `-result.md`）；R19 代码 `dpost/c1_r16_uv_render.py`、`dpost/c1_r19_triplanar_continuity.py`、`scripts/run_c1_r19_triplanar_continuity.py`、`dpost/c1_r12_source_feasibility.py`；R16a 设计文档（deformed 网格来源）。
2. 哈希自算（Bash `sha256sum`，共 10 个文件）：四个冻结 mask、`vertex-colors.npy`、z-plus/iso-plus 两网格四张 render、`inputs.json`。
3. PNG IHDR 自解析（Python struct，8 张）：z-plus/iso-plus 两网格的 renders 与 masks 实测宽高。
4. `vertex-colors.npy` 自加载（numpy，`allow_pickle=False`）：dtype/shape 实测、逐通道均值实算、两种取整口径对比、".5 平局不可能"奇偶论证。
5. 网络复核（WebFetch 共 26 次，逐条记录于第 2 节）：api.crossref.org 12 次、history.siggraph.org 3 次、arxiv.org 5 次、shop.elsevier.com、iquilezles.org、developer.nvidia.com、github.com、cns.nyu.edu 各 1 次、cs.umd.edu 作者副本 PDF 1 次（提取失败，如实记录）。
6. 未执行：任何 git 命令、任何渲染、任何训练、任何对被审文档或其他文件的写入（本文件是唯一写入物）。

## 2. 文献核验表（R25-LIT-01..16 逐条独立复核）

复核标准：条目元数据与"已核实主张"是否被我本次亲自抓取的一手来源支持；标签（[TECH-REF]/次级/仅元数据）是否如实。

| 条目 | 我的复核方式（本次实际抓取） | 结果 |
|---|---|---|
| R25-LIT-01 Perlin 1985 | Crossref 10.1145/325165.325247（题名/作者/ACM SIGGRAPH CG/1985/含摘要）+ history.siggraph.org 存档页（摘录 "solid texture"、"controlled stochastic effects"、"composition of non-linear functions"、marble/rock 实例） | match |
| R25-LIT-02 Improving Noise 2002 | Crossref 10.1145/566654.566636（题名/Perlin/ACM TOG/2002；摘要确认修正 "second order interpolation discontinuity" 与 "unoptimal gradient computation"） | match（核心）；"quintic 淡入"与"消除可见格点伪影"超出其记录的证据链，见 Minor-1 |
| R25-LIT-03 Musgrave 1989 | Crossref 10.1145/74334.74337（题名/三作者/刊物/1989 匹配；注意：该 Crossref 记录实际含摘要——地形高度场分形合成） | match（台账自称仅元数据、主张自限于题名/作者/刊物层面，为保守方向；见 Minor-5） |
| R25-LIT-04 Texturing and Modeling 3e | shop.elsevier.com 官方页（书名/第 3 版/五作者确认；目录确认 Making Noises（lattice/value/gradient/sparse-convolution）、Procedural fBm、Multifractal Functions、octaves "Limits to Detail"、Fractal Solid Textures、Cellular Texturing、Real-Time Procedural Solid Texturing；ISBN 见 URL slug 978-1-55860-848-1） | match；但目录含 Mojoworld 章 "Domain Distortion" 小节，台账"本书未确认覆盖 domain warping"陈述过时（保守方向错误），见 Minor-2 |
| R25-LIT-05 Worley 1996 | Crossref 10.1145/237170.237267（题名/Worley/SIGGRAPH '96；无摘要）+ history.siggraph.org 存档页（"complements Perlin noise"、空间随机划分为 cells、示例含 "organic crusty skin"、"without the need for precalculation or table storage"） | match |
| R25-LIT-06 Gabor 噪声 2009 | Crossref 10.1145/1531326.1531360（题名/四作者/ACM TOG/2009；摘要含 "accurate spectral control with intuitive parameters such as orientation, principal frequency and bandwidth"、"does not require a texture parameterization"）+ history.siggraph.org 存档页（同句复核，另确认 "setup-free surface noise"） | match |
| R25-LIT-07 噪声综述 2010 | Crossref 10.1111/j.1467-8659.2010.01827.x（题名/全部九作者/CGF 29(8):2579-2600/2010；摘要提及 formal definitions 与 classification）；作者副本 PDF（cs.umd.edu）抓取到但受密码保护无法提取正文 | match（元数据与"定义+分类"层面）；括注"（紧凑随机过程）"属正文级具体表述，我亦无法核验，见 Minor-3 |
| R25-LIT-08 Peachey 1985 | Crossref 10.1145/325165.325246（题名/Peachey/ACM SIGGRAPH CG/1985；摘要含 "texture functions defined throughout a region of three-dimensional space"、"can easily be applied to complex surface which are difficult to texture using two-dimensional texture functions"）+ history.siggraph.org 存档页（同句复核） | match |
| R25-LIT-09 Quilez warp | iquilezles.org/articles/warp/ 直接抓取（作者 Inigo Quilez；核心构造 f(g(p))、g(p)=p+h(p)；可迭代嵌套 f(p+fbm(p+fbm(p)))；fBm 作偏移场；无正式发表日期、无同行评审信息） | match；[TECH-REF] 标注如实 |
| R25-LIT-10 GPU Gems 3 ch.1 | developer.nvidia.com 官方页（第 1 章/Ryan Geiss/GPU Gems 3；三平面段落确认 "use the projection that offers the least distortion (stretching) at that point—with some projections blending in the in-between areas"） | match；[TECH-REF] 标注如实；设计仅作谱系上下文、未据此实现，如实 |
| R25-LIT-11 Geirhos 2019 | arxiv.org/abs/1811.12231（题名/六作者；摘要原句 "strongly biased towards recognising textures rather than shapes"；ICLR 2019 oral 备注确认） | match（台账层面）；设计正文引用措辞见 Minor-6 |
| R25-LIT-12 Tobin 2017 | arxiv.org/abs/1703.06907（题名/六作者；逐字确认台账引句 "With enough variability in the simulator, the real world may appear to the model as just another variation"；"non-realistic random textures" 确认；任务为 object localization 确认）+ Crossref 10.1109/IROS.2017.8202133（IROS 2017 正式版同题同作者） | match |
| R25-LIT-13 Tremblay 2018 | arxiv.org/abs/1804.06516（题名/十作者；摘要原句 "randomized in non-realistic ways to force the neural network to learn the essential features"）+ Crossref 10.1109/CVPRW.2018.00143（CVPRW 2018） | match；Workshop/次级标注如实 |
| R25-LIT-14 VisionBlender | Crossref 10.1080/21681163.2020.1835546（题名/五作者/CMBBE: I&V/2020 上线、2021 刊卷/Informa=T&F）+ github.com/Cartucho/vision_blender（README 确认 depth/disparity/segmentation/normals/optical flow/pose/相机参数输出并引用该文；README 确有 MICCAI 2020 workshop 最佳论文奖自述） | match；台账"奖项未独立核验、不得引用"的处置如实且必要；已确认 R25-DESIGN.md 全篇未引用该奖项 |
| R25-LIT-15 Pfeiffer MICCAI 2019 | Crossref 10.1007/978-3-030-32254-0_14（题名/LNCS/MICCAI 2019）+ arxiv.org/abs/1907.02882 两次（作者逐一清点恰 15 人，与台账"十五位作者"一致；摘要确认：合成腹腔镜数据、非配对图像翻译弥合 domain gap、肝脏分割、真实术中图像 dice 最高 0.89、无需人工标注真实图像；"Accepted at MICCAI 2019" 确认） | match |
| R25-LIT-16 Portilla-Simoncelli 2000 | Crossref 10.1023/A:1026553619983（题名/两作者/IJCV 40(1)/2000-10；页码 49-70）+ cns.nyu.edu/~lcv/texture/ 官方模型页（书目 40(1):49-71/2000-10；模型确认：跨位置/方向/尺度的复小波系数联合统计；自高斯白噪声迭代调整以匹配统计实现合成） | match；页码 49-70（Crossref）与 49-71（NYU 官方页）不一致，见 Minor-4 |

标签合规专项确认：R25-LIT-09、R25-LIT-10 均已标 `[TECH-REF]`（非同行评审）；R25-LIT-13 已标注 Workshop 论文且"不得作首要出处"；R25-LIT-03 已加粗标注"仅元数据核验"；R25-LIT-14 的 MICCAI 奖项在设计文档中零引用。均通过。

## 3. 事实锚定核验表（哈希与参数：我算出/读出的值 vs 设计声称值）

| 锚定项 | 设计声称值 | 我的一手核验 | 结果 |
|---|---|---|---|
| inputs.json `canonical_file_sha256` | f0a301cf...5e3e2d | 读 inputs.json 同值；且 R19 代码 `c1_r16_uv_render.py` L37 冻结常量同值（两处独立来源一致） | match |
| inputs.json `deformed_file_sha256` | 82915fe9...099493 | 读 inputs.json 同值；R19 代码 L38 同值；R16a 设计文档 L84 同值 | match |
| inputs.json `camera_names` 含 z-plus/iso-plus | 是（五机位注册表） | 实为 [z-plus, y-minus, y-plus, iso-plus, iso-minus]，恰五个 | match |
| `vertex_count` / `face_count` | 2,005 / 4,006 | inputs.json 实读 2005/4006；vertex-colors.npy 实测 shape (2005,3) | match |
| `mapping_space` | canonical | 实读 canonical | match |
| `deformed_color_policy` | reuse_exact_canonical_bytes | 实读同值 | match |
| `worker_count` | 1 | inputs.json 与 telemetry.json 均实读 1 | match |
| mask canonical/z-plus | 5cdcfe8f818de089018a95fe50730d41923a8ee26755dc827c84429016d5e33d | sha256sum 实算同值（逐字符一致） | match |
| mask canonical/iso-plus | 8d4f75d71240cbb56ff1e99da76cd9d95ef2288f7fa1f03d581ac5323bdece30 | 实算同值（逐字符一致） | match |
| mask deformed/z-plus | 7ef2dea7d1725b6fdf537d217c3ae351b4406c593642c3a045e4b4e2dcb76b48 | 实算同值（逐字符一致） | match |
| mask deformed/iso-plus | 1f87171958c394beb44a2b2add57afeb8b55334b24eaef58fde35d3758c123ad | 实算同值（逐字符一致） | match |
| vertex-colors.npy | af2c92d61b73cf34e3802beef7b85f95cd63b4b47e2d3fb5242dd0d17b20474b | 实算同值（逐字符一致） | match |
| 渲染分辨率 512x512 | 是 | 8 张 renders/masks IHDR 实测均 512x512 | match |
| 渲染器无光照 | Open3D legacy unlit | 代码一手证据：`c1_r16_uv_render.py` L178-194 `render_legacy_view`，`create_window(width=512, height=512, visible=False)`、`render_option.light_on = False`；`run_c1_r19_triplanar_continuity.py` L37/L223 确认 R19 正是经 `render_legacy_view` 渲染 | match |
| 相机 z-plus/iso-plus 存在 | 是 | 代码 `_CAMERA_VIEWS` L25-31 逐名确认（含 front/up 向量）；`intrinsic_matrix(512, 512, 60.0)` L163 | match |
| 归一化坐标系 | 包围盒中心+单一最大边长（R19 同式） | R19 设计文档"方法"节原文；代码 `c1_r19_triplanar_continuity.py` L153-159（canonical 包围盒、单一 max_extent、`(v-center)/max_extent + 0.5`） | match |
| 共享边 6,009 条 | 是 | R19 结果文档原句 "all 6,009 shared edges have zero endpoint-colour mismatches"；且 Euler 校验 2005+4006-2=6009 自算一致 | match |
| RSS 先例 232.6 MB / 上限 500 MB | 是 | telemetry.json 实读 peak_process_tree_rss_bytes=232,599,552、rss_limit_bytes=500,000,000；R19 结果文档同值 | match |
| "采样密度是日后独立变量" | 是 | R19 结果文档原句 "Sampling-density work is a later, separate variable" | match |
| base_rgb 派生规则确定性 | mean 后逐通道 round，8-bit | 自算：均值 [139.5317, 98.6688, 117.4913]；np.round 与 floor(x+0.5) 两口径同得 (140, 99, 117)；因 2005 为奇数，均值分数部分恰为 .5 在整数和/2005 下不可能，取整平局不存在，规则完全确定 | match（确定性成立） |
| 聚合统计合规 | 仅冻结聚合统计、无真实像素空间映射 | 均值为 3 通道标量聚合，不保留任何空间结构，符合 fable5_policy.allowed_default_data 的 frozen_aggregate_statistics；符合 T-005 禁令 real_pixel_spatial_mapping | match |
| deformed 实例 s0521 与 seq04 关系 | 设计未声称，评审专项核查 | R16a 设计文档 L77：deformed 网格源文件为 `DeformedSample_ComplexObject_26_06_10_223933\deformed_s0521_v0000.ply`（DeformSim 合成 FEM 变形样本，哈希与锚定一致）；代码中样本 id 形如 `deformed_s0521_v####` 且同一 bare id 跨 seq01..seq32 多序列复用（`c1_r12_source_feasibility.py` L47-58），序列 token 形如 `seqNN`、与 `s0521` 构词不同 | 确认：s0521 是 DeformSim FEM 变形状态样本 id，非真实视频序列号，几何选择不涉及 seq04；seq04 排除令不受影响 |

## 4. 契约与门逐项评估

### 4.1 单变量契约可执行性

- 唯一变量（逐顶点颜色生成函数）定义清晰；四变体共享渲染/序列化路径、base 为 a=0 退化情形，属同族单变量比较。成立。
- 隐藏第二变量排查：几何（双哈希锚定）、相机（同注册表子集）、背景（M5 逐像素相等门）、光照（unlit 继承，C-F007 不回流）、分辨率（512）、映射路径（逐顶点+线性插值、deformed 逐字节复用）、并行度（串行）、基色（四变体共用冻结常量）——逐项有锚且有对应机械门。**未发现隐藏第二变量。**
- 排除清单与 T-005 禁令逐一对应：patch_tiling、real_pixel_spatial_mapping、add_r23_vessels、change_geometry/camera/background/lighting/base_colour、write_r19（§8 限 r25 worktree）、train、gap_claim、overwrite_artifact（no-clobber）。TDD 红绿契约（§8）与 RSS<500,000,000（M11）在案。一致。

### 4.2 机械门 M1-M13 可计算性

| 门 | 评估 |
|---|---|
| M1 计数命名 | 可计算（16 全名枚举在案） |
| M2 网格守恒 | 可计算（哈希锚定在案） |
| M3 同一性 | 可计算 |
| M4 连续性 6,009 边 | 可计算（数值经 Euler 校验与 R19 结果文档双重确认） |
| M5 mask 冻结+背景逐像素 | 可计算（四 mask 哈希已自算核实；R19 renders 在 screen-v1 在案可比对背景区） |
| M6 base 精确性 | 可计算 |
| M7 均值保持 | **有单位歧义与可行性风险，见 Important-1** |
| M8 振幅界 | 数学上成立：base_rgb 为整数时 round(base_rgb(1+a·n))-base_rgb = round(base_rgb·a·n)，|round(y)| <= ceil(0.16·base_rgb) 恒成立；且按我实算的 base_rgb=(140,99,117)，140*1.16=162.4 < 255、99*0.84>0，上下均无 clip 干扰。可计算且可通过 |
| M9 确定性重放 | 可计算 |
| M10 频带下限 | 基本可计算；"所有倍频程"集合边界有小歧义，见 Minor-8 |
| M11 资源门 | 可计算（psutil 进程树采样，R19 先例既有实现可复用；设计已声明先例不充当证据，正确） |
| M12 可区分性预门 | **聚合口径未定义，见 Important-2** |
| M13 闭合 | 基本可计算；manifest 自指细节未写死，见 Minor-9 |

### 4.3 十六图门可重放性

- 16 个文件名逐一枚举（4 变体 x 2 网格 x 2 视图），与 STATE.yaml T-005 验收 token 完全对应（base/candidate_1..3、canonical/deformed、z_plus/iso_plus；token 映射句在案）。
- 计数规则明确：仅 `clean/` 计数；fields/masks/controls/diagnostics 不计入——对应 T-005 的 diagnostics_are_separate 与 sheets_masks_and_diagnostics_do_not_count 两条验收。
- no-clobber（存在即拒写）与版本化（重跑仅允许新建 development-preview-v2）明确；manifest+receipt 闭合字段清单明确；输出根与 T-005 outputs 一致。
- 结论：两名实现者依此产出不同工件集的空间已基本封死；仅 Minor-9（manifest 自指/写序）一处闭合细节建议写死。**可重放性成立（含 Minor-9 修复后完全成立）。**

### 4.4 主张边界

- §10 与 STATE.yaml claim_boundary.unsupported、F-EXP-012/013 逐条对齐：不声称外观差距缩小、不声称训练收益、不声称医学/生理真实性、不超出注册视图与采样密度泛化。通过。
- 动机段（§1）三处引用（L-11/12/15）均处于"动机（仅动机，非结论）"显式限定之内，未以证据口吻出现；两处措辞可再收紧（Minor-6、Minor-11）。
- 停止条件 §9 共 7 项均显式；1-4 项直接命名终态；第 5 项（RSS）经 M11 失败归入 R25_INVALID_OR_FAILED、第 6-7 项为过程检查点（C-H003/C-F010），终态覆盖闭合（表述可再显化，Minor-10）。
- 全文无 emoji、正文中文、技术 token 英文，符合语言契约。

## 5. 发现列表

### Critical（0 项）

无。特别声明：未发现虚构文献、未发现哈希或参数错报、未发现隐藏第二变量、未发现差距/训练/医学主张越界、未发现与 STATE.yaml 禁令冲突。

### Important（3 项）

1. **M7 阈值单位歧义且 8-bit 口径下统计上近不可行**
   - 位置：R25-DESIGN.md §6 M7"每候选渲染前顶点颜色逐通道 |mean − base_rgb| ≤ 2/255"。
   - 问题：colour 与 base_rgb 全文定义在 8-bit 整数尺度（§3.6、§4.1），而阈值写作"2/255"是归一化尺度写法。按 8-bit 尺度读，阈值约 0.0078 灰度级：由于 colour 经逐顶点 round，均值残差的标准误约 0.29/sqrt(2005) ≈ 0.0065，单通道超限概率约 20%+，3 通道 x 3 候选下几乎必然误触发失败终态；按归一化尺度读（即 2 个灰度级）则轻松可过。两名实现者会得出相反的通过/失败结论。
   - 证据：我对 vertex-colors.npy 实算 shape(2005,3)；§4.1 步骤 1-2 保证 mean(n)=0，残差仅来自取整，量级如上。
   - 建议修复：改写为"逐通道 |mean(colour) − base_rgb| ≤ 2.0（8-bit 灰度级）"或等价的明确单位表述。
2. **M12 聚合口径未定义**
   - 位置：R25-DESIGN.md §6 M12"6 个变体对在 4 个 (网格,视图) 组合上的 masked MAE……每对均 > 8.0"。
   - 问题："在 4 个组合上的 masked MAE"可读作（a）每对每组合各算一次、24 项检查全部 > 8.0；（b）每对把 4 个组合聚合成一个数（且聚合可以是 4 个 MAE 取均值，也可以是像素池化——四个冻结 mask 前景像素数不同，两种算法数值不同）后 6 项检查 > 8.0。三种实现互不等价。
   - 证据：条文原文；mask 前景大小随网格/视图不同（四个 mask 为不同哈希的不同图）。
   - 建议修复：写死口径，例如"每对在 4 个组合上分别计算 masked MAE，要求 4 个值的最小值 > 8.0（即 24 项检查）"。
3. **§4.1 数值参数（lacunarity=2、gain=0.5、a=0.16）未落 adaptation 标注，且引用位置暗示书源支持具体数值**
   - 位置：R25-DESIGN.md §4.1"fBm 逐倍频程求和（lacunarity = 2，gain = 0.5，R25-LIT-04）"与"振幅 a = 0.16"。
   - 问题：R25-LIT-04 的台账核验深度自限于"章节标题级而非页级内容"，据此只能支持 fBm 逐倍频程结构，不能支持具体数值；将 R25-LIT-04 引注直接挂在含数值的括号内，读作"书中给定这些数值"。§4.3 的 adaptation 总标注覆盖候选表参数，但不覆盖 §4.1 的这三个数。这与本轮验收项"工程适配必须标注为 adaptation、不得标注为文献事实"直接相关（台账自身在 LIT-04/LIT-07 的边界条款也正是同一标准）。
   - 证据：R25-LITERATURE.md LIT-04"核验到章节标题级"；Elsevier 目录抓取未及页级内容。
   - 建议修复：一句话即可——§4.1 改为"结构依 R25-LIT-04；lacunarity=2、gain=0.5、a=0.16 为工程适配（adaptation），冻结值"。

### Minor（11 项）

1. LIT-02"已核实主张"含"quintic 淡入""消除可见格点伪影"，超出其记录证据（Crossref 摘要只到"二阶插值不连续+梯度计算"层面）；建议补一个可机读的内容页（如作者机构论文页）或将主张收敛到摘要层面。
2. LIT-04 边界条款与"诚实限制汇总 #3"称"本书未确认覆盖 domain warping"：Elsevier 目录实际含 Mojoworld 章"Domain Distortion"小节（即同一技术）。错误方向为保守（少引而非多引），但建议修正——顺带可为 candidate-2 的域扭曲补上一个印刷出版物级来源。
3. LIT-07 括注"（紧凑随机过程）"属正文级定义表述，台账证据链（Crossref 摘要 + HAL 搜索渲染）不含它；我抓取的作者副本 PDF 受密码保护亦无法核验。建议删去括注或完成页级核验后保留。
4. LIT-16 页码：Crossref 记录 49-70，NYU 官方页与台账 49-71。建议在条目内注明两源分歧。
5. LIT-03：该 Crossref 记录实际含摘要（分形地形高度场合成），台账"摘要未抓取"可升级；且"噪声基（fBm 族）"限定词略超题名层面证据，建议随摘要升级一并收敛或坐实。
6. 设计 §1"CNN 主要依赖纹理统计（R25-LIT-11……）"缺"ImageNet 训练的"限定（文献证据域）；虽处动机限定句内，建议补限定词。
7. 设计 §1 与 M12 引 R24 具体数值（60 视图内 3 对近重复、masked MAE 6.2-6.9）标注为 F-EXP-011/C-F009：两条状态项本身不含这些数值（数值在 C-F009 指向的 D-004 工件内）。建议直接标注 D-004。另见第 6 节范围限制。
8. M10"所有倍频程波长 ≥ λ_floor"未写明 candidate-3 的 d_cell=0.09 与 candidate-2 扭曲场 λ{0.50,0.25} 是否属于受检集合（按预估 λ_floor≈0.06 均有余量，但集合归属应写死）；另建议在 receipt 中记录"域扭曲会抬高有效带宽、λ 记账仅指成分倍频程"这一诚实注记。
9. §5/M13 闭合细节：manifest.json 无法包含自身哈希，receipt 与 manifest 的写入次序及自指排除规则未写死。建议一句话规定（例如"manifest 覆盖除自身外全部文件；receipt 先于 manifest 写入并被其覆盖"）。
10. §9 第 5-7 项停止条件未直接命名 R25_* 终态（第 5 项实际经 M11 失败归入 R25_INVALID_OR_FAILED）。建议补一句显式映射，使"每个停止条件对应一个终态或检查点"读起来零推理。
11. 设计 §1"朴素渲染外观单独不足（R25-LIT-15）"建议加"在该论文演示中"限定：一手证据是"为弥合 domain gap 而引入翻译步骤"的论文自述框架（我已核验 arXiv 摘要原文），非独立消融结论。台账条目本身已正确限定，设计句是其压缩转述。

## 6. 范围内无法核验项（scoped limitation，非违规）

1. R23/R24 验证目录不在 T-003 允许路径内。设计所引 R24 近重复数值（3 对、masked MAE 6.2-6.9）与 R23/R24 终态，我只对照了 STATE.yaml：F-EXP-009（R23_SCALE_SELECTED_CONTROLLED_DIFFUSE_ACCEPTED）、F-EXP-011（R24_V2_CONTINUITY_PASS_DIVERSITY_LIMITED，claim boundary 含 sixty_registered_views token）、C-F009（diversity limited，工件即 D-004）。终态与"60 视图/多样性受限"定性均对得上；6.2-6.9 与"3 对"两个数值本身在我范围内无一手工件可验，如实记录为范围限制。
2. canonical/deformed 两个 .ply 源文件本体（位于 DataFlow）不在允许路径内，未重算其 sha256；但其锚定值在 inputs.json 与 R19 代码冻结常量（另加 R16a 设计文档）三处独立位置一致，间接置信充分。
3. dl.acm.org、Wiley、T&F、Springer、OpenReview 等机器人墙站点：与台账相同，我经 Crossref API 与官方内容页复核，未尝试绕墙。
4. LIT-07 作者副本 PDF 密码保护，正文级定义无法核验（已计入 Minor-3）。
5. 网络复核过程中 WebFetch 将 cs.umd.edu 的 PDF 缓存到本会话 harness 内部工具结果目录（非仓库路径），未产生任何仓库写入。

## 7. 结论

**NEEDS_REVISION。** Critical 0 项；Important 3 项（M7 单位与可行性、M12 聚合口径、§4.1 数值参数标注/引注范围）；Minor 11 项。三项 Important 均为一至两句话的定义澄清或标注修正，不动摇设计的单变量结构、冻结锚定、十六图契约与主张边界——上述四者经我逐项一手核验全部成立。修复三项 Important（Minor 酌情）后，本评审支持进入 T-004 人工批准。

必须修复项清单（T-002 修订最小集）：
1. M7 改为明确的 8-bit 灰度级阈值表述（建议 ≤ 2.0 灰度级）。
2. M12 写死每对 x 每组合的计算与判定口径（建议 24 项逐一 > 8.0 或"每对 4 组合最小值 > 8.0"）。
3. §4.1 为 lacunarity=2、gain=0.5、a=0.16 落 adaptation 标注，并将 R25-LIT-04 引注限定为结构性依据。

## 8. 合规声明

本评审全程：未执行任何 git 操作（无 add/commit/branch/worktree/fetch/push）；除本文件（`handoff/2026-08-09_data-improve/R25-DESIGN-REVIEW.md`）外未写入任何文件；未修改 R25-DESIGN.md 与 R25-LITERATURE.md；未渲染、未训练；未打开 D:\MedSim2Learn 根目录三个用户保护文件（RESEARCH_DIRECTION.md、RESEARCH_GOAL.md、_paper09_extract.txt）；未接触任何医疗/患者数据（本任务全部对象为合成 CG 工件与公开文献）。

## 9. 复审（v2）

- 复审时间戳：2026-08-09T19:20 前后（+09:00）
- 对象：R25-DESIGN.md v2、R25-LITERATURE.md v2（两文件全文重读，逐行与 v1 对照；两文件末尾均有修订记录，主链接与 DOI 无一变更，冻结锚定表、16 文件名枚举、§10 主张边界经比对逐字未动）。
- 本节新增核验动作：两 v2 文件全文重读；一次数值蒙特卡洛（numpy，300+60 试次，仅 stdout，无文件产物）独立检验 M12 阈值推导；未做任何新的网络抓取（v2 未新增文献条目与链接）。

### 9.1 v1 三项 Important 的解决确认

| 项 | v2 处置 | 判定 |
|---|---|---|
| Important-1（M7 单位） | M7 改为"逐通道 \|mean(colour) − base_rgb\| ≤ 2.0（单位：8-bit 灰度级）"。可行性复核：取整残差均值的标准误约 0.0065 灰度级，远小于 2.0，门既可通过又仍能捕捉粗均值漂移（clip 偏置、归一化 bug 等） | **已解决** |
| Important-2（M12 口径） | 写死为：6 对 × 4 组合各自计算、前景取第 3 节冻结 mask、逐像素三通道绝对差先对通道后对前景像素取均值、8-bit 灰度级、24 值全部 > 4.0（并给出等价最小值表述）。口径不再有任何自由度 | **已解决**（阈值/振幅变更另评，见 9.2-B） |
| Important-3（§4.1 数值标注） | lacunarity=2、gain=0.5、a=0.20 显式标注"工程适配（adaptation）之冻结值"，R25-LIT-04 引注限定为"目录级支撑结构本身，不为任何具体数值背书"；quintic 降为"标准实现惯例"，与 LIT-02 v2 的摘要级主张一致 | **已解决** |

### 9.2 实质性变更 A/B/C 的独立评估

**A. 振幅 a=0.16 → 0.20（M8 界同步 ceil(0.20·base_rgb)）。** 数学有效性复核：base_rgb 为整数时 |round(base_rgb·a·n)| ≤ ceil(0.20·base_rgb) 恒成立；按我 v1 实算的 base_rgb=(140,99,117)，上界 140·1.20=168 < 255、下界 99·0.80=79.2 > 0，全程无 clip 干扰，M7/M8 的推导前提保持成立。单变量契约不受影响（三候选共用振幅、base 仍为 a=0 退化），已落 adaptation 标注并冻结。**评估：成立，无异议。**

**B. M12 阈值 8.0 → 4.0 及其推导。** 我用与设计无关的独立蒙特卡洛复核（2005 个椭球面点、平面波叠加的带限高斯场逼近 fBm、每场去均值+max 归一，300 试次；另以真实抖动网格 Worley F1 构造 0.65·fBm+0.35·W 偏态混合 60 试次）：

- cand1 型 fBm{0.64,0.32,0.16}：E|n| 均值 0.283（p5 0.223，300 试次最差 0.182）→ base-对-候选 MAE 估计（a=0.20，mean(base_rgb)≈118.7）均值 6.7、p5 5.3、最差 4.3；
- cand2 型 fBm{0.48,0.24,0.12}：E|n| 均值 0.266 → MAE 均值 6.3、最差 4.2；
- cand3 型 Worley 偏态混合：E|n| 均值 0.254 → MAE 均值 6.0、最差 4.2；
- 候选互对（各自归一后差场）：MAE 估计均值 9.2、最差 5.5；
- 全部试次（含偏态压力情形与最差抽样）均 > 4.0。设计声称的期望带（base-对-候选 5.5–6.9、互对 7.8–9.7）与我的独立均值带（6.0–6.7、9.2）吻合；其"原 8.0 阈值在 a=0.16 下会误杀健康结果（期望约 5.5）"的诊断亦被我复算证实（a=0.16 时期望 MAE 约 4.7–5.4 < 8.0）。**结论：阈值 4.0 数量级站得住、余量合理，且 v2 条 3 已把 M12 误杀风险显式让位于 V3 原始分辨率复核，安全侧闭合。**
- 两处推导表述瑕疵（record-only，见 9.4 新 Minor）：（1）"2005 样本 max≈2.9–3.2σ" 归因错标——该比值是**相关场**的有效表现（我实测均值 2.89、p95 3.48），iid 2005 样本应约 4.07σ；数字本身对本场景取值正确，且即便按 iid 比值（E|n|≈0.196→MAE≈4.7）结论也不翻转；（2）E|n| 宽估上沿 0.35 按同式应映射到 MAE≈8.3，与文中"5.5–6.9"上沿不一致（区间传播未对齐；方向为多余保守，不影响门可行性）。

**C. 停止条件改写。** 条 1 移出 M12（消除 v1 条 1/条 3 矛盾，该自查修复成立）；条 2（V1∨V5→CONTINUITY_FAILED）、条 4（V2∨V4→STRUCTURE_UNSTRUCTURED_FAILED）覆盖全部视觉门，V1–V5 无遗漏、无重叠二义；条 5 RSS 显式落 R25_INVALID_OR_FAILED；条 6/7 显式声明为过程检查点不构成终态。**但发现一处新引入矛盾（v2-I1，Important）**：条 3 末句规定"若 M12 未达而 V3 判定可分，如实记录分歧并以 V3 为准（预门定位即止于预门）"，而第 145 行成功终态仍写"唯一成功终态：R25_MICROTEXTURE_ELIGIBLE（M1–M13 与 V1–V5 全过）"——M12 属 M1–M13。在可达状态"M12 未达且 V3 判可分"（按我 9.2-B 的余量分析，实测落在 4.0 附近的低概率情形真实存在）下：按第 145 行字面，ELIGIBLE 不可达，且条 1 已排除 M12、条 3 前半又因 V3 判可分而不触发 DIVERSITY_LIMITED——该状态**没有任何条款赋予终态**；按条 3 意图则应为 ELIGIBLE。两名执行者会给出不同终态判定，与 v1 Important-1/2 同类，必须修复。建议一句话：第 145 行改为"唯一成功终态：R25_MICROTEXTURE_ELIGIBLE（M1–M11、M13 与 V1–V5 全过，且 M12 通过或按条 3 记录分歧后 V3 判定可分）"。

### 9.3 v1 Minor 1–11 抽查

逐条对照 v2 文本确认：#1（LIT-02 收敛到摘要层级、quintic 降为实现惯例）、#2（LIT-04 补记目录级 "Domain Distortion"、§4.3 改为"存在性 LIT-04（目录级）+ 构造 LIT-09"、诚实限制 #3 同步）、#3（LIT-07 删正文级括注、记 PDF 密码保护）、#4（LIT-16 并记 49–70/49–71 两源分歧并声明以 DOI 记录为准）、#5（LIT-03 升级为含摘要核验、删"噪声基"超限定词）、#6（§1 补"ImageNet 训练的"）、#7（R24 数值改注 D-004、M12 处降级为叙事背景）、#8（§4.2 写死受检尺度集合并加带宽诚实注记）、#9（§5 写死 receipt 先写、manifest 最后写且不含自身哈希）、#10（条 5/6/7 显式映射终态/检查点）、#11（§1 补"在该论文的演示中"）——**11 项全部解决**。台账中以"T-003 复核确认"标注引用我方复核发现（LIT-03 摘要存在、LIT-04 Domain Distortion、LIT-07 PDF 密码保护），来源归属如实，合规。

### 9.4 新引入问题

- **v2-I1（Important）**：§9 条 3 V3 覆写条款与第 145 行成功终态公式矛盾，"M12 未达且 V3 判可分"状态终态未定义。详见 9.2-C，一句话可修。
- v2-M1（Minor，record-only）：M12 推导中 "2005 样本 max≈2.9–3.2σ" 归因错标（应为相关场有效比值；iid 2005 约 4.07σ）；数值与结论均不受影响，建议改一处措辞。
- v2-M2（Minor，record-only）：E|n| 宽估上沿 0.35 与期望 MAE 带上沿 6.9 区间传播不一致（0.35 应映射约 8.3）；方向保守，不影响门。
- v2-M3（Minor）：M10 仍写"所有倍频程 λ ≥ λ_floor"，未同步引用 §4.2 新定义的"受检尺度集合"（该集合已规范性地包含非倍频程尺度：candidate-2 扭曲场 λ 与 candidate-3 d_cell）。§4.2 本身已写死"集合内任一元素违反即机械门失败"，故无执行歧义实害，但 M10 措辞应改为"受检尺度集合（§4.2）内所有 λ ≥ λ_floor"以免两处表述分叉。

### 9.5 复审结论

**NEEDS_REVISION**（Critical 0 / Important 1 / 新 Minor 3）。v1 全部 Critical/Important/Minor 均已确认解决；实质性变更 A、B 经独立定量复核成立；唯一阻塞项为 v2-I1（成功终态公式与条 3 覆写条款的矛盾），修复为一句话量级。v2-M3 建议随手修复；v2-M1/M2 可 record-only。修复 v2-I1 后，本评审即可出具 APPROVED，无需再触发新一轮实质性复核（前提：除该句外其余文本不动；若修复时改动超出该句，需增量说明）。

### 9.6 复审合规声明

复审阶段：未执行任何 git 操作；除本文件外未写入任何文件（蒙特卡洛仅 stdout，无文件产物）；未修改两份被审文档；未渲染、未训练；未打开用户保护文件；未接触任何医疗/患者数据。

## 10. 终审（v3）

- 终审时间戳：2026-08-09T19:35 前后（+09:00）
- 对象：R25-DESIGN.md v3（全文重读，逐段与本人上下文中的 v2 副本对照）；R25-LITERATURE.md（重读首尾并对照，确认 v3 未触碰）。

### 10.1 核验 (a)：两处修复文本的语义与终态覆盖

**v2-I1 修复（第 145 行）**。实测文本："唯一成功终态：`R25_MICROTEXTURE_ELIGIBLE`（M1–M11、M13 与 V1–V5 全过，且 M12 通过，或 M12 未达但已按第 3 条如实记录分歧且 V3 原始分辨率判定可分）。"——与我在 9.2-C 给出的建议语义一致，且额外加入"已按第 3 条如实记录分歧"的审计要求（比我的建议更严，方向正确）。终态覆盖复核（逐状态枚举）：M1–M11/M13 任一失败→条 1 INVALID；RSS 越界→条 5 INVALID；V1∨V5 失败→条 2 CONTINUITY_FAILED；V2∨V4 失败→条 4 STRUCTURE_UNSTRUCTURED_FAILED；V3 失败→条 3 DIVERSITY_LIMITED；M12 未达且 V3 确认同质→条 3 DIVERSITY_LIMITED；M12 未达且 V3 判可分（记录分歧）→成功行第二析取支 ELIGIBLE；全过→ELIGIBLE。**每个可达终止状态恰有一个终态，原真空状态已闭合，无双重赋值。**"或"的辖域理论上可有两读，但在"触发即停"前提下条 1–4 先于成功判定耗尽所有失败路径，两种解析行为等价——无可利用的歧义。**v2-I1 确认解决，无新矛盾。**

**v2-M3 修复（第 118 行 M10）**。实测文本："M10 频带下限：§4.2 受检尺度集合（含 candidate-2 扭曲场尺度与 candidate-3 的 d_cell）内所有 λ ≥ λ_floor（实测记录于 receipt）。"——与 §4.2 的规范性集合枚举（c1 {0.64,0.32,0.16}；c2 主场 {0.48,0.24,0.12}+扭曲场 {0.50,0.25}；c3 fBm {0.64,0.32,0.16}+d_cell 0.09）逐项一致，两处表述不再分叉。**v2-M3 确认解决。**

### 10.2 核验 (b)：修订记录 v3 如实性

§12 v3 条目三项：条 1 如实转述第 145 行改动（措辞为摘要式转写，语义与正文一致）；条 2 如实记录 M10 同步；条 3 如实记录 v2-M1/M2 的 record-only 处置并指向本文件第 9 节——与协调方通报及实际改动一致。**如实。**

### 10.3 核验 (c)：其余文本未动

- R25-DESIGN.md：除第 118、145 两行为原位替换、§12 追加 v3 条目（4 行，177=173+4）外，第 1–117、119–144、147–163 行与我上下文中的 v2 副本逐段一致；冻结锚定表、16 文件名枚举、§10 主张边界、条 1–7 停止条件均逐字未动。
- R25-LITERATURE.md：首尾重读与 v2 副本逐字一致（wc 行数 183 与此前显示 184 之差仅为文件末尾无换行符）；本次留档 sha256 = `c823858e6177d57e45a80f308c5567e273899785a9733a478007faed855e20c3` 供后续任何一方复核基线。**确认未改动。**

### 10.4 终审结论

**APPROVED。** Critical 0 / Important 0：v1 三项 Important、11 项 Minor，v2 一项 Important（v2-I1）与 v2-M3 均已在正文中确认解决；v2-M1/M2 按约定 record-only 归档于本文件 9.4 节与设计 §12 v3 条 3，不构成阻塞。T-003 验收条件逐项满足：文献主张全部有一手来源支撑且不超界（第 2 节 16/16 复核）、工程适配已全部如实标注、单变量契约可执行且无隐藏第二变量（第 4 节）、十六图门可重放（4.3 节）、Critical 与 Important 清零。本评审支持将 T-004 置为 ready，交人工批准；本结论不构成任何 git、worktree 或实现授权（T-004/T-008 人工闸门不变）。

### 10.5 终审合规声明

终审阶段：未执行任何 git 操作；除本文件外未写入任何文件；未修改两份被审文档；未渲染、未训练；未打开用户保护文件；未接触任何医疗/患者数据。

## 11. v4 增量评审（M5 修订）

- 评审时间戳：2026-08-09（v4 增量，+09:00）
- 背景：T-005 实现按失败纪律在 M5 停机，报告 v3 M5 第二子句（"背景像素与 R19 渲染逐像素一致"）对任何颜色场不等于 R19 的变体结构性恒假。设计出 v4：M5 整条改写（§6 第 113 行）+ §12 追加 v4 条目，其余文本声明未动。
- 证据来源划分：R19 侧证据（下文 11.1）为**本人一手实测**；T-005 实现侧数字（其渲染 mask 与 R19 逐字节相同、其 canonical/z-plus 背景差异恰 89 像素且全在轮廓圈内）为**协调方转述**，本人未进入 r25 目录（按任务约束），不作独立背书、仅核其与 R19 侧证据的机制一致性。

### 11.1 证据 3 的一手复核（R19 冻结工件，本人实算）

方法：对 `screen-v1` 四对 renders/masks（z-plus、iso-plus × canonical、deformed），以 mask==255 为前景，实施 1 像素 8-邻域膨胀（3×3 结构元，边界截断），统计 mask 外非清屏色 (5,5,5) 像素及其与膨胀圈的包含关系。

| 视图 | mask 外像素 | 非 (5,5,5) 像素 | 落在 1px 膨胀圈内 | 圈外 | 膨胀圈大小 | 真背景区大小（膨胀补集） | 真背景区是否全为 (5,5,5) 且即 R19 自身 |
|---|---|---|---|---|---|---|---|
| canonical/z-plus | 234,626 | **89** | 89 | 0 | 837 | 233,789 | 是 |
| canonical/iso-plus | 239,917 | **82** | 82 | 0 | 744 | 239,173 | 是 |
| deformed-s0521-v0000/z-plus | 234,627 | **86** | 86 | 0 | 837 | 233,790 | 是 |
| deformed-s0521-v0000/iso-plus | 239,926 | **85** | 85 | 0 | 740 | 239,186 | 是 |

- 四数 **89/82/86/85 与设计 v4 修订记录所载逐一吻合**；越圈像素为 0——"深度为 0 而 RGB 被前景色覆盖"的像素**恰好全部**位于轮廓 1 像素 8-邻域圈内。
- 抽样该 89 像素的 RGB（如 (139,92,111)、(142,96,115)、(148,101,121)……）均为前景组织色而非清屏色，且彼此不同——故任何常量或不同色场（含 base）都不可能与之逐像素一致，**v3 M5 第二子句结构性不可满足得证**。
- 清屏色 (5,5,5) 与本人 v1 评审时读到的 R19 代码 `render_option.background_color = (0.02, 0.02, 0.02)`（`c1_r16_uv_render.py` L193，rint(0.02×255)=5）独立吻合。
- 附带确认：本人 v1–v3 评审曾判 M5"可计算"——可计算属实，但未检验"R19 自身渲染是否满足该子句于 mask 外全域"，故未发现其不可满足性；此为本评审自身的遗漏，如实记录。

### 11.2 M5 v4 新文本评审

实测文本（§6 第 113 行）三子句：
- **(a) mask 哈希相等**：保留不变（措辞升为"每 (网格,视图)"，更精确）。**通过。**
- **(b) 真背景一致性**：区域 = "mask 经 1 像素 8-邻域膨胀后的补集"——膨胀口径（1 像素、8-邻域）与区域划分（前景/轮廓圈/真背景三分，互斥完备）均写死，无歧义可计算；要求 = 等于清屏色（实测 (5,5,5)，rerun receipt 复记）且与 R19 逐像素一致。本人实测 R19 自身四视图真背景区全为 (5,5,5)（上表），故该门**可满足**且两项要求相容互证。**通过。**
- **(c) 轮廓圈豁免**：豁免区 = 膨胀区减前景，即上表 837/744/837/740 像素的圈；被豁免的失配像素（89/82/86/85）经实测**恰好全部**在圈内。豁免范围恰等于渲染器轮廓覆盖行为的发生域，且：几何/相机/投影仍由 (a) 的逐字节 mask 相等钉死（栅格覆盖集只依赖几何+相机+渲染器，与颜色场无关）；背景仍由 (b) 钉死；圈内像素取值本身就是受试单变量（顶点色场）的函数，其异常仍暴露在 clean 图中受 V 门与 T-007 原始分辨率复核审视——**豁免不放走任何冻结项泄漏，也不豁免受试变量的可见性**。**通过。**
- 与其余门/终态/主张边界零冲突：M1–M4、M6–M13、V1–V5、§8、§9 条 1–7、成功终态行、§10、§11 逐段与 v3 逐字一致（本人全文重读比对）；M5 仍属条 1 集合，失败→INVALID 不变；V2 注"mask 相等已保证轮廓"经 (a) 仍成立；台账未动（sha256 复核仍为 `c823858e6177d57e45a80f308c5567e273899785a9733a478007faed855e20c3`）。**通过。**

### 11.3 修订记录 v4 如实性

- 实质声明如实：结构性不可满足的论证与我 11.1 一手复核一致；"实验变量、冻结项、参数、16 图契约与主张边界零变化"经全文逐段比对为**真**；"经 T-003 评审确认后 T-005 方可续跑"的流程约束正确。
- **v4-m1（Minor，record-only，建议下次自然修订时顺手更正）**：v4 条目括注"真背景区（mask 1 像素膨胀之补集，共 234,537 像素与 R19 完全一致的区域）"数字错标——234,537 = canonical/z-plus 的 mask 外像素数 234,626 减 89 个失配像素（本人实算恰合），即 T-005 尝试中"mask 外经验性一致像素数"，**不是** v4 定义的真背景区（膨胀补集）大小；后者按视图分别为 233,789 / 239,173 / 233,790 / 239,186（上表），且该量本应按视图分列而非单数。M5 门文本自身不含任何像素计数，可执行性不受影响；正确数值以本节为准。
- v4-m2（Minor，record-only）：§12 条目顺序为 v1、v2、v4、v3——v4 误插于 v3 之前，时序阅读混乱，建议顺手归位。
- v4-m3（Minor，record-only）：§3 冻结表"背景与深度 mask｜与 R19 逐像素一致"行未随 M5 更新措辞；在 v4 的区域三分法下"背景"=真背景区，该行仍为真且 M5 才是操作性判据，无执行歧义；建议下次自然修订时在该行加"（背景之操作定义见 M5(b)(c)）"指针。

### 11.4 v4 增量结论

**APPROVED。** Critical 0 / Important 0；新增 record-only 注记 3 条（v4-m1/m2/m3，均不阻塞，正确数值与更正建议已归档于本节）。M5 v4 三子句无歧义、经 R19 一手工件验证可满足、豁免恰好只覆盖渲染器固有行为、冻结证明链完整、与全文零冲突。本评审同意 T-005 按 v4 续跑；按 no-clobber 纪律，停机工件应保留原位、续跑走新版本目录。本结论不构成任何 git、worktree 或额外实现授权。

### 11.5 v4 增量合规声明

本阶段：未执行任何 git 操作；除本文件外未写入任何文件（像素统计仅 stdout）；未修改被审文档；未渲染、未训练；未进入 r25 验证目录与 r25 worktree；未打开用户保护文件；未接触任何医疗/患者数据。
