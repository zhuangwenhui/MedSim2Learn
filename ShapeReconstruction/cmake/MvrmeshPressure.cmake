# Default TetGen location: prefer the TETGEN_ROOT environment variable when
# set, falling back to the workspace-vendored copy. An explicit
# -DTETGEN_ROOT=... on the configure line still overrides both.
if(DEFINED ENV{TETGEN_ROOT})
    set(MVRMESH_TETGEN_DEFAULT_ROOT "$ENV{TETGEN_ROOT}")
else()
    set(MVRMESH_TETGEN_DEFAULT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/tetgen-1.6.0")
endif()

set(TETGEN_ROOT "${MVRMESH_TETGEN_DEFAULT_ROOT}" CACHE PATH
    "Root directory of the TetGen 1.6 source (workspace third_party by default)")

set(MVRMESH_REQUIRED_TETGEN_SOURCES
    "${TETGEN_ROOT}/predicates.cxx"
    "${TETGEN_ROOT}/tetgen.cxx"
)

set(MVRMESH_REQUIRED_TETGEN_FILES
    ${MVRMESH_REQUIRED_TETGEN_SOURCES}
    "${TETGEN_ROOT}/tetgen.h"
)

foreach(MVRMESH_TETGEN_FILE IN LISTS MVRMESH_REQUIRED_TETGEN_FILES)
    if(NOT EXISTS "${MVRMESH_TETGEN_FILE}")
        message(FATAL_ERROR "Required TetGen file not found: ${MVRMESH_TETGEN_FILE}")
    endif()
endforeach()

add_library(mvrmesh_tetgen STATIC
    ${MVRMESH_REQUIRED_TETGEN_SOURCES}
)

target_include_directories(mvrmesh_tetgen PUBLIC
    "${TETGEN_ROOT}"
)

target_compile_definitions(mvrmesh_tetgen PUBLIC TETLIBRARY)
target_compile_features(mvrmesh_tetgen PUBLIC cxx_std_17)

if(MSVC)
    target_compile_options(mvrmesh_tetgen PRIVATE /Zc:strictStrings-)
endif()

set(MVRMESH_TETGEN_LIBRARIES
    mvrmesh_tetgen
)

set(MVRMESH_PRESSURE_SOURCES
    src/pressure/pressure_evaluator.cpp
    src/pressure/pressure_metrics.cpp
)

