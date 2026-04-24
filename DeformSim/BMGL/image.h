/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _IMG_H_
#define _IMG_H_

#include "stdafx.h"
#include "imagefilter.h"


class Image3D
{

public:
	int width;		// image width
	int height;		// image height
	int depth;		// image depth

	int low;		// lowest voxel value
	int high;		// highest voxel value


	short *voxel;			// voxel value (16bit)
	short *curv;
	unsigned char *lut;		// color look up table

	Image3D();
	~Image3D();

	bool InitImage(int sizeX, int sizeY, int sizeZ, float resX, float resY, float resZ, bool isSwap, int typeNum);
	bool FreeImage();

	bool ReadLookUpTable(CString filepath);		// Read look up table
	bool ReadImageRAW(CString filepath, bool isUpdate);		// Read raw image (InitImage first)
	bool WriteImageRAW(CString filepath);		// Write raw image
	bool WriteImageCubeRAW(CString filepath);
	bool WriteImageSphereRAW(CString filepath);

	bool EvaluateFilter(Filter3D *fi);
	bool EvaluateSUSAN(int radius, int th);

	void UpdateIntensityVolume(bool isUpdate);
	void UpdateGradientVolume(bool isUpdate);
	void UpdateColorLookUpTable();

private:
	int type;		// 0: no image, 1: 8bit image, 2: 16bit image

	float rwidth;	// real image width (mm)
	float rheight;	// real image height (mm)
	float rdepth;	// real image depth (mm)
	float rmax;		// max real length (mm)

	float rx;		// image ratio x
	float ry;		// image ratio y
	float rz;		// image ratio z 

	bool swap;		// little or big endian 
	
};


#endif