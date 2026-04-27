foreach(required IN ITEMS CLI_EXE INPUT_MVR OUTPUT_BASE PRESSURE_JSON)
    if(NOT DEFINED ${required})
        message(FATAL_ERROR "${required} is required")
    endif()
endforeach()

file(REMOVE "${PRESSURE_JSON}" "${OUTPUT_BASE}.ply" "${OUTPUT_BASE}.stl")

execute_process(
    COMMAND
        "${CLI_EXE}"
        "${INPUT_MVR}"
        --format ply
        -o "${OUTPUT_BASE}"
        --deformsim-pressure-output "${PRESSURE_JSON}"
    RESULT_VARIABLE result
    OUTPUT_VARIABLE stdout
    ERROR_VARIABLE stderr
)

if(NOT result EQUAL 0)
    message(FATAL_ERROR "DeformSim pressure CLI failed with ${result}. Output: ${stdout}\n${stderr}")
endif()

set(output_ply "${OUTPUT_BASE}.ply")
if(NOT EXISTS "${output_ply}")
    message(FATAL_ERROR "DeformSim pressure CLI did not write PLY surface handoff: ${output_ply}")
endif()
file(SIZE "${output_ply}" output_ply_size)
if(output_ply_size EQUAL 0)
    message(FATAL_ERROR "DeformSim pressure CLI wrote an empty PLY surface handoff: ${output_ply}")
endif()

include("${CMAKE_CURRENT_LIST_DIR}/check_deformsim_pressure_json.cmake")
