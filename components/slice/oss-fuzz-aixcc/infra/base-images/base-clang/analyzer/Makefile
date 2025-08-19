SRC_DIR := $(CURDIR)/src
BUILD_DIR := $(CURDIR)/build
NPROC := $(shell nproc)

build_ka_func = \
        (rm -rf ${2}/* \
        && mkdir -p ${2} \
        && cd ${2} \
        && export CC=clang CXX=clang++ CFLAGS= CXXFLAGS= \
        && cmake ${1} \
            -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_CXX_FLAGS_RELEASE="-std=c++14 -fno-rtti -fpic -g" \
            -DCMAKE_EXE_LINKER_FLAGS="-L/usr/lib/x86_64-linux-gnu -lz" \
	    -DZLIB_LIBRARY_RELEASE=/usr/lib/x86_64-linux-gnu/libz.a \
            -DZLIB_INCLUDE_DIR=/usr/include \
        && make -j${NPROC})

all: analyzer

analyzer:
	$(call build_ka_func, ${SRC_DIR}, ${BUILD_DIR})
