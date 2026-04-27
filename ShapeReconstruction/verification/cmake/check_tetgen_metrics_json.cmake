if(NOT DEFINED METRICS_JSON)
    message(FATAL_ERROR "METRICS_JSON is required")
endif()

if(NOT EXISTS "${METRICS_JSON}")
    message(FATAL_ERROR "TetGen metrics JSON was not written: ${METRICS_JSON}")
endif()

file(READ "${METRICS_JSON}" contents)

foreach(expected IN ITEMS
    "\"success\": true"
    "\"switches\": \"pYQ\""
    "\"output_tetra_count\": 1"
    "\"total_volume\":"
    "\"min_tetra_quality\":"
    "\"mean_tetra_quality\":"
)
    string(FIND "${contents}" "${expected}" found_at)
    if(found_at EQUAL -1)
        message(FATAL_ERROR "TetGen metrics JSON did not contain ${expected}. Contents: ${contents}")
    endif()
endforeach()
