LLVM_CONFIG ?= llvm-config

CXXFLAGS    ?= -O3 -funroll-loops
CXXFLAGS    += -Wall -D_FORTIFY_SOURCE=2 -g -Wno-pointer-sign \
			   -Wno-variadic-macros -std=c++17

CLANG_CFL    = `$(LLVM_CONFIG) --cxxflags` -Wl,-znodelete -fno-rtti -fpic $(CXXFLAGS)
CLANG_LFL    = `$(LLVM_CONFIG) --ldflags` $(LDFLAGS)

ifeq "$(origin CC)" "default"
  CC         = clang
  CXX        = clang++
endif

.PHONY: all clean

all: writebc.so

writebc.so: src/writebc-pass.cc
	$(CXX) $(CLANG_CFL) -shared -lssl -lcrypto $< -o $@ $(CLANG_LFL)

clean:
	rm -f *.o *.so *~ a.out core core.[1-9][0-9]*
