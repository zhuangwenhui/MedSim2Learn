cmake_minimum_required(VERSION 3.20)

project(mvrmesh LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(mvrmesh
    src/algorithms.cpp
    src/geometry.cpp
    src/io.cpp
    src/pipeline.cpp
    src/topology.cpp
)

target_include_directories(mvrmesh
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

add_executable(mvr_to_mesh_cli
    apps/mvr_to_mesh_cli.cpp
)

target_link_libraries(mvr_to_mesh_cli PRIVATE mvrmesh)

enable_testing()

add_executable(mvrmesh_smoke_tests
    tests/smoke_tests.cpp
)

target_link_libraries(mvrmesh_smoke_tests PRIVATE mvrmesh)

add_test(NAME mvrmesh_smoke COMMAND mvrmesh_smoke_tests)

set(MVRMESH_SAMPLE_INPUT "")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
    set(MVRMESH_SAMPLE_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/kidney.mvr")
    set(MVRMESH_SAMPLE_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/kidney.mvr")
endif()

if(NOT MVRMESH_SAMPLE_INPUT STREQUAL "")
    add_test(
        NAME mvrmesh_cli_direct
        COMMAND mvr_to_mesh_cli
            "${MVRMESH_SAMPLE_INPUT}"
            --format ply
            -o "${CMAKE_CURRENT_BINARY_DIR}/kidney_direct_cpp"
    )
endif()
