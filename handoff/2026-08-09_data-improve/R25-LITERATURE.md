# C1-R25 程序化多尺度组织微纹理文献台账

**编制时间戳：** `2026-08-09T18:42:13+09:00`
**检索窗口（本地 JST +09:00）：** `2026-08-09T18:31:55` 至 `2026-08-09T18:37:59`（并行批量抓取，逐条 retrieved_at 精确到分钟）
**检索执行：** 文献检索子代理（机械检索按 `fable5_policy.cost_strategy` 委派）；台账编纂与主张边界把关：main（Fable 5）。

本台账记录方法的存在性与 R25 设计所引用的主张。它不构成"任一方法能改进本项目图像或缩小外观差距"的实验证据。

## 核验方式说明（诚实记录）

dl.acm.org、Wiley、Taylor&Francis、SpringerLink、OpenReview、HAL 等站点对自动抓取返回 403 / CAPTCHA / 机器人墙。对这些条目，DOI 与标题/作者/年份/刊物的对应关系经 Crossref 官方注册库 API（`https://api.crossref.org/works/<DOI>`）核验；摘要内容经官方存档或作者机构页面（arXiv、ACM SIGGRAPH History Archives、NVIDIA developer、cns.nyu.edu、GitHub、iquilezles.org——本次会话内均直接抓取成功）核验。人工在浏览器中打开主链接可正常访问；自动复核请使用各条目列出的机器可核验 URL。每条注明实际抓到了什么。

标签约定：`[ADOPT-STRUCTURE]` 设计直接采用其构造；`[ADOPT-PRINCIPLE]` 设计采用其原理但非完整实现；`[ADOPT-JUSTIFICATION]` 仅作研究动机依据；`[TECH-REF]` 非同行评审的技术参考，引用强度受限。

## R25-LIT-01 `[ADOPT-STRUCTURE]` Perlin 梯度噪声与 solid texture

- K. Perlin, "An Image Synthesizer", SIGGRAPH '85 / ACM SIGGRAPH Computer Graphics 19(3), 1985.
- 主链接：https://dl.acm.org/doi/10.1145/325165.325247 （DOI: https://doi.org/10.1145/325165.325247 ）
- 机器可核验：https://api.crossref.org/works/10.1145/325165.325247 ；内容页：https://history.siggraph.org/learning/an-image-synthesizer-by-perlin/
- 核验：Crossref 元数据匹配；SIGGRAPH History 存档页抓取成功，摘要确认 "solid texture" 概念、受控随机效应原语、以非线性函数复合构建自然复杂度（marble、rock 等实例）。retrieved_at: 2026-08-09T18:32/18:37+09:00。
- 已核实主张：带限随机 Noise 函数与"solid texture"——自然材质外观可由直接在三维空间求值的随机函数复合生成，而非依赖二维纹理映射。
- 项目用法：R25 微纹理场以三维 canonical 空间中的梯度噪声为基元，逐顶点求值。
- 主张边界：不预先证明该基元在本项目 512×512 无光照渲染下产生合格的组织样外观。

## R25-LIT-02 `[ADOPT-STRUCTURE]` 改进型梯度噪声

- K. Perlin, "Improving Noise", ACM Transactions on Graphics 21(3) (Proc. SIGGRAPH 2002), 2002.
- 主链接：https://dl.acm.org/doi/10.1145/566654.566636 （DOI: https://doi.org/10.1145/566654.566636 ）
- 机器可核验：https://api.crossref.org/works/10.1145/566654.566636
- 核验：Crossref 元数据匹配；Crossref 记录摘要确认修正原始 Noise 的"二阶插值不连续（second order interpolation discontinuity）"与"非最优梯度计算（unoptimal gradient computation）"。retrieved_at: 2026-08-09T18:32+09:00。
- 已核实主张：2002 修订修正了原始 Noise 的二阶插值不连续与非最优梯度计算（以 Crossref 摘要为证据层级）。
- 项目用法：R25 实现采用该修订思路的梯度噪声；具体的 quintic 淡入形式作为标准实现惯例采用，标注为实现选择，不归为本条逐句核验内容。
- 主张边界：证据层级到摘要为止；"消除可见格点伪影"等正文级效果表述不在本条已核验范围内；仅支持基元性质，不预证视觉结果。

## R25-LIT-03 `[ADOPT-PRINCIPLE]` 噪声基分形多尺度合成

- F. K. Musgrave, C. E. Kolb, R. S. Mace, "The Synthesis and Rendering of Eroded Fractal Terrains", SIGGRAPH '89 / ACM SIGGRAPH Computer Graphics 23(3), 1989.
- 主链接：https://dl.acm.org/doi/10.1145/74334.74337 （DOI: https://doi.org/10.1145/74334.74337 ）
- 机器可核验：https://api.crossref.org/works/10.1145/74334.74337
- 核验：Crossref 匹配标题、三位作者、刊物与年份；T-003 复核确认该 Crossref 记录并含摘要（分形地形高度场的合成与渲染）。正文未读（ACM 403，无官方镜像抓取成功）。retrieved_at: 2026-08-09T18:32+09:00；T-003 复核 2026-08-09T19:03 前后。
- 已核实主张：以分形多尺度方法合成与渲染自然地形（高度场）的 SIGGRAPH 一手来源（Crossref 元数据与摘要层面）。
- 项目用法：作为"多尺度组合合成自然结构"的原理出处之一。
- 主张边界：核验到 Crossref 摘要为止、正文未读；octave/lacunarity 等具体构造术语不归于本文，以 R25-LIT-04 已核验目录为准。

## R25-LIT-04 `[ADOPT-STRUCTURE]` fBm 逐倍频程构造（octaves/lacunarity/gain）

- D. S. Ebert, F. K. Musgrave, D. Peachey, K. Perlin, S. Worley, "Texturing and Modeling: A Procedural Approach", 3rd ed., Morgan Kaufmann/Elsevier, ISBN 9781558608481, 2003.
- 主链接：https://shop.elsevier.com/books/texturing-and-modeling/ebert/978-1-55860-848-1
- 核验：Elsevier 官方页两次抓取成功；作者、版次、ISBN 确认；目录确认含 "Making Noises"（lattice/value/gradient/sparse-convolution noise）、"Procedural fBm"、"Multifractal Functions"、"Octaves: Limits to Detail"、"Fractal Solid Textures"、"Cellular Texturing"、"Real-Time Procedural Solid Texturing"；T-003 复核另确认目录含 Mojoworld 章 "Domain Distortion" 小节。retrieved_at: 2026-08-09T18:34/18:35+09:00；T-003 复核 2026-08-09T19:03 前后。
- 已核实主张：由发明者本人（Perlin、Peachey、Worley、Musgrave）成书的程序化纹理规范实践：fBm 为噪声倍频程加权求和，带频率/粗糙度控制；含 solid texturing、cellular texturing，且目录级含域扭曲（Domain Distortion）主题。
- 项目用法：R25 三个候选的 fBm 构造采用本书的逐倍频程结构；candidate-2 域扭曲的"印刷出版物级存在性"亦引本条（目录级）。lacunarity=2、gain=0.5 等具体数值为项目工程适配，不引本书背书。
- 主张边界：专著而非同行评审论文；核验到章节/小节标题级而非页级内容；域扭曲的具体构造式仍以 R25-LIT-09 为参考。

## R25-LIT-05 `[ADOPT-STRUCTURE]` 细胞（Worley）基函数

- S. Worley, "A Cellular Texture Basis Function", SIGGRAPH '96, 1996.
- 主链接：https://dl.acm.org/doi/10.1145/237170.237267 （DOI: https://doi.org/10.1145/237170.237267 ）
- 机器可核验：https://api.crossref.org/works/10.1145/237170.237267 ；内容页：https://history.siggraph.org/learning/a-cellular-texture-basis-function-by-worley/
- 核验：Crossref 匹配；SIGGRAPH History 存档页抓取成功，摘要确认"补足 Perlin 噪声的新基函数，基于把空间随机划分为细胞"，示例纹理明确包含 "organic crusty skin"，无需预计算或查表。retrieved_at: 2026-08-09T18:32/18:37+09:00。
- 已核实主张：基于三维随机特征点距离场的细胞基函数是与 Perlin 噪声互补的程序化物体空间基元，且被演示可产生有机表面外观（明确含 organic crusty skin）。
- 项目用法：candidate-3 混入 Worley F1 分量以引入可表示频带边缘的颗粒/细胞结构。
- 主张边界："organic crusty skin" 是图形学示例词，不构成对肾脏组织外观的任何生理学主张。

## R25-LIT-06 `[ADOPT-PRINCIPLE]` 频谱可控程序化噪声与免参数化表面噪声

- A. Lagae, S. Lefebvre, G. Drettakis, P. Dutré, "Procedural Noise using Sparse Gabor Convolution", ACM TOG 28(3) (Proc. SIGGRAPH 2009), 2009.
- 主链接：https://dl.acm.org/doi/10.1145/1531326.1531360 （DOI: https://doi.org/10.1145/1531326.1531360 ）
- 机器可核验：https://api.crossref.org/works/10.1145/1531326.1531360 ；内容页：https://history.siggraph.org/learning/procedural-noise-using-sparse-gabor-convolution-by-lagae-lefebvre-drettakis-and-dutre/
- 核验：Crossref 匹配；SIGGRAPH History 页抓取成功，摘要确认"以方向、主频率、带宽等直观参数实现精确频谱控制"，且 "setup-free surface noise …… 不需要纹理参数化"。retrieved_at: 2026-08-09T18:32/18:36+09:00。
- 已核实主张：程序化噪声可按主频率/带宽/方向做精确频谱设计；噪声可以在不建立任何 UV 参数化的情况下附着于表面。
- 项目用法：R25 按"每倍频程波长明确记账"的频谱意识设计候选，并以此文佐证免 UV 路线的正当性；R25 不实现 Gabor 卷积本身。
- 主张边界：R25 并非 Gabor 噪声实现，不得以其名称标注本方法。

## R25-LIT-07 `[ADOPT-PRINCIPLE]` 程序化噪声函数综述（定义与分类）

- A. Lagae, S. Lefebvre, R. Cook, T. DeRose, G. Drettakis, D. S. Ebert, J. P. Lewis, K. Perlin, M. Zwicker, "A Survey of Procedural Noise Functions", Computer Graphics Forum 29(8):2579–2600, 2010.
- 主链接：https://onlinelibrary.wiley.com/doi/10.1111/j.1467-8659.2010.01827.x （DOI: https://doi.org/10.1111/j.1467-8659.2010.01827.x ）
- 机器可核验：https://api.crossref.org/works/10.1111/j.1467-8659.2010.01827.x ；作者副本：https://www.cs.umd.edu/~zwicker/publications/SurveyProceduralNoise-CGF10.pdf
- 核验：Crossref 匹配标题与全部九位作者；摘要文本来自 HAL 记录（hal-00920177）的搜索结果渲染而非子代理直接抓取的官方页面（Wiley/HAL 对机器人 403）；T-003 复核抓取 cs.umd.edu 作者副本 PDF 受密码保护、正文不可提取。retrieved_at: 2026-08-09T18:32/18:36+09:00。
- 已核实主张：同行评审综述，正式定义程序化噪声函数并对 lattice 梯度噪声、稀疏卷积/Gabor、细胞噪声等族系分类比较。
- 项目用法：为 R25 的术语与噪声族选择提供定义与分类依据。
- 主张边界：只引其定义与分类；未经作者副本逐页核对前，不引用其正文中任何具体公式或数值结论。

## R25-LIT-08 `[ADOPT-PRINCIPLE]` Solid texturing（连续三维物体空间纹理场）

- D. R. Peachey, "Solid Texturing of Complex Surfaces", SIGGRAPH '85 / ACM SIGGRAPH Computer Graphics 19(3), 1985.
- 主链接：https://dl.acm.org/doi/10.1145/325165.325246 （DOI: https://doi.org/10.1145/325165.325246 ）
- 机器可核验：https://api.crossref.org/works/10.1145/325165.325246 ；内容页：https://history.siggraph.org/learning/solid-texturing-of-complex-surfaces-by-peachey/
- 核验：Crossref 匹配；SIGGRAPH History 页抓取成功，摘要确认 solid texturing "使用定义在三维空间区域上的纹理函数"，"可轻松应用于难以用二维纹理函数处理的复杂表面"。retrieved_at: 2026-08-09T18:32/18:37+09:00。
- 已核实主张：把纹理定义为三维物体空间上的连续函数可回避复杂表面的二维/UV 参数化问题。
- 项目用法：R25 连续物体空间场约束（继承 C-F003 的 R17 UV 教训与 R19 物体空间基线）的直接一手依据。
- 主张边界：与 R25-LIT-01 同为 solid texturing 起源；不预证视觉质量。

## R25-LIT-09 `[TECH-REF]` Domain warping（域扭曲）

- I. Quilez, "warping"（domain distortion / fBm warping），iquilezles.org 技术文章（无日期）。
- 主链接：https://iquilezles.org/articles/warp/
- 核验：页面抓取成功；确认作者与核心构造 f(p + h(p))（可迭代嵌套），以 fBm 作为偏移场产生有机形态。retrieved_at: 2026-08-09T18:33+09:00。
- 已核实主张：以噪声场作为域偏移复合 fBm（f(p+h(p))，可迭代）是公认的实践者技术，可把平稳噪声转化为有机外观结构。
- 项目用法：candidate-2 采用单步域扭曲，具体构造式以本条为参考。
- 主张边界：**非同行评审**技术文章，仅以实践者参考身份引用。谱系支撑：R25-LIT-01 已核验的"非线性函数复合"表述为同行评审先驱；R25-LIT-04 目录级含 "Domain Distortion" 小节（印刷出版物级存在性，T-003 复核确认）；本条仍是具体构造的唯一直接参考。

## R25-LIT-10 `[TECH-REF]` 三平面投影（R19 谱系上下文）

- R. Geiss, "Generating Complex Procedural Terrains Using the GPU", GPU Gems 3, ch.1, NVIDIA/Addison-Wesley, 2007.
- 主链接：https://developer.nvidia.com/gpugems/gpugems3/part-i-geometry/chapter-1-generating-complex-procedural-terrains-using-gpu
- 核验：NVIDIA 官方开发者页抓取成功；章节、作者、书目确认；三平面段落原文核对（三个轴向平面投影按失真最小选取并在过渡区混合）。retrieved_at: 2026-08-09T18:33+09:00。
- 已核实主张：三平面投影（三个轴对齐平面投影按表面朝向加权混合）是无需 UV 参数化的表面纹理技术。
- 项目用法：仅作 R19 映射谱系的上下文。R25 的场直接在三维空间求值（true solid texture），**不经过**三平面投影；R19 的三平面路径只保留在"基色派生自 R19 顶点颜色统计"这一冻结继承上。
- 主张边界：厂商书章，非同行评审；若 R25 未来改用二维场投影变体才需要正式引用。

## R25-LIT-11 `[ADOPT-JUSTIFICATION]` CNN 的纹理偏好

- R. Geirhos, P. Rubisch, C. Michaelis, M. Bethge, F. A. Wichmann, W. Brendel, "ImageNet-trained CNNs are biased towards texture; increasing shape bias improves accuracy and robustness", ICLR 2019 (oral)。
- 主链接：https://arxiv.org/abs/1811.12231 （会议正式页：https://openreview.net/forum?id=Bygh9j09KX ）
- 核验：arXiv 页抓取成功；标题、六位作者、摘要引文确认（"strongly biased towards recognising textures rather than shapes"）；arXiv 备注确认 ICLR 2019 oral。OpenReview 对机器人弹 CAPTCHA（人工浏览器可开）。retrieved_at: 2026-08-09T18:33–18:34+09:00。
- 已核实主张：标准 ImageNet 训练的 CNN 主要依赖局部纹理统计而非全局形状进行识别。
- 项目用法：作为"合成渲染的表面纹理统计是下游 CNN 所学内容的一阶决定因素、纹理统计失配是合理的域差距机制"这一研究动机。
- 主张边界：其证据在 ImageNet 分类 CNN；外推到本项目 image→force 回归网络是推断，措辞只可用"提示（suggests）"，不可用"证明"。

## R25-LIT-12 `[ADOPT-JUSTIFICATION]` 域随机化

- J. Tobin, R. Fong, A. Ray, J. Schneider, W. Zaremba, P. Abbeel, "Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World", IEEE/RSJ IROS 2017。
- 主链接：https://arxiv.org/abs/1703.06907 （正式版 DOI: https://doi.org/10.1109/IROS.2017.8202133 ）
- 机器可核验：https://api.crossref.org/works/10.1109/IROS.2017.8202133
- 核验：arXiv 页抓取成功；标题、六位作者、摘要引文确认（"With enough variability in the simulator, the real world may appear to the model as just another variation"；训练仅用"non-realistic random textures"的模拟数据）；IEEE DOI 经 Crossref 核验同题同作者。retrieved_at: 2026-08-09T18:33/18:34+09:00。
- 已核实主张：训练时随机化渲染属性（明确包括非写实随机纹理）可使纯模拟图像训练的模型迁移到真实图像。
- 项目用法：支撑 R25 "参数化可随机族"的取向（相对于逼近单一真实外观）；R25 预览本身仍是固定种子的三个候选，随机化属未来阶段。
- 主张边界：其任务是机器人目标定位，非力回归；仅作原则出处。

## R25-LIT-13 `[ADOPT-JUSTIFICATION]` 非写实随机化的补充证据

- J. Tremblay, A. Prakash, D. Acuna, M. Brophy, V. Jampani, C. Anil, T. To, E. Cameracci, S. Boochoon, S. Birchfield, "Training Deep Networks with Synthetic Data: Bridging the Reality Gap by Domain Randomization", CVPR 2018 Workshops。
- 主链接：https://arxiv.org/abs/1804.06516 （正式版 DOI: https://doi.org/10.1109/CVPRW.2018.00143 ）
- 机器可核验：https://api.crossref.org/works/10.1109/CVPRW.2018.00143
- 核验：arXiv 页抓取成功；标题、十位作者、摘要引文确认（以"非写实方式随机化模拟器参数，迫使网络学习本质特征"）；IEEE CVPRW DOI 经 Crossref 核验。retrieved_at: 2026-08-09T18:33/18:34+09:00。
- 已核实主张：对模拟器参数（含纹理）做刻意非写实的随机化可推动网络学习任务本质特征，合成训练的检测器可迁移至真实图像。
- 项目用法：R25-LIT-12 的补充证据。
- 主张边界：**Workshop 论文**（CVPR-W），仅作 R25-LIT-12 之后的次级支撑，不得作首要出处。

## R25-LIT-14 `[ADOPT-JUSTIFICATION]` 手术视觉合成数据管线（工具证据）

- J. Cartucho, S. Tukra, Y. Li, D. S. Elson, S. Giannarou, "VisionBlender: a tool to efficiently generate computer vision datasets for robotic surgery", Computer Methods in Biomechanics and Biomedical Engineering: Imaging & Visualization (Taylor & Francis), 2020（刊卷 2021）。
- 主链接：https://doi.org/10.1080/21681163.2020.1835546 （出版社页：https://www.tandfonline.com/doi/full/10.1080/21681163.2020.1835546 ）
- 机器可核验：https://api.crossref.org/works/10.1080/21681163.2020.1835546 ；官方代码：https://github.com/Cartucho/vision_blender
- 核验：Crossref 匹配标题、五位作者、期刊、年份；官方 GitHub 抓取成功，确认工具生成 depth/disparity/segmentation/normals/optical flow/pose/相机参数的稠密真值并引用该文。T&F 站点对机器人 403。retrieved_at: 2026-08-09T18:34+09:00。
- 已核实主张：存在同行评审、专为机器人/腹腔镜手术视觉构建的 Blender 合成数据集管线，提供真实数据无法获得的稠密真值监督。
- 项目用法：佐证"渲染合成数据是手术视觉领域被接受的监督来源"这一背景。
- 主张边界：短工具文（约 8 页，T&F 非 MDPI）；其演示的是数据集生成而非力估计。README 中"MICCAI 2020 workshop 最佳论文奖"未独立核验，**不得引用该奖项**。

## R25-LIT-15 `[ADOPT-JUSTIFICATION]` 腹腔镜合成数据可用但朴素渲染外观不足

- M. Pfeiffer, I. Funke, M. R. Robu, S. Bodenstedt, L. Strenger, S. Engelhardt, T. Roß, M. J. Clarkson, K. Gurusamy, B. R. Davidson, L. Maier-Hein, C. Riediger, T. Welsch, J. Weitz, S. Speidel, "Generating Large Labeled Data Sets for Laparoscopic Image Processing Tasks Using Unpaired Image-to-Image Translation", MICCAI 2019 (LNCS 11768, Springer)。
- 主链接：https://doi.org/10.1007/978-3-030-32254-0_14 （预印本：https://arxiv.org/abs/1907.02882 ）
- 机器可核验：https://api.crossref.org/works/10.1007/978-3-030-32254-0_14
- 核验：Crossref 匹配标题与全部十五位作者、MICCAI 2019 LNCS；arXiv 摘要抓取成功：由腹腔镜模拟生成带标注合成数据，经非配对图像翻译增真后训练肝脏分割，在真实术中图像上 dice 最高 0.89，无需人工标注真实录像；arXiv 备注确认 MICCAI 2019 接收。retrieved_at: 2026-08-09T18:34+09:00。
- 已核实主张：在模拟腹腔镜场景渲染上训练的网络可在真实术中图像上工作——但该一手演示中，渲染需要额外的学习式增真步骤（非配对图像翻译）来弥合外观差距。
- 项目用法：双向诚实引用——既支持"合成手术数据路线成立"，也记录"朴素渲染外观单独不够"，后者正是 R25 纹理路线要面对的问题。
- 主张边界：MICCAI 主会论文（强）；其任务为肝脏分割，非肾脏、非力回归。不得由此推出 R25 会缩小差距。

## R25-LIT-16 `[ADOPT-PRINCIPLE]` 多尺度联合统计刻画自然纹理

- J. Portilla, E. P. Simoncelli, "A Parametric Texture Model Based on Joint Statistics of Complex Wavelet Coefficients", International Journal of Computer Vision 40(1), 2000（页码两源分歧：Crossref 记 49–70，NYU 官方模型页记 49–71，如实并记，以 DOI 记录为准）。
- 主链接：https://doi.org/10.1023/A:1026553619983 （出版社页：https://link.springer.com/article/10.1023/A:1026553619983 ）
- 机器可核验：https://api.crossref.org/works/10.1023/A:1026553619983 ；官方模型页：https://www.cns.nyu.edu/~lcv/texture/
- 核验：Crossref 匹配标题、两位作者、IJCV 2000（页码 49–70）；NYU 计算视觉实验室官方页抓取成功，确认书目（IJCV 40(1):49–71, 2000-10）与模型内容（跨尺度、跨方向复小波系数联合统计表征纹理，以迭代调整噪声匹配统计实现合成）；两源页码分歧已并记。SpringerLink 机器人墙（303 跳转）。retrieved_at: 2026-08-09T18:33/18:37+09:00。
- 已核实主张：自然纹理的感知外观由跨尺度、跨方向的带通系数联合统计良好刻画——即"跨尺度相关的多尺度结构"而非单带无结构噪声。
- 项目用法：支撑 T-006 验收中"纹理须呈现连贯多尺度结构而非无结构噪声"这一门的合理性，以及 R25 采用跨倍频程相关构造（fBm 共享同一基场）的设计取向。
- 主张边界：R25 不实现 Portilla–Simoncelli 模型，不得以其名称标注方法；径向功率谱只作诊断辅助，不作为通过判据。

## 诚实限制汇总

1. R25-LIT-03（Musgrave 1989）核验到 Crossref 元数据与摘要（T-003 复核确认其记录含摘要）；正文未读。octave/lacunarity 术语出处以 R25-LIT-04 已核验目录为准。
2. R25-LIT-07（综述）摘要文本来自 HAL 记录的搜索结果渲染，非直接抓取的官方页面；元数据经 Crossref 核验；作者副本 PDF 受密码保护，正文级表述一律不引。
3. Domain warping 的同行评审级一手构造来源仍缺——R25-LIT-09 是实践者技术文章，已如实标注 `[TECH-REF]`；R25-LIT-04 目录级含 "Domain Distortion" 小节（T-003 复核确认），提供印刷出版物级的存在性支撑，但页级内容未核验。
4. 机器人墙站点（dl.acm.org、Wiley、T&F、Springer、OpenReview、HAL、KU Leuven 个人页、nyuscholars）：自动复核须使用各条目的 api.crossref.org URL 与已列内容页（arXiv、history.siggraph.org、developer.nvidia.com、cns.nyu.edu、github.com、iquilezles.org——本会话均抓取成功）。
5. 检索过程中一次 WebFetch 将某 Inria PDF 自动缓存到会话工具结果目录（harness 内部路径，非仓库文件）；未发生任何仓库写入或 git 操作。
6. 按仓库既定偏好，本台账不收录 MDPI 来源。

## 修订记录

- v1（2026-08-09T18:42:13+09:00）：初版，16 条。
- v2（2026-08-09，响应 T-003 评审 Minor-1..5）：LIT-02 主张收敛到 Crossref 摘要层级（quintic 降为实现惯例）；LIT-03 升级为"含摘要"核验并收敛限定词；LIT-04 补记目录级 "Domain Distortion" 小节并修正"未覆盖 domain warping"的过时陈述（保守方向错误）；LIT-07 删去正文级括注、补记作者副本 PDF 密码保护；LIT-16 并记两源页码分歧（Crossref 49–70 / NYU 页 49–71）；LIT-09 谱系注记同步更新；诚实限制汇总 #1/#2/#3 同步更新。条目主链接与 DOI 无一变更。
