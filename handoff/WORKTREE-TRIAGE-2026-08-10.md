# Worktree 清理批签清单（2026-08-10）

> **执行记录（2026-08-10 过夜，所有者当晚指令"收尾 codex 实验分支、不必逐项请示"）：**
> 全部按本清单执行完毕，38 → 7（主检出 + R19/R23/R24/R25 + DataImprove + Windows-Render-Guards）。
> B 类 9 个直接删除；C-2 类 7 个丢弃琐碎脏文件后删除（R1 的"M9"经 add -A 证实为 CRLF 幻影、树本干净）；
> C-1 保全提交后删除：r20-color a8567ca、r20-exemplar d2196d5、r10a be32237、r10b 9503378、r22 d77a64c、
> r13b 台账笔迹 0cefc30（其两份 R14 文档经核实已在两个 R14 分支中入库，按预案丢弃）；
> DataImprove 文档保全 4482526（工作目录保留）；C-3 类 8 个保全提交（8125e96/6bc72eb/527bf25/86d975e/
> f139ee3/f6ae802/e3ae5f5/6bee9e0）后删除；DomainGapMetrics 的 MMD² 工具判定有价值，保全为 77f8252
> （codex/domain-gap-metrics 分支）后删除工作目录。全部提交署名 WENHUIZ、无任何尾巴；分支引用零删除。

盘点基准：38 个 worktree（含主检出）。原则：**分支引用一律保留**（已提交内容零丢失），本清单只裁决"工作目录"的去留；删除动作逐批等您批签后执行（`git worktree remove`），任何"处置前提"未完成不删。请在"批签"列填 同意/保留/改判。

## A 类：保留（6 个，不删）

| worktree | 分支@HEAD | 脏况 | 保留理由 | 批签 |
|---|---|---|---|---|
| MedSim2Learn（主） | master@fe95b64 | M1/U4 | 主检出；M=CLAUDE.md，U=北极星双文档+handoff（有意未提交） | — |
| -DataImprove | DataImprove@09f21a5 | M1/U19 | C1 集成线；**U19 = 7 月 R6/R7 屏筛线全套设计/报告文档，仅存于此**（见 C-1 处置） | |
| -C1-R19-Triplanar-Continuity | r19@80bdd8c | 干净 | 证据锚（STATE D-009 指向其内文档）；R25 基底 | |
| -C1-R23-Implicit-Vessel-Width | r23@9d3011f | 干净 | 已关闭路线证据锚 | |
| -C1-R24-Exemplar-Source-Quality | r24@e103a15 | 干净 | 证据锚（STATE D-007 指向其内文档） | |
| -C1-R25-Procedural-Tissue-Microtexture | r25@9c74cf0 | 干净 | 刚收口提交；DR 素材现役 | |

## B 类：可直接删除（9 个，全部干净、提交内容都在分支引用里）

| worktree | 分支@HEAD | 包含关系 | 批签 |
|---|---|---|---|
| -C1-R5-Multiview | r5-multiview@ec4bdfd | 已并入 DataImprove | |
| -C1-R5-ViewCORAL | r5-view-coral-factorial@6097910 | 独立 tip（分支保留即可） | |
| -C1-R9-Texture-Fidelity | r9@40a80cd | 已并入 r19 线 | |
| -C1-R12-Training-Integration | r12-training-integration@6097910 | 独立 tip；W&B/CORAL 内容已由服务器分支 8b5081d/79ada06 重实现 | |
| -C1-R15-Joint-Graphcut-Seam | r15-joint-graphcut@83dbfff | 独立 tip（分支保留） | |
| -C1-R15-Multires-Blend | r15-multires@5be715a | 独立 tip（分支保留） | |
| -C1-R16-UV-Structure-Base | r16-uv-structure@38d7c1b | 已并入 r19 线 | |
| -C1-R21-Procedural-Vessels | r21@9646545 | 已并入 r23 线 | |
| -C1-R6-Background-Real | r6-background-real@f7f36b1 | 独立 tip（分支保留） | |

## C 类：删除前有处置前提（23 个）

### C-1 含"仅存于此"的路线文档/代码 —— 建议先在**各自分支**做一次保全提交再删（分支提交不触碰 master；若您裁定不值得保全，改判"直接删"即丢弃）

| worktree | 脏况摘要 | 建议处置 | 批签 |
|---|---|---|---|
| -DataImprove（A 类保留，此处只裁文档） | U19：7 月 R6/R7 屏筛全套设计/审计/报告 md | 在 DataImprove 分支保全提交（必要性：C1 屏筛线唯一文档记录，ROUTES 台账要引用） | |
| -C1-R20-Color-Diversity | U6：R20-C 路线代码+测试+设计三件套（从未提交） | r20-color 分支保全提交后删 | |
| -C1-R20-Exemplar-Diversity | U6：R20-E 路线代码+测试+设计三件套（从未提交） | r20-exemplar 分支保全提交后删 | |
| -C1-R10A-Crossfit-Texture | U2：r10a 代码+测试（未提交）；M1=.gitattributes | r10a 分支保全提交后删 | |
| -C1-R10B-Vessel-Texture | U2：r10b 代码+测试（未提交）；M1=.gitattributes | r10b 分支保全提交后删 | |
| -C1-R22-Vessel-Contrast | M2+U14：r22 代码/设计（未提交）+ r23 早期草稿（疑被 r23 分支正式版取代） | 核对 r23 草稿确被取代后，r22 分支保全提交后删 | |
| -C1-R13B-Image-Quilting | M1+U2：R14 设计/计划 md（查 R14 系是否已有同档） | 若 R14 处已有同档→直接删；否则并入保全 | |
| -DomainGapMetrics | M2：domain_gap.py + 测试 相对 master 的未提交改动 | 我先出 diff 供您裁决（可能是有价值的工具改进→单独小分支提交；或丢弃） | |

### C-2 仅琐碎脏文件（roster 一行改动/测试残渣/junit），建议直接删（丢弃脏文件）

| worktree | 脏况 | 批签 |
|---|---|---|
| -C1-R14-Quilting-Seam-Base / -S1 / -S2（3 个） | 各 M1=verification-artifacts.md | |
| -C1-R15-Seam-Compositor-Base | M1=verification-artifacts.md | |
| -C1-R2 | M1=verification-artifacts.md | |
| -C1-R2-PBR-Validation | U1=junit/ 残渣 | |
| -C1-R13A-Multiscale-Atlas | U2=测试产物目录残渣 | |

### C-3 旧竞赛臂的大改动（疑全部被后续路线取代），建议我逐个出 diff 摘要后您再裁

| worktree | 脏况 | 备注 | 批签 |
|---|---|---|---|
| -C1-R1-B-Vertex | M9（dpost 核心多文件） | 最早竞赛臂，7 月初 | |
| -C1-R11-Source-Contract | M6/U3 | r6/r8/r9 纹理系列改动 | |
| -C1-R12-Texture-Base | M7/U1 | 同上系列 | |
| -C1-R6-Background-Procedural | M8 | R6 屏筛线 | |
| -C1-R6-Lighting | M13/U3 | R6 屏筛线 | |
| -C1-R6-Stage0 | M4 | R6 屏筛线 | |
| -C1-R6-Texture | M14/U3 | R6 屏筛线 | |
| -C1-R7-Training | M5/U2 | 含 experiments/2026-07-23_multiview-coral-factorial 清单改动 | |
| -C1-R8-Texture-Training | M5/U2 | 与 R7 同一组脏文件（同一 7 月实验） | |

## 汇总

- 立即可删（B 类 + C-2，共 16 个）：只待您批签。
- 保全后删（C-1，6 个 worktree + DataImprove 文档）：每个一次分支内保全提交（不触 master），需您对"保全提交"逐行放行（与"纯文档不提交"规则的关系：这些是**否则即灭失**的路线唯一记录，且都在各自 side branch；您也可改判直接丢弃）。
- 出 diff 再裁（C-3，9 个 + DomainGapMetrics）：我下一轮产出逐个 diff 摘要。
- 全部执行后：38 → 6 个 worktree；41+ 分支引用原样保留。
