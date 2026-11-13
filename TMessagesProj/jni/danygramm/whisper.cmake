# Danygramm on-device voice message transcription: libdanywhisper.so = whisper.cpp + ggml (CPU) + JNI bridge.
# Loaded lazily from Java only when the user transcribes a message, so the main library is unaffected.
get_filename_component(DANY_JNI_DIR "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(DANY_WHISPER_DIR ${DANY_JNI_DIR}/third_party/whisper.cpp)

set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GGML_ALL_WARNINGS OFF CACHE BOOL "" FORCE)
set(GGML_STATIC OFF CACHE BOOL "" FORCE)
if (${ANDROID_ABI} STREQUAL "arm64-v8a")
    # fp16 arithmetic + dot product (ARMv8.2, Cortex-A55/A75 and newer). Java checks /proc/cpuinfo before loading.
    set(GGML_CPU_ARM_ARCH "armv8.2-a+fp16+dotprod" CACHE STRING "" FORCE)
endif()
set(DANY_SAVED_BUILD_SHARED_LIBS ${BUILD_SHARED_LIBS})
set(BUILD_SHARED_LIBS OFF)
add_subdirectory(${DANY_WHISPER_DIR}/ggml ${CMAKE_CURRENT_BINARY_DIR}/danywhisper-ggml EXCLUDE_FROM_ALL)
set(BUILD_SHARED_LIBS ${DANY_SAVED_BUILD_SHARED_LIBS})

file(READ "${DANY_WHISPER_DIR}/CMakeLists.txt" DANY_WHISPER_CMAKE)
string(REGEX MATCH "project\\(\"whisper\\.cpp\" VERSION ([0-9]+\\.[0-9]+\\.[0-9]+)\\)" DANY_WHISPER_VERSION_MATCH "${DANY_WHISPER_CMAKE}")
set(DANY_WHISPER_VERSION "${CMAKE_MATCH_1}")

add_library(danywhisper SHARED
        ${DANY_WHISPER_DIR}/src/whisper.cpp
        ${DANY_WHISPER_DIR}/src/aneforge/whisper-aneforge.cpp
        ${DANY_JNI_DIR}/danygramm/whisper_jni.cpp)
target_include_directories(danywhisper PRIVATE
        ${DANY_WHISPER_DIR}/include
        ${DANY_WHISPER_DIR}/src
        ${DANY_WHISPER_DIR}/ggml/include)
target_compile_definitions(danywhisper PRIVATE GGML_USE_CPU WHISPER_VERSION="${DANY_WHISPER_VERSION}")
target_compile_options(danywhisper PRIVATE -O3)
target_link_libraries(danywhisper ggml log)
target_link_options(danywhisper PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,--exclude-libs,ALL")
