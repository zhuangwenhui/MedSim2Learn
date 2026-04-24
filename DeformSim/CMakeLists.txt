cmake_minimum_required(VERSION 3.28)

project(DeformSim LANGUAGES CXX RC)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/FindLocalDeps.cmake)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

find_package(OpenMP REQUIRED)

add_executable(LVBasicFramework
    ${DEFORMSIM_PROJECT_ROOT}/stdafx.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/bmgl.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/imagefilter.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/geometry.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/image.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/surface.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/matrix.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/object.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/vector.cpp
    ${DEFORMSIM_PROJECT_ROOT}/Utility/predicates.cpp
    ${DEFORMSIM_PROJECT_ROOT}/Utility/tetgen.cpp
    ${DEFORMSIM_PROJECT_ROOT}/LVBasicFramework.rc
)

target_include_directories(LVBasicFramework PRIVATE
    ${DEFORMSIM_RC_INCLUDE_DIRS}
    ${DEFORMSIM_ONEAPI_MKL_INCLUDE}
    ${DEFORMSIM_PROJECT_ROOT}
    ${DEFORMSIM_PROJECT_ROOT}/BMGL
    ${DEFORMSIM_PROJECT_ROOT}/GL
    ${DEFORMSIM_PROJECT_ROOT}/Utility
)

target_compile_definitions(LVBasicFramework PRIVATE
    WIN32
    _WINDOWS
    _AFXDLL
    MKL_LP64=1
    NOMINMAX
    _USE_MATH_DEFINES
)

target_compile_options(LVBasicFramework PRIVATE /openmp)
target_link_options(LVBasicFramework PRIVATE /DYNAMICBASE:NO)

target_link_directories(LVBasicFramework PRIVATE
    ${DEFORMSIM_SYSTEM_LIB_DIRS}
    ${DEFORMSIM_ONEAPI_MKL_LIB}
    ${DEFORMSIM_ONEAPI_COMPILER_LIB}
    ${DEFORMSIM_PROJECT_ROOT}/Lib
)

target_link_libraries(LVBasicFramework PRIVATE
    OpenMP::OpenMP_CXX
    ${DEFORMSIM_MKL_INTEL_LP64_LIB}
    ${DEFORMSIM_MKL_INTEL_THREAD_LIB}
    ${DEFORMSIM_MKL_CORE_LIB}
    ${DEFORMSIM_LIBIOMP5MD_LIB}
    opengl32.lib
    glu32.lib
    ${DEFORMSIM_GLUT32_LIB}
    ${DEFORMSIM_DEVIL_LIB}
    ${DEFORMSIM_ILU_LIB}
    ${DEFORMSIM_ILUT_LIB}
)

set_target_properties(LVBasicFramework PROPERTIES
    WIN32_EXECUTABLE OFF
)
