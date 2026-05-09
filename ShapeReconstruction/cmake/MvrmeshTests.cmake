set(MVRMESH_TEST_FIXTURE
    "${CMAKE_CURRENT_SOURCE_DIR}/verification/fixtures/tiny_surface.mvr"
)

add_executable(mvrmesh_smoke_tests
    verification/core/smoke_tests.cpp
)

target_link_libraries(mvrmesh_smoke_tests PRIVATE mvrmesh)

add_test(NAME mvrmesh_smoke COMMAND mvrmesh_smoke_tests)

add_executable(mvrmesh_pressure_evaluator_tests
    verification/pressure/pressure_evaluator_tests.cpp
    ${MVRMESH_PRESSURE_SOURCES}
)

target_link_libraries(mvrmesh_pressure_evaluator_tests
    PRIVATE
        mvrmesh
        ${MVRMESH_TETGEN_LIBRARIES}
)

add_test(NAME mvrmesh_pressure_evaluator COMMAND mvrmesh_pressure_evaluator_tests)

add_test(
    NAME mvrmesh_tetgen_no_direct_exit
    COMMAND ${CMAKE_COMMAND}
        -DTETGEN_SOURCE=${TETGEN_ROOT}/tetgen.cxx
        -P ${CMAKE_CURRENT_SOURCE_DIR}/verification/cmake/check_tetgen_no_direct_exit.cmake
)

add_executable(mvrmesh_cgal_mesh_tests
    verification/backends/cgal/cgal_mesh_tests.cpp
)
target_link_libraries(mvrmesh_cgal_mesh_tests PRIVATE mvrmesh)
add_test(NAME mvrmesh_cgal_mesh COMMAND mvrmesh_cgal_mesh_tests)

add_executable(mvrmesh_quality_smoothing_tests
    verification/core/quality_smoothing_tests.cpp
)

target_link_libraries(mvrmesh_quality_smoothing_tests PRIVATE mvrmesh)

add_test(NAME mvrmesh_quality_smoothing COMMAND mvrmesh_quality_smoothing_tests)

# Note: tiny_surface.mvr is the corner tetrahedron whose adjacent-face-normal
# angles all exceed 60 deg, which would trip stage 2's all-edges-sharp guard
# under the default --sharp-edge-degrees=60. The override to 130 mirrors what
# test_pipeline_happy_path_tetrahedron and the stage-2 unit tests already do
# for the same fixture geometry.
add_test(
    NAME mvrmesh_cli_cgal_mesh
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --cgal-mesh
        --sharp-edge-degrees 130
        -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_robust"
)

add_test(
    NAME mvrmesh_cli_uniform_subdivide
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --uniform-subdivide
        --uniform-iterations 1
        -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_uniform"
)

add_test(
    NAME mvrmesh_cli_uniform_taubin
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --uniform-subdivide
        --uniform-iterations 1
        --taubin-smooth
        --taubin-iterations 2
        -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_taubin"
)

add_test(
    NAME mvrmesh_cli_sdf_reconstruct
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --sdf-reconstruct
        --sdf-resolution 8
        --sdf-target-edge-length 0.3
        --sdf-remesh-iterations 1
        -o "${CMAKE_CURRENT_BINARY_DIR}/tiny_sdf_reconstruct"
)

# Negative: --cgal-mesh conflicts (use WILL_FAIL TRUE so CTest passes
# when the CLI exits non-zero). Each rule has its own test entry -- do not
# combine multiple rule violations into one test, since parse_args returns
# on the FIRST violation and we'd lose coverage of the later rules.
add_test(
    NAME mvrmesh_cli_cgal_mesh_rejects_adaptive_remesh
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --cgal-mesh --adaptive-remesh
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_ar"
)
set_tests_properties(mvrmesh_cli_cgal_mesh_rejects_adaptive_remesh
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_cgal_mesh_rejects_unrelated_flag_without_pipeline
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --target-edge-length 0.5
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_no_pipeline"
)
set_tests_properties(mvrmesh_cli_cgal_mesh_rejects_unrelated_flag_without_pipeline
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_uniform_subdivide_rejects_adaptive_remesh
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --uniform-subdivide --adaptive-remesh
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_uniform_adaptive"
)
set_tests_properties(mvrmesh_cli_uniform_subdivide_rejects_adaptive_remesh
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_uniform_subdivide_rejects_cgal_mesh
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --uniform-subdivide --cgal-mesh
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_uniform_cgal"
)
set_tests_properties(mvrmesh_cli_uniform_subdivide_rejects_cgal_mesh
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_uniform_iterations_requires_uniform_subdivide
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --uniform-iterations 1
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_uniform_iterations"
)
set_tests_properties(mvrmesh_cli_uniform_iterations_requires_uniform_subdivide
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_taubin_requires_uniform_subdivide
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --taubin-smooth
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_taubin_no_uniform"
)
set_tests_properties(mvrmesh_cli_taubin_requires_uniform_subdivide
    PROPERTIES WILL_FAIL TRUE)

add_test(
    NAME mvrmesh_cli_sdf_resolution_requires_sdf_reconstruct
    COMMAND mvr_to_mesh_cli
        "${MVRMESH_TEST_FIXTURE}"
        --sdf-resolution 8
        -o "${CMAKE_CURRENT_BINARY_DIR}/should_not_exist_sdf_resolution"
)
set_tests_properties(mvrmesh_cli_sdf_resolution_requires_sdf_reconstruct
    PROPERTIES WILL_FAIL TRUE)

# Single-file pressure evaluation: mvr_to_mesh_cli produces a tiny .ply
# via --cgal-mesh, then check_fem_pressure runs TetGen on it and emits
# the 4-dimensional pressure JSON. Driver script substring-matches keys.
add_test(
    NAME check_fem_pressure_single
    COMMAND ${CMAKE_COMMAND}
        -DCLI_EXE=$<TARGET_FILE:mvr_to_mesh_cli>
        -DPRESSURE_EXE=$<TARGET_FILE:check_fem_pressure>
        -DTEST_FIXTURE=${MVRMESH_TEST_FIXTURE}
        -DOUT_DIR=${CMAKE_CURRENT_BINARY_DIR}
        -P ${CMAKE_CURRENT_SOURCE_DIR}/verification/cmake/run_check_fem_pressure_single.cmake
)

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

    # Real-data integration probe. Uses default --sharp-edge-degrees=60 deliberately --
    # the point is to surface kidney's actual behavior under production defaults.
    # If this test fails, it is valuable feedback (which stage tripped on real data)
    # rather than a fixture-tuning bug. Outcome captured in Task 11 evidence.
    add_test(
        NAME mvrmesh_cli_cgal_mesh_kidney
        COMMAND mvr_to_mesh_cli
            "${MVRMESH_SAMPLE_INPUT}"
            --cgal-mesh
            -o "${CMAKE_CURRENT_BINARY_DIR}/kidney_robust"
    )

    set(MVRMESH_PLATE_BASELINE "${CMAKE_CURRENT_SOURCE_DIR}/../DeformSim/plate.ply")
    if(NOT EXISTS "${MVRMESH_PLATE_BASELINE}")
        set(MVRMESH_PLATE_BASELINE "")
    endif()

    # End-to-end FEM pressure matrix on kidney.mvr.
    # Drives scripts/run_pressure_matrix.ps1 which runs mvr_to_mesh_cli for
    # 6 candidate configurations, then check_fem_pressure --matrix to
    # aggregate a Markdown comparison report. Conditional on kidney.mvr
    # existing (matches the surrounding block); plate.ply baseline row
    # is added only if DeformSim/plate.ply is present.
    add_test(
        NAME mvrmesh_pressure_matrix_kidney
        COMMAND powershell.exe -ExecutionPolicy Bypass
            -File ${CMAKE_CURRENT_SOURCE_DIR}/scripts/run_pressure_matrix.ps1
            -InputMvr     ${MVRMESH_SAMPLE_INPUT}
            -OutDir       ${CMAKE_CURRENT_BINARY_DIR}/pressure_matrix_kidney
            -CliExe       $<TARGET_FILE:mvr_to_mesh_cli>
            -PressureExe  $<TARGET_FILE:check_fem_pressure>
            -BaselinePly  ${MVRMESH_PLATE_BASELINE}
    )
    set_tests_properties(mvrmesh_pressure_matrix_kidney PROPERTIES
        TIMEOUT 600
        LABELS "matrix"
    )
endif()
