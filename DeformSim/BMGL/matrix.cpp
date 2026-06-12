/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "matrix.h"


Matrix3x3::Matrix3x3()
{
	for (int i = 0; i<3; i++)
		for (int j = 0; j<3; j++) {
			if (i == j) m[i][j] = 1; else m[i][j] = 0;
		}
}

Matrix3x3::Matrix3x3(float r[3][3])
{
	memcpy(m, r, 9 * sizeof(float));
}

Matrix3x3::Matrix3x3(float r[9])
{
	m[0][0] = r[0]; m[0][1] = r[1]; m[0][2] = r[2];
	m[1][0] = r[3]; m[1][1] = r[4]; m[1][2] = r[5];
	m[2][0] = r[6]; m[2][1] = r[7]; m[2][2] = r[8];
}

Matrix3x3::Matrix3x3(double r[9])
{
	m[0][0] = (float)r[0]; m[0][1] = (float)r[1]; m[0][2] = (float)r[2];
	m[1][0] = (float)r[3]; m[1][1] = (float)r[4]; m[1][2] = (float)r[5];
	m[2][0] = (float)r[6]; m[2][1] = (float)r[7]; m[2][2] = (float)r[8];
}

Matrix3x3::Matrix3x3(float t00, float t01, float t02, float t10, float t11, float t12, float t20, float t21, float t22)
{
	m[0][0] = t00; m[0][1] = t01; m[0][2] = t02;
	m[1][0] = t10; m[1][1] = t11; m[1][2] = t12;
	m[2][0] = t20; m[2][1] = t21; m[2][2] = t22;
}

Matrix3x3 Matrix3x3::operator+(Matrix3x3 mat)
{
	// Matrix-matrix addition
	return Matrix3x3(m[0][0] + mat.m[0][0], m[0][1] + mat.m[0][1], m[0][2] + mat.m[0][2],
		m[1][0] + mat.m[1][0], m[1][1] + mat.m[1][1], m[1][2] + mat.m[1][2],
		m[2][0] + mat.m[2][0], m[2][1] + mat.m[2][1], m[2][2] + mat.m[2][2]);
}

Matrix3x3 Matrix3x3::operator-(Matrix3x3 mat)
{
	// Matrix-matrix subtraction
	return Matrix3x3(m[0][0] - mat.m[0][0], m[0][1] - mat.m[0][1], m[0][2] - mat.m[0][2],
		m[1][0] - mat.m[1][0], m[1][1] - mat.m[1][1], m[1][2] - mat.m[1][2],
		m[2][0] - mat.m[2][0], m[2][1] - mat.m[2][1], m[2][2] - mat.m[2][2]);
}

Matrix3x3 Matrix3x3::operator*(Matrix3x3 mat)
{
	// Matrix-matrix multiplication
	Matrix3x3 rmat;
	for (int i = 0; i < 3; i++)
		for (int j = 0; j < 3; j++)
			rmat.m[i][j] = m[i][0] * mat.m[0][j] + m[i][1] * mat.m[1][j] + m[i][2] * mat.m[2][j];

	return rmat;
}

Vector3f Matrix3x3::operator*(Vector3f vec)
{
	// Matrix-vector multiplication
	return Vector3f(m[0][0] * vec.x + m[0][1] * vec.y + m[0][2] * vec.z,
		m[1][0] * vec.x + m[1][1] * vec.y + m[1][2] * vec.z,
		m[2][0] * vec.x + m[2][1] * vec.y + m[2][2] * vec.z);

}

void Matrix3x3::Identity()
{
	for (int i = 0; i<3; i++)
		for (int j = 0; j<3; j++) {
			if (i == j) m[i][j] = 1; else m[i][j] = 0;
		}
}

void Matrix3x3::SetMatrix(float r[3][3])
{
	memcpy(m, r, 9 * sizeof(float));
}


void Matrix3x3::SetMatrix(float r[9])
{
	m[0][0] = r[0]; m[0][1] = r[1]; m[0][2] = r[2];
	m[1][0] = r[3]; m[1][1] = r[4]; m[1][2] = r[5];
	m[2][0] = r[6]; m[2][1] = r[7]; m[2][2] = r[8];
}

void Matrix3x3::SetMatrix(double r[9])
{
	m[0][0] = (float)r[0]; m[0][1] = (float)r[1]; m[0][2] = (float)r[2];
	m[1][0] = (float)r[3]; m[1][1] = (float)r[4]; m[1][2] = (float)r[5];
	m[2][0] = (float)r[6]; m[2][1] = (float)r[7]; m[2][2] = (float)r[8];
}

void Matrix3x3::SetMatrix(float t00, float t01, float t02, float t10, float t11, float t12, float t20, float t21, float t22)
{
	m[0][0] = t00; m[0][1] = t01; m[0][2] = t02;
	m[1][0] = t10; m[1][1] = t11; m[1][2] = t12;
	m[2][0] = t20; m[2][1] = t21; m[2][2] = t22;
}

void Matrix3x3::SetRotateMatrix(float a, Vector3f vec)
{
	// a: angle (degree), vec: axis for rotation
	a = a*3.1415f / 180.0f;	// degree to radian

	if (vec.GetLength() == 0) {
		Identity();
	}
	else {
		vec.Normalize();
		SetMatrix((1 - cos(a))*vec.x*vec.x + cos(a), vec.x*vec.y*(1 - cos(a)) + vec.z*sin(a), vec.x*vec.z*(1 - cos(a)) - vec.y*sin(a),
			vec.x*vec.y*(1 - cos(a)) - vec.z*sin(a), (1 - cos(a))*vec.y*vec.y + cos(a), vec.y*vec.z*(1 - cos(a)) + vec.x*sin(a),
			vec.x*vec.z*(1 - cos(a)) + vec.y*sin(a), vec.y*vec.z*(1 - cos(a)) - vec.x*sin(a), (1 - cos(a))*vec.z*vec.z + cos(a));
	}

}

void Matrix3x3::SetScaleMatrix(Vector3f vec)
{
	SetMatrix(vec.x, 0, 0,
		0, vec.y, 0,
		0, 0, vec.z);
}

Vector3f Matrix4x4::GetTranslateVector() const
{
	Vector3f vec;
	vec.SetVector(m[0][3], m[1][3], m[2][3]);
	return vec;
}


Matrix3x3 Matrix4x4::GetRotateMatrix() const
{
	Matrix3x3 mat;
	mat.SetMatrix(m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2]);
	return mat;
}


void Matrix3x3::Transpose()
{
	for (int i = 0; i<3; i++)
		for (int j = 0; j<i; j++)
			swap(m[i][j], m[j][i]);
}

bool Matrix3x3::Inverse()
{
	float a[3][3] = {};

	a[0][0] = m[1][1] * m[2][2] - m[1][2] * m[2][1]; a[0][1] = m[2][1] * m[0][2] - m[2][2] * m[0][1]; a[0][2] = m[0][1] * m[1][2] - m[0][2] * m[1][1];
	a[1][0] = m[1][2] * m[2][0] - m[1][0] * m[2][2]; a[1][1] = m[2][2] * m[0][0] - m[2][0] * m[0][2]; a[1][2] = m[0][2] * m[1][0] - m[0][0] * m[1][2];
	a[2][0] = m[1][0] * m[2][1] - m[1][1] * m[2][0]; a[2][1] = m[2][0] * m[0][1] - m[2][1] * m[0][0]; a[2][2] = m[0][0] * m[1][1] - m[0][1] * m[1][0];

	float det = m[0][0] * a[0][0] + m[1][0] * a[0][1] + m[2][0] * a[0][2];
	if (det == 0.0f) { return false; }


	m[0][0] = a[0][0] / det;	m[0][1] = a[0][1] / det; m[0][2] = a[0][2] / det;
	m[1][0] = a[1][0] / det;  m[1][1] = a[1][1] / det; m[1][2] = a[1][2] / det;
	m[2][0] = a[2][0] / det;  m[2][1] = a[2][1] / det; m[2][2] = a[2][2] / det;

	return true;

}

Matrix4x4::Matrix4x4()
{
	for (int i = 0; i<4; i++)
		for (int j = 0; j<4; j++) {
			if (i == j) m[i][j] = 1; else m[i][j] = 0;
		}
}

Matrix4x4::Matrix4x4(float r[4][4])
{
	memcpy(m, r, 16 * sizeof(float));
}


Matrix4x4::Matrix4x4(float r[16])
{
	m[0][0] = r[0]; m[0][1] = r[1]; m[0][2] = r[2]; m[0][3] = r[3];
	m[1][0] = r[4]; m[1][1] = r[5]; m[1][2] = r[6]; m[1][3] = r[7];
	m[2][0] = r[8]; m[2][1] = r[9]; m[2][2] = r[10]; m[2][3] = r[11];
	m[3][0] = r[12]; m[3][1] = r[13]; m[3][2] = r[14]; m[3][3] = r[15];
}


Matrix4x4::Matrix4x4(double r[16])
{
	m[0][0] = (float)r[0]; m[0][1] = (float)r[1]; m[0][2] = (float)r[2]; m[0][3] = (float)r[3];
	m[1][0] = (float)r[4]; m[1][1] = (float)r[5]; m[1][2] = (float)r[6]; m[1][3] = (float)r[7];
	m[2][0] = (float)r[8]; m[2][1] = (float)r[9]; m[2][2] = (float)r[10]; m[2][3] = (float)r[11];
	m[3][0] = (float)r[12]; m[3][1] = (float)r[13]; m[3][2] = (float)r[14]; m[3][3] = (float)r[15];
}


Matrix4x4::Matrix4x4(float t00, float t01, float t02, float t03,
	float t10, float t11, float t12, float t13,
	float t20, float t21, float t22, float t23,
	float t30, float t31, float t32, float t33)
{
	m[0][0] = t00; m[0][1] = t01; m[0][2] = t02; m[0][3] = t03;
	m[1][0] = t10; m[1][1] = t11; m[1][2] = t12; m[1][3] = t13;
	m[2][0] = t20; m[2][1] = t21; m[2][2] = t22; m[2][3] = t23;
	m[3][0] = t30; m[3][1] = t31; m[3][2] = t32; m[3][3] = t33;
}


Matrix4x4 Matrix4x4::operator+(Matrix4x4 mat)
{
	// Matrix-matrix addition
	return Matrix4x4(m[0][0] + mat.m[0][0], m[0][1] + mat.m[0][1], m[0][2] + mat.m[0][2], m[0][3] + mat.m[0][3],
		m[1][0] + mat.m[1][0], m[1][1] + mat.m[1][1], m[1][2] + mat.m[1][2], m[1][3] + mat.m[1][3],
		m[2][0] + mat.m[2][0], m[2][1] + mat.m[2][1], m[2][2] + mat.m[2][2], m[2][3] + mat.m[2][3],
		m[3][0] + mat.m[3][0], m[3][1] + mat.m[3][1], m[3][2] + mat.m[3][2], m[3][3] + mat.m[3][3]);
}

Matrix4x4 Matrix4x4::operator-(Matrix4x4 mat)
{
	// Matrix-matrix subtraction
	return Matrix4x4(m[0][0] - mat.m[0][0], m[0][1] - mat.m[0][1], m[0][2] - mat.m[0][2], m[0][3] - mat.m[0][3],
		m[1][0] - mat.m[1][0], m[1][1] - mat.m[1][1], m[1][2] - mat.m[1][2], m[1][3] - mat.m[1][3],
		m[2][0] - mat.m[2][0], m[2][1] - mat.m[2][1], m[2][2] - mat.m[2][2], m[2][3] - mat.m[2][3],
		m[3][0] - mat.m[3][0], m[3][1] - mat.m[3][1], m[3][2] - mat.m[3][2], m[3][3] - mat.m[3][3]);
}

Matrix4x4 Matrix4x4::operator*(Matrix4x4 mat)
{
	// Matrix-matrix multiplication
	Matrix4x4 rmat;
	for (int i = 0; i < 4; i++)
		for (int j = 0; j < 4; j++)
			rmat.m[i][j] = m[i][0] * mat.m[0][j] + m[i][1] * mat.m[1][j] + m[i][2] * mat.m[2][j] + m[i][3] * mat.m[3][j];

	return rmat;
}

Vector4f Matrix4x4::operator*(Vector4f vec)
{
	// Matrix-vector multiplication
	return Vector4f(m[0][0] * vec.x + m[0][1] * vec.y + m[0][2] * vec.z + m[0][3] * vec.r,
		m[1][0] * vec.x + m[1][1] * vec.y + m[1][2] * vec.z + m[1][3] * vec.r,
		m[2][0] * vec.x + m[2][1] * vec.y + m[2][2] * vec.z + m[2][3] * vec.r,
		m[3][0] * vec.x + m[3][1] * vec.y + m[3][2] * vec.z + m[3][3] * vec.r);
}

void Matrix4x4::Identity()
{
	for (int i = 0; i<4; i++)
		for (int j = 0; j<4; j++) {
			if (i == j) m[i][j] = 1; else m[i][j] = 0;
		}
}


void Matrix4x4::SetMatrix(float r[4][4]) 
{
	memcpy(m, r, 16 * sizeof(float));
}


void Matrix4x4::SetMatrix(float r[16])
{
	m[0][0] = r[0];  m[0][1] = r[1];  m[0][2] = r[2];  m[0][3] = r[3];
	m[1][0] = r[4];  m[1][1] = r[5];  m[1][2] = r[6];  m[1][3] = r[7];
	m[2][0] = r[8];  m[2][1] = r[9];  m[2][2] = r[10]; m[2][3] = r[11];
	m[3][0] = r[12]; m[3][1] = r[13]; m[3][2] = r[14]; m[3][3] = r[15];
}

void Matrix4x4::SetMatrix(float t00, float t01, float t02, float t03,
	float t10, float t11, float t12, float t13,
	float t20, float t21, float t22, float t23,
	float t30, float t31, float t32, float t33)
{
	m[0][0] = t00; m[0][1] = t01; m[0][2] = t02; m[0][3] = t03;
	m[1][0] = t10; m[1][1] = t11; m[1][2] = t12; m[1][3] = t13;
	m[2][0] = t20; m[2][1] = t21; m[2][2] = t22; m[2][3] = t23;
	m[3][0] = t30; m[3][1] = t31; m[3][2] = t32; m[3][3] = t33;
}

void Matrix4x4::SetRotateMatrix(float a, Vector3f vec)
{
	// a: angle (degree), vec: axis for rotation
	a = a*3.1415f / 180.0f;	// degree to radian

	if (vec.GetLength() == 0) {
		Identity();
	}
	else {
		vec.Normalize();
		SetMatrix(vec.x*vec.x + cos(a)*(1 - vec.x*vec.x), sin(a)*(-vec.z), sin(a)*(vec.y), 0,
			sin(a)*(vec.z), vec.y*vec.y + cos(a)*(1 - vec.y*vec.y), sin(a)*(-vec.x), 0,
			sin(a)*(-vec.y), sin(a)*(vec.x), vec.z*vec.z + cos(a)*(1 - vec.z*vec.z), 0,
			0, 0, 0, 1);
	}

}

void Matrix4x4::SetScaleMatrix(Vector3f vec)
{
	SetMatrix(vec.x, 0, 0, 0,
		0, vec.y, 0, 0,
		0, 0, vec.z, 0,
		0, 0, 0, 1);
}

void Matrix4x4::SetTranslateMatrix(Vector3f vec)
{
	SetMatrix(1, 0, 0, vec.x,
		0, 1, 0, vec.y,
		0, 0, 1, vec.z,
		0, 0, 0, 1);
}


void Matrix4x4::Transpose()
{
	for (int i = 0; i<4; i++)
		for (int j = 0; j<i; j++)
			swap(m[i][j], m[j][i]);
}

bool Matrix4x4::Inverse()
{
	float a[4][4] = {};

	a[0][0] = m[1][1] * (m[2][2] * m[3][3] - m[2][3] * m[3][2]) + m[1][2] * (m[2][3] * m[3][1] - m[2][1] * m[3][3]) + m[1][3] * (m[2][1] * m[3][2] - m[2][2] * m[3][1]);
	a[0][1] = m[2][1] * (-m[3][2] * m[0][3] + m[3][3] * m[0][2]) + m[2][2] * (-m[3][3] * m[0][1] + m[3][1] * m[0][3]) + m[2][3] * (-m[3][1] * m[0][2] + m[3][2] * m[0][1]);
	a[0][2] = m[3][1] * (m[0][2] * m[1][3] - m[0][3] * m[1][2]) + m[3][2] * (m[0][3] * m[1][1] - m[0][1] * m[1][3]) + m[3][3] * (m[0][1] * m[1][2] - m[0][2] * m[1][1]);
	a[0][3] = m[0][1] * (-m[1][2] * m[2][3] + m[1][3] * m[2][2]) + m[0][2] * (-m[1][3] * m[2][1] + m[1][1] * m[2][3]) + m[0][3] * (-m[1][1] * m[2][2] + m[1][2] * m[2][1]);

	a[1][0] = m[1][2] * (-m[2][3] * m[3][0] + m[2][0] * m[3][3]) + m[1][3] * (-m[2][0] * m[3][2] + m[2][2] * m[3][0]) + m[1][0] * (-m[2][2] * m[3][3] + m[2][3] * m[3][2]);
	a[1][1] = m[2][2] * (m[3][3] * m[0][0] - m[3][0] * m[0][3]) + m[2][3] * (m[3][0] * m[0][2] - m[3][2] * m[0][0]) + m[2][0] * (m[3][2] * m[0][3] - m[3][3] * m[0][2]);
	a[1][2] = m[3][2] * (-m[0][3] * m[1][0] + m[0][0] * m[1][3]) + m[3][3] * (-m[0][0] * m[1][2] + m[0][2] * m[1][0]) + m[3][0] * (-m[0][2] * m[1][3] + m[0][3] * m[1][2]);
	a[1][3] = m[0][2] * (m[1][3] * m[2][0] - m[1][0] * m[2][3]) + m[0][3] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][0] * (m[1][2] * m[2][3] - m[1][3] * m[2][2]);

	a[2][0] = m[1][3] * (m[2][0] * m[3][1] - m[2][1] * m[3][0]) + m[1][0] * (m[2][1] * m[3][3] - m[2][3] * m[3][1]) + m[1][1] * (m[2][3] * m[3][0] - m[2][0] * m[3][3]);
	a[2][1] = m[2][3] * (-m[3][0] * m[0][1] + m[3][1] * m[0][0]) + m[2][0] * (-m[3][1] * m[0][3] + m[3][3] * m[0][1]) + m[2][1] * (-m[3][3] * m[0][0] + m[3][0] * m[0][3]);
	a[2][2] = m[3][3] * (m[0][0] * m[1][1] - m[0][1] * m[1][0]) + m[3][0] * (m[0][1] * m[1][3] - m[0][3] * m[1][1]) + m[3][1] * (m[0][3] * m[1][0] - m[0][0] * m[1][3]);
	a[2][3] = m[0][3] * (-m[1][0] * m[2][1] + m[1][1] * m[2][0]) + m[0][0] * (-m[1][1] * m[2][3] + m[1][3] * m[2][1]) + m[0][1] * (-m[1][3] * m[2][0] + m[1][0] * m[2][3]);

	a[3][0] = m[1][0] * (-m[2][1] * m[3][2] + m[2][2] * m[3][1]) + m[1][1] * (-m[2][2] * m[3][0] + m[2][0] * m[3][2]) + m[1][2] * (-m[2][0] * m[3][1] + m[2][1] * m[3][0]);
	a[3][1] = m[2][0] * (m[3][1] * m[0][2] - m[3][2] * m[0][1]) + m[2][1] * (m[3][2] * m[0][0] - m[3][0] * m[0][2]) + m[2][2] * (m[3][0] * m[0][1] - m[3][1] * m[0][0]);
	a[3][2] = m[3][0] * (-m[0][1] * m[1][2] + m[0][2] * m[1][1]) + m[3][1] * (-m[0][2] * m[1][0] + m[0][0] * m[1][2]) + m[3][2] * (-m[0][0] * m[1][1] + m[0][1] * m[1][0]);
	a[3][3] = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) + m[0][1] * (m[1][2] * m[2][0] - m[1][0] * m[2][2]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);

	float det = m[0][0] * a[0][0] + m[1][0] * a[0][1] + m[2][0] * a[0][2] + m[3][0] * a[0][3];
	if (det == 0) { return false; }

	m[0][0] = a[0][0] / det; m[0][1] = a[0][1] / det; m[0][2] = a[0][2] / det; m[0][3] = a[0][3] / det;
	m[1][0] = a[1][0] / det; m[1][1] = a[1][1] / det; m[1][2] = a[1][2] / det; m[1][3] = a[1][3] / det;
	m[2][0] = a[2][0] / det; m[2][1] = a[2][1] / det; m[2][2] = a[2][2] / det; m[2][3] = a[2][3] / det;
	m[3][0] = a[3][0] / det; m[3][1] = a[3][1] / det; m[3][2] = a[3][2] / det; m[3][3] = a[3][3] / det;

	return true;

}
