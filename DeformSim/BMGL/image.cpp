/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////


#include "stdafx.h"
#include "Image.h"


Image3D::Image3D()
{
	low = -1024; 
	high = 5119; 

	width = 0; 
	height =0; 
	depth =0; 

	rwidth = 0.0f; 
	rheight = 0.0f; 
	rdepth = 0.0f; 

	rx = 0.0f; 
	ry = 0.0f; 
	rz = 0.0f; 

	swap = false; 
	type = 0; 
	voxel = 0; 
	curv = 0;

}

Image3D::~Image3D()
{ 
	delete(voxel); 
	delete(curv);
	delete(lut); 
}

bool Image3D::InitImage(int sizeX, int sizeY, int sizeZ, float resX, float resY, float resZ, bool isSwap, int typeNum)
{
	// register image information
	width = sizeX;				
	height = sizeY;				
	depth = sizeZ;				
	type = typeNum;				

	rwidth = sizeX * resX;		
	rheight = sizeY * resY;		
	rdepth = sizeZ * resZ;		

	if(rwidth >= rheight && rwidth >= rdepth) rmax = rwidth;
	if(rheight >= rwidth && rheight >= rdepth) rmax = rheight;
	else rmax = rdepth;

	rx = (float) WORKSPACE_SIZE * rwidth / rmax;
	ry = (float) WORKSPACE_SIZE * rheight / rmax;
	rz = (float) WORKSPACE_SIZE * rdepth / rmax;

	if(voxel) delete(voxel);
	voxel = new short[width*height*depth];

	if(curv) delete(curv);
	curv = new short[width*height*depth];

	return true;

}

bool Image3D::FreeImage()
{
	width = 0;
	height = 0;
	depth = 0;
	type = 0;

	rwidth = 0.0f;
	rheight = 0.0f;
	rdepth = 0.0f;

	rx = 0.0f;
	ry = 0.0f;
	rz = 0.0f;

	if(voxel) delete(voxel);

	return true;

}

bool Image3D::ReadImageRAW(CString filepath, bool isUpdate)
{

	FILE *file;
	file = fopen(filepath,"rb");
	if(!file) return false;
	
	// Get file size
	fseek( file, 0L, SEEK_END );	// Move the file pointer to the end.
	int fsize = ftell( file );		// Read the file size.
	fseek( file, 0L, SEEK_SET );	// Return to the beginning.

	if( (type == 1 && fsize == width*height*depth ) || ( type == 2 && fsize == width*height*depth*2) ) { 
		;
	} else { 
		fclose(file); return false; 
	}


	if(type == 1) {
		// 8bit gray (managed as short data)
		if(voxel) delete(voxel);
		voxel = new short[width*height*depth];

		unsigned char *temp_b = new unsigned char[width*height*depth];
		fread(temp_b, sizeof(unsigned char), width*height*depth, file);

		for(int i=0; i<width*height*depth; i++) 
			voxel[i] = (short)temp_b[i];

		delete(temp_b);
		UpdateIntensityVolume(isUpdate);

	} else if(type == 2) {

		// 16bit gray data
		if(voxel) delete(voxel);
		voxel = new short[width*height*depth];
		fread(voxel, sizeof(short), width*height*depth, file);
		UpdateIntensityVolume(isUpdate);
	}

	if(type == 2 && swap )	{

		// Swap byte order
		char *byte0, *byte1, temp;
		for(int i=0; i<width*height*depth; i++) {
			byte0 = (char *)&voxel[i];
			byte1 = (char *)&voxel[i] + 1;

			temp = *byte0;
			*byte0 = *byte1;
			*byte1 = temp;
		}
	}


	return true;

}



bool Image3D::ReadLookUpTable(CString filepath)
{
	if(!lut) delete(lut);

	std::fstream fin(filepath, ios::in);
	if(!fin.is_open()) return false;

	fin >> low; fin >> high;

	// Allocate memory and read look up table
	lut = new unsigned char [(high-low)*4];
	Vector4f *colmap = new Vector4f[high - low];

	for(int i=0; i<high-low; i++) {
		fin >> colmap[i].x >> colmap[i].y >> colmap[i].z >> colmap[i].r;

		lut[i*4+0] = (unsigned char) colmap[i].x ;
		lut[i*4+1] = (unsigned char) colmap[i].y ;
		lut[i*4+2] = (unsigned char) colmap[i].z ;
		lut[i*4+3] = (unsigned char) (colmap[i].r * 255.0f);
	}
		
	delete(colmap);

	// Update look up table data on GPU
	UpdateColorLookUpTable();

	return true;
}

bool Image3D::WriteImageRAW(CString filepath)
{
	// Write image (requires width, height and depth parameters)
	FILE *file;
	file = fopen(filepath,"wb");

	if(!file) return false;
	fwrite(voxel, sizeof(short), width*height*depth, file);
	fclose(file);
	return true;
}

bool Image3D::WriteImageCubeRAW(CString filepath)
{

	// Write test cube image (requires width, height and depth parameters)
	FILE *file;
	file = fopen(filepath,"wb");

	for(int k=0; k<depth; k++) {
		for(int j=0; j<height; j++)	{
			for(int i=0; i<width; i++) {
				if(i < 64 || j<64 || k<64 || i>192 || j>192 || k>192) 
					voxel[width*height*k + width*j + i] = 0;
				else
					voxel[width*height*k + width*j + i] = 192;
			}
		}
	}

	if(!file) return false;
	fwrite(voxel, sizeof(short), width*height*depth, file);
	fclose(file);
	return true;

}

bool Image3D::WriteImageSphereRAW(CString filepath)
{
	// Write test sphere image (requires width, height and depth parameters)
	FILE *file;
	file = fopen(filepath,"wb");

	for(int k=0; k<depth; k++) {
		for(int j=0; j<height; j++)	{
			for(int i=0; i<width; i++) {
				if((i-width/2)*(i-width/2)+(j-height/2)*(j-height/2)+(k-depth/2)*(k-depth/2) > width * width * 0.375f * 0.375f) 
					voxel[width*height*k + width*j + i] = 0;
				else
					voxel[width*height*k + width*j + i] = 192;
			}
		}
	}

	if(!file) return false;
	fwrite(voxel, sizeof(short), width*height*depth, file);
	fclose(file);
	return true;


}

bool Image3D::EvaluateFilter(Filter3D *fi)
{

	if(fi->radius == 0) return false;

	// Allocate memory for the output image
	float *temp_f = new float[width*height*depth];
	low = 32767;
	high = -32767;

	// Evaluate filter
	for(int k=fi->radius; k<depth-fi->radius; k++) {
		for(int j=fi->radius; j<height-fi->radius; j++) {
			for(int i=fi->radius; i<width-fi->radius; i++) {
				temp_f[width*height*k + width*j + i] = 0.0f;

				for(int n=-fi->radius; n<fi->radius+1; n++)
					for(int m=-fi->radius; m<fi->radius+1; m++)
						for(int l=-fi->radius; l<fi->radius+1; l++)
							temp_f[width*height*k + width*j + i] 
								+= (float) fi->GetValue(l, m ,n) * (float) voxel[width*height*(k+n) + width*(j+m) + i+l];

				// Update low and high member parameter
				if(temp_f[width*height*k + width*j + i] < low) low = (short) temp_f[width*height*k + width*j + i];
				if(temp_f[width*height*k + width*j + i] > high) high = (short) temp_f[width*height*k + width*j + i];
			}
		}
	}

	// Update voxel values (the lowest voxel value is set to the edge of the image)
	for(int k=0; k<depth; k++) {
		for(int j=0; j<height; j++)	{
			for(int i=0; i<width; i++) {
				if(i*j*k == 0 || (i-width+1)*(j-height+1)*(k-depth+1) == 0) voxel[width*height*k+ width*j + i] = low;
				else voxel[width*height*k+ width*j + i] = (short)temp_f[width*height*k + width*j + i];
			}
		}
	}

	delete(temp_f);

	return true;

}


void Image3D::UpdateIntensityVolume(bool isUpdate)
{

	unsigned short *image_s = new unsigned short[width*height*depth];
	high = 0;

	// update intensity volume texture
	for(int k=0; k<depth; k++) {
		for(int j=0; j<height; j++) {
			for(int i=0; i<width; i++) {
				image_s[width*height*k+ width*j + i] = voxel[width*height*k+ width*j + i] - low;
				if(high < voxel[width*height*k+ width*j + i]) high = voxel[width*height*k+ width*j + i];
			}
		}
	}

	// upload texture

	if(isUpdate)
	{
		unsigned int tex = 0;
		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_3D, tex);		// bind texture 

		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_S, GL_CLAMP);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_T, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_R_EXT, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
		glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

		glTexImage3DEXT(GL_TEXTURE_3D_EXT, 0, GL_INTENSITY16, width, height, depth, 0, GL_LUMINANCE, GL_UNSIGNED_SHORT, image_s);
	}

	delete(image_s);

}

void Image3D::UpdateGradientVolume(bool isUpdate)
{

	short x1, x2, y1, y2, z1, z2;
	short dx, dy, dz;
	
	// Allocate memory
	unsigned char *image_gx = new unsigned char[width*height*depth];
	unsigned char *image_gy = new unsigned char[width*height*depth];
	unsigned char *image_gz = new unsigned char[width*height*depth];

	// Compute gradient volume by differential filter
	for(int k=0; k<depth; k++) {
		for(int j=0; j<height; j++) {
			for(int i=0; i<width; i++) {

				if(i==0) x1 = low; else	x1 = voxel[k*height*width + j*width + i-1];
				if(i==width-1) x2 = low; else x2 = voxel[k*height*width + j*width + i+1];
				if(j==0) y1 = low; else y1 = voxel[k*height*width + (j-1)*width + i];
				if(j==height-1) y2 = low; else y2 = voxel[k*height*width + (j+1)*width + i];
				if(k==0) z1 = low; else z1 = voxel[(k-1)*height*width + j*width + i];
				if(k==depth-1) z2 = low; else z2 = voxel[(k+1)*height*width + j*width + i];

				dx = (int)((float)(x2 - x1) + 255.0f)/2; if(dx < 0) dx = 0; else if (dx > 255) dx = 255;
				dy = (int)((float)(y2 - y1) + 255.0f)/2; if(dy < 0) dy = 0; else if (dy > 255) dy = 255;
				dz = (int)((float)(z2 - z1) + 255.0f)/2; if(dz < 0) dz = 0; else if (dz > 255) dz = 255;

				image_gx[k*height*width + j*width + i] = (unsigned char)dx;
				image_gy[k*height*width + j*width + i] = (unsigned char)dy;
				image_gz[k*height*width + j*width + i] = (unsigned char)dz;

			}
		}
	}

	if(isUpdate)
	{

		// Bind texture (gradient x volume)
		glActiveTexture(GL_TEXTURE1);
		glBindTexture(GL_TEXTURE_3D, ntex[1]);		

		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_S, GL_CLAMP);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_T, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_R_EXT, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
		glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

		// Update gradient texture (x-direction) on GPU
		glTexImage3DEXT(GL_TEXTURE_3D_EXT, 0, GL_INTENSITY8, width, height, depth, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, image_gx);

		// Bind texture (gradient y volume)
		glActiveTexture(GL_TEXTURE2);
		glBindTexture(GL_TEXTURE_3D, ntex[2]);		

		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_S, GL_CLAMP);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_T, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_R_EXT, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
		glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

		// Update gradient texture (y-direction) on GPU
		glTexImage3DEXT(GL_TEXTURE_3D_EXT, 0, GL_INTENSITY8, width, height, depth, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, image_gy);

		// Bind texture (gradient z volume)
		glActiveTexture(GL_TEXTURE3);
		glBindTexture(GL_TEXTURE_3D, ntex[3]);		

		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_S, GL_CLAMP);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_T, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_WRAP_R_EXT, GL_CLAMP);     
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
		glTexParameteri(GL_TEXTURE_3D_EXT, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
		glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

		// Update gradient texture (z-direction) on GPU
		glTexImage3DEXT(GL_TEXTURE_3D_EXT, 0, GL_INTENSITY8, width, height, depth, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, image_gz);

		glActiveTexture(GL_TEXTURE0);

	}

	delete(image_gx);
	delete(image_gy);
	delete(image_gz);

}


void Image3D::UpdateColorLookUpTable()
{

	// BindTexture (Color look up table)
	glActiveTexture(GL_TEXTURE4);
	glBindTexture(GL_TEXTURE_2D, ntex[4]);

	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
	glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);

	// Update texture on GPU
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 4096, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, lut);
	glActiveTexture(GL_TEXTURE0);

}


bool Image3D::EvaluateSUSAN(int radius, int th)
{

	// Allocate memory for the output image
	unsigned short *temp = new unsigned short[width*height*depth];

	// Evaluate filter
	for(int k=radius; k<depth-radius; k++) {
		for(int j=radius; j<height-radius; j++) {
			for(int i=radius; i<width-radius; i++) {
				temp[width*height*k + width*j + i] = 0;

				for(int n=-radius; n<radius+1; n++)
					for(int m=-radius; m<radius+1; m++)
						for(int l=-radius; l<radius+1; l++)
						{
/*							if( n*n + m*m + l*l <= radius*radius && 
								  abs(voxel[width*height*(k+n) + width*(j+m) + i+l] - voxel[width*height*k + width*j + i]) < th)
							{
								temp[width*height*k + width*j + i] += 1;
							}
*/
							if( n*n + m*m + l*l <= radius*radius && lut[ (voxel[width*height*k + width*j + i] - low)*4 + 3] > 64 &&
								  (abs(lut[ (voxel[width*height*(k+n) + width*(j+m) + i+l] - low) *4 + 3] 
										- lut[ (voxel[width*height*k + width*j + i] - low)*4 + 3] ) > th) )
							{
								temp[width*height*k + width*j + i] += 1;
							}
						}

			}
		}
	}

	memcpy(voxel, temp, sizeof(short)*width*height*depth);
	delete(temp);

	return true;

}

