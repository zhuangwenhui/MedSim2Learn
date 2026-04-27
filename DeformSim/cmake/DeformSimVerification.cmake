include_guard(GLOBAL)

deformsim_add_tetra_verification_tool(
    deformsim_ply_tetra_smoke
    ${DEFORMSIM_PROJECT_ROOT}/verification/apps/ply_tetra_smoke.cpp
)

deformsim_add_tetra_verification_tool(
    deformsim_ply_tetra_diagnostic
    ${DEFORMSIM_PROJECT_ROOT}/verification/apps/ply_tetra_diagnostic.cpp
)

set(DEFORMSIM_SMOKE_PLY "" CACHE FILEPATH
    "Optional PLY path for the DeformSim PLY-to-tetra smoke CTest")

if(NOT DEFORMSIM_SMOKE_PLY STREQUAL "")
    enable_testing()
    add_test(
        NAME deformsim_ply_tetra_smoke
        COMMAND deformsim_ply_tetra_smoke
            "${DEFORMSIM_SMOKE_PLY}"
            "${CMAKE_BINARY_DIR}/deformsim_ply_tetra_smoke.json"
    )

    set(_deformsim_smoke_environment)
    foreach(runtime_dir IN LISTS DEFORMSIM_RUNTIME_PATH_DIRS)
        list(APPEND _deformsim_smoke_environment "PATH=path_list_prepend:${runtime_dir}")
    endforeach()

    set_tests_properties(deformsim_ply_tetra_smoke PROPERTIES
        ENVIRONMENT_MODIFICATION "${_deformsim_smoke_environment}"
    )
endif()
