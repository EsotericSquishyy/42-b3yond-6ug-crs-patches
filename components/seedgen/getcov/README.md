# GetCov

Quickly identify uncovered code in your C project. Results will be printed as a json file containing the coverage file ID.

## Usage

```bash
getcov [OPTIONS] <executable> [args]...
```

## Options

| Option                    | Description                                                     |
| ------------------------- | --------------------------------------------------------------- |
| `-i, --input <DIRECTORY>` | Sets the seed directory for batch processing                    |
| `--all`                   | Extract all functions                                           |
| `--text`                  | Output in text format instead of JSON (default: JSON)           |
| `--hybrid`                | Output in hybrid format (JSON + Text)                           |
| `--profdata <*.profdata>` | Instead of running the program, use the provided profdata file. |

## Examples

### Single Input

```bash
getcov -- /path/to/binary arg1 arg2
```

### Multiple Inputs from Directory

```bash
getcov -i ./inputs -- /path/to/binary arg1 @@
```

### Extract All Functions with Text Output

```bash
getcov --all --text -- /path/to/binary arg1
```

> **Note:** Use '@@' in arguments to specify where the input file path should be inserted.
> If '@@' is not provided when using -i/--input, the file path will be appended at the end.

## License Information

### Modified Components

This project contains a modified version of the [llvm-cov-json library](https://github.com/nbars/llvm-cov-json-rs). The modification enables public access to the `Region` struct to better support the project's functionality.

### License Terms

- Original llvm-cov-json library: AGPL-3.0-only
- This project (including modifications): AGPL-3.0-only

### Compliance Notice

By using or contributing to this project, you agree to comply with the AGPL-3.0-only license terms, which require:

- Making source code of derivative works publicly available
- Distributing modifications under the same license
