if(NOT DEFINED METRICS_JSON)
    message(FATAL_ERROR "METRICS_JSON is required")
endif()

if(NOT EXISTS "${METRICS_JSON}")
    message(FATAL_ERROR "Gmsh metrics JSON was not written: ${METRICS_JSON}")
endif()

file(READ "${METRICS_JSON}" contents)

foreach(expected IN ITEMS
    "\"success\": true"
    "\"algorithm3d\": 10"
    "\"output_tetra_count\":"
    "\"steiner_vertex_count\":"
    "\"total_volume\":"
    "\"min_tetra_quality\":"
    "\"mean_tetra_quality\":"
)
    string(FIND "${contents}" "${expected}" found_at)
    if(found_at EQUAL -1)
        message(FATAL_ERROR "Gmsh metrics JSON did not contain ${expected}. Contents: ${contents}")
    endif()
endforeach()
