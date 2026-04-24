/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////


#include "stdafx.h"
#include "imagefilter.h"


Filter3D::Filter3D()
{
	radius = 0; 
	f = 0;
}

Filter3D::Filter3D(int r) 
{ 
	radius = r; 
	int fsize = 2*radius + 1; 
	f = new float[(unsigned int)(pow((float)fsize, 3))]; 
}

Filter3D::~Filter3D()	
{ 
	if(f) delete(f); 
}


void Filter3D::Init(int r) 
{ 
	radius = r; 
	int fsize = 2*radius + 1; 
	if(f) delete(f); 
	f = new float[(unsigned int)(pow((float)fsize, 3))];

}


bool Filter3D::SetValue(int i, int j, int k, float value)
{
	int fsize = radius * 2 + 1;
	if(i< -radius || i> radius || j < -radius || j > radius || k < -radius || k > radius) {
		return false;
	}else { 
		int x = i + radius; int y = j + radius; int z = k + radius; f[fsize*fsize*z + fsize*y +x] = value; 
		return true; 
	}
}


float Filter3D::GetValue(int i, int j, int k)
{
	int fsize = radius * 2 + 1;
	if(i< -radius || i> radius || j < -radius || j > radius || k < -radius || k > radius) { return 0; }
	else { int x = i + radius; int y = j + radius; int z = k + radius; return f[fsize*fsize*z + fsize*y +x]; }
}


void Filter3D::SetGaussian(float sigma)
{
	//
	// 3D Gauss Function: 
	// f(x, y, z) = exp( - (x*x + y*y + z*z) / (2*sigma*sigma) )
	//
	float div = pow(sigma, 2)*2.0f;

	for(int k=-radius; k<radius+1; k++) {
		for(int j=-radius; j<radius+1; j++) {
			for(int i=-radius; i<radius+1; i++) {
				bool result = false;
				float value = exp( -( pow((float)i, 2) + pow((float)j, 2) + pow((float)k, 2) ) / div ) ;
				result = SetValue(i, j, k,  value);
				if(!result) return;
			}
		}
	}

	Normalize();

}

void Filter3D::SetLaplacian()
{

	for(int k=-radius; k<radius+1; k++) {
		for(int j=-radius; j<radius+1; j++) {
			for(int i=-radius; i<radius+1; i++) {

				if(i == 0 && j== 0 && k == 0) 
				{	
					SetValue(i, j, k, -1.0f);
				}
				else 
				{
					SetValue(i, j, k, 1.0f/26.0f);
				}

			}
		}
	}

}

void Filter3D::SetGradient(int type)
{

	for(int k=-radius; k<radius+1; k++) {
		for(int j=-radius; j<radius+1; j++) {
			for(int i=-radius; i<radius+1; i++) {
				if( (type == 0 && i == 0) ||  (type == 1 && j == 0) ||  (type == 2 && k == 0)) {
					SetValue(i, j, k, 0);
				} else { 
					int dist = (int)pow((float)i, 2) + (int)pow((float)j, 2) + (int)pow((float)k, 2); 
					if( (type == 0 && i > 0) || (type == 1 && j > 0) || (type == 2 && k > 0)) 
						SetValue(i, j, k, 4.0f / pow(2.0f, dist - 1)); 
					else 
						SetValue(i, j, k, -4.0f / pow(2.0f, dist - 1)); 
				}
			}
		}
	}

}



bool Filter3D::Normalize()
{

	float sum = 0;
	for(int k=-radius; k<radius+1; k++)
		for(int j=-radius; j<radius+1; j++)
			for(int i=-radius; i<radius+1; i++)
				sum += GetValue(i, j, k);

	if( sum == 0 ) { 
		return false; 
	}

	for(int k=-radius; k<radius+1; k++)
		for(int j=-radius; j<radius+1; j++)
			for(int i=-radius; i<radius+1; i++)
				SetValue(i, j, k, GetValue(i, j, k)/sum);

	return true;

}