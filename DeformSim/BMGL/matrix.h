/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _MATRIX_H_
#define _MATRIX_H_

#include "stdafx.h"
#include "vector.h"


class Matrix3x3		// 3 by 3 matrix
{

public:
	float m[3][3];		// m[row][column]

	Matrix3x3();
	Matrix3x3(float r[3][3]);
	Matrix3x3(float r[9]);
	Matrix3x3(double r[9]);
	Matrix3x3(float t00, float t01, float t02,
			  float t10, float t11, float t12,
			  float t20, float t21, float t22);

	Matrix3x3 operator+(Matrix3x3 mat);
	Matrix3x3 operator-(Matrix3x3 mat);
	Matrix3x3 operator*(Matrix3x3 mat);
	Vector3f operator*(Vector3f vec);

	void Identity();
	void SetMatrix(float r[3][3]);
	void SetMatrix(float r[9]);
	void SetMatrix(double r[9]);
	void SetMatrix(float t00, float t01, float t02,
				   float t10, float t11, float t12,
				   float t20, float t21, float t22);

	void SetRotateMatrix(float a, Vector3f vec);
	void SetScaleMatrix(Vector3f vec);
	void Transpose();
	bool Inverse();

};


class Matrix4x4		// 4 by 4 matrix
{

public:
	float m[4][4];		// m[row][column]

	Matrix4x4();
	Matrix4x4(float r[4][4]);
	Matrix4x4(float r[16]);
	Matrix4x4(double r[16]);
	Matrix4x4(float t00, float t01, float t02, float t03,
			  float t10, float t11, float t12, float t13,
			  float t20, float t21, float t22, float t23,
			  float t30, float t31, float t32, float t33);

	Matrix4x4 operator+(Matrix4x4 mat);
	Matrix4x4 operator-(Matrix4x4 mat);
	Matrix4x4 operator*(Matrix4x4 mat);
	Vector4f operator*(Vector4f vec);

	void Identity();
	void SetMatrix(float r[4][4]);
	void SetMatrix(float r[16]);
	void SetMatrix(float t00, float t01, float t02, float t03,
				   float t10, float t11, float t12, float t13,
				   float t20, float t21, float t22, float t23,
				   float t30, float t31, float t32, float t33);

	void SetRotateMatrix(float a, Vector3f vec);
	void SetScaleMatrix(Vector3f vec);
	void SetTranslateMatrix(Vector3f vec);

	Vector3f GetTranslateVector() const;
	Matrix3x3 GetRotateMatrix() const;

	void Transpose();
	bool Inverse();

};


class MatrixMxN		// M by N matrix
{
public:
	int nRows;		// Row count (height)
	int nColumns;	// Column count (width)

	double *m;		// Elements stored in column-major order; element (i, j) is j * nRows + i.
	double *w;		// Eigenvalues

	MatrixMxN(){ nRows = 0; nColumns = 0; m = 0; w = 0; };
	MatrixMxN(int a, int b) {
		nRows = a;
		nColumns = b;
		size_t totalElements = static_cast<size_t>(a) * static_cast<size_t>(b);
		m = (double*)calloc(totalElements, sizeof(double));
		w = (double*)calloc(static_cast<size_t>(a), sizeof(double));
	};
	MatrixMxN(const MatrixMxN &mat);
	~MatrixMxN(){ Clear(); };

	void Init(int nRow, int nColumn);
	void Clear();

	MatrixMxN &operator=(MatrixMxN mat);	// matrix substitution
	MatrixMxN operator+(MatrixMxN mat);		// matrix addition
	MatrixMxN &operator+=(MatrixMxN mat);	// matrix addition
	MatrixMxN operator-(MatrixMxN mat);		// matrix subtraction
	MatrixMxN &operator-=(MatrixMxN mat);	// matrix subtraction
	MatrixMxN operator*(MatrixMxN mat);		// matrix - matrix multiplication
	VectorNf operator*(VectorNf x);			// matrix - vector multiplication
	MatrixMxN operator*(double a);			// matrix - scalar multiplication
	MatrixMxN &operator*=(double a);		// matrix - scalar multiplication
	MatrixMxN operator/(double a);			// matrix - scalar division
	MatrixMxN &operator/=(double a);		// matrix - scalar division

	bool operator!=(MatrixMxN vec);
	bool operator==(MatrixMxN vec);
	
	void SetValue(int i, int j, double a);	// Set the value at (i, j).
	double GetValue(int i, int j) const;	// Get the value at (i, j).
	VectorNf GetRowVector(int i);			// Return row i as a vector.
	VectorNf GetColumnVector(int j);		// Return column j as a vector.

	void Transpose();						// Transpose the matrix.
	void Inverse();							// Invert the matrix.

	double GetFrobeniusNorm() const;				// Return the Frobenius norm.


};

#endif