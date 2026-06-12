/////////////////////////////////////////////////////////////////////////////
//
// surface.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M. Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _SURFACE_H_
#define _SURFACE_H_

#include "stdafx.h"

#include "vector.h"
#include "matrix.h"
#include "geometry.h"

class Surface
{

public:
	int nNode;					// the number of vertices
	int nTriangle;				// the number of triangles

	vector<Vertex> vertex;		// vertices 
	vector<Triangle> triangle;	// triangles

	int *tetraIndex;
	Vector3f *tetraPos;
	Vector4f color;

	Vector3f min;		// bounding box min
	Vector3f max;		// bounding box max
	Vector3f center;	// bounding box center
	float area;			// surface area

	Matrix3x3 rot;		// rotation

	double **A;			// Matrix for least square surface
	double *b;			// vector for least square surface
	double omega;
	double lambda;

	Surface();
	~Surface();

	bool ReadPLY(const std::string& filepath);
	bool WritePLY(const std::string& filepath);
	void Clear();

	void ComputeBoundingBox();
	void ComputeNeighbors();
	void ComputeNormal();
	void ComputeArea();

	void SmoothSurface(float r);
	void ResampleVertex(float r);


	double **Alloc2Dim(int nRows, int nColumns);
	void Free2Dim(double **x){ if (NULL == x){ return; } free(x[0]); free(x); x = NULL; }

};


#endif