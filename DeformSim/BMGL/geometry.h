/////////////////////////////////////////////////////////////////////////////
//
// geometry.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _GEOMETRY_H_
#define _GEOMETRY_H_

#include "vector.h"

class Vertex			// Vertex class
{

public:	
	bool isSurface;		// surface or not
	bool isFreeze;		// freeze or not
	bool isSelect;		// selected or not

	vector<int> neighborVertex;		// indexes for neighboring vertices
	
	Vector3f coord, cur_coord, ini_coord, new_coord;	// coordinate
	Vector3f normal, new_normal;						// normal vector
	Vector3f laplacian, d_laplacian;					// laplacian vector
	Vector3f vel, new_vel;								// velocity
	Vector3f acc, new_acc;								// acceleration
	Vector3f force, new_force;							// force

	int obj_id;						// corresponding object id
	int vertex_id;					// corresponding vertex id
	int tetra_id;					// corresponding tetrahedral element id
	Vector3f tetra_coord;			// barycentric coordinate

	Vector3f target;
	float e;
	float d;
	float d_;
	float w;

	float area, new_area;			// area of vertex
	float stress;

	Vertex();
	~Vertex();

	void InitNeighborVertex(int num);


};


class Line				// Line class
{

public:
	int set[2];			// indexes for vertex components
	float length;		// line length

	Line();

};


class Triangle			// Triangle class 
{

public:
	int set[3];			// indexes for vertex components
	Vector3f center;	// center
	float area;			// area

	Vector3f normal, new_normal;

	Triangle();

};


class Tetrahedron		// Tetrahedron class
{

public:
	int set[4];					// indexes for vertex components

	float volume;				// volume
	float young;				// young modulus (MPa)
	float poisson;				// poisson ratio
	float stress;				// Mises stress (MPa)
	double **Ke;				// element stiffness matrix
	double **Se;				// element stress matrix

	Tetrahedron();

};


#endif