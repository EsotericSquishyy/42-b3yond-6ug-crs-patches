from tree_sitter_language_pack import get_parser, get_language, get_binding

def extract_functions_with_line_numbers(source_code):
    language = get_language('c')
    c_binding = get_binding('c')
    parser = get_parser('c')
    tree = parser.parse(source_code.encode())

    root_node = tree.root_node
    functions = []

    def traverse(node):
        if node.type == 'function_definition':
            function_name_node = node.child_by_field_name('declarator').child_by_field_name('declarator')
            if function_name_node:
                # function_name = source_code[function_name_node.start_byte:function_name_node.end_byte]
                function_name = function_name_node.text.decode('utf-8')
                start_line = node.start_point[0] + 1  # Convert to 1-based index
                end_line = node.end_point[0] + 1      # Convert to 1-based index
                functions.append((function_name, start_line, end_line))
        for child in node.children:
            traverse(child)

    traverse(root_node)
    return functions

def find_function_by_line(source_file, line_number):
    with open(source_file, 'r') as f:
        source_code = f.read()
    functions = extract_functions_with_line_numbers(source_code)
    for function_name, start_line, end_line in functions:
        if start_line <= line_number <= end_line:
            return function_name
    return None

if __name__ == "__main__":
    source_file = "tests/c/c-blosc2/blosc/frame.c"  # Path to your C source file
    line_num = 554  # Line number you're interested in
    function_name = find_function_by_line(source_file, line_num)
    if function_name:
        print(f"Line {line_num} is inside function: {function_name}")
    else:
        print(f"No function found containing line {line_num} in file {source_file}")