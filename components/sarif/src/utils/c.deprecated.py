from clang.cindex import Index, CursorKind

# TODO: a better way to implement this
# current implementation is VERY BAD

def find_function_by_line(filename, target_line):
    # Create an index to manage the parsing process
    index = Index.create()

    # Parse the C source file
    translation_unit = index.parse(filename)

    # Function to recursively search for the function containing the target line
    def search_function(cursor):
        if cursor.kind == CursorKind.FUNCTION_DECL:
            # print(cursor.extent)
            # check if the filename matches
            if cursor.location.file.name == filename:
                start_line = cursor.extent.start.line
                end_line = cursor.extent.end.line
                if start_line <= target_line <= end_line:
                    return cursor.spelling
        for child in cursor.get_children():
            result = search_function(child)
            if result:
                return result
        return None

    # Start the search from the root cursor
    function_name = search_function(translation_unit.cursor)
    return function_name


if __name__ == "__main__":
    source_file = "tests/c/c-blosc2/blosc/frame.c"  # Path to your C source file
    line_num = 554  # Line number you're interested in
    function_name = find_function_by_line(source_file, line_num)
    if function_name:
        print(f"Line {line_num} is inside function: {function_name}")
    else:
        print(f"No function found containing line {line_num} in file {source_file}")