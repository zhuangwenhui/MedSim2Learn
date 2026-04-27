#include "mvrmesh/backends/gmsh/gmsh_evaluator.h"

#include <algorithm>
#include <array>
#include <fstream>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

extern "C" {
#include "gmshc.h"
}

namespace mvrmesh {

namespace {

std::string last_gmsh_error() {
    char* error = nullptr;
    int ierr = 0;
    gmshLoggerGetLastError(&error, &ierr);

    std::string message;
    if (ierr == 0 && error != nullptr) {
        message = error;
    }
    if (error != nullptr) {
        gmshFree(error);
    }
    return message;
}

[[noreturn]] void throw_gmsh_error(const std::string& operation, int ierr) {
    std::ostringstream oss;
    oss << operation << " failed";
    const std::string message = last_gmsh_error();
    if (!message.empty()) {
        oss << ": " << message;
    } else {
        oss << " with ierr=" << ierr;
    }
    throw std::runtime_error(oss.str());
}

void check_gmsh_error(const std::string& operation, int ierr) {
    if (ierr != 0) {
        throw_gmsh_error(operation, ierr);
    }
}

template <typename T>
class GmshArray {
public:
    GmshArray() = default;

    ~GmshArray() {
        if (data_ != nullptr) {
            gmshFree(data_);
        }
    }

    GmshArray(const GmshArray&) = delete;
    GmshArray& operator=(const GmshArray&) = delete;

    T** out() {
        return &data_;
    }

    const T* data() const {
        return data_;
    }

private:
    T* data_ = nullptr;
};

class GmshSession {
public:
    GmshSession() {
        int ierr = 0;
        const int is_initialized = gmshIsInitialized(&ierr);
        check_gmsh_error("gmshIsInitialized", ierr);
        if (!is_initialized) {
            gmshInitialize(0, nullptr, 0, 0, &ierr);
            check_gmsh_error("gmshInitialize", ierr);
            owns_session_ = true;
        }
    }

    ~GmshSession() {
        if (!owns_session_) {
            return;
        }
        int ierr = 0;
        gmshFinalize(&ierr);
        // Best effort cleanup; destructors must not throw.
        (void)ierr;
    }

    GmshSession(const GmshSession&) = delete;
    GmshSession& operator=(const GmshSession&) = delete;

private:
    bool owns_session_ = false;
};

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
        case '\\':
            out << "\\\\";
            break;
        case '"':
            out << "\\\"";
            break;
        case '\n':
            out << "\\n";
            break;
        case '\r':
            out << "\\r";
            break;
        case '\t':
            out << "\\t";
            break;
        default:
            out << ch;
            break;
        }
    }
    return out.str();
}

GmshEvaluationResult make_base_result(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const GmshEvaluationOptions& options
) {
    GmshEvaluationResult result;
    result.algorithm3d = options.algorithm3d;
    result.input_vertex_count = surface_vertices.size();
    result.input_face_count = surface_faces.size();
    return result;
}

void validate_face_index(const std::vector<Vec3>& vertices, int idx) {
    if (idx < 0 || static_cast<std::size_t>(idx) >= vertices.size()) {
        std::ostringstream oss;
        oss << "Face index out of range for Gmsh evaluation: " << idx
            << ", n_vertices=" << vertices.size();
        throw std::runtime_error(oss.str());
    }
}

void validate_gmsh_input_size(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    const auto max_size = std::numeric_limits<std::size_t>::max() / 3;
    if (vertices.size() > max_size) {
        throw std::runtime_error("Gmsh evaluation input has too many vertices.");
    }
    if (faces.size() > max_size) {
        throw std::runtime_error("Gmsh evaluation input has too many faces.");
    }
}

std::vector<double> to_gmsh_coordinates(const std::vector<Vec3>& vertices) {
    std::vector<double> coordinates;
    coordinates.reserve(vertices.size() * 3);
    for (const Vec3& vertex : vertices) {
        coordinates.push_back(vertex.x);
        coordinates.push_back(vertex.y);
        coordinates.push_back(vertex.z);
    }
    return coordinates;
}

std::vector<std::size_t> to_gmsh_triangles(
    const std::vector<Vec3>& vertices,
    const std::vector<Face>& faces
) {
    std::vector<std::size_t> triangles;
    triangles.reserve(faces.size() * 3);
    for (const Face& face : faces) {
        validate_face_index(vertices, face[0]);
        validate_face_index(vertices, face[1]);
        validate_face_index(vertices, face[2]);
        triangles.push_back(static_cast<std::size_t>(face[0]) + 1);
        triangles.push_back(static_cast<std::size_t>(face[1]) + 1);
        triangles.push_back(static_cast<std::size_t>(face[2]) + 1);
    }
    return triangles;
}

int to_zero_based_index(std::size_t value, std::size_t vertex_count) {
    if (value == 0 || value > vertex_count) {
        std::ostringstream oss;
        oss << "Gmsh returned tetrahedron index out of range: " << value
            << ", n_vertices=" << vertex_count;
        throw std::runtime_error(oss.str());
    }
    const std::size_t zero_based = value - 1;
    if (zero_based > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("Gmsh returned an index too large for mvrmesh::Tet.");
    }
    return static_cast<int>(zero_based);
}

std::size_t count_boundary_faces(const std::vector<Tet>& tetrahedra) {
    std::map<std::array<int, 3>, int> face_counts;
    for (const Tet& tet : tetrahedra) {
        std::array<std::array<int, 3>, 4> faces = {{
            {tet[0], tet[1], tet[2]},
            {tet[0], tet[1], tet[3]},
            {tet[0], tet[2], tet[3]},
            {tet[1], tet[2], tet[3]},
        }};
        for (std::array<int, 3>& face : faces) {
            std::sort(face.begin(), face.end());
            ++face_counts[face];
        }
    }

    std::size_t boundary_count = 0;
    for (const auto& [face, count] : face_counts) {
        (void)face;
        if (count == 1) {
            ++boundary_count;
        }
    }
    return boundary_count;
}

void copy_gmsh_output(
    const std::vector<Vec3>& surface_vertices,
    const std::size_t* tetrahedra,
    std::size_t tetrahedra_count,
    const double* steiner,
    std::size_t steiner_count,
    GmshEvaluationResult& result
) {
    if (steiner_count % 3 != 0) {
        throw std::runtime_error("Gmsh returned a malformed Steiner coordinate list.");
    }
    if (tetrahedra_count % 4 != 0) {
        throw std::runtime_error("Gmsh returned a malformed tetrahedron index list.");
    }
    if (tetrahedra_count > 0 && tetrahedra == nullptr) {
        throw std::runtime_error("Gmsh returned a null tetrahedron index list.");
    }
    if (steiner_count > 0 && steiner == nullptr) {
        throw std::runtime_error("Gmsh returned a null Steiner coordinate list.");
    }

    result.output_vertices = surface_vertices;
    result.steiner_vertex_count = steiner_count / 3;
    result.output_vertices.reserve(surface_vertices.size() + result.steiner_vertex_count);
    for (std::size_t i = 0; i < result.steiner_vertex_count; ++i) {
        result.output_vertices.push_back(Vec3{
            steiner[i * 3 + 0],
            steiner[i * 3 + 1],
            steiner[i * 3 + 2],
        });
    }

    result.output_vertex_count = result.output_vertices.size();
    result.output_tetra_count = tetrahedra_count / 4;
    result.output_tetrahedra.reserve(result.output_tetra_count);
    for (std::size_t i = 0; i < result.output_tetra_count; ++i) {
        result.output_tetrahedra.push_back(Tet{
            to_zero_based_index(tetrahedra[i * 4 + 0], result.output_vertex_count),
            to_zero_based_index(tetrahedra[i * 4 + 1], result.output_vertex_count),
            to_zero_based_index(tetrahedra[i * 4 + 2], result.output_vertex_count),
            to_zero_based_index(tetrahedra[i * 4 + 3], result.output_vertex_count),
        });
    }
    result.output_boundary_face_count = count_boundary_faces(result.output_tetrahedra);
    result.tetra_metrics = compute_tetra_mesh_metrics(result.output_vertices, result.output_tetrahedra);
}

}  // namespace

GmshEvaluationResult evaluate_gmsh(
    const std::vector<Vec3>& surface_vertices,
    const std::vector<Face>& surface_faces,
    const GmshEvaluationOptions& options
) {
    GmshEvaluationResult result = make_base_result(surface_vertices, surface_faces, options);

    try {
        validate_gmsh_input_size(surface_vertices, surface_faces);
        const std::vector<double> coordinates = to_gmsh_coordinates(surface_vertices);
        const std::vector<std::size_t> triangles = to_gmsh_triangles(surface_vertices, surface_faces);
        GmshArray<std::size_t> tetrahedra;
        std::size_t tetrahedra_count = 0;
        GmshArray<double> steiner;
        std::size_t steiner_count = 0;

        const GmshSession session;
        int ierr = 0;
        gmshOptionSetNumber("Mesh.Algorithm3D", static_cast<double>(result.algorithm3d), &ierr);
        check_gmsh_error("gmshOptionSetNumber(Mesh.Algorithm3D)", ierr);
        gmshAlgorithmTetrahedralize(
            coordinates.data(),
            coordinates.size(),
            tetrahedra.out(),
            &tetrahedra_count,
            steiner.out(),
            &steiner_count,
            triangles.data(),
            triangles.size(),
            &ierr
        );
        check_gmsh_error("gmshAlgorithmTetrahedralize", ierr);

        copy_gmsh_output(
            surface_vertices,
            tetrahedra.data(),
            tetrahedra_count,
            steiner.data(),
            steiner_count,
            result
        );
        if (!surface_vertices.empty() && !surface_faces.empty() && result.output_tetra_count == 0) {
            throw std::runtime_error(
                "Gmsh tetrahedralize produced no tetrahedra; verify Gmsh was built with the mesh module."
            );
        }
        result.success = true;
        result.diagnostic = "Gmsh evaluation completed.";
    } catch (const std::exception& ex) {
        result.success = false;
        result.diagnostic = ex.what();
    }
    return result;
}

std::string gmsh_evaluation_to_json(const GmshEvaluationResult& result) {
    const TetraMeshMetrics tetra_metrics =
        compute_tetra_mesh_metrics(result.output_vertices, result.output_tetrahedra);
    std::ostringstream out;
    out << std::setprecision(17);
    out << "{\n";
    out << "  \"success\": " << (result.success ? "true" : "false") << ",\n";
    out << "  \"algorithm3d\": " << result.algorithm3d << ",\n";
    out << "  \"diagnostic\": \"" << json_escape(result.diagnostic) << "\",\n";
    out << "  \"input_vertex_count\": " << result.input_vertex_count << ",\n";
    out << "  \"input_face_count\": " << result.input_face_count << ",\n";
    out << "  \"output_vertex_count\": " << result.output_vertex_count << ",\n";
    out << "  \"output_tetra_count\": " << result.output_tetra_count << ",\n";
    out << "  \"output_boundary_face_count\": " << result.output_boundary_face_count << ",\n";
    out << "  \"steiner_vertex_count\": " << result.steiner_vertex_count << ",\n";
    out << "  \"tetra_count\": " << tetra_metrics.tetra_count << ",\n";
    out << "  \"degenerate_tetra_count\": " << tetra_metrics.degenerate_tetra_count << ",\n";
    out << "  \"total_volume\": " << tetra_metrics.total_volume << ",\n";
    out << "  \"min_tetra_volume\": " << tetra_metrics.min_tetra_volume << ",\n";
    out << "  \"max_tetra_volume\": " << tetra_metrics.max_tetra_volume << ",\n";
    out << "  \"mean_tetra_volume\": " << tetra_metrics.mean_tetra_volume << ",\n";
    out << "  \"min_tetra_quality\": " << tetra_metrics.min_tetra_quality << ",\n";
    out << "  \"max_tetra_quality\": " << tetra_metrics.max_tetra_quality << ",\n";
    out << "  \"mean_tetra_quality\": " << tetra_metrics.mean_tetra_quality << "\n";
    out << "}\n";
    return out.str();
}

void write_gmsh_evaluation_json(
    const std::filesystem::path& path,
    const GmshEvaluationResult& result
) {
    std::ofstream output(path, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("Failed to open Gmsh metrics output file: " + path.string());
    }
    output << gmsh_evaluation_to_json(result);
}

}  // namespace mvrmesh
