foreach(required IN ITEMS CLI_EXE INPUT_MVR OUTPUT_BASE METRICS_JSON)
    if(NOT DEFINED ${required})
        message(FATAL_ERROR "${required} is required")
    endif()
endforeach()

file(REMOVE "${METRICS_JSON}" "${OUTPUT_BASE}.ply" "${OUTPUT_BASE}.stl")

execute_process(
    COMMAND
        "${CLI_EXE}"
        "${INPUT_MVR}"
        --format ply
        -o "${OUTPUT_BASE}"
        --evaluate-tetgen
        --tetgen-metrics-output "${METRICS_JSON}"
    RESULT_VARIABLE result
    OUTPUT_VARIABLE stdout
    ERROR_VARIABLE stderr
)

if(NOT result EQUAL 0)
    message(FATAL_ERROR "TetGen metrics CLI failed with ${result}. Output: ${stdout}\n${stderr}")
endif()

set(output_ply "${OUTPUT_BASE}.ply")
if(NOT EXISTS "${output_ply}")
    message(FATAL_ERROR "TetGen metrics CLI did not write PLY surface handoff: ${output_ply}")
endif()
file(SIZE "${output_ply}" output_ply_size)
if(output_ply_size EQUAL 0)
    message(FATAL_ERROR "TetGen metrics CLI wrote an empty PLY surface handoff: ${output_ply}")
endif()

include("${CMAKE_CURRENT_LIST_DIR}/check_tetgen_metrics_json.cmake")
