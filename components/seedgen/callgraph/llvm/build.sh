#!/bin/bash
# Build Callgraph LLVM Pass

LLVM_CXXFLAGS=`llvm-config --cxxflags`
clang++ -fno-rtti -O3 -g $LLVM_CXXFLAGS -fno-exceptions -Wno-deprecated-declarations SeedMindCFPass.cpp -fPIC -shared -Wl,-soname,SeedMindCFPass.so -o SeedMindCFPass.so