# 实验配置清单 C1-PILOT-20260810（试点渲染，跑前交检）

## 1. 目的与预注册判据

- **目的**：用 C1 外观随机化管线在 seq01 上产出 3 个种子变体，供人工目检门裁定"外观是否连续、种子间是否可区分、与白模基线是否显著不同"，从而决定是否进入 31 序列全量生成。**本实验不做、也不允许做任何 Gap 缩小主张**（Gap 主张只能来自服务器侧任务级训练对比）。
- **预注册判据**（跑完逐条对账）：
  1. 机械：每种子 1716 帧全部渲出、F2 错误日志为空、F1 零空白帧、序列化 F3 对账通过（#PLY==#PNG==#标签行）；
  2. 溯源：每种子 `appearance_meta.json` 落盘且抽样值可由种子复现；
  3. 交付：4 行（基线+3 种子）× 6 帧蒙太奇一张；
  4. 终门：**用户目检**通过/不通过（本清单不预设结论）。

## 2. 数据

| 项 | 值 |
|---|---|
| 输入 PLY | `DataFlow/Deform_post/primary/twin_full/seq01/sim/DeformedSample_ComplexObject_26_06_10_223933/`（1716 帧，只读，生产数据不写入） |
| 输入相机 | `.../seq01/camera.json`（生产冻结相机） |
| 输入标签 | `.../seq01/labels.csv`（真实传感器力，F 期已验与 `.pt` 逐字节一致） |
| 输出 | worktree `_c1_scratch/pilot/seed{1,2,3}/`（800px PNG + 256px 序列化 + 溯源 json），不触碰 DataFlow |

## 3. 代码溯源

- 分支 `codex/dataimprove-windows-render-guards` @ `3a8ac0e` + **未提交 C1 工作集**（试点通过目检后随收尾一并提交；跑前逐文件 sha256 前 16 位如下，全量哈希可复算）：
  config.py c3abdbf7 / render.py e1496cd8 / replay.py fb684b3e / main.py 6ab2e51f / diversity.py 0cca151c / kidney_twin.yaml 171f88fe / test_appearance_dr.py 58b9199d / 设计文档(勘误后) 533e6077
- R25 场族模块及其 import 闭包：自提交 `9c74cf0` **逐字节提取**（blob 哈希已核）：c1_r25_procedural_microtexture.py a58c3b04、c1_r19_triplanar_continuity.py ac6430c0、c1_r16_uv_render.py 8a24e44c、c1_r12/r13 系列 5 文件、scripts 2 个运行器与 make_appearance_montage.py。
- 实现验证（跑前已完成）：TDD 30 红→30 绿；**关闭态字节校验**：seq01 前 50 帧在"无配置"与"enabled:false"两种关闭形态下，800px PNG、256px PNG、`.pt` 三层全部与生产逐字节一致；开启态冒烟 10 帧有色有序（详见实现报告，junit 存 `_c1_scratch/junit/`）。

## 4. 随机化参数（全部冻结于设计文档 §2，此处照录）

organ_mode：uniform 0.3 / r25_field 0.7；uniform 色域 R[0.45,0.62] G[0.28,0.42] B[0.30,0.44]；r25 变体 candidate-1/2/3 等概率、振幅 a∈[0.15,0.30]；背景 R[0.10,0.35] G[0.04,0.22] B[0.05,0.24]；逐帧后处理 亮度×[0.85,1.15]、对比×[0.85,1.15]、gamma[0.8,1.25]、暗角[0,0.35]、高斯噪声 σ[0,0.012]；光照不随机。种子结构：`SeedSequence([appearance.seed, seq序号])` → organ/background/postprocess 三子流，逐帧 spawn_key=(2,帧号)。

## 5. 命令（逐字，k ∈ {1,2,3}）

工作目录 `D:\MedSim2Learn-Windows-Render-Guards\Deform_post`，python = `C:\Users\space\anaconda3\envs\MedLearning\python.exe`：

```
python main.py render --config ..\_c1_scratch\config_pilot.yaml --ply-dir "..\DataFlow\Deform_post\primary\twin_full\seq01\sim\DeformedSample_ComplexObject_26_06_10_223933" --camera "..\DataFlow\Deform_post\primary\twin_full\seq01\camera.json" --out-png-dir ..\_c1_scratch\pilot\seed<k>\png --seq-ordinal 1 --appearance-seed <k> --yes
python -c "import sys; sys.path.insert(0,'.'); from dpost.realvideo import build_from_pngs; build_from_pngs('01', r'..\_c1_scratch\pilot\seed<k>\png', r'..\DataFlow\Deform_post\primary\twin_full\seq01\labels.csv', r'..\_c1_scratch\pilot\seed<k>\seq01_256', size=256, mask=True)"
python scripts\make_appearance_montage.py --out ..\_c1_scratch\pilot\pilot_montage.png --baseline "..\DataFlow\Deform_post\primary\twin_full\seq01\png" --dirs seed1=..\_c1_scratch\pilot\seed1\png seed2=..\_c1_scratch\pilot\seed2\png seed3=..\_c1_scratch\pilot\seed3\png --num-frames 6
```

`--yes` 跳过交互确认门（预览 PNG 仍生成，蒙太奇即人工检视物）。

## 6. 环境与成本

Windows 11 本机（渲染硬约束机）；MedLearning env（python 3.12.13 / open3d 0.19.0 / numpy 2.4.3 / pillow 12.1.1）；预计每种子渲染约 75s + 序列化约 1 分钟，总计约 10 分钟；磁盘约 3×(0.6G PNG+1.3G pt) ≈ 6G，落 worktree scratch。

## 6b. 运行回执与修订（2026-08-10 协调者填写）

- 注册的种子 1/2/3 全部按清单跑完：各 1716 帧、F2 错误日志为空、溯源 json 落盘。序列化各 1716 样本 1 批。
- **修订（补充抽样，透明记录）**：三个注册种子全部抽中 organ_mode=uniform（p=0.3 三连中，概率 2.7%）。当场核查采样器无偏差：200 种子分布 58/142≈0.29/0.71、seed=1 跨 31 序号 10/21——确认属小概率事件而非缺陷。为使目检门能看到 R25 纹理模式，按预先声明的确定性规则（">3 的最小两个抽中 r25_field 的种子"，只按模式选择、不看外观效果）补渲种子 4、5（均 candidate-2，a=0.276/0.200），蒙太奇为 6 行（基线+5 种子）。注册结果未做任何替换或删除。
- 协调者预检视记录：基线行即"灰模+纯白"问题原样；种子行肾色调+深腔背景+逐帧光度抖动，轮廓与基线一致，无接缝/空白帧；r25 行与 uniform 行差异在缩略图尺度偏细腻（冒烟实测 |Δ|≈0.007–0.011，比对基线差低一个量级），与 2005 顶点采样密度上限一致——留待用户原图裁定。
- 种子 3 首跑因外层 10 分钟超时被截断，清理后完整重跑（非管线故障；渲染+序列化每种子约 5 分钟）。

## 7. 术语表（术语｜通俗解释｜来路）

| 术语 | 解释 | 来路 |
|---|---|---|
| C1 | 因子代号=外观/着色随机化（区别于 C2 视角、C3 接触点） | 提交 95b765f `experiments/2026-07-03_windows-render-diversity/PLAN.md` §2 |
| 域随机化 (DR) | 训练数据在渲染期做受控随机变化，靠多样性而非逼真度提升迁移 | RESEARCH_GOAL.md §6.3；文献台账 R25-LIT-12 (Tobin, IROS 2017) |
| R25 场族 / candidate-1/2/3 | 三种程序化多尺度顶点颜色场（粗斑驳 fBm / 域扭曲 / 细胞混合） | 提交 9c74cf0 `research/data_improve/2026-08-09-c1-r25-...-result.md` §受控变量 |
| base_rgb | 顶点色场围绕波动的基色（本实验为逐序列随机抽取的肾样色） | 设计文档 §2；构造式出自 R25-DESIGN §4.1 |
| 关闭态字节校验 (OFF-parity) | 项目自造词：随机化关闭时输出必须与生产数据逐字节相同的验收 | 本分支 `_c1_scratch/parity_check_c1.py`；先例 7db8976 提交说明 |
| F1/F2/F3 | 渲染三守卫：空白帧断言+预览门 / 逐帧错误隔离日志 / 计数硬对账 | 提交 7db8976；规格出自 95b765f DATA_SIDE_HANDOFF §5 |
| seq-ordinal | 序列序号，参与种子派生使不同序列抽样不同 | `main.py` CLI flag（本工作集） |
| SeedSequence / spawn | numpy 官方确定性随机数种子派生 API | numpy.random.SeedSequence 文档 |
| FOV mask | 序列化时套用的圆形视场掩膜（模拟内窥镜视野） | `dpost/realvideo.py::build_from_pngs(mask=True)` |
| 蒙太奇 | 多变体×多帧的拼贴对比图 | `scripts/make_appearance_montage.py`（本工作集） |
| 目检门 | 人工查看原图后作 通过/不通过 裁定的检查点 | 设计文档 §4 第 3 条；PLAN.md §4 QUALIFIED 清单第 1 项 |
