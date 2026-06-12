# Graph Report - DeformSim  (2026-06-12)

## Corpus Check
- 22 files · ~287,625 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1067 nodes · 5020 edges · 30 communities detected
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
- [[_COMMUNITY_Community 31|Community 31]]

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
- `scale_expansion()` --calls--> `split()`  [INFERRED]
  Utility/predicates.cpp → third_party/nlohmann/json.hpp
- `ApplyContactRegion()` --calls--> `Vector3f()`  [INFERRED]
  stdafx.cpp → BMGL/vector.h

## Hyperedges (group relationships)
- **DeformSim build orchestration** — cmakelists_deformsim_project, cmakelists_findlocaldeps_include, cmakelists_deformsimtargets_include, cmakelists_deformsimverification_include [EXTRACTED 1.00]

## Communities (43 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (146): adjustlocateseg(), adjustlocatesub(), areabound(), badfacedealloc(), badfacetraverse(), bowatinsertsegsite(), bowatinsertsubsite(), carveholessub() (+138 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (143): adjustedgering(), adjustlocate(), apex(), assignregionattribs(), bond(), bowatinsertsite(), bowatinsertvolsite(), carvecavity() (+135 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (109): accept(), add(), array(), at(), back(), basic_json(), begin(), binary() (+101 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (32): assignvarconstraints(), brio_multiscale_sort(), check_enc_segment(), check_encroachment(), dequeuebadtet(), dummyinit(), get_steiner_on_segment(), getsteinerptonsegment() (+24 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (58): AngleWithZAxis(), AppendCsvRecord(), ApplyBiasContactSelection(), ApplyContactRegion(), ApplyFreezeFromAnnotation(), ApplyFreezeState(), ApplyMaterialParams(), BuildBiasContactCache() (+50 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (53): decode(), orient3d(), calculateabovepoint(), calculateabovepoint4(), constraineddelaunay(), constrainedfacets(), cos_interiorangle(), delaunizecavity() (+45 more)

### Community 6 - "Community 6"
Cohesion: 0.1
Nodes (26): dstore(), estimate(), fast_expansion_sum_zeroelim(), fppow2(), fstore(), incircle(), incircleadapt(), incircleexact() (+18 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (37): exactinit(), alltetrahedrontraverse(), check_mesh(), check_segments(), check_shells(), collectremovepoints(), delaunizevertices(), get_laplacian_center() (+29 more)

### Community 8 - "Community 8"
Cohesion: 0.13
Nodes (36): findnextfield(), findnextnumber(), list::append(), list::insert(), list::
listinit(), load_addnodes(), load_edge(), load_elem() (+28 more)

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (16): Alloc2Dim(), CheckSelfIntersection(), Clear(), CloneMatrixStateFrom(), ComputeLeastSquareMesh(), ComputeMatrixB(), ComputeMatrixD(), ComputeMatrixK() (+8 more)

### Community 10 - "Community 10"
Cohesion: 0.15
Nodes (27): add_steinerpt_in_schoenhardtpoly(), add_steinerpt_in_segment(), add_steinerpt_to_recover_edge(), checkflipeligibility(), distance2(), flipnm(), flipnm_post(), is_collinear_at() (+19 more)

### Community 11 - "Community 11"
Cohesion: 0.12
Nodes (16): Alloc2Dim(), ChangeHSVToColor(), Clear(), ComputeArea(), ComputeBoundingBox(), ComputeLaplacian(), ComputeLeastSquareMesh(), ComputeNeighbors() (+8 more)

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (24): check_conforming(), checktet4split(), circumsphere(), create_segment_info_list(), createsubpbcgrouptable(), cross(), dot(), edgeorthonormal() (+16 more)

### Community 13 - "Community 13"
Cohesion: 0.14
Nodes (16): Clear(), GetRotateMatrix(), GetValue(), Identity(), Indentity(), Init(), Matrix3x3(), Matrix4x4() (+8 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (23): check_subface(), create_segment_facet_map(), delaunayrefinement(), dequeue_subface(), does_seg_contain_acute_vertex(), enqueue_subface(), enqueuesubface(), enqueuetetrahedron() (+15 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (11): badface(), deinitialize(), goend(), initialize(), link::hasitem(), link::locate(), rewind(), set_compfunc() (+3 more)

### Community 16 - "Community 16"
Cohesion: 0.24
Nodes (19): add_index_to_stats(), compute_bounding_box(), copy_surface_to_object(), count_degenerate_surface_triangles(), count_unique_lines_from_tets(), fill_tetgen_input(), json_escape(), main() (+11 more)

### Community 17 - "Community 17"
Cohesion: 0.21
Nodes (10): Clear(), float(), GetLength(), Init(), Normalize(), operator(), SetVector(), Vector2f() (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.15
Nodes (5): Image3D(), ReadImageRAW(), ReadLookUpTable(), UpdateColorLookUpTable(), UpdateIntensityVolume()

### Community 19 - "Community 19"
Cohesion: 0.24
Nodes (14): add_steinerpt_to_repair(), check_enc_subface(), create_a_shorter_edge(), dequeue_badtet(), enqueue_badtet(), facet_ridge_vertex_adjacent(), flip_edge_to_improve(), get_tet() (+6 more)

### Community 20 - "Community 20"
Cohesion: 0.19
Nodes (4): Line(), Tetrahedron(), Triangle(), Vertex()

### Community 21 - "Community 21"
Cohesion: 0.29
Nodes (10): ChangeHSVToColor(), ComputeBoundingBox(), GetColorValue(), MapObject(), RenderColorMap(), RenderDeform(), RenderLaplacian(), RenderNormal() (+2 more)

### Community 22 - "Community 22"
Cohesion: 0.33
Nodes (7): Filter3D(), GetValue(), Normalize(), SetGaussian(), SetGradient(), SetLaplacian(), SetValue()

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (5): qmul(), qrot(), trackballInit(), trackballMotion(), trackballStop()

### Community 24 - "Community 24"
Cohesion: 0.32
Nodes (4): Assert-RequiredFile(), Get-VsDevCmdPath(), Normalize-PathValue(), Update-EnvironmentPrefix()

### Community 25 - "Community 25"
Cohesion: 0.43
Nodes (8): insphere(), orient4d(), check_delaunay(), check_regular(), flipcertify(), insphere_s(), insphere_sos(), orient4d_s()

### Community 26 - "Community 26"
Cohesion: 0.43
Nodes (6): ADMM(), Alloc2Dim(), Compute(), Init(), Optimize(), SoftThreshold()

### Community 27 - "Community 27"
Cohesion: 0.52
Nodes (6): copy_surface_to_object(), json_escape(), main(), tetra_volume(), total_tetra_volume(), write_json()

### Community 28 - "Community 28"
Cohesion: 0.4
Nodes (6): C++17 standard setting, deformsim_add_main_target() call, DeformSim CMake Project, DeformSimTargets.cmake include, FindLocalDeps.cmake include, OpenMP dependency

## Knowledge Gaps
- **5 isolated node(s):** `json_sax_acceptor`, `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include`, `DEFORMSIM_ENABLE_VERIFICATION option`, `C++17 standard setting`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tetrahedralize()` connect `Community 7` to `Community 0`, `Community 1`, `Community 3`, `Community 5`, `Community 8`, `Community 9`, `Community 14`, `Community 16`, `Community 19`, `Community 25`?**
  _High betweenness centrality (0.214) - this node is a cross-community bridge._
- **Why does `decode()` connect `Community 5` to `Community 0`, `Community 1`, `Community 2`, `Community 7`, `Community 10`, `Community 14`?**
  _High betweenness centrality (0.188) - this node is a cross-community bridge._
- **Why does `Vector3f()` connect `Community 21` to `Community 17`, `Community 11`, `Community 4`, `Community 13`?**
  _High betweenness centrality (0.153) - this node is a cross-community bridge._
- **Are the 81 inferred relationships involving `orient3d()` (e.g. with `insphere_s()` and `orient4d_s()`) actually correct?**
  _`orient3d()` has 81 INFERRED edges - model-reasoned connections that need verification._
- **What connects `json_sax_acceptor`, `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include` to the rest of the system?**
  _5 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._