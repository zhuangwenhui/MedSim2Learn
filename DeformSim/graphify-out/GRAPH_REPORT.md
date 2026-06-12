# Graph Report - DeformSim  (2026-06-12)

## Corpus Check
- 22 files · ~288,634 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1067 nodes · 5021 edges · 31 communities detected
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 148 edges (avg confidence: 0.8)
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
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `pointmark()` - 99 edges
2. `sorg()` - 90 edges
3. `orient3d()` - 83 edges
4. `sdest()` - 83 edges
5. `org()` - 77 edges
6. `dest()` - 77 edges
7. `apex()` - 77 edges
8. `reconstructmesh()` - 66 edges
9. `sym()` - 64 edges
10. `tetrahedralize()` - 62 edges

## Surprising Connections (you probably didn't know these)
- `ComputeQualityTetrahedralMesh()` --calls--> `tetrahedralize()`  [INFERRED]
  BMGL/object.cpp → Utility/tetgen.cpp
- `CheckSelfIntersection()` --calls--> `tetrahedralize()`  [INFERRED]
  BMGL/object.cpp → Utility/tetgen.cpp
- `badface()` --calls--> `key()`  [INFERRED]
  Utility/tetgen.h → third_party/nlohmann/json.hpp
- `ApplyContactRegion()` --calls--> `Vector3f()`  [INFERRED]
  stdafx.cpp → BMGL/vector.h
- `Transpose()` --calls--> `swap()`  [INFERRED]
  BMGL/matrix.cpp → third_party/nlohmann/json.hpp

## Hyperedges (group relationships)
- **DeformSim build orchestration** — cmakelists_deformsim_project, cmakelists_findlocaldeps_include, cmakelists_deformsimtargets_include, cmakelists_deformsimverification_include [EXTRACTED 1.00]

## Communities (44 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (149): insphere(), adjustlocateseg(), adjustlocatesub(), areabound(), badfacedealloc(), badfacetraverse(), bowatinsertsegsite(), bowatinsertsubsite() (+141 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (146): adjustedgering(), adjustlocate(), apex(), assignregionattribs(), bond(), bowatinsertsite(), bowatinsertvolsite(), carvecavity() (+138 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (110): accept(), add(), array(), at(), back(), basic_json(), begin(), binary() (+102 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (30): assignvarconstraints(), brio_multiscale_sort(), check_enc_segment(), check_encroachment(), dequeuebadtet(), dummyinit(), get_steiner_on_segment(), getsteinerptonsegment() (+22 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (58): AngleWithZAxis(), AppendCsvRecord(), ApplyBiasContactSelection(), ApplyContactRegion(), ApplyFreezeFromAnnotation(), ApplyFreezeState(), ApplyMaterialParams(), BuildBiasContactCache() (+50 more)

### Community 5 - "Community 5"
Cohesion: 0.1
Nodes (26): dstore(), estimate(), exactinit(), fast_expansion_sum_zeroelim(), fppow2(), fstore(), incircle(), incircleadapt() (+18 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (37): findnextfield(), findnextnumber(), list::append(), list::insert(), list::
listinit(), load_addnodes(), load_edge(), load_elem() (+29 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (36): orient3d(), calculateabovepoint4(), cos_interiorangle(), delaunizecavity(), edge_edge_cop_inter(), edge_vert_col_inter(), fillcavity(), flip31() (+28 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (16): Alloc2Dim(), CheckSelfIntersection(), Clear(), CloneMatrixStateFrom(), ComputeLeastSquareMesh(), ComputeMatrixB(), ComputeMatrixD(), ComputeMatrixK() (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.16
Nodes (32): add_steinerpt_in_schoenhardtpoly(), add_steinerpt_in_segment(), add_steinerpt_to_recover_edge(), add_steinerpt_to_repair(), distance2(), does_seg_contain_acute_vertex(), enqueuesubface(), enqueuetetrahedron() (+24 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (16): Alloc2Dim(), ChangeHSVToColor(), Clear(), ComputeArea(), ComputeBoundingBox(), ComputeLaplacian(), ComputeLeastSquareMesh(), ComputeNeighbors() (+8 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (26): alltetrahedrontraverse(), check_mesh(), check_segments(), check_shells(), collectremovepoints(), delaunizevertices(), get_laplacian_center(), get_seg_laplacian_center() (+18 more)

### Community 12 - "Community 12"
Cohesion: 0.14
Nodes (26): check_conforming(), checkflipeligibility(), checktet4split(), circumsphere(), create_segment_info_list(), createsubpbcgrouptable(), cross(), dot() (+18 more)

### Community 13 - "Community 13"
Cohesion: 0.09
Nodes (11): badface(), deinitialize(), goend(), initialize(), link::hasitem(), link::locate(), rewind(), set_compfunc() (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (15): Clear(), GetRotateMatrix(), GetValue(), Identity(), Indentity(), Init(), Matrix3x3(), Matrix4x4() (+7 more)

### Community 15 - "Community 15"
Cohesion: 0.13
Nodes (21): decode(), orient4d(), calculateabovepoint(), check_delaunay(), check_regular(), flipcertify(), flipinsertfacet(), getpointmeshsize() (+13 more)

### Community 16 - "Community 16"
Cohesion: 0.24
Nodes (19): add_index_to_stats(), compute_bounding_box(), copy_surface_to_object(), count_degenerate_surface_triangles(), count_unique_lines_from_tets(), fill_tetgen_input(), json_escape(), main() (+11 more)

### Community 17 - "Community 17"
Cohesion: 0.18
Nodes (15): operator+(), ChangeHSVToColor(), ComputeBoundingBox(), GetColorValue(), MapObject(), RenderColorMap(), RenderDeform(), RenderLaplacian() (+7 more)

### Community 18 - "Community 18"
Cohesion: 0.16
Nodes (17): check_enc_subface(), check_subface(), constraineddelaunay(), create_a_shorter_edge(), create_segment_facet_map(), delaunayrefinement(), dequeue_subface(), enqueue_subface() (+9 more)

### Community 19 - "Community 19"
Cohesion: 0.15
Nodes (5): Image3D(), ReadImageRAW(), ReadLookUpTable(), UpdateColorLookUpTable(), UpdateIntensityVolume()

### Community 20 - "Community 20"
Cohesion: 0.25
Nodes (14): finddirection(), flipnm(), flipnm_post(), getedge(), is_segment(), recoveredgebyflips(), recoversegments(), reduceedgesatvertex() (+6 more)

### Community 21 - "Community 21"
Cohesion: 0.19
Nodes (4): Line(), Tetrahedron(), Triangle(), Vertex()

### Community 22 - "Community 22"
Cohesion: 0.33
Nodes (7): Filter3D(), GetValue(), Normalize(), SetGaussian(), SetGradient(), SetLaplacian(), SetValue()

### Community 23 - "Community 23"
Cohesion: 0.28
Nodes (6): Clear(), GetLength(), Init(), Normalize(), SetVector(), VectorNf()

### Community 24 - "Community 24"
Cohesion: 0.33
Nodes (5): qmul(), qrot(), trackballInit(), trackballMotion(), trackballStop()

### Community 25 - "Community 25"
Cohesion: 0.32
Nodes (4): Assert-RequiredFile(), Get-VsDevCmdPath(), Normalize-PathValue(), Update-EnvironmentPrefix()

### Community 26 - "Community 26"
Cohesion: 0.36
Nodes (8): dequeue_badtet(), enqueue_badtet(), flip_edge_to_improve(), get_tet(), improve_mesh(), repair_badqual_tets(), repair_tet(), top_badtet()

### Community 27 - "Community 27"
Cohesion: 0.43
Nodes (6): ADMM(), Alloc2Dim(), Compute(), Init(), Optimize(), SoftThreshold()

### Community 28 - "Community 28"
Cohesion: 0.52
Nodes (6): copy_surface_to_object(), json_escape(), main(), tetra_volume(), total_tetra_volume(), write_json()

### Community 29 - "Community 29"
Cohesion: 0.4
Nodes (6): C++17 standard setting, deformsim_add_main_target() call, DeformSim CMake Project, DeformSimTargets.cmake include, FindLocalDeps.cmake include, OpenMP dependency

## Knowledge Gaps
- **5 isolated node(s):** `json_sax_acceptor`, `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include`, `DEFORMSIM_ENABLE_VERIFICATION option`, `C++17 standard setting`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tetrahedralize()` connect `Community 11` to `Community 0`, `Community 1`, `Community 3`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 15`, `Community 16`, `Community 18`, `Community 26`?**
  _High betweenness centrality (0.218) - this node is a cross-community bridge._
- **Why does `decode()` connect `Community 15` to `Community 1`, `Community 2`, `Community 7`, `Community 9`, `Community 11`, `Community 20`?**
  _High betweenness centrality (0.193) - this node is a cross-community bridge._
- **Why does `Vector3f()` connect `Community 17` to `Community 10`, `Community 4`?**
  _High betweenness centrality (0.146) - this node is a cross-community bridge._
- **Are the 81 inferred relationships involving `orient3d()` (e.g. with `insphere_s()` and `orient4d_s()`) actually correct?**
  _`orient3d()` has 81 INFERRED edges - model-reasoned connections that need verification._
- **What connects `json_sax_acceptor`, `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._