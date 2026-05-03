# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~18,863 words - fits in a single context window. You may not need a graph.

## Summary
- 311 nodes · 490 edges · 32 communities detected
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.84)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Adaptive Remesh Core|Adaptive Remesh Core]]
- [[_COMMUNITY_Surface Build Pipeline|Surface Build Pipeline]]
- [[_COMMUNITY_FEM Pressure CLI|FEM Pressure CLI]]
- [[_COMMUNITY_TetGen Pressure Evaluator|TetGen Pressure Evaluator]]
- [[_COMMUNITY_CGAL Remesh Algorithms|CGAL Remesh Algorithms]]
- [[_COMMUNITY_CGAL Pipeline Tests|CGAL Pipeline Tests]]
- [[_COMMUNITY_Core Smoke Tests|Core Smoke Tests]]
- [[_COMMUNITY_CLI Entry & Path Discovery|CLI Entry & Path Discovery]]
- [[_COMMUNITY_CGAL Mesh Conversion|CGAL Mesh Conversion]]
- [[_COMMUNITY_MVR File Parser|MVR File Parser]]
- [[_COMMUNITY_Pressure CLI Main|Pressure CLI Main]]
- [[_COMMUNITY_Surface Metrics|Surface Metrics]]
- [[_COMMUNITY_Vector Geometry Primitives|Vector Geometry Primitives]]
- [[_COMMUNITY_Topology & Indexing|Topology & Indexing]]
- [[_COMMUNITY_Remesh Internals|Remesh Internals]]
- [[_COMMUNITY_Pressure Evaluator Tests|Pressure Evaluator Tests]]
- [[_COMMUNITY_Index Parity (Python Compat)|Index Parity (Python Compat)]]
- [[_COMMUNITY_Docs & Design Rationale|Docs & Design Rationale]]
- [[_COMMUNITY_CGAL Result Types|CGAL Result Types]]
- [[_COMMUNITY_CGAL Test Suites|CGAL Test Suites]]
- [[_COMMUNITY_Boundary Extraction Parity|Boundary Extraction Parity]]
- [[_COMMUNITY_Edge Type|Edge Type]]
- [[_COMMUNITY_Face Orientation|Face Orientation]]
- [[_COMMUNITY_Face Matching|Face Matching]]
- [[_COMMUNITY_Triangle Normal|Triangle Normal]]
- [[_COMMUNITY_Vec3 Math|Vec3 Math]]
- [[_COMMUNITY_Mesh Quality|Mesh Quality]]
- [[_COMMUNITY_Metrics Serialization|Metrics Serialization]]
- [[_COMMUNITY_Pressure Serialization|Pressure Serialization]]
- [[_COMMUNITY_Pressure JSON Writer|Pressure JSON Writer]]
- [[_COMMUNITY_Mode Output Paths|Mode Output Paths]]
- [[_COMMUNITY_Mode String Converter|Mode String Converter]]

## God Nodes (most connected - your core abstractions)
1. `require()` - 13 edges
2. `main()` - 13 edges
3. `require()` - 13 edges
4. `main()` - 13 edges
5. `mvr_to_mesh_cli main (surface reconstruction CLI entry point)` - 10 edges
6. `evaluate_deformsim_pressure` - 9 edges
7. `parse_mvr()` - 8 edges
8. `copy_tetgen_output()` - 8 edges
9. `smoke_tests (core API unit tests)` - 8 edges
10. `parse_mvr()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `PressureMetrics (local CLI metrics struct for matrix report)` --semantically_similar_to--> `DeformSimPressureResult (full TetGen pre-flight diagnostics)`  [INFERRED] [semantically similar]
  check_fem_pressure_cli.cpp → include/mvrmesh/pressure/pressure_evaluator.h
- `CMakeLists.txt (build definition)` --references--> `evaluate_deformsim_pressure`  [INFERRED]
  CMakeLists.txt → src/pressure/pressure_evaluator.cpp
- `CMakeLists.txt (build definition)` --references--> `build_surface`  [INFERRED]
  CMakeLists.txt → src/core/pipeline.cpp
- `TetGen exit(1) → terminatetetgen(1) patch constraint` --rationale_for--> `evaluate_deformsim_pressure`  [EXTRACTED]
  CLAUDE.md → src/pressure/pressure_evaluator.cpp
- `adaptive_remesh (curvature-adaptive surface refinement)` --references--> `legacy adaptive_remesh (Python curvature-adaptive remesh)`  [INFERRED]
  include/mvrmesh/core/algorithms.h → legacy/mvr_to_mesh.py

## Hyperedges (group relationships)
- **End-to-end surface reconstruction pipeline: parse_mvr -> build_surface -> optional run_cgal_mesh -> write_ply** — io_h_parse_mvr, pipeline_h_build_surface, cgal_mesh_h_run_cgal_mesh, io_h_write_ply [EXTRACTED 0.95]
- **Pressure matrix workflow: run_pressure_matrix.ps1 drives mvr_to_mesh_cli per candidate then check_fem_pressure --matrix** — run_pressure_matrix_ps1, mvr_cli_main, check_fem_cli_run_matrix [EXTRACTED 1.00]
- **Adaptive remesh kernel: estimate_vertex_curvature -> select_split_edges_by_curvature -> split_faces_with_edge_set (iterated)** — algorithms_h_estimate_vertex_curvature, algorithms_h_select_split_edges, algorithms_h_split_faces [EXTRACTED 0.95]
- **Curvature-driven adaptive remesh pipeline** — algorithms_cpp_estimate_vertex_curvature, algorithms_cpp_select_split_edges_by_curvature, algorithms_cpp_split_faces_with_edge_set [EXTRACTED 1.00]
- **Surface build dispatch: tet boundary or adaptive remesh** — pipeline_cpp_build_surface, topology_cpp_boundary_faces_from_tets, algorithms_cpp_adaptive_remesh [EXTRACTED 1.00]
- **TetGen-backed FEM pressure pre-flight** — pressure_evaluator_cpp_fill_input_points, pressure_evaluator_cpp_fill_input_facets, pressure_evaluator_cpp_copy_tetgen_output [EXTRACTED 1.00]

## Communities (43 total, 12 thin omitted)

### Community 0 - "Adaptive Remesh Core"
Cohesion: 0.09
Nodes (39): adaptive_remesh, estimate_vertex_curvature, midpoint_index (internal cache helper), select_split_edges_by_curvature, split_faces_with_edge_set, CLAUDE.md (ShapeReconstruction module guidance), CMakeLists.txt (build definition), cross (+31 more)

### Community 1 - "Surface Build Pipeline"
Cohesion: 0.15
Nodes (30): adaptive_remesh(), boundary_faces_from_tets(), build_surface(), cross(), default_outputs_for_input(), dot(), estimate_vertex_curvature(), face_normal() (+22 more)

### Community 2 - "FEM Pressure CLI"
Cohesion: 0.08
Nodes (26): CgalMeshOptions (CGAL pipeline configuration), PressureMetrics (local CLI metrics struct for matrix report), compute_metrics (invokes evaluate_deformsim_pressure, computes FLOPs), check_fem_pressure_cli main (FEM pressure CLI entry point), run_matrix (multi-PLY pressure matrix aggregation mode), run_single (single PLY pressure evaluation mode), write_matrix_md (Markdown report writer for pressure matrix), parse_mvr (MVR file parser) (+18 more)

### Community 3 - "TetGen Pressure Evaluator"
Cohesion: 0.16
Nodes (24): copy_tetgen_output(), count_degenerate_surface_triangles(), count_unique_lines_from_tets(), deformsim_pressure_to_json(), empty_index_stats(), evaluate_deformsim_pressure(), face_index_stats(), fill_bounding_box() (+16 more)

### Community 4 - "CGAL Remesh Algorithms"
Cohesion: 0.13
Nodes (20): adaptive_remesh (curvature-adaptive surface refinement), estimate_vertex_curvature (vertex curvature estimation), select_split_edges_by_curvature (high-curvature edge selection), split_faces_with_edge_set (face subdivision at selected edges), protected_remesh_step implementation (detect sharp edges + isotropic remeshing), repair_polygon_soup_step implementation (PMP repair+orient+hole-fill), run_cgal_mesh implementation (CGAL pipeline orchestrator), protected_remesh_step (CGAL constrained remesh detail) (+12 more)

### Community 5 - "CGAL Pipeline Tests"
Cohesion: 0.36
Nodes (15): main(), message_contains(), require(), test_pipeline_happy_path_tetrahedron(), test_pipeline_propagates_step1_failure(), test_remesh_clean_octahedron_runs(), test_remesh_detects_sharp_edge_in_flat_bipyramid(), test_remesh_target_edge_length_auto_resolves_to_mean() (+7 more)

### Community 6 - "Core Smoke Tests"
Cohesion: 0.36
Nodes (14): main(), require(), test_adaptive_single_triangle_split(), test_boundary_faces_single_tet(), test_build_surface_uses_tet_boundary_without_triangles(), test_metrics_json_includes_quality_fields(), test_normalize_faces_indices(), test_read_ply_round_trip() (+6 more)

### Community 7 - "CLI Entry & Path Discovery"
Cohesion: 0.27
Nodes (13): default_outputs_for_input(), ensure_parent_directory(), find_project_root(), find_project_root_upward(), infer_project_root_from_input(), looks_like_project_root(), main(), parse_args() (+5 more)

### Community 8 - "CGAL Mesh Conversion"
Cohesion: 0.32
Nodes (11): log_remesh(), log_repair(), mean_edge_length(), mvrmesh_to_polygon_soup(), mvrmesh_to_surface_mesh(), preflight_repair_input(), protected_remesh_step(), repair_polygon_soup_step() (+3 more)

### Community 9 - "MVR File Parser"
Cohesion: 0.36
Nodes (8): is_section_marker(), parse_mvr(), parse_required_int(), parse_tetra(), parse_triangles(), parse_vertices(), split_ws(), trim_copy()

### Community 10 - "Pressure CLI Main"
Cohesion: 0.4
Nodes (9): compute_metrics(), format_bytes_human(), format_flops_sci(), main(), run_matrix(), run_single(), usage(), write_matrix_md() (+1 more)

### Community 11 - "Surface Metrics"
Cohesion: 0.33
Nodes (7): add_half_edge_direction(), compute_surface_metrics(), DisjointSet, make_edge_key(), make_face_key(), triangle_area(), validate_face_index()

### Community 12 - "Vector Geometry Primitives"
Cohesion: 0.36
Nodes (6): cross(), dot(), face_normal(), norm(), normalize(), vsub()

### Community 13 - "Topology & Indexing"
Cohesion: 0.39
Nodes (5): boundary_faces_from_tets(), orient_like_face(), oriented_face_outward(), sorted_face_key(), validate_vertex_index()

### Community 14 - "Remesh Internals"
Cohesion: 0.62
Nodes (6): adaptive_remesh(), estimate_vertex_curvature(), make_edge_key(), midpoint_index(), select_split_edges_by_curvature(), split_faces_with_edge_set()

### Community 15 - "Pressure Evaluator Tests"
Cohesion: 0.73
Nodes (5): main(), require(), test_deformsim_pressure_json_matches_diagnostic_shape(), test_deformsim_pressure_json_rejects_out_of_range_boundary_face_index(), test_deformsim_pressure_tetrahedralizes_closed_surface()

### Community 16 - "Index Parity (Python Compat)"
Cohesion: 0.4
Nodes (5): legacy normalize_faces_indices (Python 1-based index normalization), legacy normalize_tet_indices (Python tet index normalization), Index Parity Design: auto-detect and convert 1-based vs 0-based indices to match legacy Python behavior, normalize_faces_indices (1-based to 0-based index normalization), normalize_tet_indices (tet index normalization)

### Community 17 - "Docs & Design Rationale"
Cohesion: 0.5
Nodes (5): pressure_matrix.md (FEM cost comparison report), adaptive_iter3 FEM cost ceiling (8.2x baseline, infeasible), CGAL protect_constraints: sharp edge length must be < 4/3 * target_edge_length, DGETRI vs DGEMV crossover at V_surf ~= 2500, README.md (ShapeReconstruction user documentation)

### Community 19 - "CGAL Result Types"
Cohesion: 0.67
Nodes (3): CgalMeshResult (CGAL pipeline output), ProtectedRemeshStepReport (stage 2 remesh diagnostics), RepairStepReport (stage 1 repair diagnostics)

### Community 20 - "CGAL Test Suites"
Cohesion: 1.0
Nodes (3): test suite: protected_remesh_step (Stage 2 CGAL), test suite: repair_polygon_soup_step (Stage 1 CGAL), test suite: run_cgal_mesh orchestrator

## Knowledge Gaps
- **46 isolated node(s):** `Edge (pair of ints)`, `SurfaceMode (DirectSurface|AdaptiveRemesh enum)`, `BuildOptions (surface build configuration)`, `write_ply (PLY mesh writer)`, `outputs_for_mode (output path resolver)` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `mvr_to_mesh_cli main (surface reconstruction CLI entry point)` connect `FEM Pressure CLI` to `CGAL Remesh Algorithms`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Why does `run_cgal_mesh (two-stage CGAL repair+remesh pipeline)` connect `CGAL Remesh Algorithms` to `FEM Pressure CLI`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **What connects `Edge (pair of ints)`, `SurfaceMode (DirectSurface|AdaptiveRemesh enum)`, `BuildOptions (surface build configuration)` to the rest of the system?**
  _46 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Adaptive Remesh Core` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `FEM Pressure CLI` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `CGAL Remesh Algorithms` be split into smaller, more focused modules?**
  _Cohesion score 0.13 - nodes in this community are weakly interconnected._