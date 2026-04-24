
/////////////////////////////////////////////////////////////////////////////
//
// bmgl.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _BMGL_H_
#define _BMGL_H_


constexpr int WORKSPACE_SIZE = 1;
constexpr int MAX_PROXY_POLYGON = 1024;
constexpr int MAX_PROXY_PLANE = 2048;
constexpr int MAX_VERTEX_NUM = 4000;
constexpr int TEXTURE_NUM = 32;
constexpr int RENDER_OBJ_NUM = 6;
constexpr int GRAY_TEX_BASE = 0;
constexpr int ROI_GRAY_TEX_ALL = 9;
constexpr int LUT_TEX_BASE = 10;
constexpr int GRAD_TEX_BASE = 20;

#include <iostream>
using std::ios;
using std::ifstream;

#include <fstream>
#include <memory>
#include <list>
#include <math.h>

#include <vector>
using std::vector;

#include <algorithm>
using std::swap;
using std::sort;


extern PFNGLTEXIMAGE3DEXTPROC glTexImage3DEXT;
extern PFNGLACTIVETEXTUREPROC glActiveTexture;
extern PFNGLACTIVETEXTUREARBPROC glActiveTextureARB;
extern PFNGLGENFRAMEBUFFERSEXTPROC glGenFramebuffersEXT;
extern PFNGLBINDFRAMEBUFFEREXTPROC glBindFramebufferEXT;
extern PFNGLFRAMEBUFFERTEXTURE3DEXTPROC glFramebufferTexture3DEXT;
extern PFNGLFRAMEBUFFERTEXTURE2DEXTPROC glFramebufferTexture2DEXT;
extern PFNGLGENRENDERBUFFERSEXTPROC glGenRenderbuffersEXT;
extern PFNGLBINDRENDERBUFFEREXTPROC glBindRenderbufferEXT;
extern PFNGLRENDERBUFFERSTORAGEEXTPROC glRenderbufferStorageEXT;
extern PFNGLFRAMEBUFFERRENDERBUFFEREXTPROC glFramebufferRenderbufferEXT;

// GLSL parameters
extern GLuint frb, rrb;
extern GLuint vertShader;
extern GLuint fragShader;
extern GLuint gl2Program;

// Texture paramters
extern GLuint ntex[TEXTURE_NUM];

#include "stdafx.h"
#include "vector.h"
#include "matrix.h"
#include "trackball.h"

#include "filter.h"
#include "image.h"

#include "geometry.h"
#include "surface.h"
#include "object.h"

#endif