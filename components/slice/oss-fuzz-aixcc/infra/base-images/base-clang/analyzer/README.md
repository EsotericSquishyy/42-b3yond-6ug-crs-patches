# static-analyzer-for-program-slicing
This project is based on [hot_bpf_analyzer](https://github.com/Markakd/hot_bpf_analyzer/)

## Step 1: build clang
According to the README.md in the for_llvm directory, you should obtain the LLVM source and build Clang.

## Step 2 : build target
When building the target, ensure that the build flags include "-g" for debugging information and "-O2" for getting output from the custom clang.

## Step 3: build the analyzer
You should update the content of Makefile.inc with the path to the LLVM build folder that you built in step 1.

Then run `make` to build the analyzer.

You can also find the prebuilt binary at `prebuilt/analyzer`

## Step 4: run analyzer

cd into the working directory  

You can set the target with the line number or function name. If it is impossible to get debug information, you should use it with function name. Now the analyzer support building call graph and slicing seperately.

line number example:
```
/home/xxylab/yj/static-analyzer-for-program-slicing/build/lib/analyzer --srcroot=/home/xxylab/yj/proj/uwsgi/ --file=core/strings.c --line=247 `find . -name "*.bc"`
```

line number example with building call graph only:
```
/home/xxylab/yj/static-analyzer-for-program-slicing/build/lib/analyzer -callgraph=true --srcroot=/home/xxylab/yj/proj/uwsgi/ --file=core/strings.c --line=247 `find . -name "*.bc"`
```

line number example with slicing only (using previously built call graph):
```
/home/xxylab/yj/static-analyzer-for-program-slicing/build/lib/analyzer -slicing=true --srcroot=/home/xxylab/yj/proj/uwsgi/ --file=core/strings.c --line=247 `find . -name "*.bc"`
```

## Attention: Now slicing only has bug, please add '-callgraph=true' and '-slicing=true' together to get the correct result.

function name example:
```
/home/xxylab/yj/static-analyzer-for-program-slicing/build/lib/analyzer --srcroot=/home/xxylab/yj/proj/linux/ --file=drivers/net/wireless/marvell/mwifiex/cfg80211.c --func=mwifiex_cfg80211_sched_scan_start `find . -name "*.bc"`
```

Result will be saved as a callgraph_result and slicing_result.

slicing_result:
```
block:x11_out.c:980:100
block:x11_out.c:983:100
block:x11_out.c:984:100
block:x11_out.c:993:100
func:bifs/bifs_codec.c:126:100
func:bifs/bifs_codec.c:214:100
func:bifs/bifs_codec.c:226:100
func:bifs/bifs_codec.c:259:100
func:bifs/bifs_codec.c:347:100
```
