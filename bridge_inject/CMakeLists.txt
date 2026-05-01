# bridge_inject/CMakeLists.txt
#
# Builds sciter_bridge.dll — the runtime memory-injection bridge for AJiaSu.
# This produces ONE DLL per architecture; pass -A x64 / -A Win32 to MSVC
# generators to control bitness. The Python injector picks the matching DLL
# based on the AJiaSu process bitness.
#
# Build (from repo root):
#   cmake -S bridge_inject -B build/bridge_x64 -A x64
#   cmake --build build/bridge_x64 --config Release
#   cmake -S bridge_inject -B build/bridge_x86 -A Win32
#   cmake --build build/bridge_x86 --config Release
#
# Outputs (in build/bridge_*/Release):
#   sciter_bridge.dll   — copy + rename to sciter_bridge_x64.dll / _x86.dll
#                         when bundling for distribution.

cmake_minimum_required(VERSION 3.20)
project(sciter_bridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Sciter SDK — headers only. We don't link against any Sciter library; we
# only need ISciterAPI's struct layout to call SciterEval at the right
# offset. Sciter's API struct is forward-compatible (new fields appended)
# so building against a recent SDK works with older runtime sciter.dll
# inside AJiaSu — as long as the major version matches (Sciter 5.x both
# sides). AJiaSu uses QuickJS-era Sciter, which is 5.x.
#
# We pin to a specific commit/tag for reproducibility. Bump when needed.
# ---------------------------------------------------------------------------
include(FetchContent)
FetchContent_Declare(
    sciter_sdk
    GIT_REPOSITORY https://gitlab.com/sciter-engine/sciter-js-sdk.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(sciter_sdk)

# ---------------------------------------------------------------------------
# Target: sciter_bridge.dll
# ---------------------------------------------------------------------------
add_library(sciter_bridge SHARED
    sciter_bridge.cpp
    bridge_resource.rc
)

target_include_directories(sciter_bridge PRIVATE
    "${sciter_sdk_SOURCE_DIR}/include"
)

target_link_libraries(sciter_bridge PRIVATE
    user32
    shell32
    advapi32
)

# Don't add a "lib" prefix on MinGW; we want a clean "sciter_bridge.dll".
set_target_properties(sciter_bridge PROPERTIES
    PREFIX ""
    OUTPUT_NAME "sciter_bridge"
)

# Static-link the C/C++ runtime so the DLL doesn't need vcruntime/msvcp
# present in AJiaSu's runtime environment. Saves a class of "DLL load failed
# in remote process because dependent DLL missing" failures.
if(MSVC)
    set_property(TARGET sciter_bridge PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded")
    target_compile_options(sciter_bridge PRIVATE /W3 /utf-8)
    # Sciter SDK headers use some non-portable patterns; silence noise.
    target_compile_options(sciter_bridge PRIVATE
        /wd4100   # unreferenced formal parameter
        /wd4505   # unreferenced local function
    )
endif()

# Distribution naming: copy to ../dist/ with arch suffix so the Python
# injector finds them. Top-level CMake invocation (per arch) drops the
# resulting DLL into ../dist/.
if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(_arch_suffix "x64")
else()
    set(_arch_suffix "x86")
endif()

add_custom_command(TARGET sciter_bridge POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory
            "${CMAKE_SOURCE_DIR}/dist"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "$<TARGET_FILE:sciter_bridge>"
            "${CMAKE_SOURCE_DIR}/dist/sciter_bridge_${_arch_suffix}.dll"
    COMMENT "Copying sciter_bridge.dll -> dist/sciter_bridge_${_arch_suffix}.dll"
)
