find_package(gmsh CONFIG REQUIRED)

set(MVRMESH_GMSH_SOURCES
    src/backends/gmsh/gmsh_evaluator.cpp
)

if(TARGET gmsh::shared)
    set_target_properties(gmsh::shared PROPERTIES
        MAP_IMPORTED_CONFIG_DEBUG RelWithDebInfo
        MAP_IMPORTED_CONFIG_RELEASE RelWithDebInfo
        MAP_IMPORTED_CONFIG_MINSIZEREL RelWithDebInfo
        MAP_IMPORTED_CONFIG_RELWITHDEBINFO RelWithDebInfo
    )
    add_library(mvrmesh_gmsh INTERFACE)
    target_include_directories(mvrmesh_gmsh INTERFACE
        $<TARGET_PROPERTY:gmsh::shared,INTERFACE_INCLUDE_DIRECTORIES>
    )
    target_link_libraries(mvrmesh_gmsh INTERFACE $<TARGET_LINKER_FILE:gmsh::shared>)
elseif(TARGET gmsh::lib)
    add_library(mvrmesh_gmsh INTERFACE)
    target_link_libraries(mvrmesh_gmsh INTERFACE gmsh::lib)
else()
    message(FATAL_ERROR "Required Gmsh CMake target not found: expected gmsh::shared or gmsh::lib")
endif()

set(MVRMESH_GMSH_LIBRARIES
    mvrmesh_gmsh
)

set(MVRMESH_GMSH_DEFINITIONS
    MVRMESH_GMSH_ENABLED=1
)

function(mvrmesh_copy_gmsh_runtime target_name)
    if(TARGET gmsh::shared)
        add_custom_command(TARGET ${target_name} POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                $<TARGET_FILE:gmsh::shared>
                $<TARGET_FILE_DIR:${target_name}>
        )
    endif()
endfunction()
