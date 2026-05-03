# Runs:
#   1. mvr_to_mesh_cli on tiny_surface.mvr to produce a tiny .ply
#   2. check_fem_pressure on that .ply, single mode
#   3. Verifies the output JSON contains expected keys
set(TINY_PLY ${OUT_DIR}/tiny_for_pressure)
execute_process(
    COMMAND ${CLI_EXE} ${TEST_FIXTURE} --cgal-mesh --sharp-edge-degrees 130 -o ${TINY_PLY}
    RESULT_VARIABLE rc
)
if(NOT rc EQUAL 0)
    message(FATAL_ERROR "mvr_to_mesh_cli failed (rc=${rc})")
endif()

set(PRESSURE_JSON ${OUT_DIR}/tiny_pressure.json)
execute_process(
    COMMAND ${PRESSURE_EXE} ${TINY_PLY}.ply -o ${PRESSURE_JSON}
    RESULT_VARIABLE rc2
)
if(NOT rc2 EQUAL 0)
    message(FATAL_ERROR "check_fem_pressure failed (rc=${rc2})")
endif()

if(NOT EXISTS ${PRESSURE_JSON})
    message(FATAL_ERROR "Expected output JSON not produced: ${PRESSURE_JSON}")
endif()

file(READ ${PRESSURE_JSON} JSON_CONTENT)

foreach(key
    "v_surface"
    "v_tet"
    "matrix_order_3v_tet"
    "memory_peak_bytes_kl"
    "dgetri_flops"
    "n_samples"
    "dgemv_total_flops"
    "tetgen_success")
    string(FIND "${JSON_CONTENT}" "\"${key}\":" key_pos)
    if(key_pos EQUAL -1)
        message(FATAL_ERROR "JSON missing required key: ${key}\n${JSON_CONTENT}")
    endif()
endforeach()
