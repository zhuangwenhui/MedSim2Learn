// stdafx.h : include file for standard system include files,
// or project specific include files that are used frequently, but
// are changed infrequently

#pragma once

#ifndef VC_EXTRALEAN
#define VC_EXTRALEAN		// Exclude rarely-used stuff from Windows headers.
#endif

// =============================================================================
// Critical Preprocessor Definitions (MUST BE FIRST)
// =============================================================================

// Enable math constants before ANY math-related includes
#ifndef _USE_MATH_DEFINES
#define _USE_MATH_DEFINES   // Enable M_PI, M_E, etc. in <corecrt_math_defines.h>
#endif

// =============================================================================
// Windows Version Targeting Configuration - Updated for Windows 10/11
// =============================================================================


// Target Windows 10/11 - This enables access to modern Windows APIs
// while maintaining compatibility with Windows 7 SP1 and later
#ifndef WINVER
#define WINVER 0x0A00		// Windows 10/11 - Updated from Windows XP (0x0501)
#endif

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00	// Windows 10/11 - Updated from Windows XP (0x0501) 
#endif						

// Note: _WIN32_WINDOWS is removed as it was for Windows 98/ME support only
// Original value was 0x0410 (Windows 98) - no longer needed in modern applications

#ifndef _WIN32_IE
#define _WIN32_IE 0x0800	// IE 8.0 - Updated from IE 6.0 (0x0600)
#endif

// =============================================================================
// Windows API
// =============================================================================

#pragma warning(disable: 4996)

#include <windows.h>

// =============================================================================
// Standard C Libraries
// =============================================================================

#include <math.h>			// Math functions + constants (M_PI enabled above)
#include <stdlib.h>			// General utilities: malloc, rand, etc.
#include <string.h>			// String manipulation functions (C98 standard)
#include <time.h>			// Time/date utilities
#include <direct.h>			// Directory operations (_mkdir, etc.)

// =============================================================================
// Standard C++ Libraries
// =============================================================================

#include <iostream>
#include <fstream>
#include <chrono>
#include <memory>
#include <vector>
#include <array>
#include <list>
#include <thread>
#include <mutex>
#include <unordered_set>
#include <functional>

// =============================================================================
// Intel Math Kernel Library (MKL) - UPDATED FOR MODERN VERSIONS
// =============================================================================

// OpenMP and MKL Core
#include "omp.h"
#include "mkl.h"

// Link oneAPI MKL through the project settings; pragma comments are not needed.
// Preferred setup: Linker -> Input -> Additional Dependencies.

// Modern MKL library linking (Intel oneAPI MKL)
//#pragma comment(lib, "mkl_intel_thread.lib")	// Thread support
//#pragma comment(lib, "mkl_core.lib")			// Core library

// CRITICAL UPDATE: Replace deprecated libguide40.lib
// libguide40.lib was from Intel MKL 10.0 (2008) and causes runtime conflicts
// with modern OpenMP libraries. It has been removed.

// Modern OpenMP runtime is handled automatically by the compiler
// or included via mkl_rt.lib (runtime library) if needed

//#pragma comment(lib, "mkl_intel_thread.lib")		// Intel MKL 10.0 or later
//#pragma comment(lib, "mkl_core.lib")				// Intel MKL 10.0 or later
//#pragma comment(lib, "libguide40.lib")			// Intel MKL 10.0 or later

//#ifdef _WIN64
//#pragma comment(lib, "mkl_intel_lp64.lib")     // 64-bit interface
//#else
//#pragma comment(lib, "mkl_intel_c.lib")        // 32-bit interface
//#endif

// =============================================================================
// Custom Graphics Library
// =============================================================================

// BMGL
#include "bmgl.h"

