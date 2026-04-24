/////////////////////////////////////////////////////////////////////////////
//
// admm.h - Biomedical Graphics Library 
// Copyright(C) 2017  M. Nakao  All rights reserved.
//
// E-Mail : megumi@i.kyoto-u.ac.jp
//
/////////////////////////////////////////////////////////////////////////////

#ifndef _ADMM_H_
#define _ADMM_H_

#include "vector.h"
#include "matrix.h"
#include "geometry.h"

class ADMM
{

public:
	int m_nRows;		// Row count (number of equations)
	int m_nColumns;		// Column count (number of variables)

	double **Lo;
	double **tr_Lo;
	double **LoLo;

	double *uo;
	double *Louo;

	double **P;
	double **inv_P;

	double **I;
	double *q;
	double *x;
	double *z;
	double *h;
	
	ADMM();
	~ADMM();

	void Compute(int nRows, int nColumns, double *A, double *y, double *out, double mu, double lambda, int ite);
	void Optimize(int nRows, int nColumns, double **A, double *y, double *out, double mu, double lambda, int ite);

private:
	void Init(int nRows, int nColumns, double **A, double *y, double mu, double lambda);
	double SoftThreshold(double z, double Threshold);

	double **Alloc2Dim(int nRows, int nColumns);
	void Free2Dim(double **x){ free(x[0]); free(x); }

};


#endif
