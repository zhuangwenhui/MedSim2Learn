cmake_minimum_required(VERSION 3.28)

project(DeformSim LANGUAGES CXX)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/FindLocalDeps.cmake)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

include(${CMAKE_CURRENT_LIST_DIR}/cmake/DeformSimTargets.cmake)

deformsim_add_main_target()

option(DEFORMSIM_ENABLE_VERIFICATION "Build DeformSim verification tools" ON)

if(DEFORMSIM_ENABLE_VERIFICATION)
    include(${CMAKE_CURRENT_LIST_DIR}/cmake/DeformSimVerification.cmake)
endif()
