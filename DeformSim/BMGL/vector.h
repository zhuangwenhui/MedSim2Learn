/////////////////////////////////////////////////////////////////////////////
//
// vector.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////


#ifndef _VECTOR_H_
#define _VECTOR_H_

#include "stdafx.h"

class Vector2f  // 2D vector class
{

public:
	float x,y;

	Vector2f(){ x=0.0f; y=0.0f;};
	Vector2f(float a, float b){ x=a; y=b;};
	Vector2f(float a[]){ x=a[0]; y=a[1];};

	Vector2f operator+(Vector2f vec){ return Vector2f(x+vec.x, y+vec.y); };		// vector addition
	Vector2f &operator+=(Vector2f vec){ x+=vec.x; y+=vec.y; return *this; };	// vector addition
	Vector2f operator+(float a){ return Vector2f(x+a, y+a); };					// scalar addition
	Vector2f &operator+=(float a){ x+=a; y+=a; return *this; };					// scalar addition
	Vector2f operator-(Vector2f vec){ return Vector2f(x-vec.x, y-vec.y); };		// vector subtraction
	Vector2f &operator-=(Vector2f vec){ x-=vec.x; y-=vec.y; return *this; };	// vector subtraction
	float operator*(Vector2f vec){ return x*vec.x+y*vec.y; };					// dot product
	Vector2f operator*(float a){ return Vector2f(x*a, y*a); };					// scalar multiplication
	Vector2f &operator*=(float a){ x*=a; y*=a; return *this; };					// scalar multiplication
	Vector2f operator/(float a){ return Vector2f(x/a, y/a); };					// scalar division
	Vector2f &operator/=(float a){ x/=a; y/=a; return *this; };					// scalar division

	void Init(){ SetVector(0.0f, 0.0f); };
	void SetVector(float a, float b){ x=a; y=b;};
	float GetLength() const { return (float)sqrt(x*x+y*y); };	
	float GetLength2() const { return x*x+y*y; };	
	bool Normalize(){ float l = GetLength(); if(l != 0){ SetVector(x/l, y/l); return 1;} else { SetVector(0,0); return 0;} };

};


class Vector3f	// 3D vector class
{

public:
	float x,y,z;

	Vector3f(){ x = 0.0f; y = 0.0f; z = 0.0f;};
	Vector3f(float a, float b, float c){ x=a; y=b; z=c; };
	Vector3f(float a[]){ x = a[0]; y=a[1]; z=a[2];};

	Vector3f operator+(Vector3f vec){ return Vector3f(x+vec.x, y+vec.y, z+vec.z); };	// vector addition
	Vector3f &operator+=(Vector3f vec){ x+=vec.x; y+=vec.y; z+=vec.z; return *this; };	// vector addition
	Vector3f operator+(float a){ return Vector3f(x+a, y+a, z+a); };						// scalar addition
	Vector3f &operator+=(float a){ x+=a; y+=a; z+=a; return *this; };					// scalar addition
	Vector3f operator-(Vector3f vec){ return Vector3f(x-vec.x, y-vec.y, z-vec.z); };	// vector subtraction
	Vector3f &operator-=(Vector3f vec){ x-=vec.x; y-=vec.y; z-=vec.z; return *this; };	// vector subtraction
	float operator*(Vector3f vec){ return x*vec.x+y*vec.y+z*vec.z; };					// dot product
	Vector3f operator*(float a){ return Vector3f(x*a, y*a, z*a); };						// scalar multiplication
	Vector3f &operator*=(float a){ x*=a; y*=a; z*=a; return *this; };					// scalar multiplication
	Vector3f operator/(float a){ return Vector3f(x/a, y/a, z/a); };						// scalar division
	Vector3f &operator/=(float a){ x/=a; y/=a; z/=a; return *this; };					// scalar division
	Vector3f operator^(Vector3f vec){ return Vector3f(y*vec.z-z*vec.y, z*vec.x-x*vec.z, x*vec.y-y*vec.x); };	// cross product
	bool operator!=(Vector3f vec){ return x == vec.x && y == vec.y && z == vec.z; };
	bool operator==(Vector3f vec){ return x == vec.x && y == vec.y && z == vec.z; };
	bool operator<(float a){ return (x < a && y < a && z < a); };
	bool operator>(float a){ return (x > a && y > a && z > a); };
	float &operator[](int a){ if(a==0) return x; else if (a==1) return y; else return z; };

	void Init(){ SetVector(0.0f, 0.0f, 0.0f); };
	void SetVector(float a, float b, float c){ x=a; y=b; z=c;};
	float GetLength() const { return (float)sqrt(x*x+y*y+z*z); };				
	float GetLength2() const { return x*x+y*y+z*z; };	
	float DotProduct(Vector3f vec1){ return (*this)*vec1; };
	Vector3f CrossProduct(Vector3f vec1){ return (*this)^vec1; };

	bool Normalize(){ float l=GetLength(); if(l != 0)	{ SetVector(x/l, y/l, z/l); return 1; } else { SetVector(0,0,0); return 0; } }
	Vector3f SurfaceProjection(Vector3f normal, Vector3f coord);

};


class Vector4f	// 4D vector class
{

public:
	float x, y, z, r;

	Vector4f(){ x=0.0f; y=0.0f; z=0.0f; r=0.0f; }
	Vector4f(float a, float b, float c, float d) { x=a; y=b; z=c; r=d; }
	Vector4f(float a[]) { x=(float)a[0]; y=(float)a[1]; z=(float)a[2]; r=(float)a[3]; }

	Vector4f operator+(Vector4f vec){ return Vector4f(x+vec.x, y+vec.y, z+vec.z, r+vec.r); };		// vector addition
	Vector4f &operator+=(Vector4f vec){ x+=vec.x; y+=vec.y; z+=vec.z; r+=vec.r; return *this; };	// vector addition
	Vector4f operator+(float a){ return Vector4f(x+a, y+a, z+a, r+a); };							// scalar addition
	Vector4f &operator+=(float a){ x+=a; y+=a; z+=a; r+=a; return *this; };							// scalar addition
	Vector4f operator-(Vector4f vec){ return Vector4f(x-vec.x, y-vec.y, z-vec.z,r-vec.r); };		// vector subtraction
	Vector4f &operator-=(Vector4f vec){ x-=vec.x; y-=vec.y; z-=vec.z; r-=vec.r; return *this; };	// vector subtraction
	float operator*(Vector4f vec){ return x*vec.x+y*vec.y+z*vec.z+r*vec.r; };						// dot product
	Vector4f operator*(float a){ return Vector4f(x*a, y*a, z*a, r*a); };							// scalar multiplication
	Vector4f &operator*=(float a){ x*=a; y*=a; z*=a; r*=a; return *this; };							// scalar multiplication
	Vector4f operator/(float a){ return Vector4f(x/a, y/a, z/a, r/a); };							// scalar division
	Vector4f &operator/=(float a){ x/=a; y/=a; z/=a; r/=a; return *this; };							// scalar division

	void Init(){ SetVector(0.0f, 0.0f, 0.0f, 0.0f); };
	void SetVector(float a, float b, float c, float d){ x=a; y=b; z=c; r=d; };

	float GetLength() const { return (float)sqrt(x*x + y*y + z*z + r*r); };
	float GetLength2() const { return x*x + y*y + z*z; };

};


class VectorNf	// N dimensional vector class
{
public:
	int nDims;		// dimension
	double *m;		// elements

	VectorNf(){ nDims = 0; m = 0; };
	VectorNf(int n){ nDims = n; m = (double *)calloc(nDims, sizeof(double)); };
	VectorNf(int n, double *a){ nDims = n; 	memcpy(m, a, nDims * sizeof(double)); };
	VectorNf(const VectorNf &vec);
	~VectorNf() { Clear(); };

	VectorNf &operator=(VectorNf vec);		// vector substitution
	VectorNf operator+(VectorNf vec);		// vector addition
	VectorNf &operator+=(VectorNf vec);		// vector addition
	VectorNf operator+(double a);			// scalar addition
	VectorNf &operator+=(double a);			// scalar addition
	VectorNf operator-(VectorNf vec);		// vector subtraction
	VectorNf &operator-=(VectorNf vec);		// vector subtraction
	VectorNf operator-(double a);			// scalar subtraction
	VectorNf &operator-=(double a);			// scalar subtraction

	double operator*(VectorNf vec);			// dot product
	VectorNf operator*(double a);			// scalar multiplication
	VectorNf &operator*=(double a);			// scalar multiplication
	VectorNf operator/(double a);			// scalar division
	VectorNf &operator/=(double a);			// scalar division

	bool operator!=(VectorNf vec);
	bool operator==(VectorNf vec);

	void Init(int n);
	void Init(int n, double *a);
	void Clear();

	double GetLength() const;
	double GetLength2() const;

};

#endif