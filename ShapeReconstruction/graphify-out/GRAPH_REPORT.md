# Graph Report - ShapeReconstruction  (2026-06-14)

## Corpus Check
- 55 files · ~42,107 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 383 nodes · 730 edges · 16 communities detected
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 122 edges (avg confidence: 0.8)
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
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `main()` - 33 edges
2. `vsub()` - 19 edges
3. `main()` - 19 edges
4. `compute_mesh_quality_metrics()` - 15 edges
5. `dot()` - 14 edges
6. `main()` - 14 edges
7. `norm()` - 13 edges
8. `reconstruct_surface_sdf()` - 13 edges
9. `cross()` - 12 edges
10. `closest_point_on_triangle()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `mvrmesh()` --calls--> `resolve_outputs()`  [INFERRED]
  include/mvrmesh/cli/cli_common.h → src/cli/cli_common.cpp
- `mvrmesh()` --calls--> `estimate_vertex_curvature()`  [INFERRED]
  include/mvrmesh/core/curvature.h → src/core/curvature.cpp
- `mvrmesh()` --calls--> `compact_mesh_to_referenced_vertices()`  [INFERRED]
  include/mvrmesh/core/compaction.h → src/core/compaction.cpp
- `mvrmesh()` --calls--> `select_split_edges_by_curvature()`  [INFERRED]
  include/mvrmesh/core/curvature.h → src/core/curvature.cpp
- `mvrmesh()` --calls--> `outputs_for_mode()`  [INFERRED]
  include/mvrmesh/core/pipeline.h → src/core/pipeline.cpp

## Communities (38 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.13
Nodes (45): estimate_vertex_curvature(), clamp01(), closest_on_segment(), closest_point_on_triangle(), cross(), dot(), face_normal(), norm() (+37 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (37): all_vertices_are_referenced(), main(), require_throws_invalid_argument(), require_throws_runtime_error(), test_asymmetric_geometry_is_exposed_in_directional_or_symmetric_distance(), test_compact_mesh_to_referenced_vertices_preserves_face_vertex_order(), test_compact_mesh_to_referenced_vertices_removes_isolated_vertices(), test_compare_shape_to_reference_invalid_empty_candidate_throws() (+29 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (21): mvrmesh(), select_split_edges_by_curvature(), make_edge_key(), add_half_edge_direction(), compute_surface_metrics(), DisjointSet, make_face_key(), build_surface() (+13 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (20): dataflow_stage_dir(), default_outputs_for_input(), ensure_parent_dir(), find_project_root(), find_project_root_upward(), infer_project_root_from_input(), log_build_result(), looks_like_project_root() (+12 more)

### Community 4 - "Community 4"
Cohesion: 0.19
Nodes (21): copy_tetgen_output(), count_unique_lines_from_tets(), deformsim_pressure_to_json(), empty_index_stats(), evaluate_deformsim_pressure(), face_index_stats(), fill_bounding_box(), fill_input_facets() (+13 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (17): extract_faces_from_cgal_mesh(), log_remesh(), log_repair(), mean_edge_length(), mvrmesh_to_polygon_soup(), mvrmesh_to_surface_mesh(), preflight_repair_input(), protected_remesh_step() (+9 more)

### Community 6 - "Community 6"
Cohesion: 0.2
Nodes (18): is_section_marker(), parse_double_field(), parse_int_field(), parse_mvr(), parse_required_int(), parse_tetra(), parse_triangles(), parse_vertices() (+10 more)

### Community 7 - "Community 7"
Cohesion: 0.19
Nodes (20): count_vertex_near(), main(), test_adaptive_single_triangle_split(), test_boundary_faces_single_tet(), test_build_surface_sdf_reconstruct(), test_build_surface_uniform_subdivide(), test_build_surface_uniform_taubin_smooth(), test_build_surface_uses_tet_boundary_without_triangles() (+12 more)

### Community 8 - "Community 8"
Cohesion: 0.22
Nodes (18): restore_physical_coordinates(), append_triangle(), checked_size_t_add(), checked_size_t_mul(), checked_size_t_mul3(), decode_node(), fill_signed_distance(), get_or_add_intersection() (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.27
Nodes (15): main(), message_contains(), test_pipeline_happy_path_tetrahedron(), test_pipeline_propagates_step1_failure(), test_remesh_clean_octahedron_runs(), test_remesh_detects_sharp_edge_in_flat_bipyramid(), test_remesh_target_edge_length_auto_resolves_to_mean(), test_remesh_throws_when_all_edges_sharp() (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.38
Nodes (13): load_adaptive_remesh_section(), load_cgal_mesh_section(), load_config(), load_config_from_yaml(), load_sdf_reconstruct_section(), load_taubin_section(), load_uniform_subdivide_section(), parse_double_value() (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.26
Nodes (9): require_throws(), test_parse_surface_mode_rejects_unknown(), test_validate_adaptive_split_ratio_above_1(), test_validate_adaptive_split_ratio_zero(), test_validate_cgal_post_bad_angle(), test_validate_rejects_empty_input(), test_validate_rejects_sdf_with_cgal_post(), test_validate_rejects_zero_uniform_iterations() (+1 more)

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (5): extent(), make_box(), test_centering_puts_centroid_at_origin(), test_pose_is_proper_rigid_transform(), test_thin_axis_becomes_z()

### Community 15 - "Community 15"
Cohesion: 0.42
Nodes (8): read_ply(), compute_metrics(), format_bytes_human(), format_flops_sci(), run_pressure_matrix(), run_pressure_single(), write_matrix_md(), write_single_json()

### Community 16 - "Community 16"
Cohesion: 0.52
Nodes (6): main(), test_deformsim_pressure_json_escapes_backslash_path(), test_deformsim_pressure_json_matches_diagnostic_shape(), test_deformsim_pressure_json_rejects_out_of_range_boundary_face_index(), test_deformsim_pressure_tetrahedralizes_closed_surface(), test_write_single_json_escapes_backslash_paths()

### Community 17 - "Community 17"
Cohesion: 0.83
Nodes (3): load_pressure_config(), usage(), validate()

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `build_surface()` connect `Community 2` to `Community 5`, `Community 6`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `validate_face_indices()` connect `Community 2` to `Community 0`, `Community 4`, `Community 5`, `Community 6`, `Community 8`?**
  _High betweenness centrality (0.068) - this node is a cross-community bridge._
- **Why does `outputs_for_mode()` connect `Community 3` to `Community 2`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `vsub()` (e.g. with `hull_support_down_direction()` and `edge_length()`) actually correct?**
  _`vsub()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `compute_mesh_quality_metrics()` (e.g. with `validate_face_indices()` and `triangle_area()`) actually correct?**
  _`compute_mesh_quality_metrics()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `dot()` (e.g. with `estimate_vertex_curvature()` and `apply_frame()`) actually correct?**
  _`dot()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.13 - nodes in this community are weakly interconnected._