set(MVRMESH_TEST_FIXTURE
    "${CMAKE_CURRENT_SOURCE_DIR}/verification/fixtures/tiny_surface.mvr"
)

add_executable(mvrmesh_smoke_tests
    verification/core/smoke_tests.cpp
)

target_link_libraries(mvrmesh_smoke_tests PRIVATE mvrmesh)

add_test(NAME mvrmesh_smoke COMMAND mvrmesh_smoke_tests)

if(MVRMESH_ENABLE_TETGEN)
    add_executable(mvrmesh_tetgen_evaluator_tests
        verification/backends/tetgen/tetgen_evaluator_tests.cpp
    )

    target_link_libraries(mvrmesh_tetgen_evaluator_tests PRIVATE mvrmesh)

    add_test(NAME mvrmesh_tetgen_evaluator COMMAND mvrmesh_tetgen_evaluator_tests)

    add_test(
        NAME mvrmesh_tetgen_no_direct_exit
        COMMAND ${CMAKE_COMMAND}
            -DTETGEN_SOURCE=${TETGEN_ROOT}/tetgen.cxx
            -P ${CMAKE_CURRENT_SOURCE_DIR}/verification/cmake/check_tetgen_no_direct_exit.cmake
    )
endif()

if(MVRMESH_ENABLE_CGAL)
    add_executable(mvrmesh_cgal_pmp_tests
        verification/backends/cgal/cgal_pmp_backend_tests.cpp
    )

    target_link_libraries(mvrmesh_cgal_pmp_tests PRIVATE mvrmesh)

    add_test(NAME mvrmesh_cgal_pmp COMMAND mvrmesh_cgal_pmp_tests)
endif()

add_test(
    NAME mvrmesh_cli_metrics
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --format ply
        -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_cli_metrics"
        --metrics-output "${CMAKE_CURRENT_BINARY_DIR}/tiny_cli_metrics.json"
)

if(MVRMESH_ENABLE_TETGEN)
    add_test(
        NAME mvrmesh_cli_deformsim_pressure
        COMMAND ${CMAKE_COMMAND}
            -DCLI_EXE=$<TARGET_FILE:mvr_to_mesh_cli>
            -DINPUT_MVR=${MVRMESH_TEST_FIXTURE}
            -DOUTPUT_BASE=${CMAKE_CURRENT_BINARY_DIR}/tiny_cli_deformsim_pressure
            -DPRESSURE_JSON=${CMAKE_CURRENT_BINARY_DIR}/tiny_cli_deformsim_pressure.json
            -P ${CMAKE_CURRENT_SOURCE_DIR}/verification/cmake/run_cli_deformsim_pressure.cmake
    )
endif()

if(MVRMESH_ENABLE_CGAL)
    add_test(
        NAME mvrmesh_cli_cgal_backend
        COMMAND mvr_to_mesh_cli
            "${MVRMESH_TEST_FIXTURE}"
            --surface-backend cgal
            --format ply
            -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_cli_cgal"
    )
endif()

set(MVRMESH_SAMPLE_INPUT "")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
    set(MVRMESH_SAMPLE_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
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
