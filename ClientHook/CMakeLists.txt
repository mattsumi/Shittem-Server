cmake_minimum_required(VERSION 3.20)
project(BAUnpin LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)

# Expect MinHook via vcpkg: vcpkg install minhook:x64-windows
find_package(minhook CONFIG REQUIRED)

# Main DLL
add_library(BAUnpin SHARED
  src/Hook.cpp
)

target_include_directories(BAUnpin PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)

target_link_libraries(BAUnpin PRIVATE
  minhook::minhook
  wintrust
  crypt32
  shlwapi
)

set_target_properties(BAUnpin PROPERTIES
  OUTPUT_NAME BAUnpin
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)

# New injector executable (BA-Cheeto style)
add_executable(BAUnpinInjector
  src/Injector.cpp
)

target_link_libraries(BAUnpinInjector PRIVATE
  kernel32
)

set_target_properties(BAUnpinInjector PROPERTIES
  OUTPUT_NAME BAUnpinInjector
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
)

# Copy the old PowerShell script for compatibility
configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/inject.ps1
  ${CMAKE_BINARY_DIR}/bin/inject_legacy.ps1
  COPYONLY
)
