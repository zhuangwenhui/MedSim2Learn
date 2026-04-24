#include <stdafx.h>

#include <stdio.h>
#include <stdlib.h>
#include <malloc.h>

#include "glsl.h"

#if defined(WIN32)
PFNGLATTACHSHADERPROC glAttachShader;
PFNGLBINDATTRIBLOCATIONPROC glBindAttribLocation;
PFNGLBLENDEQUATIONSEPARATEPROC glBlendEquationSeparate;
PFNGLCOMPILESHADERPROC glCompileShader;
PFNGLCREATEPROGRAMPROC glCreateProgram;
PFNGLCREATESHADERPROC glCreateShader;
PFNGLDELETEPROGRAMPROC glDeleteProgram;
PFNGLDELETESHADERPROC glDeleteShader;
PFNGLDETACHSHADERPROC glDetachShader;
PFNGLDISABLEVERTEXATTRIBARRAYPROC glDisableVertexAttribArray;
PFNGLDRAWBUFFERSPROC glDrawBuffers;
PFNGLENABLEVERTEXATTRIBARRAYPROC glEnableVertexAttribArray;
PFNGLGETACTIVEATTRIBPROC glGetActiveAttrib;
PFNGLGETACTIVEUNIFORMPROC glGetActiveUniform;
PFNGLGETATTACHEDSHADERSPROC glGetAttachedShaders;
PFNGLGETATTRIBLOCATIONPROC glGetAttribLocation;
PFNGLGETPROGRAMINFOLOGPROC glGetProgramInfoLog;
PFNGLGETPROGRAMIVPROC glGetProgramiv;
PFNGLGETSHADERINFOLOGPROC glGetShaderInfoLog;
PFNGLGETSHADERIVPROC glGetShaderiv;
PFNGLGETSHADERSOURCEPROC glGetShaderSource;
PFNGLGETUNIFORMFVPROC glGetUniformfv;
PFNGLGETUNIFORMIVPROC glGetUniformiv;
PFNGLGETUNIFORMLOCATIONPROC glGetUniformLocation;
PFNGLGETVERTEXATTRIBDVPROC glGetVertexAttribdv;
PFNGLGETVERTEXATTRIBFVPROC glGetVertexAttribfv;
PFNGLGETVERTEXATTRIBIVPROC glGetVertexAttribiv;
PFNGLGETVERTEXATTRIBPOINTERVPROC glGetVertexAttribPointerv;
PFNGLISPROGRAMPROC glIsProgram;
PFNGLISSHADERPROC glIsShader;
PFNGLLINKPROGRAMPROC glLinkProgram;
PFNGLSHADERSOURCEPROC glShaderSource;
PFNGLSTENCILFUNCSEPARATEPROC glStencilFuncSeparate;
PFNGLSTENCILMASKSEPARATEPROC glStencilMaskSeparate;
PFNGLSTENCILOPSEPARATEPROC glStencilOpSeparate;
PFNGLUNIFORM1FPROC glUniform1f;
PFNGLUNIFORM1FVPROC glUniform1fv;
PFNGLUNIFORM1IPROC glUniform1i;
PFNGLUNIFORM1IVPROC glUniform1iv;
PFNGLUNIFORM2FPROC glUniform2f;
PFNGLUNIFORM2FVPROC glUniform2fv;
PFNGLUNIFORM2IPROC glUniform2i;
PFNGLUNIFORM2IVPROC glUniform2iv;
PFNGLUNIFORM3FPROC glUniform3f;
PFNGLUNIFORM3FVPROC glUniform3fv;
PFNGLUNIFORM3IPROC glUniform3i;
PFNGLUNIFORM3IVPROC glUniform3iv;
PFNGLUNIFORM4FPROC glUniform4f;
PFNGLUNIFORM4FVPROC glUniform4fv;
PFNGLUNIFORM4IPROC glUniform4i;
PFNGLUNIFORM4IVPROC glUniform4iv;
PFNGLUNIFORMMATRIX2FVPROC glUniformMatrix2fv;
PFNGLUNIFORMMATRIX3FVPROC glUniformMatrix3fv;
PFNGLUNIFORMMATRIX4FVPROC glUniformMatrix4fv;
PFNGLUSEPROGRAMPROC glUseProgram;
PFNGLVALIDATEPROGRAMPROC glValidateProgram;
PFNGLVERTEXATTRIB1DPROC glVertexAttrib1d;
PFNGLVERTEXATTRIB1DVPROC glVertexAttrib1dv;
PFNGLVERTEXATTRIB1FPROC glVertexAttrib1f;
PFNGLVERTEXATTRIB1FVPROC glVertexAttrib1fv;
PFNGLVERTEXATTRIB1SPROC glVertexAttrib1s;
PFNGLVERTEXATTRIB1SVPROC glVertexAttrib1sv;
PFNGLVERTEXATTRIB2DPROC glVertexAttrib2d;
PFNGLVERTEXATTRIB2DVPROC glVertexAttrib2dv;
PFNGLVERTEXATTRIB2FPROC glVertexAttrib2f;
PFNGLVERTEXATTRIB2FVPROC glVertexAttrib2fv;
PFNGLVERTEXATTRIB2SPROC glVertexAttrib2s;
PFNGLVERTEXATTRIB2SVPROC glVertexAttrib2sv;
PFNGLVERTEXATTRIB3DPROC glVertexAttrib3d;
PFNGLVERTEXATTRIB3DVPROC glVertexAttrib3dv;
PFNGLVERTEXATTRIB3FPROC glVertexAttrib3f;
PFNGLVERTEXATTRIB3FVPROC glVertexAttrib3fv;
PFNGLVERTEXATTRIB3SPROC glVertexAttrib3s;
PFNGLVERTEXATTRIB3SVPROC glVertexAttrib3sv;
PFNGLVERTEXATTRIB4BVPROC glVertexAttrib4bv;
PFNGLVERTEXATTRIB4DPROC glVertexAttrib4d;
PFNGLVERTEXATTRIB4DVPROC glVertexAttrib4dv;
PFNGLVERTEXATTRIB4FPROC glVertexAttrib4f;
PFNGLVERTEXATTRIB4FVPROC glVertexAttrib4fv;
PFNGLVERTEXATTRIB4IVPROC glVertexAttrib4iv;
PFNGLVERTEXATTRIB4NBVPROC glVertexAttrib4Nbv;
PFNGLVERTEXATTRIB4NIVPROC glVertexAttrib4Niv;
PFNGLVERTEXATTRIB4NSVPROC glVertexAttrib4Nsv;
PFNGLVERTEXATTRIB4NUBPROC glVertexAttrib4Nub;
PFNGLVERTEXATTRIB4NUBVPROC glVertexAttrib4Nubv;
PFNGLVERTEXATTRIB4NUIVPROC glVertexAttrib4Nuiv;
PFNGLVERTEXATTRIB4NUSVPROC glVertexAttrib4Nusv;
PFNGLVERTEXATTRIB4SPROC glVertexAttrib4s;
PFNGLVERTEXATTRIB4SVPROC glVertexAttrib4sv;
PFNGLVERTEXATTRIB4UBVPROC glVertexAttrib4ubv;
PFNGLVERTEXATTRIB4UIVPROC glVertexAttrib4uiv;
PFNGLVERTEXATTRIB4USVPROC glVertexAttrib4usv;
PFNGLVERTEXATTRIBPOINTERPROC glVertexAttribPointer;
#endif

/*
** Initialize GLSL entry points.
*/
int glslInit(void)
{
  int error = 0;
  
#if defined(WIN32)
#define PADDR(functype, funcname) \
  ((funcname = (functype) wglGetProcAddress( #funcname )) == 0)
  
  error |= PADDR(PFNGLATTACHSHADERPROC, glAttachShader);
  error |= PADDR(PFNGLBINDATTRIBLOCATIONPROC, glBindAttribLocation);
  error |= PADDR(PFNGLBLENDEQUATIONSEPARATEPROC, glBlendEquationSeparate);
  error |= PADDR(PFNGLCOMPILESHADERPROC, glCompileShader);
  error |= PADDR(PFNGLCREATEPROGRAMPROC, glCreateProgram);
  error |= PADDR(PFNGLCREATESHADERPROC, glCreateShader);
  error |= PADDR(PFNGLDELETEPROGRAMPROC, glDeleteProgram);
  error |= PADDR(PFNGLDELETESHADERPROC, glDeleteShader);
  error |= PADDR(PFNGLDETACHSHADERPROC, glDetachShader);
  error |= PADDR(PFNGLDISABLEVERTEXATTRIBARRAYPROC, glDisableVertexAttribArray);
  error |= PADDR(PFNGLDRAWBUFFERSPROC, glDrawBuffers);
  error |= PADDR(PFNGLENABLEVERTEXATTRIBARRAYPROC, glEnableVertexAttribArray);
  error |= PADDR(PFNGLGETACTIVEATTRIBPROC, glGetActiveAttrib);
  error |= PADDR(PFNGLGETACTIVEUNIFORMPROC, glGetActiveUniform);
  error |= PADDR(PFNGLGETATTACHEDSHADERSPROC, glGetAttachedShaders);
  error |= PADDR(PFNGLGETATTRIBLOCATIONPROC, glGetAttribLocation);
  error |= PADDR(PFNGLGETPROGRAMINFOLOGPROC, glGetProgramInfoLog);
  error |= PADDR(PFNGLGETPROGRAMIVPROC, glGetProgramiv);
  error |= PADDR(PFNGLGETSHADERINFOLOGPROC, glGetShaderInfoLog);
  error |= PADDR(PFNGLGETSHADERIVPROC, glGetShaderiv);
  error |= PADDR(PFNGLGETSHADERSOURCEPROC, glGetShaderSource);
  error |= PADDR(PFNGLGETUNIFORMFVPROC, glGetUniformfv);
  error |= PADDR(PFNGLGETUNIFORMIVPROC, glGetUniformiv);
  error |= PADDR(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation);
  error |= PADDR(PFNGLGETVERTEXATTRIBDVPROC, glGetVertexAttribdv);
  error |= PADDR(PFNGLGETVERTEXATTRIBFVPROC, glGetVertexAttribfv);
  error |= PADDR(PFNGLGETVERTEXATTRIBIVPROC, glGetVertexAttribiv);
  error |= PADDR(PFNGLGETVERTEXATTRIBPOINTERVPROC, glGetVertexAttribPointerv);
  error |= PADDR(PFNGLISPROGRAMPROC, glIsProgram);
  error |= PADDR(PFNGLISSHADERPROC, glIsShader);
  error |= PADDR(PFNGLLINKPROGRAMPROC, glLinkProgram);
  error |= PADDR(PFNGLSHADERSOURCEPROC, glShaderSource);
  error |= PADDR(PFNGLSTENCILFUNCSEPARATEPROC, glStencilFuncSeparate);
  error |= PADDR(PFNGLSTENCILMASKSEPARATEPROC, glStencilMaskSeparate);
  error |= PADDR(PFNGLSTENCILOPSEPARATEPROC, glStencilOpSeparate);
  error |= PADDR(PFNGLUNIFORM1FPROC, glUniform1f);
  error |= PADDR(PFNGLUNIFORM1FVPROC, glUniform1fv);
  error |= PADDR(PFNGLUNIFORM1IPROC, glUniform1i);
  error |= PADDR(PFNGLUNIFORM1IVPROC, glUniform1iv);
  error |= PADDR(PFNGLUNIFORM2FPROC, glUniform2f);
  error |= PADDR(PFNGLUNIFORM2FVPROC, glUniform2fv);
  error |= PADDR(PFNGLUNIFORM2IPROC, glUniform2i);
  error |= PADDR(PFNGLUNIFORM2IVPROC, glUniform2iv);
  error |= PADDR(PFNGLUNIFORM3FPROC, glUniform3f);
  error |= PADDR(PFNGLUNIFORM3FVPROC, glUniform3fv);
  error |= PADDR(PFNGLUNIFORM3IPROC, glUniform3i);
  error |= PADDR(PFNGLUNIFORM3IVPROC, glUniform3iv);
  error |= PADDR(PFNGLUNIFORM4FPROC, glUniform4f);
  error |= PADDR(PFNGLUNIFORM4FVPROC, glUniform4fv);
  error |= PADDR(PFNGLUNIFORM4IPROC, glUniform4i);
  error |= PADDR(PFNGLUNIFORM4IVPROC, glUniform4iv);
  error |= PADDR(PFNGLUNIFORMMATRIX2FVPROC, glUniformMatrix2fv);
  error |= PADDR(PFNGLUNIFORMMATRIX3FVPROC, glUniformMatrix3fv);
  error |= PADDR(PFNGLUNIFORMMATRIX4FVPROC, glUniformMatrix4fv);
  error |= PADDR(PFNGLUSEPROGRAMPROC, glUseProgram);
  error |= PADDR(PFNGLVALIDATEPROGRAMPROC, glValidateProgram);
  error |= PADDR(PFNGLVERTEXATTRIB1DPROC, glVertexAttrib1d);
  error |= PADDR(PFNGLVERTEXATTRIB1DVPROC, glVertexAttrib1dv);
  error |= PADDR(PFNGLVERTEXATTRIB1FPROC, glVertexAttrib1f);
  error |= PADDR(PFNGLVERTEXATTRIB1FVPROC, glVertexAttrib1fv);
  error |= PADDR(PFNGLVERTEXATTRIB1SPROC, glVertexAttrib1s);
  error |= PADDR(PFNGLVERTEXATTRIB1SVPROC, glVertexAttrib1sv);
  error |= PADDR(PFNGLVERTEXATTRIB2DPROC, glVertexAttrib2d);
  error |= PADDR(PFNGLVERTEXATTRIB2DVPROC, glVertexAttrib2dv);
  error |= PADDR(PFNGLVERTEXATTRIB2FPROC, glVertexAttrib2f);
  error |= PADDR(PFNGLVERTEXATTRIB2FVPROC, glVertexAttrib2fv);
  error |= PADDR(PFNGLVERTEXATTRIB2SPROC, glVertexAttrib2s);
  error |= PADDR(PFNGLVERTEXATTRIB2SVPROC, glVertexAttrib2sv);
  error |= PADDR(PFNGLVERTEXATTRIB3DPROC, glVertexAttrib3d);
  error |= PADDR(PFNGLVERTEXATTRIB3DVPROC, glVertexAttrib3dv);
  error |= PADDR(PFNGLVERTEXATTRIB3FPROC, glVertexAttrib3f);
  error |= PADDR(PFNGLVERTEXATTRIB3FVPROC, glVertexAttrib3fv);
  error |= PADDR(PFNGLVERTEXATTRIB3SPROC, glVertexAttrib3s);
  error |= PADDR(PFNGLVERTEXATTRIB3SVPROC, glVertexAttrib3sv);
  error |= PADDR(PFNGLVERTEXATTRIB4BVPROC, glVertexAttrib4bv);
  error |= PADDR(PFNGLVERTEXATTRIB4DPROC, glVertexAttrib4d);
  error |= PADDR(PFNGLVERTEXATTRIB4DVPROC, glVertexAttrib4dv);
  error |= PADDR(PFNGLVERTEXATTRIB4FPROC, glVertexAttrib4f);
  error |= PADDR(PFNGLVERTEXATTRIB4FVPROC, glVertexAttrib4fv);
  error |= PADDR(PFNGLVERTEXATTRIB4IVPROC, glVertexAttrib4iv);
  error |= PADDR(PFNGLVERTEXATTRIB4NBVPROC, glVertexAttrib4Nbv);
  error |= PADDR(PFNGLVERTEXATTRIB4NIVPROC, glVertexAttrib4Niv);
  error |= PADDR(PFNGLVERTEXATTRIB4NSVPROC, glVertexAttrib4Nsv);
  error |= PADDR(PFNGLVERTEXATTRIB4NUBPROC, glVertexAttrib4Nub);
  error |= PADDR(PFNGLVERTEXATTRIB4NUBVPROC, glVertexAttrib4Nubv);
  error |= PADDR(PFNGLVERTEXATTRIB4NUIVPROC, glVertexAttrib4Nuiv);
  error |= PADDR(PFNGLVERTEXATTRIB4NUSVPROC, glVertexAttrib4Nusv);
  error |= PADDR(PFNGLVERTEXATTRIB4SPROC, glVertexAttrib4s);
  error |= PADDR(PFNGLVERTEXATTRIB4SVPROC, glVertexAttrib4sv);
  error |= PADDR(PFNGLVERTEXATTRIB4UBVPROC, glVertexAttrib4ubv);
  error |= PADDR(PFNGLVERTEXATTRIB4UIVPROC, glVertexAttrib4uiv);
  error |= PADDR(PFNGLVERTEXATTRIB4USVPROC, glVertexAttrib4usv);
  error |= PADDR(PFNGLVERTEXATTRIBPOINTERPROC, glVertexAttribPointer);
  
  if (error) fprintf(stderr, "Could not obtain all of entry points.\n");
#endif
  
  return error;
}

/*
** Load a shader source program into memory.
*/
int readShaderSource(GLuint shader, const char *file)
{
  FILE *fp;
  const GLchar *source;
  GLsizei length;
  int ret;
  
  /* Open the file. */
  fp = fopen(file, "rb");
  if (fp == NULL) {
    perror(file);
    return -1;
  }
  
  /* Seek to the end and read the file size. */
  fseek(fp, 0L, SEEK_END);
  length = ftell(fp);
  
  /* Allocate memory for the source buffer. */
  source = (GLchar *)malloc(length);
  if (source == NULL) {
    fprintf(stderr, "Could not allocate read buffer.\n");
    return -1;
  }
  
  /* Read the file from the beginning. */
  fseek(fp, 0L, SEEK_SET);
  ret = fread((void *)source, 1, length, fp) != (size_t)length;
  fclose(fp);
  
  /* Attach the shader source to the shader object. */
  if (ret)
    fprintf(stderr, "Could not read file: %s.\n", file);
  else
    glShaderSource(shader, 1, &source, &length);
  
  /* Release the temporary buffer. */
  free((void *)source);
  
  return ret;
}

/*
** Print shader information.
*/
void printShaderInfoLog(GLuint shader)
{
  GLsizei bufSize;
  
  glGetShaderiv(shader, GL_INFO_LOG_LENGTH , &bufSize);
  
  if (bufSize > 1) {
    GLchar *infoLog;
    
    infoLog = (GLchar *)malloc(bufSize);
    if (infoLog != NULL) {
      GLsizei length;
      
      glGetShaderInfoLog(shader, bufSize, &length, infoLog);
      fprintf(stderr, "InfoLog:\n%s\n\n", infoLog);
      free(infoLog);
    }
    else
      fprintf(stderr, "Could not allocate InfoLog buffer.\n");
  }
}

/*
** Print program information.
*/
void printProgramInfoLog(GLuint program)
{
  GLsizei bufSize;
  
  glGetProgramiv(program, GL_INFO_LOG_LENGTH , &bufSize);
  
  if (bufSize > 1) {
    GLchar *infoLog;
    
    infoLog = (GLchar *)malloc(bufSize);
    if (infoLog != NULL) {
      GLsizei length;
      
      glGetProgramInfoLog(program, bufSize, &length, infoLog);
      fprintf(stderr, "InfoLog:\n%s\n\n", infoLog);
      free(infoLog);
    }
    else
      fprintf(stderr, "Could not allocate InfoLog buffer.\n");
  }
}
