if(NOT DEFINED CLI_EXE)
    message(FATAL_ERROR "CLI_EXE is required")
endif()
if(NOT DEFINED INPUT_MVR)
    message(FATAL_ERROR "INPUT_MVR is required")
endif()
if(NOT DEFINED OUTPUT_BASE)
    message(FATAL_ERROR "OUTPUT_BASE is required")
endif()
if(NOT DEFINED EXPECTED_TEXT)
    message(FATAL_ERROR "EXPECTED_TEXT is required")
endif()

set(args "${CLI_EXE}" "${INPUT_MVR}" --format ply -o "${OUTPUT_BASE}")
if(DEFINED CLI_EXTRA_ARGS)
    list(APPEND args ${CLI_EXTRA_ARGS})
endif()
if(NOT DEFINED INCLUDE_EVALUATE_TETGEN OR INCLUDE_EVALUATE_TETGEN)
    list(APPEND args --evaluate-tetgen)
endif()

execute_process(
    COMMAND ${args}
    RESULT_VARIABLE result
    OUTPUT_VARIABLE stdout
    ERROR_VARIABLE stderr
)

if(result EQUAL 0)
    message(FATAL_ERROR "CLI was expected to fail, but exited 0")
endif()

set(combined "${stdout}\n${stderr}")
string(FIND "${combined}" "${EXPECTED_TEXT}" found_at)
if(found_at EQUAL -1)
    message(FATAL_ERROR "CLI output did not contain expected text '${EXPECTED_TEXT}'. Output was: ${combined}")
endif()
