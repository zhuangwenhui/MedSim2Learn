cmake_minimum_required(VERSION 3.20)

project(mvrmesh LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MVRMESH_ENABLE_CGAL "Build the CGAL PMP surface backend" ON)
option(MVRMESH_ENABLE_TETGEN "Build the TetGen tetrahedral evaluation backend" ON)
option(MVRMESH_BUILD_TESTS "Build mvrmesh CTest suites (smoke, backends, CLI)" ON)

if(MVRMESH_ENABLE_CGAL AND NOT MVRMESH_ENABLE_TETGEN)
    message(FATAL_ERROR
        "MVRMESH_ENABLE_CGAL=ON requires MVRMESH_ENABLE_TETGEN=ON because the robust "
        "pipeline (cgal_mesh.cpp) calls evaluate_deformsim_pressure. "
        "Either disable CGAL or enable TetGen.")
endif()

include(cmake/MvrmeshCore.cmake)

set(MVRMESH_BACKEND_SOURCES)
set(MVRMESH_PUBLIC_LIBRARIES)
set(MVRMESH_PRIVATE_LIBRARIES)
set(MVRMESH_BACKEND_DEFINITIONS)

if(MVRMESH_ENABLE_CGAL)
    include(cmake/MvrmeshCgalMesh.cmake)
    list(APPEND MVRMESH_BACKEND_SOURCES ${MVRMESH_CGAL_MESH_SOURCES})
    list(APPEND MVRMESH_PRIVATE_LIBRARIES ${MVRMESH_CGAL_MESH_LIBRARIES})
    list(APPEND MVRMESH_BACKEND_DEFINITIONS ${MVRMESH_CGAL_MESH_DEFINITIONS})
else()
    list(APPEND MVRMESH_BACKEND_DEFINITIONS MVRMESH_CGAL_PMP_ENABLED=0)
endif()

if(MVRMESH_ENABLE_TETGEN)
    include(cmake/MvrmeshTetGen.cmake)
    list(APPEND MVRMESH_BACKEND_SOURCES ${MVRMESH_TETGEN_SOURCES})
    list(APPEND MVRMESH_PRIVATE_LIBRARIES ${MVRMESH_TETGEN_LIBRARIES})
    list(APPEND MVRMESH_BACKEND_DEFINITIONS ${MVRMESH_TETGEN_DEFINITIONS})
else()
    list(APPEND MVRMESH_BACKEND_DEFINITIONS MVRMESH_TETGEN_ENABLED=0)
endif()

add_library(mvrmesh
    ${MVRMESH_CORE_SOURCES}
    ${MVRMESH_BACKEND_SOURCES}
)

target_include_directories(mvrmesh
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(mvrmesh
    PUBLIC
        ${MVRMESH_PUBLIC_LIBRARIES}
    PRIVATE
        ${MVRMESH_PRIVATE_LIBRARIES}
)

target_compile_definitions(mvrmesh PUBLIC
    ${MVRMESH_BACKEND_DEFINITIONS}
)

add_executable(mvr_to_mesh_cli
    mvr_to_mesh_cli.cpp
)

target_link_libraries(mvr_to_mesh_cli PRIVATE mvrmesh)

add_executable(check_fem_pressure
    check_fem_pressure_cli.cpp
)

target_link_libraries(check_fem_pressure PRIVATE mvrmesh)

# enable_testing() must be called unconditionally so CMake regenerates an
# up-to-date CTestTestfile.cmake on every configure. Otherwise toggling
# MVRMESH_BUILD_TESTS off leaves stale add_test entries from a prior ON build.
enable_testing()

if(MVRMESH_BUILD_TESTS)
    include(cmake/MvrmeshTests.cmake)
endif()
