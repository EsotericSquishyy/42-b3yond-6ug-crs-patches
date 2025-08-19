CXXFLAGS    ?= -O3 -g -funroll-loops
CXXEFLAGS   := $(CXXFLAGS) $(CPPFLAGS) -Wall -std=c++11

CC          ?= gcc
CXX         ?= g++
PLUGIN_BASE = "$(shell $(CC) -print-file-name=plugin)"
PLUGIN_FLAGS = -fPIC -fno-rtti -fno-exceptions -I$(PLUGIN_BASE)/include -I$(PLUGIN_BASE)

all: find_inst_pass.so

find_inst_pass.so: src/find-inst-pass.cc
	$(CXX) $(CXXEFLAGS) $(PLUGIN_FLAGS) -shared $< -o $@

.PHONY: clean

clean:
	rm -f *.o *.so *~ a.out core core.[1-9][0-9]*
