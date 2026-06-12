/////////////////////////////////////////////////////////////////////////////
//
// vector.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "vector.h"

Vector3f Vector3f::SurfaceProjection(Vector3f normal, Vector3f coord)		
{
	// Project this vertex to the surface
	// normal = surface normal, coord = arbitrary 3D point on the surface
	Vector3f vec;
	float distance;
	distance = normal * (*this - coord);
	vec = *this - normal * distance;
	return vec;
}

