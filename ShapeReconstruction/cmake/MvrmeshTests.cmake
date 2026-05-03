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
    if(MVRMESH_ENABLE_TETGEN)
        add_executable(mvrmesh_robust_pipeline_tests
            verification/backends/cgal/cgal_robust_pipeline_tests.cpp
        )
        target_link_libraries(mvrmesh_robust_pipeline_tests PRIVATE mvrmesh)
        add_test(NAME mvrmesh_robust_pipeline COMMAND mvrmesh_robust_pipeline_tests)

        # Note: tiny_surface.mvr is the corner tetrahedron whose adjacent-face-normal
        # angles all exceed 60 deg, which would trip stage 2's all-edges-sharp guard
        # under the default --sharp-edge-degrees=60. The override to 130 mirrors what
        # test_pipeline_happy_path_tetrahedron and the stage-2 unit tests already do
        # for the same fixture geometry.
        add_test(
            NAME mvrmesh_cli_robust_pipeline
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_TEST_FIXTURE}"
                --robust-pipeline
                --sharp-edge-degrees 130
                -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_robust"
        )
        add_test(
            NAME mvrmesh_cli_robust_pipeline_with_pressure
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_TEST_FIXTURE}"
                --robust-pipeline
                --sharp-edge-degrees 130
                -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_robust_pressure"
                --deformsim-pressure-output "${CMAKE_CURRENT_BINARY_DIR}/tiny_robust_pressure.json"
        )

        # Negative: --robust-pipeline conflicts (use WILL_FAIL TRUE so CTest passes
        # when the CLI exits non-zero). Each rule has its own test entry -- do not
        # combine multiple rule violations into one test, since parse_args returns
        # on the FIRST violation and we'd lose coverage of the later rules.
        add_test(
            NAME mvrmesh_cli_robust_pipeline_rejects_adaptive_remesh
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_TEST_FIXTURE}"
                --robust-pipeline --adaptive-remesh
                -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_ar"
        )
        set_tests_properties(mvrmesh_cli_robust_pipeline_rejects_adaptive_remesh
            PROPERTIES WILL_FAIL TRUE)

        add_test(
            NAME mvrmesh_cli_robust_pipeline_rejects_zero_budget
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_TEST_FIXTURE}"
                --robust-pipeline --max-dense-kl-bytes 0
                -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_zb"
        )
        set_tests_properties(mvrmesh_cli_robust_pipeline_rejects_zero_budget
            PROPERTIES WILL_FAIL TRUE)

        add_test(
            NAME mvrmesh_cli_robust_pipeline_rejects_unrelated_flag_without_pipeline
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_TEST_FIXTURE}"
                --max-dense-kl-bytes 4294967296
                -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_no_pipeline"
        )
        set_tests_properties(mvrmesh_cli_robust_pipeline_rejects_unrelated_flag_without_pipeline
            PROPERTIES WILL_FAIL TRUE)
    endif()
endif()

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

set(MVRMESH_SAMPLE_INPUT "")
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
    set(MVRMESH_SAMPLE_INPUT "${CMAKE_CURRENT_SOURCE_DIR}/originalData/MVR/kidney.mvr")
endif()

if(NOT MVRMESH_SAMPLE_INPUT STREQUAL "")
    add_test(
        NAME mvrmesh_cli_direct
        COMMAND mvr_to_mesh_cli
            "${MVRMESH_SAMPLE_INPUT}"
            -o "${CMAKE_CURRENT_BINARY_DIR}/kidney_direct_cpp"
    )

    if(MVRMESH_ENABLE_CGAL AND MVRMESH_ENABLE_TETGEN)
        # Real-data integration probe. Uses default --sharp-edge-degrees=60 deliberately --
        # the point is to surface kidney's actual behavior under production defaults.
        # If this test fails, it is valuable feedback (which stage tripped on real data)
        # rather than a fixture-tuning bug. Outcome captured in Task 11 evidence.
        add_test(
            NAME mvrmesh_cli_robust_pipeline_kidney
            COMMAND mvr_to_mesh_cli
                "${MVRMESH_SAMPLE_INPUT}"
                --robust-pipeline
                -o "${CMAKE_CURRENT_BINARY_DIR}/kidney_robust"
                --deformsim-pressure-output "${CMAKE_CURRENT_BINARY_DIR}/kidney_robust_pressure.json"
        )
    endif()
endif()
