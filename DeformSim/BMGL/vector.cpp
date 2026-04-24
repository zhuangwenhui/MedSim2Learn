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


VectorNf::VectorNf(const VectorNf &vec)
{
	// Copy constructor
	nDims = vec.nDims;
	m = (double *)calloc(nDims, sizeof(double));
	if (m && vec.m) {
		memcpy(m, vec.m, nDims * sizeof(double));
	}
}

void VectorNf::Init(int n)
{
	// Initialize storage
	Clear();

	nDims = n;
	m = (double *)calloc(nDims, sizeof(double));
}

void VectorNf::Init(int n, double *a)
{
	// Initialize with explicit element values
	Clear();

	nDims = n;
	memcpy(m, a, nDims * sizeof(double));
}

void VectorNf::Clear()
{
	// Release storage
	free(m);
	m = 0;
	nDims = 0;
}


VectorNf &VectorNf::operator=(VectorNf vec)
{
	Clear();

	nDims = vec.nDims;
	m = (double *)calloc(nDims, sizeof(double));
	if (m && vec.m) {
		memcpy(m, vec.m, nDims * sizeof(double));
	}

	return *this;
}

VectorNf VectorNf::operator+(VectorNf vec)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] + vec.m[i];
	}

	return v;
}

VectorNf &VectorNf::operator+=(VectorNf vec)
{
	for (int i = 0; i < nDims; i++){
		m[i] += vec.m[i];
	}

	return *this;
}

VectorNf VectorNf::operator+(double a)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] + a;
	}

	return v;
}

VectorNf &VectorNf::operator+=(double a)
{
	for (int i = 0; i < nDims; i++){
		m[i] += a;
	}

	return *this;
}


VectorNf VectorNf::operator-(VectorNf vec)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] - vec.m[i];
	}

	return v;

}

VectorNf &VectorNf::operator-=(VectorNf vec)
{
	for (int i = 0; i < nDims; i++){
		m[i] -= vec.m[i];
	}

	return *this;
}

VectorNf VectorNf::operator-(double a)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] - a;
	}

	return v;
}

VectorNf &VectorNf::operator-=(double a)
{
	for (int i = 0; i < nDims; i++){
		m[i] -= a;
	}

	return *this;
}


double VectorNf::operator*(VectorNf vec)
{
	double d = 0.0;
	for (int i = 0; i < nDims; i++){
		d += m[i] * vec.m[i];
	}

	return d;

}

VectorNf VectorNf::operator*(double a)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] * a;
	}

	return v;
}

VectorNf &VectorNf::operator*=(double a)
{
	for (int i = 0; i < nDims; i++){
		m[i] *= a;
	}

	return *this;
}

VectorNf VectorNf::operator/(double a)
{
	VectorNf v(nDims);

	for (int i = 0; i < nDims; i++){
		v.m[i] = m[i] / a;
	}

	return v;
}

VectorNf &VectorNf::operator/=(double a)
{
	for (int i = 0; i < nDims; i++){
		m[i] /= a;
	}

	return *this;
}


bool VectorNf::operator!=(VectorNf vec)
{
	for (int i = 0; i < nDims; i++){
		if (m[i] != vec.m[i]) return true;
	}

	return false;

}

bool VectorNf::operator==(VectorNf vec)
{
	for (int i = 0; i < nDims; i++){
		if (m[i] != vec.m[i]) return false;
	}

	return true;
}

double VectorNf::GetLength() const
{
	double len = 0.0;

	for (int i = 0; i < nDims; i++){
		len += m[i] * m[i];
	}

	return sqrt(len);

}


double VectorNf::GetLength2() const
{
	double len = 0.0;

	for (int i = 0; i < nDims; i++){
		len += m[i] * m[i];
	}

	return len;

}

