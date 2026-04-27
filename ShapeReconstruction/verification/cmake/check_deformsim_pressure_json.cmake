if(NOT DEFINED PRESSURE_JSON)
    message(FATAL_ERROR "PRESSURE_JSON is required")
endif()

if(NOT EXISTS "${PRESSURE_JSON}")
    message(FATAL_ERROR "DeformSim pressure JSON was not written: ${PRESSURE_JSON}")
endif()

file(READ "${PRESSURE_JSON}" contents)

foreach(expected IN ITEMS
    "\"success\": true"
    "\"stage\": \"tetgen_output_validated\""
    "\"surface_vertex_count\": 4"
    "\"surface_face_count\": 4"
    "\"object_node_count\": 4"
    "\"object_triangle_count\": 4"
    "\"bounding_box_valid\": true"
    "\"tetgen_output_tetra_count\": 1"
    "\"estimated_unique_line_count\": 6"
    "\"line_capacity_nnode_times_32\": 128"
    "\"estimated_line_capacity_exceeded\": false"
    "\"estimated_dense_k_l_bytes\": 2304"
)
    string(FIND "${contents}" "${expected}" found_at)
    if(found_at EQUAL -1)
        message(FATAL_ERROR "DeformSim pressure JSON did not contain ${expected}. Contents: ${contents}")
    endif()
endforeach()
