# Graph Report - DeformSim  (2026-06-14)

## Corpus Check
- 33 files · ~24,050 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 195 nodes · 322 edges · 13 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.8)
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

## God Nodes (most connected - your core abstractions)
1. `main()` - 29 edges
2. `processObjects()` - 13 edges
3. `main()` - 11 edges
4. `Print_progress_bar()` - 8 edges
5. `make_empty_index_stats()` - 8 edges
6. `write_json_result()` - 8 edges
7. `Vector3f()` - 7 edges
8. `LoadSimHyperParams()` - 7 edges
9. `ReadPLY()` - 6 edges
10. `generateVectors()` - 6 edges

## Surprising Connections (you probably didn't know these)
- `ApplyContactRegion()` --calls--> `Vector3f()`  [INFERRED]
  src/sim/sample_pipeline.cpp → BMGL/vector.h
- `main()` --calls--> `SeedForceRng()`  [INFERRED]
  src/main.cpp → src/sim/force_sampling.cpp
- `main()` --calls--> `ConfigureMklThreads()`  [INFERRED]
  src/main.cpp → src/sim/hyper_params.cpp
- `main()` --calls--> `RunSampleWorkers()`  [INFERRED]
  src/main.cpp → src/sim/worker.cpp
- `operator+()` --calls--> `Vector3f()`  [INFERRED]
  BMGL/matrix.cpp → BMGL/vector.h

## Communities (25 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.1
Nodes (32): LoadAnnotationJSON(), PrecomputeContactRegions(), SelectKRingNeighbors(), AppendCsvRecord(), BuildSortedCsvRecordsSnapshot(), CloseCsvJournal(), Generate_run_string(), HaveMatchingSampleIds() (+24 more)

### Community 1 - "Community 1"
Cohesion: 0.12
Nodes (11): Alloc2Dim(), Clear(), CloneMatrixStateFrom(), ComputeMatrixB(), ComputeMatrixD(), ComputeMatrixK(), ComputeMatrixKe(), ComputeNormal() (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.24
Nodes (19): add_index_to_stats(), compute_bounding_box(), copy_surface_to_object(), count_degenerate_surface_triangles(), count_unique_lines_from_tets(), fill_tetgen_input(), json_escape(), main() (+11 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (14): CreateSampleID(), MarkSampleComputed(), MarkSampleInflight(), MarkSampleRetired(), ApplyContactRegion(), ApplyFreezeFromAnnotation(), ApplyMaterialParams(), BuildMatrixCacheKey() (+6 more)

### Community 4 - "Community 4"
Cohesion: 0.23
Nodes (9): GetRotateMatrix(), Identity(), Matrix3x3(), Matrix4x4(), operator+(), SetMatrix(), SetRotateMatrix(), SetScaleMatrix() (+1 more)

### Community 5 - "Community 5"
Cohesion: 0.24
Nodes (8): Clear(), ComputeArea(), ComputeBoundingBox(), ComputeNeighbors(), ComputeNormal(), ReadPLY(), ResampleVertex(), Surface()

### Community 6 - "Community 6"
Cohesion: 0.33
Nodes (12): ConfigureMklThreads(), LoadBoolParam(), LoadFloatParam(), LoadIntParam(), LoadSimHyperParams(), LoadStringParam(), LoadUIntParam(), ParseBoolStrict() (+4 more)

### Community 7 - "Community 7"
Cohesion: 0.29
Nodes (9): ComputeBoundingBox(), float(), Init(), Normalize(), operator(), SetVector(), Vector2f(), Vector3f() (+1 more)

### Community 8 - "Community 8"
Cohesion: 0.32
Nodes (4): Assert-RequiredFile(), Get-VsDevCmdPath(), Normalize-PathValue(), Update-EnvironmentPrefix()

### Community 9 - "Community 9"
Cohesion: 0.43
Nodes (4): Line(), Tetrahedron(), Triangle(), Vertex()

### Community 10 - "Community 10"
Cohesion: 0.57
Nodes (6): AngleWithZAxis(), ComputeForceEuclidean(), generateVectors(), generateVectorsFromCsv(), RandomFloat(), SeedForceRng()

### Community 11 - "Community 11"
Cohesion: 0.52
Nodes (6): copy_surface_to_object(), json_escape(), main(), tetra_volume(), total_tetra_volume(), write_json()

### Community 12 - "Community 12"
Cohesion: 0.83
Nodes (3): build_bar_surface(), main(), run_case()

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Vector3f()` connect `Community 7` to `Community 3`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.311) - this node is a cross-community bridge._
- **Why does `ApplyContactRegion()` connect `Community 3` to `Community 7`?**
  _High betweenness centrality (0.243) - this node is a cross-community bridge._
- **Why does `main()` connect `Community 0` to `Community 10`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.208) - this node is a cross-community bridge._
- **Are the 28 inferred relationships involving `main()` (e.g. with `LoadSimHyperParams()` and `SeedForceRng()`) actually correct?**
  _`main()` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `processObjects()` (e.g. with `CloneTetraTemplate()` and `ApplyMaterialParams()`) actually correct?**
  _`processObjects()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.12 - nodes in this community are weakly interconnected._