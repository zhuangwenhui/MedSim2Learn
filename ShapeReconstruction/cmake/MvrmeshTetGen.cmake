set(TETGEN_ROOT "D:/dev/tetgen-1.6.0" CACHE PATH
    "Root directory of the external TetGen 1.6 source checkout")

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

set(MVRMESH_TETGEN_SOURCES
    src/backends/tetgen/tetgen_evaluator.cpp
)

set(MVRMESH_TETGEN_DEFINITIONS
    MVRMESH_TETGEN_ENABLED=1
)
