cmake_minimum_required(VERSION 3.13.4)

project(CodeInjector)



find_package(LLVM REQUIRED CONFIG)
find_package(Clang REQUIRED CONFIG)

include_directories(${LLVM_INCLUDE_DIRS} ${CLANG_INCLUDE_DIRS})
link_directories(${LLVM_LIBRARY_DIRS})

add_definitions(${LLVM_DEFINITIONS})

add_executable(code_injector code_injector.cpp)

target_link_libraries(code_injector
  clangTooling
  clangBasic
  clangASTMatchers
  clangFrontend
  clangToolingRefactoring
  clangLex
  clangAST
  clangRewrite
  clangRewriteFrontend
  ${LLVM_LIBRARIES}
)

set_target_properties(code_injector PROPERTIES
  COMPILE_FLAGS "-fno-rtti"
)