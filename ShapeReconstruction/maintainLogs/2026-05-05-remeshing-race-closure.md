# Remeshing Race Closure Log

## 文档用途

本日志用于记录 `ShapeReconstruction` 的 remeshing 赛马（race）历史和决策，避免未来重复引入已经验证失败或已收口的方案。  
它的职责是：

- 记录已产出方案与失败方案的时间线与产物。
- 记录每个方案的设计目标、关键参数、可行性结论与失败原因。
- 记录当前收口状态与后续清理动作，保留可追溯证据。

## 时间线（输出结果）

| 时间 (UTC+9) | 输出路径 | 对应赛道 |
|---|---|---|
| 2026-05-05 18:12:20 | `outPut/race/kidney_u2` | mesh-in-place / uniform / Taubin / Repair |
| 2026-05-06 06:04:13 | `outPut/race/kidney_recon_sdf` | SDF reconstruction |
| 2026-05-06 22:46:10 | `outPut/race/kidney_budget` | Closed FEM-Budget Race |
| 2026-05-06 23:18:49 | `outPut/race/kidney_decimation` | High-quality remesh then decimation |
| 2026-05-06 23:19:04 | `outPut/race/kidney_alpha_wrap` | CGAL Alpha Wrap |
| 2026-05-06 23:19:58 | `outPut/race/kidney_multi_track` | Multi-track orchestration |

## 全量落地方案与结论

以下方案均来自 remeshing 赛马记录中历史提交，保留为完整历史信息以便复盘。

### 1) `closed_fem_budget`

- 设计目的：建立与 FEM 压力门控相关的主线预算策略，先验证闭合性与几何稳健性，再执行后续重建。
- 关键参数（示例）：  
  `budget_sdf64_L025`、`budget_sdf72_L025`、`budget_sdf72_L015`、`budget_sdf64_L015`、`skip_pressure`、`max_review_v_tet`、`max_recommended_v_tet` 等。
- 结果状态：**可行并保留**（主线）。
- 可行原因：在当前环境下可稳定产出主线可用输出；参数覆盖了 FEM 门控与 SDF 预处理路径，便于稳定迭代。

### 2) `reconstruction_sdf` / `recon_sdf_remesh`

- 设计目的：将 SDF 阶段作为基础重建路径，得到可控的网格质量基础，再配合 CGAL 重网格化与体素策略。
- 关键参数（示例）：  
  `resolution`、`target_edge_length`、`remesh_iterations`、`padding_ratio`、`recon_sdf96_remesh`、`recon_sdf64`、`recon_sdf96`、`recon_sdf128`、`source_sdf64` 等。
- 结果状态：**可行（保留基础能力）**。
- 可行原因：SDF 基础链路能生成有意义的产物；与 FEM 主线协同时可用于补充验证与回归。

### 3) `uniform_taubin` / `uniform_taubin_project` / `uniform_repair_remesh` / `uniform_control`

- 设计目的：提供 mesh-in-place 的局部平滑、投影、修复与重网格控制能力，用于快速收敛几何噪声。
- 关键参数（示例）：  
  `uniform_iterations`、`taubin lambda`、`taubin mu`、`taubin iterations`、`project`、`repair/remesh target length`、`u2_taubin`、`u2_repair_remesh`、`u2_taubin_project`、`u2_control` 等。
- 结果状态：**历史可行产物存在，但不作为主线**。
- 可行原因：`kidney_u2` 有历史成功路径，可用于对比；但在全链路稳定性和主线优先级上不再作为首选。

### 4) `alpha_wrap`

- 设计目的：引入 CGAL Alpha Wrap 进行全局包裹式重建，期望在闭合形体边界上获得稳定结果。
- 关键参数（示例）：  
  `alpha_factor`、`offset_factor`、`post_remesh_target_edge_length`、`n_samples`。
- 结果状态：**可产出 `.ply`，但视觉质量偏差较大**。
- 可行原因：能产出面片，但实际形状保真与细节保留不满足主线期望，故不设为主线，仅保留历史记录。

### 5) `high_quality_remesh_then_decimation`（`high_quality_decimation`）

- 设计目的：先重建后再尝试高质量简化，目标是在质量和面数之间平衡。
- 关键参数（示例）：  
  `source_sdf_resolution`、`source_target_edge_length`、`target_faces`、`post_remesh_target_edge_length`、`decim_4k/8k/12k/20k`、`recon_sdf_*` 对齐参数。
- 结果状态：**失败并已清理**。
- 失败原因：依赖的 Surface_mesh_simplification API/头文件与当前工程能力不匹配，未能稳定产出有效可用 `.ply`，且 CMake 集成复杂。

### 6) `adaptive_sdf`（Adaptive / Octree SDF）

- 设计目的：用 adaptive/octree SDF 的多尺度 cell 策略改善稀疏体素区域重建，兼顾细节补齐。
- 关键参数（示例）：  
  `coarse_resolutions`、`refine_factors`、`band_factors`、`post_remesh_target_edge_lengths`、`max_candidate_profiles`、`max_total_refined_cells`、`max_estimated_output_faces`。
- 结果状态：**失败并已清理**。
- 失败原因：当前实现路径在稳定性、输出可重复性上未达标；在 blocked-safe 与 adaptive cell stitching 场景下无稳定通过结果。

### 7) `poisson_point_normal`（Poisson / point-normal reconstruction）

- 设计目的：基于 Poisson/点法向重建形成闭合表面，探索更平滑、全局拟合路径。
- 关键参数（示例）：  
  `sample_mode`、`profile`、`post_remesh_target_edge_length`、`n_samples`、`max_candidate_profiles`。
- 结果状态：**失败并已清理**。
- 失败原因：CGAL Poisson surface reconstruction API 在当前环境下不可用或不兼容；缺少稳定产物。

### 8) `multi_track_orchestrator`

- 设计目的：统一多轨道入口，支持一次运行并发执行多个候选重建路径，统一产出摘要与指标。
- 关键参数（示例）：  
  `--tracks`、`--skip-pressure`、`--tiny-test-mode` 及各候选轨道开关。
- 结果状态：**已清理**。
- 说明：该脚手架在 `alpha_wrap` 清理后曾短暂收缩为 `budget` 单入口；随后确认其已失去多赛道编排价值，已从当前代码主线移除。历史记录与历史产物保留。后续维护入口曾短暂迁移到 `mesh_budget_race_cli`，并已在 2026-05-09 后续收口中继续迁移到 `mvr_to_mesh_cli --sdf-reconstruct`。

## 当前收口结论

- 主线保留：`closed_fem_budget`。
- SDF 基础能力保留：`reconstruction_sdf` / `recon_sdf_remesh` 仍作为基础能力存在，保留参数与产出能力。
- `alpha_wrap`：历史上有成功产出，但视觉与后续可用性不理想；已从当前代码主线移除，仅保留历史记录。
- `mesh-in-place`（`uniform_taubin` 系列）：历史可行产物存在，但不作为当前主线。
- `high_quality_decimation`、`adaptive_sdf`、`poisson_point_normal`：三条失败赛道已确认失败并完成清理。
- `multi_track_orchestrator`：历史编排脚手架已完成清理；当前不再维护该 CLI，保留历史产物和日志。

## 2026-05-09 第一批失败赛道清理记录

- 删除目标（实现/CLI/CTest）：
  - 失败赛道实现：`high_quality_decimation`、`adaptive_sdf`、`poisson_point_normal`
  - 删除文件：
    - `include/mvrmesh/core/decimation_race_candidates.h`
    - `src/core/decimation_race_candidates.cpp`
    - `mesh_decimation_race_cli.cpp`
    - `verification/cmake/run_mesh_decimation_race_cli.cmake`
    - `include/mvrmesh/core/adaptive_sdf_race_candidates.h`
    - `src/core/adaptive_sdf_race_candidates.cpp`
    - `mesh_adaptive_sdf_race_cli.cpp`
    - `include/mvrmesh/core/poisson_race_candidates.h`
    - `src/core/poisson_race_candidates.cpp`
    - `mesh_poisson_race_cli.cpp`
  - CTest 删除：`mesh_decimation_race_cli_tiny_skip_pressure`。
- `multi_track_orchestrator` 处理：
  - 当时**未删除脚手架本体**，仅瘦身入口与依赖。
  - 后续已在 `multi_track_orchestrator` 实际清理记录中删除该脚手架；历史记录保留在本日志。
- 验证与环境状态：
  - `cmake` / `ctest` 不在 PATH，无法执行真实 `cmake configure` 和 `ctest`。
  - 静态字符串扫描已覆盖 `CMakeLists.txt`、`cmake/`、`include/`、`src/`、`verification/`、`mesh_multi_track_race_cli.cpp`、`README.md`、`verification/core/quality_smoothing_tests.cpp`，未检出目标残留调用。
  - 删除文件检查：10 个目标文件已不存在。
- 残余风险：
  - 缺少 `cmake/ctest`，当前只能完成静态级校验；未能做完整构建与测试验证。

### 未跟踪文件审计补充

- 这次审计不依赖 `git diff` 作为主要证据，因为 `git diff` 无法覆盖未跟踪文件；为补齐覆盖面，额外执行了：
  - `git status --short`：记录已修改与未跟踪项；
  - `rg --files`：拉齐仓库文件清单，确认新增/未跟踪的 CLI/source/header/test/script（含 `mesh_*_race_cli.cpp`、`run_mesh_*_race_cli.cmake`、`quality_smoothing_tests.cpp`、`*_race_candidates.*`）。
  - 残留符号静态扫描（允许历史说明命中）：在 `CMakeLists.txt`、`cmake/`、`src/`、`include/`、`verification/`、`mesh_*.cpp`、`README.md`、`maintainLogs/` 做关键符号扫描。
- 真实结果：
  - 删除文件审计：10 个失败赛道删除目标均不存在（`include/mvrmesh/core/decimation_race_candidates.h`、`src/core/decimation_race_candidates.cpp`、`mesh_decimation_race_cli.cpp`、`verification/cmake/run_mesh_decimation_race_cli.cmake`、`include/mvrmesh/core/adaptive_sdf_race_candidates.h`、`src/core/adaptive_sdf_race_candidates.cpp`、`mesh_adaptive_sdf_race_cli.cpp`、`include/mvrmesh/core/poisson_race_candidates.h`、`src/core/poisson_race_candidates.cpp`、`mesh_poisson_race_cli.cpp`）。
  - 规则性扫描结果：在构建/生产/测试逻辑路径（`CMakeLists.txt`、`cmake/`、`src/`、`include/`、`verification/`、`mesh_*.cpp`）未检出失败赛道活跃符号；命中项仅为 `README.md` 与 `maintainLogs/2026-05-05-remeshing-race-closure.md` 的历史说明文本。
  - 环境：
    - `cmake` 不在 PATH；
    - `ctest` 不在 PATH。
  - 未跟踪文件核对：`git status --short` 与 `rg --files` 同步确认 `mesh_*_race_cli.cpp`、`run_mesh_*_race_cli.cmake`、`quality_smoothing_tests.cpp`、`*_race_candidates.*` 已处于未跟踪/已重写历史管理范围，且不与未清理失败赛道残留混淆。

## 后续记录与引用

| 日期 | 文档来源 | 说明 |
|---|---|---|
| 2026-05-09 | `maintainLogs/2026-05-05-remeshing-race-closure.md` | 记录本次失败赛道清理决策、保留范围与后续校验边界。 |

## 备注

历史记录完整保留在此文档中；如需复现历史参数，可先行检索上述轨道名称，并按本记录中的关键参数与结论进行回放。

## 2026-05-09 `alpha_wrap` 维护决策与实际清理（已执行）

- 方案英文名：`alpha_wrap`。
- 决策结论（已落地）：`alpha_wrap` 不再作为当前主线方案，相关实现与独立 CLI 已从代码主线移除。
- 不适用原因（适用范围限定）：在当前 kidney 数据、当前参数组合和当前形状保真优先的评估标准下，虽然 `alpha_wrap` 在 surface gate 与 FEM budget 维度表现可接受，但视觉确认显示重建质量普遍较差；结果更接近 watertight 外包络，而不是高保真器官曲面重建。
- 技术储备定位：`alpha_wrap` 仅保留历史记录与历史产物，作为未来低成本封闭外包络/粗碰撞壳/快速预览的备选参考，不进入当前代码主线。

### 实际清理文件

- 已删除：
  - `include/mvrmesh/core/alpha_wrap_race_candidates.h`
  - `src/core/alpha_wrap_race_candidates.cpp`
  - `mesh_alpha_wrap_race_cli.cpp`
  - `verification/cmake/run_mesh_alpha_wrap_race_cli.cmake`
- 已更新：
  - `CMakeLists.txt`
  - `cmake/MvrmeshCore.cmake`
  - `cmake/MvrmeshTests.cmake`
  - `mesh_multi_track_race_cli.cpp`（当时仅保留 budget，后续已删除，见下方 `multi_track_orchestrator` 清理记录）
  - `verification/cmake/run_mesh_multi_track_race_cli.cmake`（当时仅验证 budget，后续已删除，见下方 `multi_track_orchestrator` 清理记录）
  - `verification/core/quality_smoothing_tests.cpp`
  - `README.md`

### 本轮验证 artifact roster（同文件留痕，无额外 artifact）

| 路径 | 目的 | 责任人 | 清理预期 |
|---|---|---|---|
| `maintainLogs/2026-05-05-remeshing-race-closure.md` | 记录本轮 `alpha_wrap` 清理与验证证据 | alpha_wrap 清理实现子代理（GPT-5.3-Codex xhigh） | 保留（长期维护日志） |

### 本轮验证结果（2026-05-09）

- UTF-8 严格解码：
  - `README.md`：`UTF8Encoding(throwOnInvalidBytes=true)` 解码通过，`U+FFFD` 未出现。
  - `maintainLogs/2026-05-05-remeshing-race-closure.md`：`UTF8Encoding(throwOnInvalidBytes=true)` 解码通过，`U+FFFD` 未出现。
- 删除目标存在性检查（`Test-Path`）：
  - `include/mvrmesh/core/alpha_wrap_race_candidates.h` => `False`
  - `src/core/alpha_wrap_race_candidates.cpp` => `False`
  - `mesh_alpha_wrap_race_cli.cpp` => `False`
  - `verification/cmake/run_mesh_alpha_wrap_race_cli.cmake` => `False`
- 残留关键字扫描（`rg -n "alpha_wrap|Alpha Wrap|mesh_alpha_wrap" CMakeLists.txt cmake src include verification mesh_multi_track_race_cli.cpp README.md maintainLogs`）：
  - 命中仅在 `README.md` 与 `maintainLogs/...` 历史说明中；
  - `CMakeLists.txt`、`cmake/`、`src/`、`include/`、`verification/`、`mesh_multi_track_race_cli.cpp` 未命中活跃逻辑残留。
- budget-only 保留检查（该项为 `alpha_wrap` 清理时的中间状态）：
  - 当时 `mesh_multi_track_race_cli.cpp` 仍保留 `--tracks budget` 与 `budget` track 逻辑；
  - 当时 `verification/cmake/run_mesh_multi_track_race_cli.cmake` 仍保留 `--tracks budget` 运行与 `budget` 候选校验；
  - 后续已在 `multi_track_orchestrator` 清理中删除上述脚手架文件。
- 工具可用性：
  - `cmake --version`：失败（`cmake` 不在 PATH）。
  - `ctest --version`：失败（`ctest` 不在 PATH）。
- `git diff --check`：退出码 `0`（无 diff-check 错误）；存在若干 CRLF 归一化 warning。

## 2026-05-09 SDF mainflow supersession note

Historical sections above may refer to `mesh_budget_race_cli`, `budget_race_candidates`, and `verification/cmake/run_mesh_budget_race_cli.cmake` as the maintained `closed_fem_budget` entry. That was true at that closure point. The current maintained product entry is now `mvr_to_mesh_cli --sdf-reconstruct`; the budget race CLI and helper were removed after the accepted SDF + CGAL remesh path was migrated into the main flow.

## 2026-05-09 `multi_track_orchestrator` 实际清理（已执行）

- 方案英文名：`multi_track_orchestrator`。
- 决策结论（已落地）：`multi_track_orchestrator` 不再作为当前代码主线的一部分维护。该脚手架在失败赛道与 `alpha_wrap` 清理后已退化为 `budget` 单入口，继续保留会与独立 `mesh_budget_race_cli` 重复，因此从当前代码主线移除。
- 保留内容：历史输出目录 `outPut/race/kidney_multi_track`、历史 `summary.md/metrics.json` 和本日志中的赛马记录保留，用于未来复盘。
- 当时维护入口：`closed_fem_budget` 赛道在本清理点之后曾继续通过 `mesh_budget_race_cli`、`budget_race_candidates` 和 `verification/cmake/run_mesh_budget_race_cli.cmake` 维护；该入口后续已被 `mvr_to_mesh_cli --sdf-reconstruct` 取代。

### 实际清理文件

- 已删除：
  - `mesh_multi_track_race_cli.cpp`
  - `verification/cmake/run_mesh_multi_track_race_cli.cmake`
- 已更新：
  - `CMakeLists.txt`
  - `cmake/MvrmeshTests.cmake`
  - `README.md`
  - `maintainLogs/2026-05-05-remeshing-race-closure.md`

### 本轮验证 artifact roster（同文件留痕，无额外 artifact）

| 路径 | 目的 | 责任人 | 清理预期 |
|---|---|---|---|
| `maintainLogs/2026-05-05-remeshing-race-closure.md` | 记录本轮 `multi_track_orchestrator` 清理与验证证据 | 主代理 | 保留（长期维护日志） |

### 本轮验证结果（2026-05-09）

- UTF-8 严格解码：
  - `README.md`：`UTF8Encoding(throwOnInvalidBytes=true)` 解码通过，`U+FFFD` 未出现。
  - `maintainLogs/2026-05-05-remeshing-race-closure.md`：`UTF8Encoding(throwOnInvalidBytes=true)` 解码通过，`U+FFFD` 未出现。
- 删除目标存在性检查（`Test-Path`）：
  - `mesh_multi_track_race_cli.cpp` => `False`
  - `verification/cmake/run_mesh_multi_track_race_cli.cmake` => `False`
- 残留关键字扫描（`rg -n "multi_track|mesh_multi_track|Multi-Track|multi-track" CMakeLists.txt cmake src include verification README.md maintainLogs`）：
  - 活跃构建、源码与测试逻辑中不再存在 `multi_track` / `mesh_multi_track` 入口引用。
  - 命中仅保留在 `README.md` 与本维护日志的历史说明中。
- budget 主线保留检查（历史状态）：
  - `mesh_budget_race_cli.cpp`、`budget_race_candidates`、`verification/cmake/run_mesh_budget_race_cli.cmake` 在本清理点仍为维护入口；该状态后续已被 `mvr_to_mesh_cli --sdf-reconstruct` 取代。
- 工具可用性：
  - `cmake --version`：失败（`cmake` 不在 PATH）。
  - `ctest --version`：失败（`ctest` 不在 PATH）。
- `git diff --check`：退出码 `0`（无 diff-check 错误）；存在若干 CRLF 归一化 warning。
