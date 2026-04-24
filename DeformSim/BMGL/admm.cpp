/////////////////////////////////////////////////////////////////////////////
//
// admm.h - Biomedical Graphics Library 
// Copyright(C) 2017  M. Nakao  All rights reserved.
//
// E-Mail : megumi@i.kyoto-u.ac.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "admm.h"


ADMM::ADMM()
{
	Lo = 0;
	tr_Lo = 0;
	LoLo = 0;

	P = 0;
	inv_P = 0;
	I = 0;

	uo = 0;
	Louo = 0;

	x = 0;
	z = 0;
	h = 0;
	q = 0;

}

ADMM::~ADMM()
{
	if (Lo) Free2Dim(Lo);
	if (tr_Lo) Free2Dim(tr_Lo);
	if (LoLo) Free2Dim(LoLo);

	if (P) Free2Dim(P);
	if (inv_P) Free2Dim(inv_P);
	if (I) Free2Dim(I);

	if (uo) free(uo);
	if (Louo) free(Louo);

	if (x) free(x);
	if (z) free(z);
	if (h) free(h);
	if (q) free(q);

	Lo = 0;
	tr_Lo = 0;
	LoLo = 0;

	P = 0;
	inv_P = 0;
	I = 0;

	uo = 0;
	Louo = 0;

	x = 0;
	z = 0;
	h = 0;
	q = 0;

}

double **ADMM::Alloc2Dim(int nRows, int nColumns)
{
	// Array[i][j]: column i and row j (column-major format)
	double **Array;

	Array = (double **)calloc(nRows, sizeof(double *));
	Array[0] = (double *)calloc(nRows * nColumns, sizeof(double));
	for (int i = 0; i < nRows; i++)  Array[i] = Array[0] + i * nColumns;

	return (double **)Array;

}

void ADMM::Init(int nRows, int nColumns, double **A, double *y, double mu, double lambda)
{

	// Copy A into Lo.
	if (Lo) Free2Dim(Lo);
	Lo = Alloc2Dim( nRows, nColumns);
	memcpy(Lo[0], A[0], sizeof(double)*nRows*nColumns);
	
	// Copy y into uo.
	if (uo) free(uo); 
	uo = (double *)calloc(nRows, sizeof(double));
	memcpy(uo, y, sizeof(double)*nRows);
	

	// Compute the transpose of Lo.
	if (tr_Lo) Free2Dim(tr_Lo);
	tr_Lo = Alloc2Dim( nColumns, nRows );

	for (int i = 0; i < nRows; i++){
		for (int j = 0; j < nColumns; j++){
			tr_Lo[j][i] = Lo[i][j];
		}
	}

	// Allocate storage for Lo^T * Lo.
	if (LoLo) Free2Dim(LoLo);
	LoLo = Alloc2Dim(nColumns, nColumns);

	// Compute Lo^T * Lo.
	for (int i = 0; i < nColumns; i++){
		for (int j = 0; j < nColumns; j++){
			double term = 0;
			for (int k = 0; k < nRows; k++)
				term = term + tr_Lo[i][k] * Lo[k][j];
			LoLo[i][j] = term;
		}
	}

	// Allocate the identity matrix.
	if (I) Free2Dim(I);
	I = Alloc2Dim(nColumns, nColumns);

	// Fill the identity matrix.
	for (int i = 0; i < nColumns; i++){
		for (int j = 0; j < nColumns; j++){
			I[i][j] = 0.0;
			if (i == j) I[i][j] = 1.0;
		}
	}

	// Allocate matrix P.
	if (P) Free2Dim(P);
	P = Alloc2Dim(nColumns, nColumns);

	// Compute matrix P.
	for (int i = 0; i <nColumns; i++){
		for (int j = 0; j < nColumns; j++){
			P[i][j] = mu * I[i][j] + LoLo[i][j] / lambda;
		}
	}

	// Compute the inverse of P.
	if (inv_P) Free2Dim(inv_P);
	inv_P = Alloc2Dim(nColumns, nColumns);
	memcpy(inv_P[0], P[0], sizeof(double)*nColumns*nColumns );

	int nOrder = nColumns;
	int *ipiv;
	int info;
	double *work;
	int nWork = nColumns * 64;
	work = new double[nWork];
	ipiv = new int[nOrder];

	DGETRF(&nOrder, &nOrder, &inv_P[0][0], &nOrder, &ipiv[0], &info);
	DGETRI(&nOrder, &inv_P[0][0], &nOrder, &ipiv[0], &work[0], &nWork, &info);
	delete[] ipiv;
	delete[] work;

	// Allocate storage for Lo^T * uo.
	if (Louo) free (Louo);  
	Louo = (double *)calloc(nColumns, sizeof(double));

	// Compute Lo^T * uo.
	for (int i = 0; i < nColumns; i++){
		double term = 0;
		for (int k = 0; k < nRows; k++)
			term = term + tr_Lo[i][k] * uo[k];
		Louo[i] = term;
	}

	// Allocate working vectors.
	if (x) free(x); x = (double *)calloc(nColumns, sizeof(double));
	if (z) free(z); z = (double *)calloc(nColumns, sizeof(double));
	if (h) free(h); h = (double *)calloc(nColumns, sizeof(double));
	if (q) free(q); q = (double *)calloc(nColumns, sizeof(double));

}


void ADMM::Compute(int nRows, int nColumns, double *A, double *y, double *out, double mu, double lambda, int ite)
{

	double **B = Alloc2Dim(nRows, nColumns);

	for (int i = 0; i < nRows; i++){
		for (int j = 0; j < nColumns; j++){
			B[i][j] = A[nRows * j + i];
		}
	}

	// Initialize solver state.
	Init(nRows, nColumns, B, y, mu, lambda);

	// Run the L1 reconstruction step.
	Optimize(nRows, nColumns, B, y, out, mu, lambda, ite);

	Free2Dim(B);

}


void ADMM::Optimize(int nRows, int nColumns, double **A, double *y, double *out, double mu, double lambda, int ite)
{

	// Append debug output.
	ofstream fout;
	fout.open( "Debug.txt", ios::app);
	if (!fout.is_open()) { return; }

	fout << "Call OK, ";


	// Perform the requested number of update iterations.
	for (int n = 0; n < ite; n++){

		// Update x.
		// Compute q.
		for (int i = 0; i < nColumns; i++){
			q[i] = Louo[i] / lambda + mu * z[i] - h[i];
		}

		// Solve the update.
		for (int i = 0; i < nColumns; i++){
			double term = 0;
			for (int k = 0; k < nColumns; k++)
				term = term + inv_P[i][k] * q[k];
			x[i] = term;
		}

		// Update z.
		for (int i = 0; i < nColumns; i++){
			z[i] = SoftThreshold((x[i] + h[i] / mu), 1.0 / mu);
		}

		// Update h.
		for (int i = 0; i < nColumns; i++){
			h[i] = h[i] + mu * (x[i] - z[i]);
		}

	}

	// Store the final solution.
	for (int i = 0; i < nColumns; i++){
		out[i] = x[i];
	}

	fout << "Optimize OK, ";
	fout.close();

}


double ADMM::SoftThreshold(double r, double Threshold)
{

	double z = 0.0;

	if (r > Threshold) z = r - Threshold;
	else if (r < -Threshold) z = r + Threshold;

	return z;

}
