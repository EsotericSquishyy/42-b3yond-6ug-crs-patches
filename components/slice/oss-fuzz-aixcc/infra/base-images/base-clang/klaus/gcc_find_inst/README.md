## GCC-Find-Inst-Pass
This tool is designed to identify code locations affected by the output results of patch_analyzer. Tested with GCC 11.4.0.

## Build
Compile the pass with:
```bash
sudo apt install -y gcc-11-plugin-dev
make all
```

## Usage
Pass the two files path by patch_analyzer, `COND_FILE` and `PROP_FILE`, using environment variables, and specify the output path with the environment variable `OUTPUT_FILE`.
```bash
COND_FILE="cond_file.txt" PROP_FILE="prop_file.txt" OUTPUT_FILE="output.txt" gcc -fsanitize-coverage=trace-pc -fplugin=./find_inst_pass.so -O0 -g example.c -o example
```
The results of the slicing will be output to the file output.txt.
