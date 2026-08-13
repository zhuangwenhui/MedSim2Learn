# C1 外观 DFS 路线总台账（假设-验证-总结 纸面闭环）

编制：2026-08-10（过夜收尾）。范围：Windows 主机 codex 实验分支线（DataImprove C1，R1–R25）。
服务器训练线的实验台账另见仓库 `experiments/INDEX.md`（branch `kidknet-experiments`）。
证据锚：STATE 事实/检查点 = `handoff/2026-08-09_data-improve/STATE.yaml`；验证工件根 = `D:\MedSim2Learn-C1-verification\`；各路线研究文档在其分支的 `Deform_post/research/data_improve/`。
处置代号：CLOSED=有终态结论；LIMITED=受限关闭；FAIL=否定结论（同样是结论）；SUPERSEDED=被后续路线取代；FROZEN=整线冻结后的保留资产。所有分支引用完整保留；worktree 已按批签清单收纳（见 WORKTREE-TRIAGE-2026-08-10.md 执行记录）。

| 路线 | 假设/问题 | 验证结果（终态） | 处置 |
|---|---|---|---|
| R1 legacy-vertex-sine 等竞赛 | 最小外观改动可行性竞赛 | 赛果见 2026-07-14 race report（DataImprove 分支） | SUPERSEDED |
| R2 PBR 环境 | PBR 渲染在本环境可行 | headless 失败→Windows 原生通过（C-F002）；方向技术上开放但未续投 | CLOSED（搁置） |
| R5 多视角 / ViewCORAL | 视角因子与 CORAL 因子设计 | 未跑出结论即被 07-03 重定标吸收（视角=H1b 待消融） | SUPERSEDED |
| R6 光照/背景/纹理 stage0 屏筛 | 各外观因子的 stage0 探针 | 部分探针有产出、无统一终态；规划/审计文档已保全（DataImprove@4482526） | SUPERSEDED |
| R7 光照训练筛 | 光照因子对训练的影响 | INCONCLUSIVE（F-EXP-003） | CLOSED |
| R8 纹理训练筛 | 纹理因子对训练的影响 | TRADEOFF（F-EXP-004） | CLOSED |
| R9 纹理保真门 | 保真度门控设计 | 门规格入档（2026-07-30 spec） | SUPERSEDED |
| R10A/B 结构纹理竞赛 | crossfit 图集 vs 血管纹理 | 竞赛报告 2026-07-30；未晋级 | SUPERSEDED（残留已保全 be32237/9503378） |
| R11/R12 源契约与纹理基线 | 纹理源契约、PBR 完整竞赛 | 演进入 R13–R16 | SUPERSEDED（残留已保全 8125e96/6bc72eb） |
| R13A/B 图集与 quilting | 多尺度图集 vs 图像 quilting | 演进入 R14/R15 缝合线 | SUPERSEDED（台账笔迹已保全 0cefc30） |
| R14 缝合竞赛（3 臂） | quilting 接缝消除 | 演进入 R15 | SUPERSEDED |
| R15 合成器竞赛（3 臂） | 接缝合成器 | 演进入 R16/R17 | SUPERSEDED |
| R16 UV 渲染契约 / 净源平坦度 | UV 纹理渲染契约 | 契约建立，暴露 UV chart 问题 | SUPERSEDED |
| R17 连续样本纹理 | 一张连续 atlas + UV 映射可得连续表面 | **FAIL**：UV chart 邻接断裂（C-F003）→ 裁定改物体空间 | CLOSED |
| **R19 三平面连续基线** | 物体空间三平面逐顶点场可消除 chart 突变 | **R19_SURFACE_CONTINUITY_ELIGIBLE**（十视角零断裂；RSS 232.6MB） | CLOSED，**基线资产** |
| R20 C/E 多样性双臂 | 色彩抖动 / 真实样本源的多样性 | R20_BOTH_DIVERSITY_LIMITED（F-EXP-006；C-F004） | LIMITED（残留已保全 a8567ca/d2196d5） |
| R21 程序化血管 | 顶点色可表现亚边宽血管 | 尺度/表示受限（C-F005）→ 需连续场/片元级 | LIMITED |
| R22 血管对比度 | 配对 ROI 标注定血管色 | **FAIL**：ROI 语义不连贯（C-F006） | CLOSED（残留已保全 d77a64c） |
| R23 隐式血管宽度 | 隐式场携带血管宽度 | 四固定视图受限接受；controlled diffuse 胜出（F-EXP-009/010；C-F007） | CLOSED，资产冻结 |
| R24 样本源质量 | 精选真实样本源 v2 契约 | 连续性过 / 空间多样性受限（F-EXP-011；C-F008/9） | LIMITED，路线关闭 |
| **R25 程序化多尺度微纹理** | 程序化场替代真实像素源 | **R25_MICROTEXTURE_ELIGIBLE**（16 图全门通过；提交 9c74cf0） | CLOSED，**DR 素材** |

## 整线裁定（2026-08-09/10 已与所有者确认）

外观 DFS 整线**冻结**（无 R26）。全部路线的共同主张边界不变：**没有任何一条曾建立
外观差距缩小或训练收益**（F-EXP-012/013）——那正是转向现行主线的原因。存活资产三件：
R19 连续性基线、R23 受限血管资产、R25 程序化纹理族；三者的下游用途 = 现行主线
Track C 的 C1 外观随机化素材（设计见 render-guards 分支
`Deform_post/research/data_improve/2026-08-10-c1-appearance-dr-design.md`）。

## 现行主线（接棒者）

`kidknet-experiments`@95b765f 的 07-03 重定标：zero-real-label sim→real、c2=基线/c1=天花板、
主指标 gap-closed %；路线图 = F 修（已落地并字节验证，guards@7db8976）→ Track C 因子隔离
（C1 外观 → C3 接触点 → C2 视角）→（测量卫生并行）→ UDA 后手（CORAL 训练损失已判 NULL
并 PARK，见 `experiments/2026-07-03_trackb-uda/README.md`）。
