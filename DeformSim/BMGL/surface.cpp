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

bool Surface::ReadPLY(CString filepath)
{
	
	int i, num;
	char buf[256], dummy[256], dummy2[256];

	ifstream fin;
	fin.open(filepath, ios::in);
	if(!fin.is_open()) { return false; }

	int property = 0;
	int amira = 0;
	Clear();

	while(fin.getline(buf, sizeof(buf)))
	{
		// Reading headers
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
		if (strstr(buf, "end_header")) break;
	}
	
	Vertex v;
	Triangle t;

	if (nNode == 0) return false;

	for(i=0; i< nNode; i++){
		if (property == 1) fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z >> num >> num >> num; 
		else if (property == 2) fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z >> num >> num >> num >> num;
		else fin >> v.new_coord.x >> v.new_coord.y >> v.new_coord.z;
		v.coord = v.new_coord;
		v.cur_coord = v.new_coord;
		v.isSurface = true;
		vertex.push_back(v);
	}

	for(i=0; i< nTriangle; i++){
		if (amira) fin >> num >> t.set[0] >> t.set[1] >> t.set[2] >> num;
		else fin >> num >> t.set[0] >> t.set[1] >> t.set[2];
		triangle.push_back(t);
	}

	ComputeNormal();
	ComputeArea();
	ComputeBoundingBox();
//	ComputeNeighbors();

	fin.close();

	
	return true;

}

bool Surface::WritePLY(CString filepath)
{
	FILE *fout = fopen(filepath, "w");
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

void Surface::RenderVertex()
{
	GLUquadricObj* quadObj;
	quadObj = gluNewQuadric();
	gluQuadricDrawStyle(quadObj, GLU_FILL);
	gluQuadricNormals(quadObj, GLU_SMOOTH);

	for (int i = 0; i<nNode; i++){

		if (vertex[i].isSelect){ glColor3f(0.0f, 0.8f, 0.0f); }
		else if (vertex[i].isFreeze) { glColor3f(0.8f, 0.0f, 0.0f); }
		else { glColor3f(0.0f, 0.0f, 0.8f); }

		glPushMatrix();
		glTranslatef(vertex[i].new_coord.x, vertex[i].new_coord.y, vertex[i].new_coord.z);
		gluSphere(quadObj, 2.0f, 10, 10);
		glPopMatrix();

	}

}

void Surface::RenderLine()
{
	Vector3f norm, coord;
	glShadeModel(GL_SMOOTH);
	glColor3f(0.0f, 0.0f, 0.0f);

	glDisable(GL_LIGHTING);
	glPolygonMode(GL_FRONT_AND_BACK, GL_LINE);
	glLineWidth(1.5f);

	for (int i = 0; i< nTriangle; i++)
	{
		glBegin(GL_TRIANGLE_STRIP);
		for (int j = 0; j < 3; j++){
			norm = vertex[triangle[i].set[j]].new_normal;
			coord = vertex[triangle[i].set[j]].new_coord;
			glNormal3f(norm.x, norm.y, norm.z);
			glVertex3f(coord.x, coord.y, coord.z);
		}
		glEnd();
	}

	glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
	glEnable(GL_LIGHTING);

}

void Surface::RenderTriangle()
{
	Vector3f v1, v2, norm, coord;

	glShadeModel(GL_SMOOTH);
//	glColor4f( 0.75f, 0.75f, 0.75f, 1.0f );


	for (int i = 0; i< nTriangle; i++)
	{
		v1 = vertex[triangle[i].set[1]].new_coord - vertex[triangle[i].set[0]].new_coord;
		v2 = vertex[triangle[i].set[2]].new_coord - vertex[triangle[i].set[0]].new_coord;
		norm = v1.CrossProduct(v2);

		glBegin(GL_TRIANGLES);
		for (int j = 0; j < 3; j++){
			coord = vertex[triangle[i].set[j]].new_coord;
			glNormal3f(norm.x, norm.y, norm.z);
			glVertex3f(coord.x, coord.y, coord.z);
		}
		glEnd();
	}

}

void Surface::RenderSurface()
{
	Vector3f norm, coord;

	for (int i = 0; i< nTriangle; i++)
	{
		glBegin(GL_TRIANGLES);
		for (int j = 0; j < 3; j++){
			norm = vertex[triangle[i].set[j]].new_normal;
			coord = vertex[triangle[i].set[j]].new_coord;
			glNormal3f(norm.x, norm.y, norm.z);
			glVertex3f(coord.x, coord.y, coord.z);
		}
		glEnd();
	}


}

void Surface::RenderDeform(float min_d, float max_d)
{

	GLUquadricObj* quadObj;
	quadObj = gluNewQuadric();
	gluQuadricDrawStyle(quadObj, GLU_FILL);
	gluQuadricNormals(quadObj, GLU_SMOOTH);

	float d = 0.5f;		// Vector radius
	float s = 0.0f;		// Vector length

	int value = 0;
	float val = 0.0f;
	int step = 256;				// Color resolution
	Vector3f color;

	Vector3f pos, vec, vec1, vec2;

	for (int i = 0; i<nNode; i++){

		if (!vertex[i].isSelect) continue;

		pos = vertex[i].coord;
		vec = vertex[i].new_coord - vertex[i].coord;
		s = vec.GetLength();

		vec1 = vec;
		vec1.Normalize();
		vec2 = Vector3f(0.0f, 1.0f, 0.0f);
		vec2.Normalize();
		vec = vec2.CrossProduct(vec1);

		// Clamp values above max_d to the top color.
		if (s > max_d) val = max_d;
		else val = s;

		// Map the displacement into the color ramp.
		value = (int)(((float)step - 1.0f) * (val - min_d) / (max_d - min_d));
		color = GetColorValue(0, 240, step, value) * 0.8f;

		glColor3f(color.x, color.y, color.z);

		glPushMatrix();
		glTranslatef(pos.x, pos.y, pos.z);
		glRotatef(acos(vec1*vec2) * 180.0f / 3.1415f, vec.x, vec.y, vec.z);

		RenderVector(d, s);
		glPopMatrix();

	}

}

void Surface::RenderVector(float d, float s)
{

	int i;
	float pi = 3.1415f, t;

	glBegin(GL_QUAD_STRIP);

	for (i = 0; i <= 6; i++){
		t = i * 2 * pi / 6;
		glNormal3f(cos(t), 0.0, sin(t));
		glVertex3f(d * cos(t), 0.0, d * sin(t));
		glVertex3f(d * cos(t), s, d * sin(t));
	}

	glEnd();

	glTranslatef(0.0, s, 0.0);
	glRotatef(-90.0, 1.0, 0.0, 0.0);

	GLUquadricObj* quadObj;
	quadObj = gluNewQuadric();
	gluCylinder(quadObj, 2.0*d, 0.0, 4.0*d, 5, 5);
	gluDeleteQuadric(quadObj);
}

void Surface::RenderNormal()
{
	Vector3f v, p, n;
	glLineWidth(1.0f);

	for (int i = 0; i <nNode; i++){

		v = vertex[i].new_coord;
		p = v + vertex[i].new_normal * 0.1f;
		n = vertex[i].new_normal;

		glBegin(GL_LINES);
		glNormal3f(n.x, n.y, n.z);
		glVertex3f(v.x, v.y, v.z);
		glNormal3f(n.x, n.y, n.z);
		glVertex3f(p.x, p.y, p.z);
		glEnd();
	}

}

void Surface::RenderLaplacian()
{
	Vector3f v, p, n;
	glLineWidth(1.0f);

	for (int i = 0; i <nNode; i++){

		v = vertex[i].new_coord;
		p = v + vertex[i].laplacian * 10.0f;
		n = vertex[i].new_normal;

		glBegin(GL_LINES);
		glNormal3f(n.x, n.y, n.z);
		glVertex3f(v.x, v.y, v.z);
		glNormal3f(n.x, n.y, n.z);
		glVertex3f(p.x, p.y, p.z);
		glEnd();

	}

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

void Surface::ComputeLaplacian()
{

	// Compute the discrete Laplacian field.
	int *nNeighbor = new int[nNode];
	Vector3f *laplacian = new Vector3f[nNode];
	memset(nNeighbor, 0, sizeof(int)*nNode);

	int id[3];
	Vector3f vec[3];
	float len_sum, wij;

	// Compute all triangle areas first.
	ComputeArea();

	for (int i = 0; i < nTriangle; i++){

		for (int m = 0; m<3; m++) id[m] = triangle[i].set[m];

		// Sum the triangle edge lengths.
		len_sum = (vertex[id[0]].coord - vertex[id[1]].coord).GetLength()
			+ (vertex[id[1]].coord - vertex[id[2]].coord).GetLength()
			+ (vertex[id[2]].coord - vertex[id[0]].coord).GetLength();


		// Accumulate the Laplacian term: L(vi) += wij * (vi - vj), where wij = |vi - vj| / L * S.
		// nNeighbor ends up as twice the adjacent-vertex count because each edge is processed in both directions.

		// v0 - v1
		wij = ((vertex[id[0]].coord - vertex[id[1]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[0]] += (vertex[id[0]].coord - vertex[id[1]].coord) * wij;

		// v0 - v2 
		wij = ((vertex[id[0]].coord - vertex[id[2]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[0]] += (vertex[id[0]].coord - vertex[id[2]].coord) * wij;

		// v0 receives two neighbor contributions.
		nNeighbor[id[0]] += 2;

		// v1 - v2 
		wij = ((vertex[id[1]].coord - vertex[id[2]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[1]] += (vertex[id[1]].coord - vertex[id[2]].coord) * wij;

		// v1 - v0
		wij = ((vertex[id[1]].coord - vertex[id[0]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[1]] += (vertex[id[1]].coord - vertex[id[0]].coord) * wij;

		// v1 receives two neighbor contributions.
		nNeighbor[id[1]] += 2;

		// v2 - v0  
		wij = ((vertex[id[2]].coord - vertex[id[0]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[2]] += (vertex[id[2]].coord - vertex[id[0]].coord) * wij;

		// v2 - v1 
		wij = ((vertex[id[2]].coord - vertex[id[1]].coord).GetLength()) / len_sum * triangle[i].area;
		laplacian[id[2]] += (vertex[id[2]].coord - vertex[id[1]].coord) * wij;

		// v0 receives two neighbor contributions.
		nNeighbor[id[2]] += 2;

	}
	
	// L(vi) = wi * sum, wi = 1/A (A: vonoroi area)
	// wij is not normalized by nNeighbor, so compensate here with wi.
	for (int i = 0; i < nNode; i++){
		vertex[i].laplacian = laplacian[i] / (float)nNeighbor[i];
		vertex[i].laplacian *= 1.0f / vertex[i].area;
	}

	delete[] laplacian;
	delete[] nNeighbor;



}

void Surface::ComputeLeastSquareMesh()
{

	int nTrans = 0;
	int *trans = new int[nNode];

	for (int i = 0; i < nNode; i++){
		if (vertex[i].isFreeze || vertex[i].isSelect){
			trans[nTrans] = i;
			nTrans++;
		}
	}

	if (A) Free2Dim(A);
	size_t matrixSize = static_cast<size_t>(nNode) * 3;
	A = Alloc2Dim(matrixSize, matrixSize);

	if (b) delete[] b;
	size_t vectorSize = static_cast<size_t>(nNode) * 3;
	b = (double*)calloc(vectorSize, sizeof(double));

	// A. Assemble the diagonal terms of A.

	for (int i = 0; i< nNode; i++)
	{
		// A[i][j] is the element at row j, column i in column-major storage.
		A[3 * i + 0][3 * i + 0] += 1;
		A[3 * i + 1][3 * i + 1] += 1;
		A[3 * i + 2][3 * i + 2] += 1;

		for (int j = 0; j<vertex[i].neighborVertex.size(); j++)
		{
			int num = vertex[i].neighborVertex[j];
			A[3 * num + 0][3 * num + 0] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
			A[3 * num + 1][3 * num + 1] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
			A[3 * num + 2][3 * num + 2] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
		}
	}


	// B. Assemble the off-diagonal terms of A.
	for (int i = 0; i< nNode; i++)
	{
		for (int j = 0; j< vertex[i].neighborVertex.size(); j++)
		{
			int num1 = vertex[i].neighborVertex[j];
			A[3 * i + 0][3 * num1 + 0] += -1.0f / (float)(vertex[i].neighborVertex.size());
			A[3 * i + 1][3 * num1 + 1] += -1.0f / (float)(vertex[i].neighborVertex.size());
			A[3 * i + 2][3 * num1 + 2] += -1.0f / (float)(vertex[i].neighborVertex.size());
			A[3 * num1 + 0][3 * i + 0] += -1.0f / (float)(vertex[i].neighborVertex.size());
			A[3 * num1 + 1][3 * i + 1] += -1.0f / (float)(vertex[i].neighborVertex.size());
			A[3 * num1 + 2][3 * i + 2] += -1.0f / (float)(vertex[i].neighborVertex.size());

			for (int k = 0; k< vertex[i].neighborVertex.size(); k++)
			{
				int num2 = vertex[i].neighborVertex[k];
				if (num1 == num2) continue;
				A[3 * num1 + 0][3 * num2 + 0] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
				A[3 * num1 + 1][3 * num2 + 1] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
				A[3 * num1 + 2][3 * num2 + 2] += 1.0f / (float)(vertex[i].neighborVertex.size() * vertex[i].neighborVertex.size());
			}
		}
	}

	for (int i = 0; i< nNode; i++)
	{
		for (int j = 0; j< nNode; j++)
		{
			/*			if(vertex[i].isInside == true && vertex[j].isInside == true)
			{
			A[3*i+0][3*j+0] *= gamma;
			A[3*i+0][3*j+1] *= gamma;
			A[3*i+0][3*j+2] *= gamma;
			A[3*i+1][3*j+0] *= gamma;
			A[3*i+1][3*j+1] *= gamma;
			A[3*i+1][3*j+2] *= gamma;
			A[3*i+2][3*j+0] *= gamma;
			A[3*i+2][3*j+1] *= gamma;
			A[3*i+2][3*j+2] *= gamma;
			}
			else
			{
			*/				
			A[3 * i + 0][3 * j + 0] *= omega;
			A[3 * i + 0][3 * j + 1] *= omega;
			A[3 * i + 0][3 * j + 2] *= omega;
			A[3 * i + 1][3 * j + 0] *= omega;
			A[3 * i + 1][3 * j + 1] *= omega;
			A[3 * i + 1][3 * j + 2] *= omega;
			A[3 * i + 2][3 * j + 0] *= omega;
			A[3 * i + 2][3 * j + 1] *= omega;
			A[3 * i + 2][3 * j + 2] *= omega;
		}
	}


	// C. Assemble the right-hand side vector b.
	for (int i = 0; i< nNode; i++)
	{
		for (int j = 0; j< vertex[i].neighborVertex.size(); j++)
		{
			int num = vertex[i].neighborVertex[j];
			b[3 * i + 0] += (1.0f / (float)vertex[num].neighborVertex.size()) * vertex[num].laplacian.x;
			b[3 * i + 1] += (1.0f / (float)vertex[num].neighborVertex.size()) * vertex[num].laplacian.y;
			b[3 * i + 2] += (1.0f / (float)vertex[num].neighborVertex.size()) * vertex[num].laplacian.z;
		}
		/*		if(vertex[i].isInside == true)
		{
		b[3*i+0] = -1.0f * gamma * (-vertex[i].laplacian.x + b[3*i+0]);
		b[3*i+1] = -1.0f * gamma * (-vertex[i].laplacian.y + b[3*i+1]);
		b[3*i+2] = -1.0f * gamma * (-vertex[i].laplacian.z + b[3*i+2]);
		}
		else
		{
		*/	
			b[3 * i + 0] = -1.0f * omega * (-vertex[i].laplacian.x + b[3 * i + 0]);
			b[3 * i + 1] = -1.0f * omega * (-vertex[i].laplacian.y + b[3 * i + 1]);
			b[3 * i + 2] = -1.0f * omega * (-vertex[i].laplacian.z + b[3 * i + 2]);
		//		}
	}


	// D. Add positional constraints to A.
	for (int i = 0; i<nTrans; i++)
	{
		A[3 * trans[i] + 0][3 * trans[i] + 0] += lambda;
		A[3 * trans[i] + 1][3 * trans[i] + 1] += lambda;
		A[3 * trans[i] + 2][3 * trans[i] + 2] += lambda;
	}

	// E. Add positional constraints to b.
	for (int i = 0; i<nTrans; i++)
	{
		b[3 * trans[i] + 0] += 1.0f * lambda * vertex[trans[i]].new_coord.x;
		b[3 * trans[i] + 1] += 1.0f * lambda * vertex[trans[i]].new_coord.y;
		b[3 * trans[i] + 2] += 1.0f * lambda * vertex[trans[i]].new_coord.z;
	}


	// Solve Ax = b and write the result to new_coord.
	int nOrder = nNode * 3;
	int flag;
	int *ipiv = new int[nOrder];

	// LU factorization
	DGETRF(&nOrder, &nOrder, &A[0][0], &nOrder, &ipiv[0], &flag);


	int		nInc = 1;
	double  dAlpha = 1.0;
	double  dBeta = 0.0;
	char cTrans = 'N';

	// Solve the linear system without iterative refinement.
	DGETRS(&cTrans, &nOrder, &nInc, &A[0][0], &nOrder, &ipiv[0], &b[0], &nOrder, &flag);

	for (int i = 0; i< nNode; i++)
	{
		vertex[i].new_coord.x = (float)b[3 * i + 0];
		vertex[i].new_coord.y = (float)b[3 * i + 1];
		vertex[i].new_coord.z = (float)b[3 * i + 2];
	}

	delete[] ipiv;
	delete[] trans;
}

void Surface::RenderColorMap(float min_d, float max_d)
{
	// Colormap for displacement magnitude
	Vector3f norm, coord, color;

	int value = 0;
	int step = 256;				// Color resolution
	float min_hue = 0.0f;		// Minimum hue value
	float max_hue = 255.0f;		// Maximum hue value



	for (int i = 0; i<nTriangle; i++)
	{
		glBegin(GL_TRIANGLES);
		for (int j = 0; j < 3; j++){
			norm = vertex[triangle[i].set[j]].new_normal;
			coord = vertex[triangle[i].set[j]].new_coord;
			glNormal3f(norm.x, norm.y, norm.z);


			vertex[triangle[i].set[j]].d = (vertex[triangle[i].set[j]].new_coord - vertex[triangle[i].set[j]].coord).GetLength();

			// Clamp values above max_d to the top color.
			if (vertex[triangle[i].set[j]].d > max_d) vertex[triangle[i].set[j]].d = max_d;

			// Map the displacement into the color ramp.
			value = (int)(((float)step - 1.0f) * (vertex[triangle[i].set[j]].d - min_d) / (max_d - min_d));
			color = GetColorValue(0, 240, step, value) * 0.8f;

			glColor3f(color.x, color.y, color.z);
			glVertex3f(coord.x, coord.y, coord.z);
		}
		glEnd();
	}
}

Vector3f Surface::GetColorValue(float min, float max, int step, int num)
{
	num = num % step;			// % returns the remainder.

	float hue = 240.0f - (max - min) / step * num + min;		// 240 maps to blue and 0 maps to red.
	return ChangeHSVToColor(hue, 1.0f, 1.0f);

}

Vector3f Surface::ChangeHSVToColor(float hue, float saturation, float value)
{
	int r =0, g = 0, b = 0;
	int region;
	float fraction;
	int min, max, up, down;
	/*
	while( hue>360.0f || hue<0.0f ){
	if(hue>=360.0f) hue-=360.0f;
	else if(hue<0.0f) hue+=360.0f;
	}
	*/

	while (hue>240.0f || hue<0.0f){			// Clamp hue to the supported range.
		if (hue >= 240.0f) hue = 240.0f;
		else if (hue<0.0f) hue = 0.0f;
	}


	if (saturation>1.0f) saturation = 1.0f;
	else if (saturation<0.0f) saturation = 0.0f;

	if (value>1.0f) value = 1.0f;
	else if (value<0.0f) value = 0.0f;

	max = (int)(value * 255);

	if (saturation == 0.0f){
		r = max;
		g = max;
		b = max;
	}
	else{
		region = (int)(hue / 60.0f);
		fraction = hue / 60.0f - region;
		min = (int)(max*(1.0f - saturation));
		up = min + (int)(fraction*max*saturation);
		down = max - (int)(fraction*max*saturation);

		switch (region){
		case 0:r = max; g = up; b = min; break;	// red -> yellow
		case 1:r = down; g = max; b = min; break;	// yellow -> green
		case 2:r = min; g = max; b = up; break;	// green -> cyan
		case 3:r = min; g = down; b = max; break;	// cyan -> blue
		case 4:r = up; g = min; b = max; break;	// blue -> magenta
		case 5:r = max; g = min; b = down; break;	// magenta -> red
		}
	}

	return Vector3f(r / 256.0f, g / 256.0f, b / 256.0f);

}