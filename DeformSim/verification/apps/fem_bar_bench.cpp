#include "stdafx.h"

#include <cmath>
#include <cstdio>
#include <vector>

#include "object.h"
#include "surface.h"

// Analytic FEM benchmark: axial extension of a rectangular bar.
//
// A bar of size W x W x L (mm) is fixed at z=0 and loaded with a total axial
// force F (N) applied as consistent nodal loads (area-weighted thirds) on the
// z=L face. With Poisson ratio 0 the exact solution is a homogeneous uniaxial
// strain field, which linear tetrahedra reproduce exactly (patch test), so
// the FEM tip displacement must equal delta = F*L/(E*A) to solver precision.
// A second case with Poisson 0.4 sanity-checks the same formula loosely
// (Saint-Venant end effects at the clamped face).

namespace {

const float kBarWidth = 10.0f;   // mm
const float kBarLength = 50.0f;  // mm
const float kTotalForce = 2.0f;  // N, applied along +z

void build_bar_surface(Object& object)
{
	// 8 corners of [0,W]x[0,W]x[0,L]
	const float w = kBarWidth;
	const float l = kBarLength;
	const float coords[8][3] = {
		{ 0, 0, 0 }, { w, 0, 0 }, { w, w, 0 }, { 0, w, 0 },
		{ 0, 0, l }, { w, 0, l }, { w, w, l }, { 0, w, l },
	};
	// 12 outward-oriented triangles
	const int faces[12][3] = {
		{ 0, 2, 1 }, { 0, 3, 2 },  // bottom (z=0), normal -z
		{ 4, 5, 6 }, { 4, 6, 7 },  // top (z=L), normal +z
		{ 0, 1, 5 }, { 0, 5, 4 },  // y=0
		{ 1, 2, 6 }, { 1, 6, 5 },  // x=W
		{ 2, 3, 7 }, { 2, 7, 6 },  // y=W
		{ 3, 0, 4 }, { 3, 4, 7 },  // x=0
	};

	object.InitVertex(8);
	for (int i = 0; i < 8; i++) {
		Vector3f p(coords[i][0], coords[i][1], coords[i][2]);
		object.vertex[i].coord = p;
		object.vertex[i].cur_coord = p;
		object.vertex[i].new_coord = p;
		object.vertex[i].isSurface = true;
	}
	object.InitTriangle(12);
	for (int i = 0; i < 12; i++) {
		object.triangle[i].set[0] = faces[i][0];
		object.triangle[i].set[1] = faces[i][1];
		object.triangle[i].set[2] = faces[i][2];
	}
}

// Returns the relative error of the mean tip displacement vs F*L/(E*A).
bool run_case(double young, double poisson, double tolerance, char* switches, double& rel_err)
{
	Object object;
	build_bar_surface(object);

	object.ComputeQualityTetrahedralMesh(switches);
	if (object.nTetra <= 0) {
		fprintf(stderr, "[error] tetrahedralization produced no tetrahedra\n");
		return false;
	}

	for (int i = 0; i < object.nTetra; i++) {
		object.tetra[i].young = (float)young;
		object.tetra[i].poisson = (float)poisson;
	}

	const float eps = 1e-4f;
	for (int i = 0; i < object.nNode; i++) {
		object.vertex[i].isFreeze = (object.vertex[i].coord.z < eps);
		object.vertex[i].force.Init();
	}

	// Consistent nodal loads on the top face: each top triangle spreads
	// (area / total_area) * F equally over its three corners.
	double total_top_area = 0.0;
	std::vector<double> top_tri_area(object.nTriangle, 0.0);
	for (int i = 0; i < object.nTriangle; i++) {
		bool on_top = true;
		for (int j = 0; j < 3; j++) {
			if (object.vertex[object.triangle[i].set[j]].coord.z < kBarLength - eps) {
				on_top = false;
				break;
			}
		}
		if (!on_top) continue;
		Vector3f a = object.vertex[object.triangle[i].set[0]].coord;
		Vector3f b = object.vertex[object.triangle[i].set[1]].coord;
		Vector3f c = object.vertex[object.triangle[i].set[2]].coord;
		double area = 0.5 * (double)((b - a).CrossProduct(c - a)).GetLength();
		top_tri_area[i] = area;
		total_top_area += area;
	}
	if (total_top_area <= 0.0) {
		fprintf(stderr, "[error] no top-face triangles found\n");
		return false;
	}
	for (int i = 0; i < object.nTriangle; i++) {
		if (top_tri_area[i] <= 0.0) continue;
		const float node_force =
			(float)(kTotalForce * top_tri_area[i] / total_top_area / 3.0);
		for (int j = 0; j < 3; j++) {
			Vertex& v = object.vertex[object.triangle[i].set[j]];
			v.force.SetVector(v.force.x, v.force.y, v.force.z + node_force);
		}
	}

	if (!object.ComputeMatrixK()) {
		fprintf(stderr, "[error] ComputeMatrixK failed\n");
		return false;
	}
	object.ReleaseAssemblyScratch();
	if (!object.Deform()) {
		fprintf(stderr, "[error] Deform failed\n");
		return false;
	}

	// Mean axial displacement of the top-face nodes.
	double sum_uz = 0.0;
	int n_top = 0;
	for (int i = 0; i < object.nNode; i++) {
		if (object.vertex[i].coord.z < kBarLength - eps) continue;
		sum_uz += (double)(object.vertex[i].new_coord.z - object.vertex[i].coord.z);
		n_top++;
	}
	const double mean_uz = sum_uz / n_top;
	const double area = (double)kBarWidth * (double)kBarWidth;
	const double analytic = (double)kTotalForce * (double)kBarLength / (young * area);
	rel_err = std::fabs(mean_uz - analytic) / analytic;

	printf("[case] E=%g MPa nu=%g: tets=%d nodes=%d tip_uz=%.6f mm analytic=%.6f mm rel_err=%.3e (tol %.0e)\n",
	       young, poisson, object.nTetra, object.nNode, mean_uz, analytic, rel_err, tolerance);
	return rel_err <= tolerance;
}

}  // namespace

int main()
{
	double rel_err = 0.0;
	bool ok = true;

	// Patch-test case: nu = 0 makes the uniaxial field exactly representable
	// by linear tetrahedra, so the FEM answer must match to solver precision.
	// This is the hard correctness assertion for B/D/Ke/assembly/LU/solve.
	char coarse[] = "pq1.4a40.0Y";
	ok &= run_case(0.03, 0.0, 1e-3, coarse, rel_err);

	// Production-like material (nu = 0.4): linear tetrahedra are over-stiff
	// near incompressibility (volumetric locking) and the fully clamped end
	// violates the FL/EA assumptions, so this case BOUNDS the deviation on a
	// refined mesh instead of asserting equality. The same systematic
	// stiffness applies to the production kidney runs.
	char fine[] = "pq1.4a4.0Y";
	ok &= run_case(0.03, 0.4, 0.30, fine, rel_err);

	if (!ok) {
		fprintf(stderr, "[FAIL] fem_bar_bench: FEM result deviates from the analytic solution\n");
		return 1;
	}
	printf("[ok] fem_bar_bench passed\n");
	return 0;
}
