/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////


#ifndef _IMAGEFILTER_H_
#define _IMAGEFILTER_H_


class Filter3D
{

public:
	float *f;		// filter value
	int radius;		// filter radius (radius 1 = 3x3 filter)

	Filter3D();
	Filter3D(int r);
	~Filter3D();

	void Init(int r);
	bool SetValue(int i, int j, int k, float value);
	float GetValue(int i, int j, int k);
	bool Normalize();

	void SetGaussian(float sigma);		// Gaussian filter
	void SetGradient(int type);			// Gradient filter
	void SetLaplacian();

};

#endif