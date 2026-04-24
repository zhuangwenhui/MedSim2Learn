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

void BoundingBox::Rotate(float angle, Vector3f axis)
{
	Matrix3x3 rotate_matrix;
	rotate_matrix.SetRotateMatrix(angle, axis);

	axisX = rotate_matrix * axisX;
	axisY = rotate_matrix * axisY;
	axisZ = rotate_matrix * axisZ;

}

void BoundingBox::Translate(Vector3f trans)
{
	center = center + trans;
}

void BoundingBox::Scale(Vector3f scale)
{
	axisX = axisX * scale.x;
	axisY = axisY * scale.y;
	axisZ = axisZ * scale.z;
}


void BoundingBox::Transform(Matrix4x4 mat)
{
	center = center + mat.GetTranslateVector();

	axisX = mat.GetRotateMatrix() * axisX;
	axisY = mat.GetRotateMatrix() * axisY;
	axisZ = mat.GetRotateMatrix() * axisZ;

}

void BoundingBox::RenderBoundingBox(Vector3f vec)
{

	Vector3f norm, coord1, coord2;
	glLineWidth(1.0f);
	glColor3f(0.0f, 0.0f, 0.0f);


	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY + axisZ) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY + axisZ) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY + axisZ) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY*-1.0f + axisZ) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY*-1.0f + axisZ) / 2.0f;
	coord2 = center - (axisX + axisY*-1.0f + axisZ) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY*-1.0f + axisZ) / 2.0f;
	coord2 = center - (axisX + axisY + axisZ) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY + axisZ*-1.0f) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY + axisZ*-1.0f) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	coord2 = center - (axisX + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	coord2 = center - (axisX + axisY + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();


	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY + axisZ) / 2.0f;
	coord2 = center - (axisX + axisY + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY + axisZ) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX*-1.0f + axisY*-1.0f + axisZ) / 2.0f;
	coord2 = center - (axisX*-1.0f + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();

	glBegin(GL_LINES);
	coord1 = center - (axisX + axisY*-1.0f + axisZ) / 2.0f;
	coord2 = center - (axisX + axisY*-1.0f + axisZ*-1.0f) / 2.0f;
	glNormal3f(vec.x, vec.y, vec.z);
	glVertex3f(coord1.x, coord1.y, coord1.z);
	glVertex3f(coord2.x, coord2.y, coord2.z);
	glEnd();


}

void Vertex::InitNeighborVertex(int num)
{
	neighborVertex.clear();
	neighborVertex.reserve(num);  // reserve memory for the number of neighbor vertices
}
