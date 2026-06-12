include_guard(GLOBAL)

# Third-party code is vendored once for the whole workspace under
# third_party/ at the repo root (pristine upstream files plus their own
# licenses; see THIRD_PARTY_NOTICES.md).
set(DEFORMSIM_WORKSPACE_THIRD_PARTY ${DEFORMSIM_PROJECT_ROOT}/../third_party)
set(DEFORMSIM_TETGEN_ROOT ${DEFORMSIM_WORKSPACE_THIRD_PARTY}/tetgen-1.6.0)

foreach(_deformsim_tetgen_file IN ITEMS tetgen.cxx predicates.cxx tetgen.h)
    deformsim_require_file("${DEFORMSIM_TETGEN_ROOT}/${_deformsim_tetgen_file}"
        "workspace-vendored TetGen file")
endforeach()

set(DEFORMSIM_COMMON_INCLUDE_DIRS
    ${DEFORMSIM_ONEAPI_MKL_INCLUDE}
    ${DEFORMSIM_PROJECT_ROOT}
    ${DEFORMSIM_PROJECT_ROOT}/BMGL
    ${DEFORMSIM_TETGEN_ROOT}
    ${DEFORMSIM_WORKSPACE_THIRD_PARTY}
)

set(DEFORMSIM_TETRA_SUPPORT_SOURCES
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/geometry.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/matrix.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/object.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/surface.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/vector.cpp
    ${DEFORMSIM_TETGEN_ROOT}/predicates.cxx
)

function(deformsim_apply_common_compile_settings target_name)
    target_include_directories(${target_name} PRIVATE
        ${DEFORMSIM_COMMON_INCLUDE_DIRS}
    )

    target_compile_definitions(${target_name} PRIVATE
        WIN32
        _WINDOWS
        MKL_LP64=1
        NOMINMAX
        _USE_MATH_DEFINES
    )

endfunction()

function(deformsim_apply_common_link_settings target_name)
    target_link_options(${target_name} PRIVATE /DYNAMICBASE:NO)

    target_link_directories(${target_name} PRIVATE
        ${DEFORMSIM_SYSTEM_LIB_DIRS}
        ${DEFORMSIM_ONEAPI_MKL_LIB}
        ${DEFORMSIM_ONEAPI_COMPILER_LIB}
    )

    target_link_libraries(${target_name} PRIVATE
        ${DEFORMSIM_MKL_INTEL_LP64_LIB}
        ${DEFORMSIM_MKL_INTEL_THREAD_LIB}
        ${DEFORMSIM_MKL_CORE_LIB}
        ${DEFORMSIM_LIBIOMP5MD_LIB}
    )
endfunction()

function(deformsim_apply_common_target_settings target_name)
    deformsim_apply_common_compile_settings(${target_name})
    deformsim_apply_common_link_settings(${target_name})
endfunction()

set(DEFORMSIM_SIM_SOURCES
    ${DEFORMSIM_PROJECT_ROOT}/src/main.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/annotation.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/force_sampling.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/hyper_params.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/output_writer.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/progress.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/sample_pipeline.cpp
    ${DEFORMSIM_PROJECT_ROOT}/src/sim/worker.cpp
)

function(deformsim_add_main_target)
    # TETLIBRARY strips TetGen's standalone main() and switches its error path
    # to throw (BMGL/object.h defines the same macro on the consumer side).
    add_library(deformsim_main_tetgen OBJECT
        ${DEFORMSIM_TETGEN_ROOT}/tetgen.cxx
    )
    deformsim_apply_common_compile_settings(deformsim_main_tetgen)
    target_compile_definitions(deformsim_main_tetgen PRIVATE TETLIBRARY)

    add_executable(LVBasicFramework
        ${DEFORMSIM_SIM_SOURCES}
        ${DEFORMSIM_TETRA_SUPPORT_SOURCES}
        $<TARGET_OBJECTS:deformsim_main_tetgen>
    )

    deformsim_apply_common_target_settings(LVBasicFramework)

    target_include_directories(LVBasicFramework PRIVATE
        ${DEFORMSIM_PROJECT_ROOT}/src
    )

    set_target_properties(LVBasicFramework PROPERTIES
        WIN32_EXECUTABLE OFF
    )
endfunction()

function(deformsim_add_tetra_verification_tool target_name source_path)
    set(tetgen_object_target ${target_name}_tetgen)

    add_library(${tetgen_object_target} OBJECT
        ${DEFORMSIM_TETGEN_ROOT}/tetgen.cxx
    )

    deformsim_apply_common_compile_settings(${tetgen_object_target})

    target_compile_definitions(${tetgen_object_target} PRIVATE
        TETLIBRARY
    )

    add_executable(${target_name}
        ${source_path}
        ${DEFORMSIM_TETRA_SUPPORT_SOURCES}
        $<TARGET_OBJECTS:${tetgen_object_target}>
    )

    deformsim_apply_common_target_settings(${target_name})
endfunction()
