/////////////////////////////////////////////////////////////////////////////
//
// surface.cpp - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M. Nakao  All rights reserved.
//
// E-Mail : megumi@i.kyoto-u.ac.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "surface.h"


Surface::Surface()
{
	vertex.clear();
	triangle.clear();

	A = 0;
	b = 0;

	tetraIndex = 0;
	tetraPos = 0;

	nNode = 0;
	nTriangle = 0;

	center.Init();
	area = 0.0f;

	omega = 1.0f;
	lambda = 10.0f;
}

Surface::~Surface()
{
	Clear();
}

void Surface::Clear()
{

	vertex.clear();
	triangle.clear();

	if (A) Free2Dim(A);
	if (b) free(b);
	if (tetraIndex) delete[] tetraIndex;
	if (tetraPos) delete[] tetraPos;

	tetraIndex = 0;
	tetraPos = 0;

	A = 0;
	b = 0;

}

bool Surface::ReadPLY(const std::string& filepath)
{
	
	int i, num;
	char buf[256], dummy[256], dummy2[256];

	ifstream fin;
	fin.open(filepath, ios::in);
	if(!fin.is_open()) { return false; }

	int property = 0;
	int amira = 0;
	bool ascii = false;
	bool header_done = false;
	Clear();

	while(fin.getline(buf, sizeof(buf)))
	{
		// Reading headers
		if (strstr(buf, "format ")) {
			ascii = (strstr(buf, "format ascii") != NULL);
		}
		if (strstr(buf, "element vertex ")) {
			if (sscanf(buf, "%s %s %d", &dummy, &dummy2, &num) == 3) {
				nNode = num;
			}
		}
		if (strstr(buf, "element face ")) {
			if (sscanf(buf, "%s %s %d", &dummy, &dummy2, &num) == 3) {
				nTriangle = num;
			}
		}
		if (strstr(buf, "property uchar red")){ property = 1; }
		if (strstr(buf, "property uchar alpha")){ property = 2; }
		if (strstr(buf, "Amira") || strstr(buf, "Avizo")){ amira = 1; }
		if (strstr(buf, "end_header")) { header_done = true; break; }
	}

	// A binary or truncated PLY must fail loudly here, not flow a silently
	// degenerate mesh into tetrahedralization.
	if (!header_done) {
		fprintf(stderr, "Error: ReadPLY: missing end_header in %s\n", filepath.c_str());
		return false;
	}
	if (!ascii) {
		fprintf(stderr, "Error: ReadPLY: only 'format ascii 1.0' is supported: %s\n", filepath.c_str());
		return false;
	}
	if (nNode <= 0 || nTriangle <= 0) {
		fprintf(stderr, "Error: ReadPLY: invalid element counts (vertex=%d, face=%d) in %s\n",
		        nNode, nTriangle, filepath.c_str());
		return false;
	}

	Vertex v;
	Triangle t;

	for(i=0; i< nNode; i++){
		if (property == 1) fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z >> num >> num >> num;
		else if (property == 2) fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z >> num >> num >> num >> num;
		else fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z;
		if (fin.fail()) {
			fprintf(stderr, "Error: ReadPLY: truncated or non-numeric vertex data at vertex %d in %s\n",
			        i, filepath.c_str());
			return false;
		}
		if (!std::isfinite(v.new_coord.x) || !std::isfinite(v.new_coord.y) || !std::isfinite(v.new_coord.z)) {
			fprintf(stderr, "Error: ReadPLY: non-finite coordinate at vertex %d in %s\n", i, filepath.c_str());
			return false;
		}
		v.coord = v.new_coord;
		v.cur_coord = v.new_coord;
		v.isSurface = true;
		vertex.push_back(v);
	}

	for(i=0; i< nTriangle; i++){
		int face_count = 0;
		if (amira) fin >> face_count >> t.set[0] >> t.set[1] >> t.set[2] >> num;
		else fin >> face_count >> t.set[0] >> t.set[1] >> t.set[2];
		if (fin.fail()) {
			fprintf(stderr, "Error: ReadPLY: truncated or non-numeric face data at face %d in %s\n",
			        i, filepath.c_str());
			return false;
		}
		if (face_count != 3) {
			fprintf(stderr, "Error: ReadPLY: face %d has %d vertices, only triangles are supported: %s\n",
			        i, face_count, filepath.c_str());
			return false;
		}
		for (int j = 0; j < 3; j++) {
			if (t.set[j] < 0 || t.set[j] >= nNode) {
				fprintf(stderr, "Error: ReadPLY: face %d references vertex %d outside [0, %d) in %s\n",
				        i, t.set[j], nNode, filepath.c_str());
				return false;
			}
		}
		triangle.push_back(t);
	}

	ComputeNormal();
	ComputeArea();
	ComputeBoundingBox();
	ComputeNeighbors();

	fin.close();

	
	return true;

}

bool Surface::WritePLY(const std::string& filepath)
{
	FILE *fout = fopen(filepath.c_str(), "w");
	if (!fout) { return false; }

	fprintf(fout, "ply\n");
	fprintf(fout, "format ascii 1.0\n");
	fprintf(fout, "comment VCGLIB generated\n");
	fprintf(fout, "element vertex %d\n", nNode);
	fprintf(fout, "property float x\n");
	fprintf(fout, "property float y\n");
	fprintf(fout, "property float z\n");
	fprintf(fout, "property uchar red\n");
	fprintf(fout, "property uchar green\n");
	fprintf(fout, "property uchar blue\n");
	fprintf(fout, "element face %d\n", nTriangle);
	fprintf(fout, "property list uchar int vertex_indices\n");
	fprintf(fout, "end_header\n");

	for (int i = 0; i< nNode; i++){
		fprintf(fout, "%f %f %f %d %d %d\n", vertex[i].new_coord.x, vertex[i].new_coord.y, vertex[i].new_coord.z, (int)(color.x * 255.0f), (int)(color.y * 255.0f), (int)(color.z * 255.0f));
	}
	
	for (int i = 0; i < nTriangle; i++){
		fprintf(fout, "3 %d %d %d\n", triangle[i].set[0], triangle[i].set[1], triangle[i].set[2]);
	}

	fclose(fout);

	return true;
}


void Surface::ComputeBoundingBox()
{

	min = Vector3f(FLT_MAX, FLT_MAX, FLT_MAX);
	max = Vector3f(-FLT_MAX, -FLT_MAX, -FLT_MAX);

	for (int i = 0; i<nNode; i++) {
		this->min.x = std::min(this->min.x, vertex[i].new_coord.x);
		this->min.y = std::min(this->min.y, vertex[i].new_coord.y);
		this->min.z = std::min(this->min.z, vertex[i].new_coord.z);
		this->max.x = std::max(this->max.x, vertex[i].new_coord.x);
		this->max.y = std::max(this->max.y, vertex[i].new_coord.y);
		this->max.z = std::max(this->max.z, vertex[i].new_coord.z);
	}

	center = (min + max) * 0.5f;

}

void Surface::ComputeArea()
{


	for (int i = 0; i<nNode; i++) vertex[i].area = 0.0f;

	Vector3f vec[3];
	area = 0.0f;

	// Compute per-vertex normal vectors
	for (int i = 0; i<nTriangle; i++){

		int tri_vert[3];
		for (int j = 0; j<3; j++){
			tri_vert[j] = triangle[i].set[j];
		}

		vec[0] = vertex[tri_vert[1]].new_coord - vertex[tri_vert[0]].new_coord;
		vec[1] = vertex[tri_vert[2]].new_coord - vertex[tri_vert[1]].new_coord;
		vec[2] = vertex[tri_vert[0]].new_coord - vertex[tri_vert[2]].new_coord;

		triangle[i].area = vec[0].CrossProduct(vec[1]).GetLength();

		vertex[tri_vert[0]].area += triangle[i].area / 3.0f;
		vertex[tri_vert[1]].area += triangle[i].area / 3.0f;
		vertex[tri_vert[2]].area += triangle[i].area / 3.0f;

		area += triangle[i].area;
	}

}

void Surface::SmoothSurface(float r)
{

	for (int i = 0; i < nNode; i++){

		Vector3f pos;
		int id;

		for (int j = 0; j < vertex[i].neighborVertex.size(); j++){
			id = vertex[i].neighborVertex[j];
			pos += vertex[id].new_coord / (float)vertex[i].neighborVertex.size();
		}

		vertex[i].cur_coord = vertex[i].new_coord * (1.0f -r) + pos * r;
	}

	for (int i = 0; i < nNode; i++){
		vertex[i].new_coord = vertex[i].cur_coord;
	}

}

void Surface::ResampleVertex(float r)
{
	ComputeBoundingBox();

	for (int i = 0; i < nNode; i++){
		vertex[i].isSelect = false;
	}

	if (r > (max - min).GetLength()) return;

	// Select points so no selected vertex lies within radius r of another.
	for (int i = 0; i < nNode; i++){

		bool flag = false;

		for (int j = 0; j < nNode; j++){
			if (!vertex[j].isSelect) continue;

			if ((vertex[i].new_coord - vertex[j].new_coord).GetLength() < r){
				flag = true;
				break;
			}
		}

		if (flag) continue;
		vertex[i].isSelect = true;
	}

}

void Surface::ComputeNormal()
{
	float *weight = new float[nNode];
	Vector3f *normal = new Vector3f[nNode];
	memset(weight, 0, sizeof(float)*nNode);

	// Compute per-vertex normal vectors
	for (int i = 0; i<nTriangle; i++){

		int tri_vert[3];
		Vector3f vec[3];
		float len[3] = { 0.0f, 0.0f, 0.0f };

		for (int j = 0; j<3; j++){
			tri_vert[j] = triangle[i].set[j];
		}

		vec[0] = vertex[tri_vert[1]].new_coord - vertex[tri_vert[0]].new_coord;
		vec[1] = vertex[tri_vert[2]].new_coord - vertex[tri_vert[1]].new_coord;
		vec[2] = vertex[tri_vert[0]].new_coord - vertex[tri_vert[2]].new_coord;
		len[0] = vec[0].GetLength();
		len[1] = vec[1].GetLength();
		len[2] = vec[2].GetLength();


		triangle[i].new_normal = vec[0].CrossProduct(vec[1]);
		triangle[i].new_normal.Normalize();

		weight[tri_vert[0]] += len[0] * len[0] + len[2] * len[2];
		weight[tri_vert[1]] += len[1] * len[1] + len[0] * len[0];
		weight[tri_vert[2]] += len[2] * len[2] + len[1] * len[1];


		normal[tri_vert[0]] += triangle[i].new_normal * weight[tri_vert[0]];
		normal[tri_vert[1]] += triangle[i].new_normal * weight[tri_vert[1]];
		normal[tri_vert[2]] += triangle[i].new_normal * weight[tri_vert[2]];

	}

	for (int i = 0; i<nNode; i++){

		if (normal[i].GetLength() == 0.0f){
			// No valid adjacent triangles contribute to this normal.
			vertex[i].new_normal.Init();
		}
		else{
			vertex[i].new_normal = normal[i] / weight[i];
			vertex[i].new_normal.Normalize();
		}
	}

	delete[] weight;
	delete[] normal;

}

void Surface::ComputeNeighbors()
{

	// Register neighbor information
	for (int i = 0; i<nTriangle; i++){

		for (int j = 0; j<3; j++){

			int id = triangle[i].set[j];

			for (int m = 0; m < 3; m++){

				if (j == m) continue;

				bool neighbor_flag = false;

				for (int n = 0; n < vertex[id].neighborVertex.size(); n++){
					if ( vertex[id].neighborVertex[n] == triangle[i].set[m]){
						neighbor_flag = true;
						break;
					}
				}

				if (neighbor_flag == false){
					vertex[id].neighborVertex.push_back( triangle[i].set[m]);
				}
			}
		}
	}

}

double **Surface::Alloc2Dim(int  nRows, int nColumns)
{
	// Array[i][j]: column i and row j (column-major format)
	double **Array;

	Array = (double **)calloc(nRows, sizeof(double *));
	if (!Array) return nullptr;

	size_t totalElements = static_cast<size_t>(nRows) * static_cast<size_t>(nColumns);
	Array[0] = (double*)calloc(totalElements, sizeof(double));
	if (!Array[0]) {
		free(Array);
		return nullptr;
	}

	for (int i = 0; i < nRows; i++)  Array[i] = Array[0] + i * nColumns;

	return (double **)Array;

}
