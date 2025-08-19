## LLVM-O0-BitcodeWriter-Pass
This LLVM pass generates O0 optimized bitcode. Tested with LLVM-14.

## Build
Compile the pass with:
```bash
make all
```

## Usage
To generate bitcode using this pass, execute:
```bash
clang -O2 -g -fpass-plugin=./writebc.so -c example.c -o example.o
```
The bitcode will be output to example.c.bc.

