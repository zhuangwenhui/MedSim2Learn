#include "stdafx.h"
#include "trackball.h"

#define M_PI 3.14159265358979323846

static int cx, cy;
static double sx, sy;

#define SCALE (2.0 * M_PI)

static double cq[4] = { 1.0, 0.0, 0.0, 0.0 };
static double tq[4];

static double rt[16] = {
  1.0, 0.0, 0.0, 0.0,
  0.0, 1.0, 0.0, 0.0,
  0.0, 0.0, 1.0, 0.0,
  0.0, 0.0, 0.0, 1.0,
};

static int drag = 0;


static void qmul(double r[], const double p[], const double q[])
{
  r[0] = p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3];
  r[1] = p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2];
  r[2] = p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1];
  r[3] = p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0];
}


static void qrot(double r[], double q[])
{
  double x2 = q[1] * q[1] * 2.0;
  double y2 = q[2] * q[2] * 2.0;
  double z2 = q[3] * q[3] * 2.0;
  double xy = q[1] * q[2] * 2.0;
  double yz = q[2] * q[3] * 2.0;
  double zx = q[3] * q[1] * 2.0;
  double xw = q[1] * q[0] * 2.0;
  double yw = q[2] * q[0] * 2.0;
  double zw = q[3] * q[0] * 2.0;
  
  r[ 0] = 1.0 - y2 - z2;
  r[ 1] = xy + zw;
  r[ 2] = zx - yw;
  r[ 4] = xy - zw;
  r[ 5] = 1.0 - z2 - x2;
  r[ 6] = yz + xw;
  r[ 8] = zx + yw;
  r[ 9] = yz - xw;
  r[10] = 1.0 - x2 - y2;
  r[ 3] = r[ 7] = r[11] = r[12] = r[13] = r[14] = 0.0;
  r[15] = 1.0;
}


void trackballInit(void)
{
	drag = 0;
	cq[0] = 1.0;
	cq[1] = 0.0;
	cq[2] = 0.0;
	cq[3] = 0.0;

	qrot(rt, cq);
}


void trackballRegion(int w, int h)
{
  sx = 1.0 / (double)w;
  sy = 1.0 / (double)h;
}

void trackballStart(int x, int y)
{
  drag = 1;

  cx = x;
  cy = y;
}


void trackballMotion(int x, int y)
{
  if (drag) {
    double dx, dy, a;
    
    dx = (x - cx) * sx;
    dy = (y - cy) * sy;
    
    a = sqrt(dx * dx + dy * dy);
    
    if (a != 0.0) {
      double ar = a * SCALE * 0.5;
      double as = sin(ar) / a;
//      double dq[4] = { cos(ar), dy * as, dx * as, 0.0 };
        double dq[4] = { cos(ar), dy * as, 0.0, dx * as };
      
	  qmul(tq, dq, cq);
	  qrot(rt, tq);
    }
  }
}

void trackballStop(int x, int y)
{
	if(drag)
	{
		trackballMotion(x, y);

		cq[0] = tq[0];
		cq[1] = tq[1];
		cq[2] = tq[2];
		cq[3] = tq[3];
	}
	
	drag = 0;
}


double *trackballRotation(void)
{
  return rt;
}
