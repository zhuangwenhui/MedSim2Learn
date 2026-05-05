# Graph Report - d:/MedSim2Learn/DeformSim  (2026-05-05)

## Corpus Check
- 37 files · ~236,093 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 736 nodes · 3743 edges · 29 communities detected
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 82 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_TetGen mesh topology core|TetGen mesh topology core]]
- [[_COMMUNITY_TetGen subfacesubsegment ops|TetGen subface/subsegment ops]]
- [[_COMMUNITY_DeformSim main entry & sampling|DeformSim main entry & sampling]]
- [[_COMMUNITY_TetGen tetgen.cpp misc init|TetGen tetgen.cpp misc init]]
- [[_COMMUNITY_TetGen mesh repair (flipperturb)|TetGen mesh repair (flip/perturb)]]
- [[_COMMUNITY_BMGL Object & FEM matrices|BMGL Object & FEM matrices]]
- [[_COMMUNITY_Shewchuk geometric predicates|Shewchuk geometric predicates]]
- [[_COMMUNITY_BMGL Surface & PLY render|BMGL Surface & PLY render]]
- [[_COMMUNITY_BMGL Matrix math|BMGL Matrix math]]
- [[_COMMUNITY_ply_tetra_diagnostic tool|ply_tetra_diagnostic tool]]
- [[_COMMUNITY_BMGL Vector math|BMGL Vector math]]
- [[_COMMUNITY_TetGen file IO loaders|TetGen file IO loaders]]
- [[_COMMUNITY_BMGL 3D image (RAWSUSAN)|BMGL 3D image (RAW/SUSAN)]]
- [[_COMMUNITY_TetGen type declarations|TetGen type declarations]]
- [[_COMMUNITY_TetGen mesh traverseoutput|TetGen mesh traverse/output]]
- [[_COMMUNITY_BMGL geometric primitives|BMGL geometric primitives]]
- [[_COMMUNITY_TetGen point location & jettison|TetGen point location & jettison]]
- [[_COMMUNITY_TetGen vector & angle utils|TetGen vector & angle utils]]
- [[_COMMUNITY_BMGL image filters|BMGL image filters]]
- [[_COMMUNITY_BMGL render helpers|BMGL render helpers]]
- [[_COMMUNITY_Trackball mouse control|Trackball mouse control]]
- [[_COMMUNITY_ADMM solver|ADMM solver]]
- [[_COMMUNITY_Env setup PowerShell|Env setup PowerShell]]
- [[_COMMUNITY_TetGen triangle intersection|TetGen triangle intersection]]
- [[_COMMUNITY_TetGen LU & quality stats|TetGen LU & quality stats]]
- [[_COMMUNITY_ply_tetra_smoke tool|ply_tetra_smoke tool]]
- [[_COMMUNITY_CMake build orchestration (root)|CMake build orchestration (root)]]
- [[_COMMUNITY_TetGen CLI parser|TetGen CLI parser]]
- [[_COMMUNITY_Verification subsystem flag|Verification subsystem flag]]

## God Nodes (most connected - your core abstractions)
1. `pointmark()` - 99 edges
2. `sorg()` - 90 edges
3. `sdest()` - 83 edges
4. `org()` - 77 edges
5. `dest()` - 77 edges
6. `apex()` - 77 edges
7. `sym()` - 64 edges
8. `sesymself()` - 61 edges
9. `reconstructmesh()` - 58 edges
10. `oppo()` - 53 edges

## Surprising Connections (you probably didn't know these)
- `ComputeQualityTetrahedralMesh()` --calls--> `tetrahedralize()`  [INFERRED]
  BMGL/object.cpp → Utility/tetgen.cpp
- `CheckSelfIntersection()` --calls--> `tetrahedralize()`  [INFERRED]
  BMGL/object.cpp → Utility/tetgen.cpp
- `ApplyBiasContactSelection()` --calls--> `Vector3f()`  [INFERRED]
  stdafx.cpp → BMGL/vector.h
- `ComputeTetrahedralMesh()` --calls--> `tetrahedralize()`  [INFERRED]
  BMGL/object.cpp → Utility/tetgen.cpp
- `main()` --calls--> `tetrahedralize()`  [INFERRED]
  verification/apps/ply_tetra_diagnostic.cpp → Utility/tetgen.cpp

## Hyperedges (group relationships)
- **DeformSim build orchestration** — cmakelists_deformsim_project, cmakelists_findlocaldeps_include, cmakelists_deformsimtargets_include, cmakelists_deformsimverification_include [EXTRACTED 1.00]

## Communities (41 total, 1 thin omitted)

### Community 0 - "TetGen mesh topology core"
Cohesion: 0.12
Nodes (126): insphere(), orient3d(), adjustedgering(), adjustlocate(), apex(), assignregionattribs(), bond(), bowatinsertsite() (+118 more)

### Community 1 - "TetGen subface/subsegment ops"
Cohesion: 0.11
Nodes (124): adjustlocateseg(), adjustlocatesub(), areabound(), assignvarconstraints(), bowatinsertsegsite(), bowatinsertsubsite(), carveholessub(), checkconforming() (+116 more)

### Community 2 - "DeformSim main entry & sampling"
Cohesion: 0.09
Nodes (51): AngleWithZAxis(), AppendCsvRecord(), ApplyBiasContactSelection(), ApplyFreezeState(), ApplyMaterialParams(), BuildBiasContactCache(), BuildEtaString(), BuildFreezeCacheFromObject() (+43 more)

### Community 3 - "TetGen tetgen.cpp misc init"
Cohesion: 0.05
Nodes (14): dequeuebadtet(), dummyinit(), initializepools(), initm44(), isedgeencroached(), isfacehasedge(), m4xm4(), m4xv4() (+6 more)

### Community 4 - "TetGen mesh repair (flip/perturb)"
Cohesion: 0.17
Nodes (43): badfacedealloc(), badfacetraverse(), checkseg4badqual(), checkseg4encroach(), circumsphere(), decode(), delaunizesegments(), distance() (+35 more)

### Community 5 - "BMGL Object & FEM matrices"
Cohesion: 0.08
Nodes (16): Alloc2Dim(), CheckSelfIntersection(), Clear(), CloneMatrixStateFrom(), ComputeLeastSquareMesh(), ComputeMatrixB(), ComputeMatrixD(), ComputeMatrixK() (+8 more)

### Community 6 - "Shewchuk geometric predicates"
Cohesion: 0.11
Nodes (18): estimate(), exactinit(), fast_expansion_sum_zeroelim(), incircle(), incircleadapt(), incircleexact(), incircleslow(), insphereadapt() (+10 more)

### Community 7 - "BMGL Surface & PLY render"
Cohesion: 0.11
Nodes (15): Alloc2Dim(), ChangeHSVToColor(), Clear(), ComputeArea(), ComputeBoundingBox(), ComputeLaplacian(), ComputeLeastSquareMesh(), ComputeNormal() (+7 more)

### Community 8 - "BMGL Matrix math"
Cohesion: 0.14
Nodes (16): Clear(), GetRotateMatrix(), GetValue(), Identity(), Indentity(), Init(), Matrix3x3(), Matrix4x4() (+8 more)

### Community 9 - "ply_tetra_diagnostic tool"
Cohesion: 0.24
Nodes (19): add_index_to_stats(), compute_bounding_box(), copy_surface_to_object(), count_degenerate_surface_triangles(), count_unique_lines_from_tets(), fill_tetgen_input(), json_escape(), main() (+11 more)

### Community 10 - "BMGL Vector math"
Cohesion: 0.21
Nodes (10): Clear(), float(), GetLength(), Init(), Normalize(), operator(), SetVector(), Vector2f() (+2 more)

### Community 11 - "TetGen file IO loaders"
Cohesion: 0.31
Nodes (16): findnextfield(), findnextnumber(), load_addnodes(), load_medit(), load_node(), load_node_call(), load_off(), load_pbc() (+8 more)

### Community 12 - "BMGL 3D image (RAW/SUSAN)"
Cohesion: 0.15
Nodes (5): Image3D(), ReadImageRAW(), ReadLookUpTable(), UpdateColorLookUpTable(), UpdateIntensityVolume()

### Community 13 - "TetGen type declarations"
Cohesion: 0.14
Nodes (10): deinitialize(), goend(), initialize(), link::hasitem(), link::locate(), rewind(), set_compfunc(), tetgenbehavior() (+2 more)

### Community 14 - "TetGen mesh traverse/output"
Cohesion: 0.15
Nodes (14): list::append(), list::insert(), list::
listinit(), maketetrahedronmap(), memorypool::alloc(), memorypool::
poolinit(), outelements(), outneighbors() (+6 more)

### Community 15 - "BMGL geometric primitives"
Cohesion: 0.19
Nodes (4): Line(), Tetrahedron(), Triangle(), Vertex()

### Community 16 - "TetGen point location & jettison"
Cohesion: 0.18
Nodes (12): delaunizevertices(), distance2(), jettisonnodes(), link::del(), link::getnitem(), link::insert(), locate(), makeindex2pointmap() (+4 more)

### Community 17 - "TetGen vector & angle utils"
Cohesion: 0.27
Nodes (11): cross(), dot(), edgeorthonormal(), facedihedral(), facenormal(), interiorangle(), planelineint(), projpt2edge() (+3 more)

### Community 18 - "BMGL image filters"
Cohesion: 0.33
Nodes (7): Filter3D(), GetValue(), Normalize(), SetGaussian(), SetGradient(), SetLaplacian(), SetValue()

### Community 19 - "BMGL render helpers"
Cohesion: 0.29
Nodes (10): ChangeHSVToColor(), ComputeBoundingBox(), GetColorValue(), MapObject(), RenderColorMap(), RenderDeform(), RenderLaplacian(), RenderNormal() (+2 more)

### Community 20 - "Trackball mouse control"
Cohesion: 0.33
Nodes (5): qmul(), qrot(), trackballInit(), trackballMotion(), trackballStop()

### Community 21 - "ADMM solver"
Cohesion: 0.43
Nodes (6): ADMM(), Alloc2Dim(), Compute(), Init(), Optimize(), SoftThreshold()

### Community 22 - "Env setup PowerShell"
Cohesion: 0.32
Nodes (4): Assert-RequiredFile(), Get-VsDevCmdPath(), Normalize-PathValue(), Update-EnvironmentPrefix()

### Community 23 - "TetGen triangle intersection"
Cohesion: 0.29
Nodes (8): edge_edge_cop_inter(), edge_vert_col_inter(), interecursive(), tri_edge_cop_inter(), tri_edge_inter(), tri_edge_inter_tail(), tri_tri_inter(), tri_vert_cop_inter()

### Community 24 - "TetGen LU & quality stats"
Cohesion: 0.38
Nodes (7): createsubpbcgrouptable(), inscribedsphere(), lu_decmp(), lu_solve(), qualitystatistics(), statistics(), tetallnormal()

### Community 25 - "ply_tetra_smoke tool"
Cohesion: 0.52
Nodes (6): copy_surface_to_object(), json_escape(), main(), tetra_volume(), total_tetra_volume(), write_json()

### Community 26 - "CMake build orchestration (root)"
Cohesion: 0.4
Nodes (6): C++17 standard setting, deformsim_add_main_target() call, DeformSim CMake Project, DeformSimTargets.cmake include, FindLocalDeps.cmake include, OpenMP dependency

### Community 29 - "TetGen CLI parser"
Cohesion: 0.83
Nodes (4): parse_commandline(), syntax(), usage(), versioninfo()

## Knowledge Gaps
- **4 isolated node(s):** `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include`, `DEFORMSIM_ENABLE_VERIFICATION option`, `C++17 standard setting`
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `tetrahedralize()` connect `TetGen subface/subsegment ops` to `TetGen mesh topology core`, `TetGen tetgen.cpp misc init`, `TetGen mesh repair (flip/perturb)`, `BMGL Object & FEM matrices`, `Shewchuk geometric predicates`, `ply_tetra_diagnostic tool`, `TetGen file IO loaders`, `TetGen mesh traverse/output`, `TetGen point location & jettison`, `TetGen LU & quality stats`?**
  _High betweenness centrality (0.325) - this node is a cross-community bridge._
- **Why does `Vector3f()` connect `BMGL render helpers` to `BMGL Matrix math`, `BMGL Vector math`, `DeformSim main entry & sampling`, `BMGL Surface & PLY render`?**
  _High betweenness centrality (0.243) - this node is a cross-community bridge._
- **Why does `ApplyBiasContactSelection()` connect `DeformSim main entry & sampling` to `BMGL render helpers`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **What connects `FindLocalDeps.cmake include`, `DeformSimVerification.cmake include`, `DEFORMSIM_ENABLE_VERIFICATION option` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `TetGen mesh topology core` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._
- **Should `TetGen subface/subsegment ops` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._
- **Should `DeformSim main entry & sampling` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._