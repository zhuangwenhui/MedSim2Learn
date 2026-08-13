# C3 接触点多样性设计（Track C / PLAN §2-C3 实例化，试点先行）

日期：2026-08-11。上游依据：`95b765f` 的 `experiments/2026-07-03_windows-render-diversity/PLAN.md`
§2-C3（已提交裁定，本文只做实例化）；所有者 2026-08-11 批准本线（"做1和2"）。

## 1. 机制与实现面结论（一手核实）

- **exe 侧**：DeformSim 对 annotation 里**每个接触 × 力列表逐帧**各仿一遍
  （`main.cpp: numObjects = contacts.size() × num_vector`；`worker.cpp:
  contact_i = k / num_vector`）；SampleID 由 C++ `CreateSampleID` 生成
  `deformed_s%04d_v%04d`，与 Python `dpost.forces.sample_id` 逐字符同格式
  （两侧均已读源核实）——不同接触种子的样本 id 天然不碰撞。
- **prep 侧**：`replay.py::prep` 取 `contacts[0]` 推导接触点/法向 → 传感器→模型
  旋转 R、labels（**保持原始真实牛顿**）、auto 相机（随接触点重定位——PLAN
  §2-C3 明文将 camera.json 列为逐接触产物，接触+其耦合视角一起变是既定语义）。
- **因此 C3 变体 = 派生单接触 annotation + config 覆写，dpost 核心零改动**；
  OFF 态（默认 annotation 不变）字节等同天然成立。唯一新代码 =
  `scripts/author_c3_variants.py`（候选著作）。

> **所有者裁定（2026-08-11）**：维持 §1 既定语义——自动相机跟随接触点，
> C3 因子 = 接触位置及其耦合视角的联合变化；不改固定相机方案。

## 2. 变体著作（确定性，已执行）

- 冻结集 = 生产 annotation `kidney_anat_contact_k1.json`（sha256 77c65178…，
  399 冻结顶点，接触 s521/k_ring=1）**逐字复制**——FEM 边界条件跨变体逐位一致。
- 候选 = `select_contacts(mesh, freeze, num_centers=30, k_ring=1, rng_seed=42)`
  （Poisson-disk over 可达区；实测可达区 377 顶点、30 候选全数接受）。
- **试点变体（预抽签规则 = 接受序前 2 个非生产种子）**：s1571（距 s521 46.15mm）、
  s0268（距 30.28mm）；表面尺度 109.9mm。产物在 `_c3_scratch/annotations/`
  （派生物不入 `inputs/annotations/`——那里只放手工原始输入）。

## 3. 试点方案（seq01 × 2 变体，全长 1716 帧）

- config = `kidney_twin.yaml` 逐字继承，仅改三处：`annotation` → 变体 JSON、
  `exe` → 主检出 build 绝对路径（worktree 无 build/）、`diversity.appearance`
  = DR-C1-v1 全量批次同款（enabled、seed 1、v3 标定乘子 [1.0656,1.0220,1.0505]、
  uv_sidecar 8dee381b…）。序数=1 → 外观抽签与全量批次 seq01 **逐位相同**，
  蒙太奇对比中唯一变量 = 接触点（受控对比）。
- 命令 = `main.py run --seq 01 --out-dir _c3_scratch/pilot/s<seed> --config
  <变体config> --keep-intermediate --no-artifacts`（prep→sim→render→serialize
  全链；keep-intermediate 留 PNG 做蒙太奇）。
- **成本测量目标**：变体 A 先行单跑，实测 sim 墙钟/序列——全量批次扩容
  （31 序列 × K 接触）的成本估算依据，扩容规模届时连同目检结果交所有者裁定。

## 4. 预注册验收门

1. 机械：sim 退出码 0、PLY=PNG=标签行=1716（F3 对账）、F1 零空白帧、F2 错误
   日志空、序列化 1716 样本、SampleID 前缀 = s1571/s0268。
2. **力标签不变性（C3 核心不变量）**：变体 labels.csv 的力列与生产 seq01
   labels.csv **数值逐行相同**（仅 SampleID 的 s 字段不同）——真实力分布零改变。
3. 接触位移可见性：变体渲染与全量批次 seq01（s521）同帧序对比，凹陷位置/轮廓
   破缺位置可见不同（蒙太奇为证）。
4. 终门 = 所有者目检：4 行蒙太奇（全量批次 seq01-s521 / s0268 / s1571 / 真实
   seq01 参照）× 同帧序列。**试点不做任何 Gap 主张**；全量批次扩容需目检通过 +
   成本批准。

## 5. 全量批次与训练走向（目检通过后另出清单）

组合集 = DR-C1 全量批次（31 序列，s521）∪ C3 变体（31 × K 接触）；合成半扩容，
真实半与测试协议不变；split 服务器端重著作。训练级裁决继续按 magMAE
gap-closed（所有者 2026-08-11 裁定：角度暂不入判定，仅记录）。

## 6. 术语表（新增项；前序清单术语表继续有效）

**术语勘误（2026-08-11，所有者审计指正）**：本线早期表述曾用"舰队"（英文 fleet 的直译）
指代 31 序列全量数据生产运行，属非正式译名，已全部订正为**全量批次 / 全量生产批次**。
双语对照（审计基准）：fleet = 全量生产批次；pilot = 试点；montage = 多帧拼贴对比图
（下表沿用"蒙太奇"仅因前序已交检文档使用该词，后续新文档改用正式译名）；
visual gate = 目视检查关卡；wall clock = 实际耗时（墙钟时间）。

| 术语 | 解释 | 来路 |
|---|---|---|
| 接触种子 | canonical 网格上的顶点索引，接触区 = 其 k_ring 邻域 | `annotation.cpp` ContactSeed；`contacts[].seed` |
| k_ring | 接触区半径：种子顶点的 k 环拓扑邻域 | `SelectKRingNeighbors`（annotation.cpp）；生产值 1 |
| 可达区 | 满足法向/肩角/曲率/支撑约束、且远离冻结区的表面顶点集 | `dpost/annotate.py accessible_zone` |
| Poisson-disk 中心 | 可达区内两两间距 ≥ 阈值的确定性贪心选点 | `dpost/annotate.py poisson_disk_centers`（rng_seed 42） |
| 力标签不变性 | 变体只改变形位置，监督目标（真实传感器牛顿）逐行不变 | PLAN §2-C3 "force label stays the real sensor force" |
| 受控对比 | 变体与全量批次 seq01 同外观抽签同帧序，蒙太奇差异即接触增量 | 本设计 §3；先例 = C1 v3-5 |
