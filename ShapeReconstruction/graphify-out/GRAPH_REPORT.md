# Graph Report - ShapeReconstruction  (2026-05-10)

## Corpus Check
- 34 files · ~35,124 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 445 nodes · 882 edges · 32 communities detected
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 114 edges (avg confidence: 0.81)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]

## God Nodes (most connected - your core abstractions)
1. `main()` - 33 edges
2. `require()` - 28 edges
3. `vsub()` - 21 edges
4. `require()` - 21 edges
5. `main()` - 21 edges
6. `compute_mesh_quality_metrics()` - 15 edges
7. `dot()` - 14 edges
8. `require()` - 14 edges
9. `main()` - 14 edges
10. `cross()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `CMakeLists.txt (build definition)` --references--> `evaluate_deformsim_pressure`  [INFERRED]
  CMakeLists.txt → src/pressure/pressure_evaluator.cpp
- `PressureMetrics (local CLI metrics struct for matrix report)` --semantically_similar_to--> `DeformSimPressureResult (full TetGen pre-flight diagnostics)`  [INFERRED] [semantically similar]
  check_fem_pressure_cli.cpp → include/mvrmesh/pressure/pressure_evaluator.h
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

## Communities (44 total, 12 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.1
Nodes (52): cross(), dot(), face_normal(), norm(), normalize(), vadd(), vmul(), vsub() (+44 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (46): adaptive_remesh (curvature-adaptive surface refinement), estimate_vertex_curvature (vertex curvature estimation), select_split_edges_by_curvature (high-curvature edge selection), split_faces_with_edge_set (face subdivision at selected edges), protected_remesh_step implementation (detect sharp edges + isotropic remeshing), repair_polygon_soup_step implementation (PMP repair+orient+hole-fill), run_cgal_mesh implementation (CGAL pipeline orchestrator), CgalMeshOptions (CGAL pipeline configuration) (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (40): all_vertices_are_referenced(), main(), near(), require(), require_throws_invalid_argument(), require_throws_invalid_argument_contains(), require_throws_runtime_error(), test_asymmetric_geometry_is_exposed_in_directional_or_symmetric_distance() (+32 more)

### Community 3 - "Community 3"
Cohesion: 0.09
Nodes (39): adaptive_remesh, estimate_vertex_curvature, midpoint_index (internal cache helper), select_split_edges_by_curvature, split_faces_with_edge_set, CLAUDE.md (ShapeReconstruction module guidance), CMakeLists.txt (build definition), cross (+31 more)

### Community 4 - "Community 4"
Cohesion: 0.15
Nodes (30): adaptive_remesh(), boundary_faces_from_tets(), build_surface(), cross(), default_outputs_for_input(), dot(), estimate_vertex_curvature(), face_normal() (+22 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (23): copy_tetgen_output(), count_unique_lines_from_tets(), deformsim_pressure_to_json(), empty_index_stats(), evaluate_deformsim_pressure(), face_index_stats(), fill_bounding_box(), fill_input_facets() (+15 more)

### Community 6 - "Community 6"
Cohesion: 0.24
Nodes (23): count_vertex_near(), main(), require(), test_adaptive_single_triangle_split(), test_boundary_faces_single_tet(), test_build_surface_sdf_reconstruct(), test_build_surface_sdf_reconstruct_conflicts_with_uniform(), test_build_surface_taubin_requires_uniform_subdivide() (+15 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (15): adaptive_remesh(), compact_mesh_to_referenced_vertices(), estimate_vertex_curvature(), make_edge_key(), midpoint_index(), mvrmesh(), select_split_edges_by_curvature(), split_faces_with_edge_set() (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (15): is_section_marker(), parse_mvr(), parse_required_int(), parse_tetra(), parse_triangles(), parse_vertices(), split_ws(), trim_copy() (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.23
Nodes (18): append_triangle(), checked_size_t_add(), checked_size_t_mul(), checked_size_t_mul3(), compute_bbox(), decode_node(), face_is_degenerate(), fill_signed_distance() (+10 more)

### Community 10 - "Community 10"
Cohesion: 0.34
Nodes (16): main(), message_contains(), require(), test_pipeline_happy_path_tetrahedron(), test_pipeline_propagates_step1_failure(), test_remesh_clean_octahedron_runs(), test_remesh_detects_sharp_edge_in_flat_bipyramid(), test_remesh_target_edge_length_auto_resolves_to_mean() (+8 more)

### Community 11 - "Community 11"
Cohesion: 0.27
Nodes (13): default_outputs_for_input(), ensure_parent_directory(), find_project_root(), find_project_root_upward(), infer_project_root_from_input(), looks_like_project_root(), main(), parse_args() (+5 more)

### Community 12 - "Community 12"
Cohesion: 0.31
Nodes (12): log_remesh(), log_repair(), mean_edge_length(), mvrmesh_to_polygon_soup(), mvrmesh_to_surface_mesh(), preflight_repair_input(), protected_remesh_step(), repair_polygon_soup_step() (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.4
Nodes (9): compute_metrics(), format_bytes_human(), format_flops_sci(), main(), run_matrix(), run_single(), usage(), write_matrix_md() (+1 more)

### Community 14 - "Community 14"
Cohesion: 0.33
Nodes (7): add_half_edge_direction(), compute_surface_metrics(), DisjointSet, make_edge_key(), make_face_key(), triangle_area(), validate_face_index()

### Community 15 - "Community 15"
Cohesion: 0.73
Nodes (5): main(), require(), test_deformsim_pressure_json_matches_diagnostic_shape(), test_deformsim_pressure_json_rejects_out_of_range_boundary_face_index(), test_deformsim_pressure_tetrahedralizes_closed_surface()

### Community 16 - "Community 16"
Cohesion: 0.4
Nodes (5): legacy normalize_faces_indices (Python 1-based index normalization), legacy normalize_tet_indices (Python tet index normalization), Index Parity Design: auto-detect and convert 1-based vs 0-based indices to match legacy Python behavior, normalize_faces_indices (1-based to 0-based index normalization), normalize_tet_indices (tet index normalization)

### Community 17 - "Community 17"
Cohesion: 0.5
Nodes (5): pressure_matrix.md (FEM cost comparison report), adaptive_iter3 FEM cost ceiling (8.2x baseline, infeasible), CGAL protect_constraints: sharp edge length must be < 4/3 * target_edge_length, DGETRI vs DGEMV crossover at V_surf ~= 2500, README.md (ShapeReconstruction user documentation)

### Community 19 - "Community 19"
Cohesion: 0.67
Nodes (3): CgalMeshResult (CGAL pipeline output), ProtectedRemeshStepReport (stage 2 remesh diagnostics), RepairStepReport (stage 1 repair diagnostics)

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (3): test suite: protected_remesh_step (Stage 2 CGAL), test suite: repair_polygon_soup_step (Stage 1 CGAL), test suite: run_cgal_mesh orchestrator

## Knowledge Gaps
- **46 isolated node(s):** `Edge (pair of ints)`, `SurfaceMode (DirectSurface|AdaptiveRemesh enum)`, `BuildOptions (surface build configuration)`, `write_ply (PLY mesh writer)`, `outputs_for_mode (output path resolver)` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `vsub()` connect `Community 0` to `Community 8`, `Community 9`, `Community 14`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `count_degenerate_surface_triangles()` connect `Community 0` to `Community 5`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `reconstruct_and_remesh_surface()` connect `Community 7` to `Community 9`, `Community 12`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `vsub()` (e.g. with `triangle_area()` and `triangle_area()`) actually correct?**
  _`vsub()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Edge (pair of ints)`, `SurfaceMode (DirectSurface|AdaptiveRemesh enum)`, `BuildOptions (surface build configuration)` to the rest of the system?**
  _46 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05 - nodes in this community are weakly interconnected._