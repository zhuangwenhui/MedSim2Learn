// stdafx.h : frozen umbrella header for the legacy no-touch zone.
//
// History: this began life as the MFC precompiled header of the 2006-2008
// BMGL Visual Studio GUI application, was retargeted from Windows XP to
// Windows 10, moved from MKL 10 (libguide40) to oneAPI MKL, and lost its
// GL/MFC content when the rendering stack was removed. It is no longer a
// precompiled header: it survives only because the BMGL/ and Utility/
// sources (and the verification apps) include it by name and rely on its
// include order (targeting defines -> windows -> C libs -> C++ libs ->
// MKL -> bmgl). Do not extend it: new orchestrator code lives under src/
// and includes what it uses directly.

#pragma once

// Enable M_PI, M_E, etc. in <corecrt_math_defines.h>; must precede any
// math-related include.
#ifndef _USE_MATH_DEFINES
#define _USE_MATH_DEFINES
#endif

// Target the Windows 10+ API surface.
#ifndef WINVER
#define WINVER 0x0A00
#endif

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

// The legacy sources use the classic CRT functions (sprintf, localtime, ...).
#pragma warning(disable: 4996)

#include <windows.h>

// Standard C libraries used throughout the legacy sources.
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <direct.h>

// Standard C++ libraries the legacy sources rely on receiving from here:
// <cmath> for std::isfinite in the FEM kernel, <mutex> for the tetgen
// serialization guard, the rest as the historical baseline of BMGL.
#include <cmath>
#include <iostream>
#include <fstream>
#include <memory>
#include <vector>
#include <list>
#include <mutex>

// Intel oneAPI MKL (threading controlled via the MKL service API; libraries
// are linked through CMake, not pragma comments).
#include "mkl.h"

// BMGL aggregate header (vector/matrix/geometry/surface/object).
#include "bmgl.h"
