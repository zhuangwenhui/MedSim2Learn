if(NOT DEFINED TETGEN_SOURCE)
    message(FATAL_ERROR "TETGEN_SOURCE is required")
endif()

if(NOT EXISTS "${TETGEN_SOURCE}")
    message(FATAL_ERROR "TetGen source not found: ${TETGEN_SOURCE}")
endif()

file(READ "${TETGEN_SOURCE}" contents)
string(FIND "${contents}" "exit(1);" direct_exit_at)
if(NOT direct_exit_at EQUAL -1)
    message(FATAL_ERROR "TetGen source contains a direct exit(1); use terminatetetgen(1) so TETLIBRARY callers can catch failures.")
endif()

