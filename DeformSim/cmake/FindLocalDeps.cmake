include_guard(GLOBAL)

get_filename_component(_deformsim_default_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)

set(DEFORMSIM_PROJECT_ROOT "${_deformsim_default_root}" CACHE PATH
    "Root of the DeformSim project")
set(DEFORMSIM_ONEAPI_MKL_INCLUDE "C:/Program Files (x86)/Intel/oneAPI/mkl/latest/include" CACHE PATH
    "Intel oneAPI MKL include directory")
set(DEFORMSIM_ONEAPI_MKL_LIB "C:/Program Files (x86)/Intel/oneAPI/mkl/latest/lib" CACHE PATH
    "Intel oneAPI MKL library directory")
set(DEFORMSIM_ONEAPI_MKL_BIN "C:/Program Files (x86)/Intel/oneAPI/mkl/latest/bin" CACHE PATH
    "Intel oneAPI MKL runtime directory")
set(DEFORMSIM_ONEAPI_COMPILER_LIB "C:/Program Files (x86)/Intel/oneAPI/compiler/latest/lib" CACHE PATH
    "Intel oneAPI compiler library directory")
set(DEFORMSIM_ONEAPI_COMPILER_BIN "C:/Program Files (x86)/Intel/oneAPI/compiler/latest/bin" CACHE PATH
    "Intel oneAPI compiler runtime directory")

function(deformsim_require_path path label)
  if(NOT EXISTS "${path}")
    message(FATAL_ERROR "${label} not found: ${path}")
  endif()
  if(NOT IS_DIRECTORY "${path}")
    message(FATAL_ERROR "${label} is not a directory: ${path}")
  endif()
endfunction()

function(deformsim_require_file path label)
  if(NOT EXISTS "${path}")
    message(FATAL_ERROR "${label} not found: ${path}")
  endif()
  if(IS_DIRECTORY "${path}")
    message(FATAL_ERROR "${label} is a directory, expected a file: ${path}")
  endif()
endfunction()

deformsim_require_path("${DEFORMSIM_PROJECT_ROOT}" "DEFORMSIM_PROJECT_ROOT")
deformsim_require_path("${DEFORMSIM_ONEAPI_MKL_INCLUDE}" "DEFORMSIM_ONEAPI_MKL_INCLUDE")
deformsim_require_path("${DEFORMSIM_ONEAPI_MKL_LIB}" "DEFORMSIM_ONEAPI_MKL_LIB")
deformsim_require_path("${DEFORMSIM_ONEAPI_MKL_BIN}" "DEFORMSIM_ONEAPI_MKL_BIN")
deformsim_require_path("${DEFORMSIM_ONEAPI_COMPILER_LIB}" "DEFORMSIM_ONEAPI_COMPILER_LIB")
deformsim_require_path("${DEFORMSIM_ONEAPI_COMPILER_BIN}" "DEFORMSIM_ONEAPI_COMPILER_BIN")

foreach(local_dir IN ITEMS BMGL Utility)
  deformsim_require_path("${DEFORMSIM_PROJECT_ROOT}/${local_dir}" "DEFORMSIM_PROJECT_ROOT/${local_dir}")
endforeach()

if(CMAKE_SIZEOF_VOID_P EQUAL 8)
  set(_deformsim_target_arch "x64")
  set(_deformsim_other_arch "x86")
else()
  set(_deformsim_target_arch "x86")
  set(_deformsim_other_arch "x64")
endif()

function(_deformsim_append_unique_existing_dir list_name candidate)
  if(EXISTS "${candidate}" AND IS_DIRECTORY "${candidate}")
    set(_items "${${list_name}}")
    list(APPEND _items "${candidate}")
    list(REMOVE_DUPLICATES _items)
    set(${list_name} "${_items}" PARENT_SCOPE)
  endif()
endfunction()

set(DEFORMSIM_SYSTEM_LIB_DIRS "")
if(DEFINED ENV{LIB} AND NOT "$ENV{LIB}" STREQUAL "")
  foreach(system_lib_dir IN LISTS ENV{LIB})
    if(system_lib_dir MATCHES "(^|[/\\\\])${_deformsim_other_arch}([/\\\\]|$)")
      continue()
    endif()
    _deformsim_append_unique_existing_dir(DEFORMSIM_SYSTEM_LIB_DIRS "${system_lib_dir}")
  endforeach()
endif()

get_filename_component(_deformsim_msvc_bin_dir "${CMAKE_LINKER}" DIRECTORY)
get_filename_component(_deformsim_msvc_bin_dir "${_deformsim_msvc_bin_dir}" DIRECTORY)
get_filename_component(_deformsim_msvc_bin_dir "${_deformsim_msvc_bin_dir}" DIRECTORY)
get_filename_component(_deformsim_msvc_root "${_deformsim_msvc_bin_dir}" DIRECTORY)

_deformsim_append_unique_existing_dir(DEFORMSIM_SYSTEM_LIB_DIRS "${_deformsim_msvc_root}/lib/${_deformsim_target_arch}")

get_filename_component(_deformsim_sdk_bin_dir "${CMAKE_MT}" DIRECTORY)
get_filename_component(_deformsim_sdk_version_dir "${_deformsim_sdk_bin_dir}" DIRECTORY)
get_filename_component(_deformsim_sdk_version "${_deformsim_sdk_version_dir}" NAME)
get_filename_component(_deformsim_sdk_bin_root "${_deformsim_sdk_version_dir}" DIRECTORY)
get_filename_component(_deformsim_sdk_root "${_deformsim_sdk_bin_root}" DIRECTORY)
if(NOT EXISTS "${_deformsim_sdk_root}/lib/${_deformsim_sdk_version}")
  if(DEFINED CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION AND
     NOT CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION STREQUAL "")
    set(_deformsim_sdk_root "C:/Program Files (x86)/Windows Kits/10")
    set(_deformsim_sdk_version "${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}")
  elseif(DEFINED CMAKE_SYSTEM_VERSION AND NOT CMAKE_SYSTEM_VERSION STREQUAL "")
    set(_deformsim_sdk_root "C:/Program Files (x86)/Windows Kits/10")
    set(_deformsim_sdk_version "${CMAKE_SYSTEM_VERSION}")
  endif()
endif()

_deformsim_append_unique_existing_dir(DEFORMSIM_SYSTEM_LIB_DIRS "${_deformsim_sdk_root}/lib/${_deformsim_sdk_version}/ucrt/${_deformsim_target_arch}")
_deformsim_append_unique_existing_dir(DEFORMSIM_SYSTEM_LIB_DIRS "${_deformsim_sdk_root}/lib/${_deformsim_sdk_version}/um/${_deformsim_target_arch}")
_deformsim_append_unique_existing_dir(DEFORMSIM_SYSTEM_LIB_DIRS "C:/Program Files (x86)/Windows Kits/NETFXSDK/4.8/lib/um/${_deformsim_target_arch}")

if(NOT DEFORMSIM_SYSTEM_LIB_DIRS)
  message(FATAL_ERROR "No system library directories available for target architecture ${_deformsim_target_arch}")
endif()

foreach(system_lib_dir IN LISTS DEFORMSIM_SYSTEM_LIB_DIRS)
  deformsim_require_path("${system_lib_dir}" "DEFORMSIM_SYSTEM_LIB_DIRS")
endforeach()

set(DEFORMSIM_MKL_INTEL_LP64_LIB "${DEFORMSIM_ONEAPI_MKL_LIB}/mkl_intel_lp64_dll.lib")
set(DEFORMSIM_MKL_INTEL_THREAD_LIB "${DEFORMSIM_ONEAPI_MKL_LIB}/mkl_intel_thread_dll.lib")
set(DEFORMSIM_MKL_CORE_LIB "${DEFORMSIM_ONEAPI_MKL_LIB}/mkl_core_dll.lib")
set(DEFORMSIM_LIBIOMP5MD_LIB "${DEFORMSIM_ONEAPI_COMPILER_LIB}/libiomp5md.lib")

deformsim_require_file("${DEFORMSIM_MKL_INTEL_LP64_LIB}" "DEFORMSIM_MKL_INTEL_LP64_LIB")
deformsim_require_file("${DEFORMSIM_MKL_INTEL_THREAD_LIB}" "DEFORMSIM_MKL_INTEL_THREAD_LIB")
deformsim_require_file("${DEFORMSIM_MKL_CORE_LIB}" "DEFORMSIM_MKL_CORE_LIB")
deformsim_require_file("${DEFORMSIM_LIBIOMP5MD_LIB}" "DEFORMSIM_LIBIOMP5MD_LIB")

set(DEFORMSIM_RUNTIME_PATH_DIRS
  "${DEFORMSIM_ONEAPI_MKL_BIN}"
  "${DEFORMSIM_ONEAPI_COMPILER_BIN}"
)
