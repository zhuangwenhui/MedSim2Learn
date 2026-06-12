/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _OBJECT_H_
#define _OBJECT_H_

#include "vector.h"
#include "matrix.h"
#include "geometry.h"
#define TETLIBRARY
#include "tetgen.h"

class Object
{

public:
	int type;
	BOOL isDispVertex;
	BOOL isDispLine;
	BOOL isDispSurface;
	BOOL isDispVolume;

	int nNode;			// the number of vertices
	int nLine;			// the number of lines
	int nTriangle;		// the number of triangles 
	int nTetra;			// the number of tetrahedra

	Vertex *vertex;			// vertices
	Line *line;				// lines
	Triangle *triangle;		// triangles
	Tetrahedron *tetra;		// tetrahedra

	Vector3f min;		// bounding box min
	Vector3f max;		// bounding box max
	Vector3f center;	// bounding box center
	float area;			// surface area
	float volume;		// volume 

	double omega;
	double lambda;


	int m_count;
	bool flag;
	bool useDirectSolver;

	Object();
	~Object();
	Object(const Object&) = delete;
	Object& operator=(const Object&) = delete;
	Object(Object&&) = delete;
	Object& operator=(Object&&) = delete;

	void InitVertex(int a){ if (vertex) delete[] vertex; nNode = a;  vertex = new Vertex[nNode]; }
	void InitLine(int a){ if (line) delete[] line; nLine = a; line = new Line[nLine]; }
	void InitTriangle(int a){ if (triangle) delete[] triangle; nTriangle = a; triangle = new Triangle[nTriangle]; }
	void InitTetrahedron(int a){ if (tetra) delete[] tetra; nTetra = a; tetra = new Tetrahedron[nTetra]; }

	bool ReadObject(const std::string& filepath);
	bool WriteObject(const std::string& filepath);
	bool WritePLY(const std::string& filepath);
	void Clear();

	void ComputeTetrahedralMesh();
	void ComputeQualityTetrahedralMesh(char str[]);

	void ComputeBoundingBox();
	void ComputeNeighbors();
	void ComputeNormal();
	void ComputeArea();
	void ComputeVolume();


	bool ComputeMatrixK(void);
	bool Deform();
	bool CloneMatrixStateFrom(const Object& source);
	void ReleaseAssemblyScratch();
	void ReleaseSolverState();


	bool CheckSelfIntersection();
	bool CheckInOutSurface(Vector3f pos);
	void Smooth(float r);

private:
	int nMatrixNode;		// the number of vertices in matrix
	int *matrixNode;		// vertex index list in matrix
	int *checkList;			// fransfer table from vertex index to matrix element index
	int *luPivot;			// pivot array for LU direct solve
	bool solverStateShared;	// L/luPivot borrowed from the matrix template (not owned)
	double **K;				// stiffness matrix
	double **L;				// inverse K matrix

	double *f;				// force
	double *u;				// displacement

	double **A;				// Matrix for least square surface
	double *b;				// vector for least square surface

	int *tetraIndex;
	Vector3f *tetraPos;

	double **Alloc2Dim(int nRows, int nColumns);
	void Free2Dim(double **x){ free(x[0]); free(x); }
	void ComputeMatrixD(double **D, double E, double v);
	void ComputeMatrixB(double **B, double &detJ, int num);
	void ComputeMatrixT(Matrix4x4 &T, int num);
	bool ComputeMatrixKe(int num);

};


#endif
