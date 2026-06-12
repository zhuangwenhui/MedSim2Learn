#pragma once

#include <vector>

#include "bmgl.h"
#include "sim/hyper_params.h"

// FNV-1a 64-bit hashing, shared by the mesh/freeze/material/selection hashes.
inline constexpr unsigned long long kFnvOffset64 = 14695981039346656037ULL;
inline constexpr unsigned long long kFnvPrime64 = 1099511628211ULL;

void HashBytes64(unsigned long long& hash, const void* data, size_t length);

// FNV-1a over every vertex's new_coord; identifies the tetrahedralized mesh.
unsigned long long ComputeMeshHash(const Object* object);

// Identity of a reusable stiffness factorization: same mesh, same freeze set,
// same material, same solver path.
struct MatrixCacheKey {
    unsigned long long mesh_hash = 0;
    unsigned long long freeze_hash = 0;
    unsigned long long material_hash = 0;
    bool solver_lu = false;
    int matrix_node_count = 0;

    bool Equals(const MatrixCacheKey& other) const {
        return mesh_hash == other.mesh_hash && freeze_hash == other.freeze_hash &&
               material_hash == other.material_hash && solver_lu == other.solver_lu &&
               matrix_node_count == other.matrix_node_count;
    }
};

MatrixCacheKey BuildMatrixCacheKey(const Object* object, const SimHyperParams& params,
                                   unsigned long long mesh_hash);

// Writes the configured Young/Poisson into every tetrahedron.
void ApplyMaterialParams(Object* object, const SimHyperParams& params);

// Marks the annotated freeze vertices on the object.
void ApplyFreezeFromAnnotation(Object* object, const std::vector<int>& freeze_vertices);

// Distributes the total contact force equally over the region vertices and
// reports how many were selected plus an FNV hash of their indices.
void ApplyContactRegion(Object* object, const std::vector<int>& region, float fx, float fy,
                        float fz, int& selected_count, unsigned long long& selected_hash);

// Tetrahedralizes the surface into a fresh Object (TetGen "pY" switches) and
// resets per-vertex simulation state.
void ComputeTetrahedralMesh(Surface* in, Object* out, const SimHyperParams& params);

// A clonable template must have geometry but no per-sample element matrices.
bool ValidateTetraTemplate(const Object* object);

// Deep-copies the template's geometry/topology into a work object, resetting
// freeze/select/force state and leaving element matrices unallocated.
bool CloneTetraTemplate(const Object& template_object, Object* work_object);
