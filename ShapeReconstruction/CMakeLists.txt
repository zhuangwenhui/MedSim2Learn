cmake_minimum_required(VERSION 3.20)

project(mvrmesh LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MVRMESH_BUILD_TESTS "Build mvrmesh CTest suites (smoke, backends, CLI)" ON)

include(cmake/MvrmeshCore.cmake)

set(MVRMESH_BACKEND_SOURCES)
set(MVRMESH_PUBLIC_LIBRARIES)
set(MVRMESH_PRIVATE_LIBRARIES)

include(cmake/MvrmeshCgalMesh.cmake)
list(APPEND MVRMESH_BACKEND_SOURCES ${MVRMESH_CGAL_MESH_SOURCES})
list(APPEND MVRMESH_PRIVATE_LIBRARIES ${MVRMESH_CGAL_MESH_LIBRARIES})

include(cmake/MvrmeshPressure.cmake)

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

add_executable(mvr_to_mesh_cli
    mvr_to_mesh_cli.cpp
)

target_link_libraries(mvr_to_mesh_cli PRIVATE mvrmesh)

add_executable(check_fem_pressure
    check_fem_pressure_cli.cpp
    ${MVRMESH_PRESSURE_SOURCES}
)

target_link_libraries(check_fem_pressure
    PRIVATE
        mvrmesh
        ${MVRMESH_TETGEN_LIBRARIES}
)

# enable_testing() must be called unconditionally so CMake regenerates an
# up-to-date CTestTestfile.cmake on every configure. Otherwise toggling
# MVRMESH_BUILD_TESTS=OFF leaves stale add_test entries from a prior ON build.
enable_testing()

if(MVRMESH_BUILD_TESTS)
    include(cmake/MvrmeshTests.cmake)
endif()
