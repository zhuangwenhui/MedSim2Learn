include_guard(GLOBAL)

set(DEFORMSIM_COMMON_INCLUDE_DIRS
    ${DEFORMSIM_RC_INCLUDE_DIRS}
    ${DEFORMSIM_ONEAPI_MKL_INCLUDE}
    ${DEFORMSIM_PROJECT_ROOT}
    ${DEFORMSIM_PROJECT_ROOT}/BMGL
    ${DEFORMSIM_PROJECT_ROOT}/GL
    ${DEFORMSIM_PROJECT_ROOT}/Utility
    ${DEFORMSIM_PROJECT_ROOT}/third_party
)

set(DEFORMSIM_TETRA_SUPPORT_SOURCES
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/bmgl.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/geometry.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/matrix.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/object.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/surface.cpp
    ${DEFORMSIM_PROJECT_ROOT}/BMGL/vector.cpp
    ${DEFORMSIM_PROJECT_ROOT}/Utility/predicates.cpp
)

function(deformsim_apply_common_compile_settings target_name)
    target_include_directories(${target_name} PRIVATE
        ${DEFORMSIM_COMMON_INCLUDE_DIRS}
    )

    target_compile_definitions(${target_name} PRIVATE
        WIN32
        _WINDOWS
        _AFXDLL
        MKL_LP64=1
        NOMINMAX
        _USE_MATH_DEFINES
    )

    target_compile_options(${target_name} PRIVATE /openmp)
endfunction()

function(deformsim_apply_common_link_settings target_name)
    target_link_options(${target_name} PRIVATE /DYNAMICBASE:NO)

    target_link_directories(${target_name} PRIVATE
        ${DEFORMSIM_SYSTEM_LIB_DIRS}
        ${DEFORMSIM_ONEAPI_MKL_LIB}
        ${DEFORMSIM_ONEAPI_COMPILER_LIB}
        ${DEFORMSIM_PROJECT_ROOT}/Lib
    )

    target_link_libraries(${target_name} PRIVATE
        OpenMP::OpenMP_CXX
        ${DEFORMSIM_MKL_INTEL_LP64_LIB}
        ${DEFORMSIM_MKL_INTEL_THREAD_LIB}
        ${DEFORMSIM_MKL_CORE_LIB}
        ${DEFORMSIM_LIBIOMP5MD_LIB}
        opengl32.lib
        glu32.lib
    )
endfunction()

function(deformsim_apply_common_target_settings target_name)
    deformsim_apply_common_compile_settings(${target_name})
    deformsim_apply_common_link_settings(${target_name})
endfunction()

function(deformsim_add_main_target)
    add_executable(LVBasicFramework
        ${DEFORMSIM_PROJECT_ROOT}/stdafx.cpp
        ${DEFORMSIM_PROJECT_ROOT}/BMGL/imagefilter.cpp
        ${DEFORMSIM_PROJECT_ROOT}/BMGL/image.cpp
        ${DEFORMSIM_TETRA_SUPPORT_SOURCES}
        ${DEFORMSIM_PROJECT_ROOT}/Utility/tetgen.cpp
        ${DEFORMSIM_PROJECT_ROOT}/LVBasicFramework.rc
    )

    deformsim_apply_common_target_settings(LVBasicFramework)

    target_link_libraries(LVBasicFramework PRIVATE
        ${DEFORMSIM_GLUT32_LIB}
        ${DEFORMSIM_DEVIL_LIB}
        ${DEFORMSIM_ILU_LIB}
        ${DEFORMSIM_ILUT_LIB}
    )

    set_target_properties(LVBasicFramework PROPERTIES
        WIN32_EXECUTABLE OFF
    )
endfunction()

function(deformsim_add_tetra_verification_tool target_name source_path)
    set(tetgen_object_target ${target_name}_tetgen)

    add_library(${tetgen_object_target} OBJECT
        ${DEFORMSIM_PROJECT_ROOT}/Utility/tetgen.cpp
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
