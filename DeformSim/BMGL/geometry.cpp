/////////////////////////////////////////////////////////////////////////////
//
// geometry.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "geometry.h"


Vertex::Vertex()
{
	isSurface = false;
	isFreeze = false;
	isSelect = false;

	neighborVertex.clear();

	obj_id = 0;
	vertex_id = 0;
	tetra_id = 0;
	e = 0.0f;
	d = 0.0f;
	d_ = 0.0f;
	w = 0.0f;
	stress = 0.0f;

	area = 0.0f;
	new_area = 0.0f;
}

Vertex::~Vertex()
{
	neighborVertex.clear();
}

Line::Line()
{
	set[0] = 0;
	set[1] = 0;

	length = 0.0f;
}

Triangle::Triangle()
{
	set[0] = 0;
	set[1] = 0;
	set[2] = 0;

	area = 0.0f;
}

Tetrahedron::Tetrahedron()
{
	set[0] = 0;
	set[1] = 0;
	set[2] = 0;
	set[3] = 0;


	Ke = 0;
	Se = 0;

	// Typical Poisson ratio test range: 0.10 to 0.45 (maximum 0.5).
	young = 1.0f;
	poisson = 0.40f;
	volume = 0.0f;
	stress = 0.0f;
}

void Vertex::InitNeighborVertex(int num)
{
	neighborVertex.clear();
	neighborVertex.reserve(num);  // reserve memory for the number of neighbor vertices
}
