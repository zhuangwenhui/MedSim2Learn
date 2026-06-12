// Per-sample mesh preparation: tetra template, material/freeze/contact state,
// and the hashes that key the shared stiffness factorization.
#include "sim/sample_pipeline.h"

void HashBytes64(unsigned long long& hash, const void* data, size_t length) {
    const unsigned char* bytes = static_cast<const unsigned char*>(data);
    for (size_t i = 0; i < length; ++i) {
        hash ^= static_cast<unsigned long long>(bytes[i]);
        hash *= kFnvPrime64;
    }
}

unsigned long long ComputeMeshHash(const Object* object) {
    unsigned long long hash = kFnvOffset64;
    for (int i = 0; i < object->nNode; ++i) {
        HashBytes64(hash, &object->vertex[i].new_coord.x, sizeof(float));
        HashBytes64(hash, &object->vertex[i].new_coord.y, sizeof(float));
        HashBytes64(hash, &object->vertex[i].new_coord.z, sizeof(float));
    }
    return hash;
}

MatrixCacheKey BuildMatrixCacheKey(const Object* object, const SimHyperParams& params,
                                   unsigned long long mesh_hash) {
    MatrixCacheKey key;
    if (object == NULL) return key;

    key.mesh_hash = mesh_hash;
    key.solver_lu = params.use_solver_lu;

    unsigned long long freeze_hash = kFnvOffset64;
    int matrix_node_count = 0;
    for (int i = 0; i < object->nNode; ++i) {
        if (object->vertex[i].isFreeze) {
            unsigned long long freeze_index = static_cast<unsigned long long>(i);
            HashBytes64(freeze_hash, &freeze_index, sizeof(freeze_index));
        } else {
            ++matrix_node_count;
        }
    }
    key.freeze_hash = freeze_hash;
    key.matrix_node_count = matrix_node_count;

    unsigned long long material_hash = kFnvOffset64;
    HashBytes64(material_hash, &params.material_young, sizeof(params.material_young));
    HashBytes64(material_hash, &params.material_poisson, sizeof(params.material_poisson));
    key.material_hash = material_hash;

    return key;
}

void ApplyMaterialParams(Object* object, const SimHyperParams& params) {
    if (object == NULL) return;
    for (int i = 0; i < object->nTetra; ++i) {
        object->tetra[i].young = params.material_young;
        object->tetra[i].poisson = params.material_poisson;
    }
}

void ApplyFreezeFromAnnotation(Object* object, const std::vector<int>& freeze_vertices) {
    for (int idx : freeze_vertices) {
        if (idx >= 0 && idx < object->nNode) {
            object->vertex[idx].isFreeze = true;
        }
    }
}

void ApplyContactRegion(Object* object, const std::vector<int>& region, float fx, float fy,
                        float fz, int& selected_count, unsigned long long& selected_hash) {
    selected_count = 0;
    selected_hash = kFnvOffset64;

    if (region.empty()) return;
    const float inv_n = 1.0f / static_cast<float>(region.size());

    for (int idx : region) {
        if (idx >= 0 && idx < object->nNode) {
            object->vertex[idx].isSelect = true;
            object->vertex[idx].force = Vector3f(fx, fy, fz) * inv_n;
            unsigned long long selected_index = static_cast<unsigned long long>(idx);
            HashBytes64(selected_hash, &selected_index, sizeof(selected_index));
            ++selected_count;
        }
    }
}

bool ValidateTetraTemplate(const Object* object) {
    if (object == NULL) return false;
    if (object->nNode <= 0 || object->nTriangle <= 0 || object->nTetra <= 0) return false;
    if (object->vertex == NULL || object->triangle == NULL || object->tetra == NULL) return false;

    for (int i = 0; i < object->nTetra; ++i) {
        if (object->tetra[i].Ke != NULL || object->tetra[i].Se != NULL) {
            return false;
        }
    }

    return true;
}

bool CloneTetraTemplate(const Object& template_object, Object* work_object) {
    if (work_object == NULL) return false;
    if (!ValidateTetraTemplate(&template_object)) return false;

    work_object->isDispVertex = template_object.isDispVertex;
    work_object->isDispLine = template_object.isDispLine;
    work_object->isDispSurface = template_object.isDispSurface;
    work_object->isDispVolume = template_object.isDispVolume;
    work_object->type = template_object.type;
    work_object->m_count = template_object.m_count;
    work_object->center = template_object.center;
    work_object->min = template_object.min;
    work_object->max = template_object.max;
    work_object->area = template_object.area;
    work_object->volume = template_object.volume;
    work_object->omega = template_object.omega;
    work_object->lambda = template_object.lambda;
    work_object->flag = template_object.flag;

    work_object->InitVertex(template_object.nNode);
    for (int i = 0; i < template_object.nNode; ++i) {
        work_object->vertex[i] = template_object.vertex[i];
        work_object->vertex[i].isFreeze = false;
        work_object->vertex[i].isSelect = false;
        work_object->vertex[i].force.Init();
    }

    if (template_object.nLine > 0) {
        work_object->InitLine(template_object.nLine);
        for (int i = 0; i < template_object.nLine; ++i) {
            work_object->line[i] = template_object.line[i];
        }
    }

    if (template_object.nTriangle > 0) {
        work_object->InitTriangle(template_object.nTriangle);
        for (int i = 0; i < template_object.nTriangle; ++i) {
            work_object->triangle[i] = template_object.triangle[i];
        }
    }

    if (template_object.nTetra > 0) {
        work_object->InitTetrahedron(template_object.nTetra);
        for (int i = 0; i < template_object.nTetra; ++i) {
            for (int j = 0; j < 4; ++j) {
                work_object->tetra[i].set[j] = template_object.tetra[i].set[j];
            }
            work_object->tetra[i].young = template_object.tetra[i].young;
            work_object->tetra[i].poisson = template_object.tetra[i].poisson;
            work_object->tetra[i].volume = template_object.tetra[i].volume;
            work_object->tetra[i].stress = template_object.tetra[i].stress;
            work_object->tetra[i].Ke = 0;
            work_object->tetra[i].Se = 0;
        }
    }

    return true;
}

void ComputeTetrahedralMesh(Surface* in, Object* out, const SimHyperParams& params) {
    // Tetrahedral mesh generation
    int nNode = in->nNode;
    int nTriangle = in->nTriangle;

    out->InitVertex(nNode);
    out->InitTriangle(nTriangle);

    for (int i = 0; i < nNode; i++) {
        out->vertex[i].new_coord = in->vertex[i].new_coord;
        out->vertex[i].coord = in->vertex[i].new_coord;
        out->vertex[i].isFreeze = in->vertex[i].isFreeze;
        out->vertex[i].isSelect = in->vertex[i].isSelect;
    }

    for (int i = 0; i < nTriangle; i++) {
        out->triangle[i].set[0] = in->triangle[i].set[0];
        out->triangle[i].set[1] = in->triangle[i].set[1];
        out->triangle[i].set[2] = in->triangle[i].set[2];
    }

    // Compute the quality of the tetrahedral mesh
    out->ComputeQualityTetrahedralMesh("pY");

    for (int i = 0; i < out->nNode; i++) {
        out->vertex[i].coord = out->vertex[i].new_coord;
        out->vertex[i].isFreeze = false;
        out->vertex[i].isSelect = false;
        out->vertex[i].force.Init();
    }

    if (!params.use_skip_normal_area) {
        out->ComputeNormal();
        out->ComputeArea();
    }
}
