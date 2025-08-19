#!/bin/bash
clang -fpass-plugin=../writebc.so -O2 -g src/all.c -o prog
rm prog
