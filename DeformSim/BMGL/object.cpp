/////////////////////////////////////////////////////////////////////////////
//
// matrix.h - Biomedical Graphics Library 
// Copyright(C) 2006-2008  M.Nakao  All rights reserved.
//
// E-Mail : meg@is.naist.jp
//
/////////////////////////////////////////////////////////////////////////////

#include "stdafx.h"
#include "object.h"

extern bool g_useSolverLU;

Object::Object()
{
	isDispVertex = false;
	isDispLine = false;
	isDispSurface = false;
	isDispVolume = false;

	nNode = 0;
	nLine = 0;
	nTriangle = 0;
	nTetra = 0;

	vertex = 0;
	line = 0;
	triangle = 0;
	tetra = 0;
	type = 0;

	nMatrixNode = 0;
	matrixNode = 0;
	checkList = 0;
	luPivot = 0;

	K = 0;
	L = 0;

	A = 0;
	b = 0;

	f = 0;
	u = 0;

	tetraPos = 0;
	tetraIndex = 0;

	m_count = 0;

	center.Init();
	area = 0.0f;
	volume = 0.0f;
	
	omega = 1.0f;
	lambda = 1.0f;

	flag = false;
	useDirectSolver = false;
}

Object::~Object()
{
	Clear();
}

void Object::Clear()
{
	if (vertex) delete[] vertex;
	if (line) delete[] line;
	if (triangle) delete[] triangle;

	if (K){
		for (int i = 0; i < nTetra; i++) {
			if (tetra[i].Ke) { Free2Dim(tetra[i].Ke); tetra[i].Ke = 0; }
			if (tetra[i].Se) { Free2Dim(tetra[i].Se); tetra[i].Se = 0; }
		}
	}

	if (tetra) delete[] tetra;

	if (K) Free2Dim(K);
	if (L) Free2Dim(L);

	if (f) free(f);
	if (u) free(u);

	if (A) Free2Dim(A);
	if (b) free(b);

	if (matrixNode) delete[] matrixNode;
	if (checkList) delete[] checkList;
	if (luPivot) delete[] luPivot;

	if (tetraPos) delete[] tetraPos;
	if (tetraIndex) delete[] tetraIndex;

	nNode = 0;
	nLine = 0;
	nTriangle = 0;
	nTetra = 0;

	vertex = 0;
	line = 0;
	triangle = 0;
	tetra = 0;

	nMatrixNode = 0;
	matrixNode = 0;
	checkList = 0;
	luPivot = 0;

	tetraPos = 0;
	tetraIndex = 0;

	K = 0;
	L = 0;

	f = 0;
	u = 0;

	A = 0;
	b = 0;

	omega = 1.0f;
	lambda = 1.0f;
	flag = false;
	useDirectSolver = false;
}
void Object::ReleaseAssemblyScratch()
{
	if (tetra)
	{
		for (int i = 0; i < nTetra; ++i)
		{
			if (tetra[i].Ke) { Free2Dim(tetra[i].Ke); tetra[i].Ke = 0; }
			if (tetra[i].Se) { Free2Dim(tetra[i].Se); tetra[i].Se = 0; }
		}
	}

	if (A) { Free2Dim(A); A = 0; }
	if (b) { free(b); b = 0; }
	if (tetraPos) { delete[] tetraPos; tetraPos = 0; }
	if (tetraIndex) { delete[] tetraIndex; tetraIndex = 0; }
}

void Object::ReleaseSolverState()
{
	if (matrixNode) { delete[] matrixNode; matrixNode = 0; }
	if (checkList) { delete[] checkList; checkList = 0; }
	if (luPivot) { delete[] luPivot; luPivot = 0; }
	if (K) { Free2Dim(K); K = 0; }
	if (L) { Free2Dim(L); L = 0; }
	if (f) { free(f); f = 0; }
	if (u) { free(u); u = 0; }
	nMatrixNode = 0;
	useDirectSolver = false;
}
double **Object::Alloc2Dim(int  nRows, int nColumns)
{
	// Array[i][j]: column i and row j (column-major format)
	double **Array;

	Array = (double **)calloc(nRows, sizeof(double *));
	if (!Array) return nullptr;

	size_t totalElements = static_cast<size_t>(nRows) * static_cast<size_t>(nColumns);
	Array[0] = (double*)calloc(totalElements, sizeof(double));
	if (!Array[0]) {
		free(Array);
		return nullptr;
	}

	for (int i = 0; i < nRows; i++)  Array[i] = Array[0] + i * nColumns;
	return (double **)Array;

}
bool Object::CloneMatrixStateFrom(const Object& source)
{
	if (&source == this) return true;
	if (nNode != source.nNode) return false;

	ReleaseSolverState();

	nMatrixNode = source.nMatrixNode;
	useDirectSolver = source.useDirectSolver;
	if (nMatrixNode <= 0)
	{
		return true;
	}
	if (!source.matrixNode || !source.checkList || !source.K || !source.L)
	{
		ReleaseSolverState();
		return false;
	}

	int nOrder = nMatrixNode * 3;
	size_t matrixSize = static_cast<size_t>(nOrder) * static_cast<size_t>(nOrder);

	matrixNode = new int[nMatrixNode];
	memcpy(matrixNode, source.matrixNode, sizeof(int) * static_cast<size_t>(nMatrixNode));

	checkList = new int[nNode];
	memcpy(checkList, source.checkList, sizeof(int) * static_cast<size_t>(nNode));

	K = Alloc2Dim(nOrder, nOrder);
	L = Alloc2Dim(nOrder, nOrder);
	if (!K || !L)
	{
		ReleaseSolverState();
		return false;
	}
	memcpy(K[0], source.K[0], sizeof(double) * matrixSize);
	memcpy(L[0], source.L[0], sizeof(double) * matrixSize);

	if (source.luPivot)
	{
		luPivot = new int[nOrder];
		memcpy(luPivot, source.luPivot, sizeof(int) * static_cast<size_t>(nOrder));
	}

	f = (double*)calloc(static_cast<size_t>(nOrder), sizeof(double));
	u = (double*)calloc(static_cast<size_t>(nOrder), sizeof(double));
	if (!f || !u)
	{
		ReleaseSolverState();
		return false;
	}

	return true;
}

void Object::ComputeMatrixK(void)
{
	useDirectSolver = false;
	if (luPivot) { delete[] luPivot; luPivot = 0; }

	// Update Boundary Condition
	nMatrixNode = 0;
	if (checkList) delete[] checkList;
	checkList = new int[nNode];

	for (int i = 0; i<nNode; i++){
		if (!vertex[i].isFreeze) { checkList[i] = nMatrixNode;  nMatrixNode++; }
		else { checkList[i] = -1; }
	}

	if (nMatrixNode == nNode) {
		if (checkList) { delete[] checkList; checkList = 0; }
		if (matrixNode) { delete[] matrixNode; matrixNode = 0; }
		if (K) { Free2Dim(K); K = 0; }
		if (L) { Free2Dim(L); L = 0; }
		if (f) { free(f); f = 0; }
		if (u) { free(u); u = 0; }
		if (luPivot) { delete[] luPivot; luPivot = 0; }
		nMatrixNode = 0;
		useDirectSolver = false;
		return;
	}

	int m = 0;
	if (matrixNode) delete[] matrixNode;
	matrixNode = new int[nMatrixNode];

	for (int i = 0; i<nNode; i++){
		if (!vertex[i].isFreeze) { matrixNode[m] = i; m++; }
	}


	// Compute Matrix K
	if (K) Free2Dim(K);
	K = Alloc2Dim(nMatrixNode * 3, nMatrixNode * 3);

	// Compute Ke Matrix
	for (int i = 0; i<nTetra; i++) {
		if (tetra[i].Ke) Free2Dim(tetra[i].Ke);
		if (tetra[i].Se) Free2Dim(tetra[i].Se);
		tetra[i].Ke = Alloc2Dim(12, 12);
		tetra[i].Se = Alloc2Dim(6, 12);
		ComputeMatrixKe(i);
	}

	for (int k = 0; k<nTetra; k++)	{

		// Assemble K matrix
		for (int i = 0; i<4; i++) {
			if (vertex[tetra[k].set[i]].isFreeze) continue;
			int ki = checkList[tetra[k].set[i]] * 3;

			for (int j = 0; j < 4; j++){
				if (vertex[tetra[k].set[j]].isFreeze) continue;
				int kj = checkList[tetra[k].set[j]] * 3;

				for (int p = 0; p < 3; p++){
					for (int q = 0; q < 3; q++){
						K[kj + q][ki + p] += tetra[k].Ke[j * 3 + q][i * 3 + p];
					}
				}
			}
		}

	}


	// Compute L (inverse K) matrix or keep LU factors for direct solve
	if (L) Free2Dim(L);
	L = Alloc2Dim(nMatrixNode * 3, nMatrixNode * 3);
	memcpy(L[0], K[0], sizeof(double)*nMatrixNode*nMatrixNode * 9);

	int nOrder = nMatrixNode * 3;
	int info = 0;

	auto build_inverse_path = [&]()
	{
		int nWork = nMatrixNode * 64;
		double *work = new double[nWork];
		int *ipiv = new int[nOrder];

		memcpy(L[0], K[0], sizeof(double) * static_cast<size_t>(nOrder) * static_cast<size_t>(nOrder));
		DGETRF(&nOrder, &nOrder, &L[0][0], &nOrder, &ipiv[0], &info);
		DGETRI(&nOrder, &L[0][0], &nOrder, &ipiv[0], &work[0], &nWork, &info);

		delete[] ipiv;
		delete[] work;
		useDirectSolver = false;
		if (luPivot) { delete[] luPivot; luPivot = 0; }
	};

	if (g_useSolverLU)
	{
		luPivot = new int[nOrder];
		DGETRF(&nOrder, &nOrder, &L[0][0], &nOrder, &luPivot[0], &info);
		if (info == 0)
		{
			useDirectSolver = true;
		}
		else
		{
			printf("Warning: SIM2LEARN_SOLVER_USE_LU factorization failed (info=%d), falling back to inverse path\n", info);
			build_inverse_path();
		}
	}
	else
	{
		build_inverse_path();
	}

	if (f) free(f);
	if (u) free(u);

	size_t vectorSize = static_cast<size_t>(nMatrixNode) * 3;
	f = (double*)calloc(vectorSize, sizeof(double));
	u = (double*)calloc(vectorSize, sizeof(double));

}
void Object::ComputeMatrixKe(int num)
{
	double **D;
	double **B;
	double **BD;
	double detJ;

	D = Alloc2Dim(6, 6);
	B = Alloc2Dim(6, 12);
	BD = Alloc2Dim(12, 6);

	ComputeMatrixD(D, tetra[num].young, tetra[num].poisson);
	ComputeMatrixB(B, detJ, num);
	tetra[num].volume = (float)detJ / 6.0f;

	// Create Ke and Se matrix. [Ke] = [B]^T*[D]*[B]*Ve / 6,  [Se] = [D][B]


	// STEP 1. [BD] = [B]^T[D]Ve/6
	for (int i1 = 0; i1 < 3; i1++)
		for (int i2 = 0; i2 < 3; i2++)
		{
			int ii = i1 + 3;
			BD[i1 + 0][i2] = B[i1][i1 + 0] * D[i1][i2] * tetra[num].volume;
			BD[i1 + 3][i2] = B[i1][i1 + 3] * D[i1][i2] * tetra[num].volume;
			BD[i1 + 6][i2] = B[i1][i1 + 6] * D[i1][i2] * tetra[num].volume;
			BD[i1 + 9][i2] = B[i1][i1 + 9] * D[i1][i2] * tetra[num].volume;

			BD[i2 + 0][ii] = B[ii][i2 + 0] * D[ii][ii] * tetra[num].volume;
			BD[i2 + 3][ii] = B[ii][i2 + 3] * D[ii][ii] * tetra[num].volume;
			BD[i2 + 6][ii] = B[ii][i2 + 6] * D[ii][ii] * tetra[num].volume;
			BD[i2 + 9][ii] = B[ii][i2 + 9] * D[ii][ii] * tetra[num].volume;
		}


	// STEP 2. [Ke] = [BD][B]
	for (int i3 = 0; i3 < 4; i3++)
		for (int i2 = 0; i2 < 4; i2++)
			for (int i1 = 0; i1 < 3; i1++)
			{
				tetra[num].Ke[i1 + i3 * 3][0 + i2 * 3] += BD[i1 + i3 * 3][0] * B[0][0 + i2 * 3];
				tetra[num].Ke[i1 + i3 * 3][1 + i2 * 3] += BD[i1 + i3 * 3][1] * B[1][1 + i2 * 3];
				tetra[num].Ke[i1 + i3 * 3][2 + i2 * 3] += BD[i1 + i3 * 3][2] * B[2][2 + i2 * 3];
			}

	for (int i1 = 0; i1 < 12; i1++)
		for (int i2 = 0; i2 < 12; i2++)
			for (int i3 = 3; i3 < 6; i3++)
				tetra[num].Ke[i1][i2] += BD[i1][i3] * B[i3][i2];


	// STEP 3. [Se] = [D][B] 
	for (int i1 = 0; i1<6; i1++)
		for (int i2 = 0; i2<12; i2++)
			for (int i3 = 0; i3<6; i3++)
				tetra[num].Se[i1][i2] += D[i1][i3] * B[i3][i2];


	Free2Dim(B);
	Free2Dim(D);
	Free2Dim(BD);

}

//========================================================================================================
//	Function: ComputeMatrixD
//	Class : Object
//	Status : Private
//	Parameter : Young's Modulus E, Poisson's Ratio v	
//  Return: stress-strain matrix D (size: 6x6)
//--------------------------------------------------------------------------------------------------------
//  Create D for the stress-strain relation sigma = D * epsilon.
//========================================================================================================
void Object::ComputeMatrixD(double **D, double E, double v)
{
	double  mm = E * (1.0 - v) / ((1.0 + v) * (1.0 - 2.0 * v));
	double  nn = E *     v / ((1.0 + v) * (1.0 - 2.0 * v));
	double  oo = E / ((1.0 + v) * 2.0);

	// Create D Matrix
	D[0][0] = mm; D[1][0] = nn; D[2][0] = nn; /*    0    */ /*    0    */ /*    0    */
	D[0][1] = nn; D[1][1] = mm; D[2][1] = nn; /*    0    */ /*    0    */ /*    0    */
	D[0][2] = nn; D[1][2] = nn; D[2][2] = mm; /*    0    */ /*    0    */ /*    0    */
	/*    0    */ /*    0    */ /*    0    */ D[3][3] = oo; /*    0    */ /*    0    */
	/*    0    */ /*    0    */ /*    0    */ /*    0    */ D[4][4] = oo; /*    0    */
	/*    0    */ /*    0    */	/*    0    */ /*    0    */	/*    0    */ D[5][5] = oo;


}

//========================================================================================================
//	Function: ComputeMatrixB
//	Class : Object
//	Status : Private
//	Parameter : Young's Modulus E, Poisson's Ratio v, Tetrahedral element id 	
//  Return: shape matrix B (size: 6x12)
//--------------------------------------------------------------------------------------------------------
//  Create B for the strain-displacement relation epsilon = B * u.
//  B = [B1, B2, ... B4], where Bi = A * Ni.
//
//	   [  d/dx   0    0   ]
//     [   0    d/dy  0   ]
//     [   0     0   d/dz ]      [ N1 0  0  | N2 0  0  |N3 0  0  | N4 0  0  ]
//	A =[  d/dy  d/dx  0   ]   N =[ 0  N1 0  | 0  N2 0  |0  N3 0  | 0  N4 0  ]
//     [   0    d/dz d/dy ]      [ 0  0  N1 | 0  0  N2 |0  0  N3 | 0  0  N4 ]
//     [  d/dz   0   d/dx ]
//
//	            [ dNi/dx    0       0    ]
//              [   0     dNi/dy    0    ]
//  Bi = A*Ni = [   0       0     dNi/dz ]
//              [ dNi/dy  dNi/dx    0    ]
//              [   0     dNi/dz  dNi/dy ]
//	            [ dNi/dz    0     dNi/dx ]		d/dx,d/dy,d/dz : partial differential
//
//	J*Ni = dN
//
// [ dx/di dy/di dz/di ][dNi/dx]   [dNi/di]
//	[ dx/dj dy/dj dz/dj ][dNi/dy] = [dNi/dj]
//	[ dx/dk dy/dk dz/dk ][dNi/dz]   [dNi/dk]
//
//  such as  J = dN * X
//
//    [ dx/di dy/di dz/di ]   [dN1/di dN2/di dN3/di dN4/di][x1 y1 z1 ]
//	J =[ dx/dj dy/dj dz/dj ] = [dN1/dj dN2/dj dN3/dj dN4/dj][x2 y2 z2 ]
//	   [ dx/dk dy/dk dz/dk ]   [dN1/dk dN2/dk dN3/dk dN4/dk][x3 y3 z3 ]
//															[x4 y4 z4 ]
//							                             
//========================================================================================================
void Object::ComputeMatrixB(double **B, double &detJ, int num)
{

	double **Differential_N;		// Differential matrix of shape function
	double **Jacobian;				// Jacobi matrix

	Differential_N = Alloc2Dim(4, 3);
	Jacobian = Alloc2Dim(3, 3);

	// Set dN matrix
	Differential_N[0][0] = 1.0; Differential_N[1][0] = 0.0;  Differential_N[2][0] = 0.0; Differential_N[3][0] = -1.0;
	Differential_N[0][1] = 0.0; Differential_N[1][1] = 1.0;  Differential_N[2][1] = 0.0; Differential_N[3][1] = -1.0;
	Differential_N[0][2] = 0.0; Differential_N[1][2] = 0.0;  Differential_N[2][2] = 1.0; Differential_N[3][2] = -1.0;

	// jacobi = N_global * X
	Matrix3x3 jacobi;
	jacobi.m[0][0] = 0.0f; jacobi.m[1][1] = 0.0f; jacobi.m[2][2] = 0.0f;
	for (int w = 0; w < 3; w++)
		for (int v = 0; v < 4; v++){
			jacobi.m[0][w] += (float)Differential_N[v][w] * vertex[tetra[num].set[v]].coord.x;
			jacobi.m[1][w] += (float)Differential_N[v][w] * vertex[tetra[num].set[v]].coord.y;
			jacobi.m[2][w] += (float)Differential_N[v][w] * vertex[tetra[num].set[v]].coord.z;
		}

	// Set determinant of J
	detJ = jacobi.m[0][0] * jacobi.m[1][1] * jacobi.m[2][2] +
		jacobi.m[1][0] * jacobi.m[2][1] * jacobi.m[0][2] +
		jacobi.m[2][0] * jacobi.m[1][2] * jacobi.m[0][1] -
		jacobi.m[2][0] * jacobi.m[1][1] * jacobi.m[0][2] -
		jacobi.m[1][0] * jacobi.m[0][1] * jacobi.m[2][2] -
		jacobi.m[0][0] * jacobi.m[1][2] * jacobi.m[2][1];

	// Compute Inv(jacobi)
	jacobi.Inverse();

	//	Ni = Inv(jacobi) * N_grobal
	double **N;
	N = Alloc2Dim(4, 3);

	for (int i = 0; i<3; i++){
		N[0][i] = jacobi.m[0][i];	N[1][i] = jacobi.m[1][i]; N[2][i] = jacobi.m[2][i]; N[3][i] = -N[0][i] - N[1][i] - N[2][i];
	}

	// Set B matrix
	for (int m = 0; m < 4; m++){
		int ii = m * 3;

		// Bi (i = 0 ~ 3)
		B[0][0 + ii] = N[m][0];  /*       0       */	 /*       0       */  B[3][0 + ii] = N[m][1];	/*       0       */	  B[5][0 + ii] = N[m][2];
		/*       0       */  B[1][1 + ii] = N[m][1];	 /*       0       */  B[3][1 + ii] = N[m][0];	B[4][1 + ii] = N[m][2];  /*       0       */
		/*       0       */   /*       0       */	B[2][2 + ii] = N[m][2];  /*       0       */	B[4][2 + ii] = N[m][1]; B[5][2 + ii] = N[m][0];
	}

	Free2Dim(N);
	Free2Dim(Differential_N);
	Free2Dim(Jacobian);

}


//========================================================================================================
//	Function : ComputeMatrixT
//	Class : Object
//	Status : Private
//	Parameter : Tetrahedral element id	
//  Return : Transform matrix T
//--------------------------------------------------------------------------------------------------------
//      [q1x q2x q3x q4x]     [p1x p2x p3x p4x]
//  T = [q1y q2y q3y q4y]* Inv[p1y p2y p3y p4y]
//      [q1z q2z q3z q4z]     [p1z p2z p3z p4z]
//      [ 1   1   1   1 ]     [ 1   1   1   1 ] 
//========================================================================================================
void Object::ComputeMatrixT(Matrix4x4 &T, int num)
{

	Matrix4x4 P, Q;

	for (int i = 0; i<4; i++){
		// P : initial position matrix
		P.m[0][i] = vertex[tetra[num].set[i]].coord.x;
		P.m[1][i] = vertex[tetra[num].set[i]].coord.y;
		P.m[2][i] = vertex[tetra[num].set[i]].coord.z;
	}

	for (int i = 0; i<4; i++){
		// Q : current position matrix
		Q.m[0][i] = vertex[tetra[num].set[i]].new_coord.x;
		Q.m[1][i] = vertex[tetra[num].set[i]].new_coord.y;
		Q.m[2][i] = vertex[tetra[num].set[i]].new_coord.z;
	}

	for (int i = 0; i<4; i++){
		P.m[3][i] = Q.m[3][i] = 1.0f;
	}

	// T = Q * Inv(P)
	P.Inverse();
	T = Q * P;

}


void Object::Force()
{

	// Register vertices marked as application points.
	int nTrans = 0;
	int *trans = new int[nNode];
	for (int i = 0; i < nNode; i++){
		if (vertex[i].isSelect) {
			trans[nTrans] = i;
			nTrans++;
		}
	}

	double *uc = new double[nTrans * 3];	// Prescribed displacement at each application point
	double *fc = new double[nTrans * 3];	// Solved external force at each application point
	int *mtrans = new int[nTrans];			// Indices in the stiffness matrix

	for (int i = 0; i < nNode; i++){
		// Initialize external forces.
		vertex[i].force.Init();
	}

	for (int i = 0; i < nTrans; i++){
		// Assign prescribed displacements to the selected vertices.
		uc[i * 3 + 0] = (double)vertex[trans[i]].new_coord.x - (double)vertex[trans[i]].coord.x;
		uc[i * 3 + 1] = (double)vertex[trans[i]].new_coord.y - (double)vertex[trans[i]].coord.y;
		uc[i * 3 + 2] = (double)vertex[trans[i]].new_coord.z - (double)vertex[trans[i]].coord.z;
		mtrans[i] = checkList[trans[i]];
	}

	// Build the submatrix.
	int	nInc = 1;
	int	nOrder = nTrans * 3;
	int	three = 3;
	int *ipiv;
	int flag;
	ipiv = new int[nOrder];
	double **Lcc = (double **)Alloc2Dim(nOrder, nOrder);;

	for (int i = 0; i < 3; i++){
		for (int j = 0; j < nTrans; j++){
			for (int k = 0; k < nTrans; k++){
				// Extract submatrix Lcc from the global inverse stiffness matrix L.
				DCOPY(&three, &L[mtrans[j] * 3 + i][mtrans[k] * 3], &nInc, &Lcc[i + j * 3][k * 3], &nInc);
			}
		}
	}

	double dAlpha = 1.0;
	double dBeta = 0.0;
	char cTrans = 'N';

	memcpy(fc, uc, sizeof(double)*nTrans * 3);

	// LU factorization
	DGETRF(&nOrder, &nOrder, &Lcc[0][0], &nOrder, &ipiv[0], &flag);

	// Solve the linear system.
	DGETRS(&cTrans, &nOrder, &nInc, &Lcc[0][0], &nOrder, &ipiv[0], &fc[0], &nOrder, &flag);

	// Store the solved external forces.
	for (int i = 0; i < nTrans; i++){
		vertex[trans[i]].force.SetVector((float)fc[i * 3], (float)fc[i * 3 + 1], (float)fc[i * 3 + 2]);
	}

	delete[] ipiv;
	delete[] uc;
	delete[] fc;
	delete[] mtrans;
	delete[] trans;
	Free2Dim(Lcc);

}


void Object::Deform()
{
	if (nMatrixNode <= 0 || !matrixNode || !f || !u || !L) return;
	if (useDirectSolver && g_useSolverLU && !luPivot) { useDirectSolver = false; }

	// Set force vector (freezed vertex is removed in matrix calculation)
	for (int i = 0; i<nMatrixNode; i++)
	{
		f[i * 3 + 0] = vertex[matrixNode[i]].force.x;
		f[i * 3 + 1] = vertex[matrixNode[i]].force.y;
		f[i * 3 + 2] = vertex[matrixNode[i]].force.z;
	}

	int	nOrder = nMatrixNode * 3;
	int nInc = 1;
	char cTrans = 'N';
	double	dAlpha = 1.0;
	double	dBeta = 0.0;

	if (useDirectSolver && g_useSolverLU)
	{
		memcpy(u, f, sizeof(double) * static_cast<size_t>(nOrder));
		int info = 0;
		DGETRS(&cTrans, &nOrder, &nInc, &L[0][0], &nOrder, &luPivot[0], &u[0], &nOrder, &info);
		if (info != 0)
		{
			printf("Warning: SIM2LEARN_SOLVER_USE_LU solve failed (info=%d), falling back to inverse path\n", info);
			int nWork = nMatrixNode * 64;
			double *work = new double[nWork];
			int *ipiv = new int[nOrder];
			info = 0;
			memcpy(L[0], K[0], sizeof(double) * static_cast<size_t>(nOrder) * static_cast<size_t>(nOrder));
			DGETRF(&nOrder, &nOrder, &L[0][0], &nOrder, &ipiv[0], &info);
			DGETRI(&nOrder, &L[0][0], &nOrder, &ipiv[0], &work[0], &nWork, &info);
			DGEMV(&cTrans, &nOrder, &nOrder, &dAlpha, &L[0][0], &nOrder, &f[0], &nInc, &dBeta, &u[0], &nInc);
			delete[] ipiv;
			delete[] work;
			useDirectSolver = false;
		}
	}
	else
	{
		DGEMV(&cTrans, &nOrder, &nOrder, &dAlpha, &L[0][0], &nOrder, &f[0], &nInc, &dBeta, &u[0], &nInc);
	}

	// Update coordinates
	for (int i = 0; i<nMatrixNode; i++)
	{
		vertex[matrixNode[i]].new_coord.x = vertex[matrixNode[i]].coord.x + (float)u[i * 3 + 0];
		vertex[matrixNode[i]].new_coord.y = vertex[matrixNode[i]].coord.y + (float)u[i * 3 + 1];
		vertex[matrixNode[i]].new_coord.z = vertex[matrixNode[i]].coord.z + (float)u[i * 3 + 2];
	}

}
bool Object::ReadObject(const std::string& filepath)
{

	int i, j, num;
	char buf[256], dummy[256];

	ifstream fin;
	fin.open(filepath, ios::in);
	if (!fin.is_open()) { return false; }

	while (fin.getline(buf, sizeof(buf)))
	{
		// Reading headers
		if (strstr(buf, "nVertex ")) {
			if (sscanf(buf, "%s %d", &dummy, &num) == 2) { InitVertex(num); }
			continue;
		}
		if (strstr(buf, "nLine ")) {
			if (sscanf(buf, "%s %d", &dummy, &num) == 2) { InitLine(num); }
			continue;
		}
		if (strstr(buf, "nTriangle ")) {
			if (sscanf(buf, "%s %d", &dummy, &num) == 2) { InitTriangle(num); }
			continue;
		}
		if (strstr(buf, "nTetrahedron ")) {
			if (sscanf(buf, "%s %d", &dummy, &num) == 2) { InitTetrahedron(num); }
			break;
		}
	}

	while (fin.getline(buf, sizeof(buf))){ if (strstr(buf, "# Data ")) break; }

	while (!strstr(buf, "@1")){ fin >> buf; if (fin.eof()) return false; }

	nMatrixNode = 0;
	checkList = new int[nNode];

	for (i = 0; i< nNode; i++)
	{
		fin >> vertex[i].coord.x >> vertex[i].coord.y >> vertex[i].coord.z
			>> vertex[i].isSurface >> vertex[i].isFreeze >> vertex[i].isSelect;

		vertex[i].new_coord = vertex[i].coord;
		vertex[i].cur_coord = vertex[i].coord;
		if (!vertex[i].isFreeze) { checkList[i] = nMatrixNode;  nMatrixNode++; }
		else { checkList[i] = -1; }
	}

	int m = 0;
	matrixNode = new int[nMatrixNode];

	for (i = 0; i<nNode; i++)
	{
		if (!vertex[i].isFreeze) { matrixNode[m] = i; m++; }
	}

	while (!strstr(buf, "@2")){ fin >> buf; if (fin.eof()) return false; }

	for (i = 0; i< nLine; i++){
		Vector3f vec;
		int set[2] = { 0, 0 };
		for (j = 0; j<2; j++){ fin >> line[i].set[j]; set[j] = line[i].set[j]; }
		vec = vertex[set[1]].coord - vertex[set[0]].coord;
		float len = vec.GetLength();
	}

	while (!strstr(buf, "@3")){ fin >> buf; if (fin.eof()) return false; }

	for (i = 0; i< nTriangle; i++){
		Vector3f vec, vec1, vec2, norm;
		int set[3] = { 0, 0, 0 };
		for (j = 0; j<3; j++){ fin >> triangle[i].set[j]; set[j] = triangle[i].set[j]; vertex[set[j]].isSurface = true; }

		vec1 = vertex[triangle[i].set[1]].coord - vertex[triangle[i].set[0]].coord;
		vec2 = vertex[triangle[i].set[2]].coord - vertex[triangle[i].set[0]].coord;
		vec = vec1.CrossProduct(vec2);
		triangle[i].area = 0.5f * vec.GetLength();

		vertex[triangle[i].set[0]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[1]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[2]].area += triangle[i].area / 3.0f;
	}

	while (!strstr(buf, "@4")){ fin >> buf; if (fin.eof()) return false; }

	for (i = 0; i< nTetra; i++){
		for (j = 0; j<4; j++){
			fin >> tetra[i].set[j];
		}
		fin >> tetra[i].young >> tetra[i].poisson;
	}

	/*
	while(!strstr(buf, "@5")){
	fin >> buf;
	if(fin.eof()) return false;
	}

	for(i=0; i< nNode; i++){
	fin >> num;
	fin >> dummy;

	vertex[i].InitNeighborVertex(num);

	for(j=0; j<vertex[i].neighborVertex.size(); j++){
	fin >> vertex[i].neighborVertex[j];
	}
	}
	*/

	fin.close();

	return true;

}

bool Object::WriteObject(const std::string& filepath)
{

	FILE *fout = fopen(filepath.c_str(), "w");
	if (!fout) { return false; }

	fprintf(fout, "# MVR Object ASCII Format 1.0\n\n");
	fprintf(fout, "nVertex %d\n", nNode);
	fprintf(fout, "nLine %d\n", nLine);
	fprintf(fout, "nTriangle %d\n", nTriangle);
	fprintf(fout, "nTetrahedron %d\n", nTetra);

	fprintf(fout, "\n");
	fprintf(fout, "Elastic 0\n");
	fprintf(fout, "RGBA Color 255 255 255 255\n");
	fprintf(fout, "Bounding Box -0.5 0.5 -0.5 0.5 -0.5 0.5");
	fprintf(fout, "\n\n");

	fprintf(fout, "Vertex{ float[3] Coord : bool[3](isSurface, isFreeze, isInside, isObserve) } @1\n");
	fprintf(fout, "Line{ int[2] VertexIndex } @2\n");
	fprintf(fout, "Triangle{ int[3] VertexIndex } @3\n");
	fprintf(fout, "Tetrahedron{ int[4] VertexIndex float[2] Young Poisson } @4\n");
	fprintf(fout, "NeighborVertex{ int neighborVertex.size() : int[neighborVertex.size()] VertexIndex } @5\n");
	fprintf(fout, "ParentLine{ int nParentLine : int[nParentLine] LineIndex } @6\n");
	fprintf(fout, "ParentTriangle{ int nParentTriangle : int[nParentTriangle] TriangleIndex } @7\n");
	fprintf(fout, "ParentTetra{ int nParentTetra : int[nParentTetra] TetraIndex } @8\n");
	fprintf(fout, "NeighborTetra{ int nNeighborTetra : int[nNeighborTetra] TetraIndex } @9\n");
	fprintf(fout, "ChildLine{ int[6] LineIndex } @10\n");
	fprintf(fout, "ChildTriangle{ int nTriangle : int[nTriangle] TriangleIndex } @11\n");

	fprintf(fout, "\n");
	fprintf(fout, "# Data section follows\n");

	fprintf(fout, "@1\n");
	for (int i = 0; i < nNode; i++)
		fprintf(fout, "%f %f %f %d %d %d\n", vertex[i].coord.x, vertex[i].coord.y, vertex[i].coord.z, vertex[i].isSurface, vertex[i].isFreeze, vertex[i].isSelect);

	fprintf(fout, "\n@2\n");
	for (int i = 0; i < nLine; i++)
		fprintf(fout, "%d %d\n", line[i].set[0], line[i].set[1]);

	fprintf(fout, "\n@3\n");
	for (int i = 0; i < nTriangle; i++)
		fprintf(fout, "%d %d %d\n", triangle[i].set[0], triangle[i].set[1], triangle[i].set[2]);

	fprintf(fout, "\n@4\n");
	for (int i = 0; i < nTetra; i++)
		fprintf(fout, "%d %d %d %d %f %f\n", tetra[i].set[0], tetra[i].set[1], tetra[i].set[2], tetra[i].set[3], tetra[i].young, tetra[i].poisson);

	fclose(fout);

	return true;

}

bool Object::WritePLY(const std::string& filepath)
{
	FILE *fout = fopen(filepath.c_str(), "w");
	if (!fout) { return false; }

	fprintf(fout, "ply\n");
	fprintf(fout, "format ascii 1.0\n");
	fprintf(fout, "comment VCGLIB generated\n");
	fprintf(fout, "element vertex %d\n", nNode);
	fprintf(fout, "property float x\n");
	fprintf(fout, "property float y\n");
	fprintf(fout, "property float z\n");
	fprintf(fout, "element face %d\n", nTriangle);
	fprintf(fout, "property list uchar int vertex_indices\n");
	fprintf(fout, "end_header\n");

	for (int i = 0; i< nNode; i++){
		fprintf(fout, "%f %f %f\n", vertex[i].new_coord.x, vertex[i].new_coord.y, vertex[i].new_coord.z);
	}

	for (int i = 0; i < nTriangle; i++){
		fprintf(fout, "3 %d %d %d\n", triangle[i].set[0], triangle[i].set[1], triangle[i].set[2]);
	}

	fclose(fout);

	return true;
}


void Object::ComputeQualityTetrahedralMesh(char str[])
{

	tetgenio in, out;
	tetgenio::facet *f;
	tetgenio::polygon *p;

	// Create Tetrahedral Elements using tetgen library
	in.firstnumber = 1;
	in.numberofpoints = nNode;
	in.pointlist = new REAL[in.numberofpoints * 3];

	in.numberoffacets = nTriangle;
	in.facetlist = new tetgenio::facet[in.numberoffacets];
	in.trifacemarkerlist = new int[in.numberoffacets];


	for (int i = 0; i<in.numberofpoints; i++)
	{
		in.pointlist[i * 3 + 0] = vertex[i].new_coord.x;
		in.pointlist[i * 3 + 1] = vertex[i].new_coord.y;
		in.pointlist[i * 3 + 2] = vertex[i].new_coord.z;
	}

	for (int i = 0; i < nTriangle; i++)
	{
		f = &in.facetlist[i];
		f->numberofpolygons = 1;
		f->polygonlist = new tetgenio::polygon[f->numberofpolygons];
		f->numberofholes = 0;
		f->holelist = NULL;
		p = &f->polygonlist[0];
		p->numberofvertices = 3;
		p->vertexlist = new int[p->numberofvertices];
		p->vertexlist[0] = triangle[i].set[0] + 1;
		p->vertexlist[1] = triangle[i].set[1] + 1;
		p->vertexlist[2] = triangle[i].set[2] + 1;
	}
	
	//	in.save_nodes("test");
	//	in.save_poly("test");

	// Create tetraheda in silence mode
	char quietStr[10];
	sprintf(quietStr, "%sQ", str);
	tetrahedralize(quietStr, &in, &out);
	
	// temporary output files by tetgen
	//	out.save_nodes("temp");
	//	out.save_elements("temp");

	int pre_nNode = nNode;
	Vertex *pre_v = new Vertex[pre_nNode];

	for (int i = 0; i < nNode; i++){
		pre_v[i].new_coord = vertex[i].new_coord;
		pre_v[i].coord = vertex[i].coord;
		pre_v[i].isFreeze = vertex[i].isFreeze;
		pre_v[i].isSelect = vertex[i].isSelect;
		pre_v[i].isSurface = vertex[i].isSurface;
	}

	InitVertex(out.numberofpoints);

	for (int i = 0; i < pre_nNode; i++){
		vertex[i].new_coord = pre_v[i].new_coord;
		vertex[i].coord = pre_v[i].coord;
		vertex[i].isFreeze = pre_v[i].isFreeze;
		vertex[i].isSelect = pre_v[i].isSelect;
		vertex[i].isSurface = pre_v[i].isSurface;
	}

	for (int i = pre_nNode; i < nNode; i++){
		vertex[i].new_coord.x = (float)out.pointlist[i * 3 + 0];
		vertex[i].new_coord.y = (float)out.pointlist[i * 3 + 1];
		vertex[i].new_coord.z = (float)out.pointlist[i * 3 + 2];
		vertex[i].coord = vertex[i].new_coord;
	}

	delete[] pre_v;

	InitTetrahedron(out.numberoftetrahedra);

	Vector3f center;
	int count = 0;

	for (int i = 0; i<nTetra; i++)
	{
		tetra[i].set[0] = out.tetrahedronlist[i * 4 + 0] - 1;
		tetra[i].set[1] = out.tetrahedronlist[i * 4 + 3] - 1;
		tetra[i].set[2] = out.tetrahedronlist[i * 4 + 2] - 1;
		tetra[i].set[3] = out.tetrahedronlist[i * 4 + 1] - 1;

		center = (vertex[tetra[i].set[0]].coord +
			vertex[tetra[i].set[1]].coord +
			vertex[tetra[i].set[2]].coord +
			vertex[tetra[i].set[3]].coord) / 4.0f;

	}

	// Create line information
	int nline = 0;
	Line *temp_line = new Line[nNode * 32];
	bool line_flag;
	bool neighbor_flag;

	for (int i = 0; i < nTetra; i++){

		for (int j = 0; j<4; j++){

			for (int m = 0; m<4; m++){
				if (j != m){

					line_flag = false;

					for (int n = 0; n < nline; n++){
						if ((temp_line[n].set[0] == tetra[i].set[j] && temp_line[n].set[1] == tetra[i].set[m]) ||
							(temp_line[n].set[0] == tetra[i].set[m] && temp_line[n].set[1] == tetra[i].set[j]) ){
							line_flag = true;
						}
					}

					if (line_flag == false){
						temp_line[nline].set[0] = tetra[i].set[j];
						temp_line[nline].set[1] = tetra[i].set[m];

						nline++;
					}

					neighbor_flag = false;

					for (int n = 0; n < vertex[tetra[i].set[j]].neighborVertex.size(); n++){
						if (vertex[tetra[i].set[j]].neighborVertex[n] == tetra[i].set[m]){
							neighbor_flag = true;
							break;
						}
					}

					if (neighbor_flag == false){
						vertex[tetra[i].set[j]].neighborVertex.push_back(tetra[i].set[m]);
					}

				}
			}
		}
	}

	// Register line information
	InitLine(nline);
	for (int i = 0; i<nLine; i++)
	{
		line[i].set[0] = temp_line[i].set[0];
		line[i].set[1] = temp_line[i].set[1];
		Vector3f vec = vertex[line[i].set[1]].coord - vertex[line[i].set[0]].coord;
		line[i].length = vec.GetLength();

	}

	delete[] temp_line;


	// Register triangle information
	InitTriangle(out.numberoftrifaces);

	for (int i = 0; i<nTriangle; i++)
	{
		triangle[i].set[0] = out.trifacelist[i * 3 + 0] - 1;
		triangle[i].set[1] = out.trifacelist[i * 3 + 2] - 1;
		triangle[i].set[2] = out.trifacelist[i * 3 + 1] - 1;

		vertex[triangle[i].set[0]].isSurface = true;
		vertex[triangle[i].set[1]].isSurface = true;
		vertex[triangle[i].set[2]].isSurface = true;

		Vector3f vec, vec1, vec2, norm;
		vec1 = vertex[triangle[i].set[1]].coord - vertex[triangle[i].set[0]].coord;
		vec2 = vertex[triangle[i].set[2]].coord - vertex[triangle[i].set[0]].coord;
		vec = vec1.CrossProduct(vec2);
		triangle[i].area = 0.5f * vec.GetLength();

		vertex[triangle[i].set[0]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[1]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[2]].area += triangle[i].area / 3.0f;
	}

}

void Object::ComputeTetrahedralMesh()
{

	tetgenio in, out;

	// Create Tetrahedral Elements using tetgen library
	in.firstnumber = 1;
	in.numberofpoints = nNode;
	in.pointlist = new REAL[in.numberofpoints * 3];

	in.numberoffacets = 0;

	for (int i = 0; i<in.numberofpoints; i++)
	{
		in.pointlist[i * 3 + 0] = vertex[i].coord.x;
		in.pointlist[i * 3 + 1] = vertex[i].coord.y;
		in.pointlist[i * 3 + 2] = vertex[i].coord.z;
	}

	// Create tetraheda
	tetrahedralize("", &in, &out);

	InitTetrahedron(out.numberoftetrahedra);

	Vector3f center;
	int count = 0;

	for (int i = 0; i<nTetra; i++)
	{
		tetra[i].set[0] = out.tetrahedronlist[i * 4 + 0] - 1;
		tetra[i].set[1] = out.tetrahedronlist[i * 4 + 3] - 1;
		tetra[i].set[2] = out.tetrahedronlist[i * 4 + 2] - 1;
		tetra[i].set[3] = out.tetrahedronlist[i * 4 + 1] - 1;

		center = (vertex[tetra[i].set[0]].coord +
			vertex[tetra[i].set[1]].coord +
			vertex[tetra[i].set[2]].coord +
			vertex[tetra[i].set[3]].coord) / 4.0f;

	}

	// Create line information
	int nline = 0;
	Line *temp_line = new Line[nNode * 32];
	bool line_flag;
	bool neighbor_flag;

	for (int i = 0; i < nTetra; i++){

		for (int j = 0; j<4; j++){

			for (int m = 0; m<4; m++){
				if (j != m){

					line_flag = false;

					for (int n = 0; n < nline; n++){
						if ((temp_line[n].set[0] == tetra[i].set[j] && temp_line[n].set[1] == tetra[i].set[m]) ||
							(temp_line[n].set[0] == tetra[i].set[m] && temp_line[n].set[1] == tetra[i].set[j])){
							line_flag = true;
						}
					}

					if (line_flag == false){
						temp_line[nline].set[0] = tetra[i].set[j];
						temp_line[nline].set[1] = tetra[i].set[m];

						nline++;
					}

					neighbor_flag = false;

					for (int n = 0; n < vertex[tetra[i].set[j]].neighborVertex.size(); n++){
						if (vertex[tetra[i].set[j]].neighborVertex[n] == tetra[i].set[m]){
							neighbor_flag = true;
							break;
						}
					}

					if (neighbor_flag == false){
						vertex[tetra[i].set[j]].neighborVertex.push_back(tetra[i].set[m]);
					}

				}
			}
		}
	}

	// Register line information
	InitLine(nline);
	for (int i = 0; i<nLine; i++)
	{
		line[i].set[0] = temp_line[i].set[0];
		line[i].set[1] = temp_line[i].set[1];
		Vector3f vec = vertex[line[i].set[1]].coord - vertex[line[i].set[0]].coord;
		line[i].length = vec.GetLength();

	}

	delete[] temp_line;


	// Register triangle information
	InitTriangle(out.numberoftrifaces);

	for (int i = 0; i<nTriangle; i++)
	{
		triangle[i].set[0] = out.trifacelist[i * 3 + 0] - 1;
		triangle[i].set[1] = out.trifacelist[i * 3 + 2] - 1;
		triangle[i].set[2] = out.trifacelist[i * 3 + 1] - 1;

		vertex[triangle[i].set[0]].isSurface = true;
		vertex[triangle[i].set[1]].isSurface = true;
		vertex[triangle[i].set[2]].isSurface = true;

		Vector3f vec, vec1, vec2, norm;
		vec1 = vertex[triangle[i].set[1]].coord - vertex[triangle[i].set[0]].coord;
		vec2 = vertex[triangle[i].set[2]].coord - vertex[triangle[i].set[0]].coord;
		vec = vec1.CrossProduct(vec2);
		triangle[i].area = 0.5f * vec.GetLength();

		vertex[triangle[i].set[0]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[1]].area += triangle[i].area / 3.0f;
		vertex[triangle[i].set[2]].area += triangle[i].area / 3.0f;
	}

	ComputeNormal();

}


void Object::Smooth(float r)
{

	Vector3f *v = new Vector3f[nNode];

	for (int i = 0; i < nNode; i++){

		Vector3f pos, diff;
		int id;

		if (vertex[i].isSurface) {

			int num = 0;

			for (int j = 0; j < vertex[i].neighborVertex.size(); j++){
				id = vertex[i].neighborVertex[j];
				if (vertex[id].isSurface){
					pos += vertex[id].new_coord;
					num++;
				}
			}

			pos /= (float)num;
			pos = pos.SurfaceProjection(vertex[i].new_normal, vertex[i].new_coord);

			v[i] = vertex[i].new_coord * (1.0f - r) + pos * r;


		}
		else{
			for (int j = 0; j < vertex[i].neighborVertex.size(); j++){
				id = vertex[i].neighborVertex[j];
				pos += vertex[id].new_coord / (float)vertex[i].neighborVertex.size();
			}

			v[i] = vertex[i].new_coord * (1.0f - r) + pos * r;
		}
	}

	for (int i = 0; i < nNode; i++){
		vertex[i].new_coord = v[i];
	}

	delete[] v;

}


void Object::ComputeArea()
{

	for (int i = 0; i<nNode; i++) vertex[i].area = 0.0f;

	Vector3f vec[3];

	area = 0.0f;

	// Compute per-vertex normal vectors
	for (int i = 0; i<nTriangle; i++){

		int tri_vert[3];
		for (int j = 0; j<3; j++){
			tri_vert[j] = triangle[i].set[j];
		}

		vec[0] = vertex[tri_vert[1]].new_coord - vertex[tri_vert[0]].new_coord;
		vec[1] = vertex[tri_vert[2]].new_coord - vertex[tri_vert[1]].new_coord;
		vec[2] = vertex[tri_vert[0]].new_coord - vertex[tri_vert[2]].new_coord;

		triangle[i].area = vec[0].CrossProduct(vec[1]).GetLength();

		vertex[tri_vert[0]].area += triangle[i].area / 3.0f;
		vertex[tri_vert[1]].area += triangle[i].area / 3.0f;
		vertex[tri_vert[2]].area += triangle[i].area / 3.0f;

		area += triangle[i].area;

	}

}


void Object::ComputeVolume()
{

	for (int i = 0; i<nNode; i++) tetra[i].volume = 0.0f;

	Vector3f norm, vec[3];
	int id[4] = { 0, 0, 0, 0 };

	volume = 0.0f;

	for (int i = 0; i < nTetra; i++){
		
		for (int j = 0; j < 4; j++) id[j] = tetra[i].set[j];

		vec[2] = vertex[id[3]].new_coord - vertex[id[0]].new_coord;
		vec[1] = vertex[id[2]].new_coord - vertex[id[0]].new_coord;
		vec[0] = vertex[id[1]].new_coord - vertex[id[0]].new_coord;

		norm = vec[0].CrossProduct(vec[1]);
		tetra[i].volume = abs(vec[2] * norm) / 6.0f;

		volume += tetra[i].volume;
	}

}

void Object::ComputeNormal()
{
	float *weight = new float[nNode];
	Vector3f *normal = new Vector3f[nNode];
	memset(weight, 0, sizeof(float)*nNode);

	int tri_vert[3] = { 0, 0, 0 };
	Vector3f vec[3];
	float len[3] = { 0, 0, 0 };

	// Compute per-vertex normal vectors
	for (int i = 0; i<nTriangle; i++){

		for (int j = 0; j<3; j++){
			tri_vert[j] = triangle[i].set[j];
		}

		vec[0] = vertex[tri_vert[1]].new_coord - vertex[tri_vert[0]].new_coord;
		vec[1] = vertex[tri_vert[2]].new_coord - vertex[tri_vert[1]].new_coord;
		vec[2] = vertex[tri_vert[0]].new_coord - vertex[tri_vert[2]].new_coord;
		len[0] = vec[0].GetLength();
		len[1] = vec[1].GetLength();
		len[2] = vec[2].GetLength();

		triangle[i].new_normal = vec[0].CrossProduct(vec[1]);
		triangle[i].new_normal.Normalize();

		weight[tri_vert[0]] += len[0] * len[0] + len[2] * len[2];
		weight[tri_vert[1]] += len[1] * len[1] + len[0] * len[0];
		weight[tri_vert[2]] += len[2] * len[2] + len[1] * len[1];


		normal[tri_vert[0]] += triangle[i].new_normal * weight[tri_vert[0]];
		normal[tri_vert[1]] += triangle[i].new_normal * weight[tri_vert[1]];
		normal[tri_vert[2]] += triangle[i].new_normal * weight[tri_vert[2]];

	}


	for (int i = 0; i<nNode; i++){
		vertex[i].new_normal = normal[i] / weight[i];
		vertex[i].new_normal.Normalize();
	}

	delete[] weight;
	delete[] normal;

}


bool Object::CheckSelfIntersection()
{

	tetgenio in, out;
	tetgenio::facet *f;
	tetgenio::polygon *p;

	// Create Tetrahedral Elements using tetgen library
	in.firstnumber = 1;
	in.numberofpoints = nNode;
	in.pointlist = new REAL[in.numberofpoints * 3];

	in.numberoffacets = nTriangle;
	in.facetlist = new tetgenio::facet[in.numberoffacets];
	in.trifacemarkerlist = new int[in.numberoffacets];


	for (int i = 0; i<in.numberofpoints; i++)
	{
		in.pointlist[i * 3 + 0] = vertex[i].new_coord.x;
		in.pointlist[i * 3 + 1] = vertex[i].new_coord.y;
		in.pointlist[i * 3 + 2] = vertex[i].new_coord.z;
	}

	for (int i = 0; i < nTriangle; i++)
	{
		f = &in.facetlist[i];
		f->numberofpolygons = 1;
		f->polygonlist = new tetgenio::polygon[f->numberofpolygons];
		f->numberofholes = 0;
		f->holelist = NULL;
		p = &f->polygonlist[0];
		p->numberofvertices = 3;
		p->vertexlist = new int[p->numberofvertices];
		p->vertexlist[0] = triangle[i].set[0] + 1;
		p->vertexlist[1] = triangle[i].set[1] + 1;
		p->vertexlist[2] = triangle[i].set[2] + 1;
	}


	// Create tetraheda
	tetrahedralize("d", &in, &out);

	if (out.numberoftrifaces > 0) return true;  // intersect!
	else return false;

}

void Object::ComputeBoundingBox()
{

	min = Vector3f(FLT_MAX, FLT_MAX, FLT_MAX);
	max = Vector3f(-FLT_MAX, -FLT_MAX, -FLT_MAX);

	for (int i = 0; i<nNode; i++) {
		this->min.x = std::min(this->min.x, vertex[i].new_coord.x);
		this->min.y = std::min(this->min.y, vertex[i].new_coord.y);
		this->min.z = std::min(this->min.z, vertex[i].new_coord.z);
		this->max.x = std::max(this->max.x, vertex[i].new_coord.x);
		this->max.y = std::max(this->max.y, vertex[i].new_coord.y);
		this->max.z = std::max(this->max.z, vertex[i].new_coord.z);
	}
}

bool Object::CheckInOutSurface(Vector3f pos)
{
	float d, min_d = FLT_MAX;
	int min_id = -1;

	if (pos.x > min.x || pos.y > max.y || pos.z > max.z || pos.x < min.x || pos.y < min.y || pos.z < min.z) return false;

	for (int i = 0; i < nTriangle; i++){
		d = (triangle[i].center - pos).GetLength();
		if (d < min_d){
			min_d = d;
			min_id = i;
		}
	}

	Vector3f v = triangle[min_id].center - pos;
	Vector3f n = triangle[min_id].new_normal;

	if (v * n > 0) return true;
	else return false;
}

