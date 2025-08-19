from sarif.loader import load_sarif_file
from utils.path import get_path_list, make_path_trie, match_file_in_path_trie, truncate_sarif_path
from utils.c import find_function_by_line
import logging

def parse_sarif_report(project_dir, sarif_path):
    """
    return 2 values:
        1. a dictionary with file path as key and a list of code locations as value
        2. statistics of the results
    """
    # preprocess the project dir
    project_path_list = get_path_list(project_dir)
    project_path_trie = make_path_trie(project_path_list)
    # Parse the report and return the results
    sarif_file = load_sarif_file(sarif_path)
    results = sarif_file.get_results()

    parse_result = []
    
    stats = {'total': 0, 'multiple_locations': 0, 'no_location': 0, 'no_function': 0, 'no_file': 0, 'multiple_file': 0, 'success': 0}

    for item in results:
        # print(item)
        if len(item['locations']) > 1:
            # TODO: possibly multiple locations for one issue
            logging.warning(f'Multiple locations found for one issue: {item}')
            stats['multiple_locations'] += 1
        elif len(item['locations']) == 0:
            logging.error(f'No location found for issue: {item}')
            stats['no_location'] += 1
        for location in item['locations']:
            stats['total'] += 1
            file_path = location['physicalLocation']['artifactLocation']['uri']

            # process the file path for different types of SARIF files
            file_path = truncate_sarif_path(file_path)

            # try to match the file path in the project directory
            matched_paths = match_file_in_path_trie(project_path_trie, file_path)

            # TODO: a better approach to handle multiple matched paths
            if len(matched_paths) == 0:
                logging.error(f'File path {file_path} not found in project directory')
                stats['no_file'] += 1
            else:
                if len(matched_paths) > 1:
                    logging.warning(f'Multiple matched paths found for {file_path}: {matched_paths}, choose the shortest one')
                    stats['multiple_file'] += 1
                    # currently we choose the one with the fewest segments
                    matched_paths = sorted(matched_paths, key=lambda x: len(x.split('/')))
                matched_path = matched_paths[0]
                logging.debug(f'File path {file_path} matched to {matched_path}')

                # get line num
                line_num = location['physicalLocation']['region']['startLine']

                # search for the function in the file
                function_name = find_function_by_line(matched_path, line_num)
                if function_name:
                    logging.debug(f'Line {line_num} is inside function: {function_name}')
                    stats['success'] += 1
                else:
                    logging.error(f'No function found containing line {line_num} in file {matched_path}')
                    stats['no_function'] += 1

                # truncate the file path to make it relative to the project directory
                relative_path = matched_path[len(project_dir) + 1:] # "/"
                
                # add the item to the parse result
                parse_result.append({'file': relative_path, 'line': line_num, 'function': function_name, 'issue': item})

    return parse_result, stats
    #         if file_path not in parse_result:
    #             parse_result[file_path] = []
    #         parse_result[file_path].append(item)
    # return parse_result

if __name__ == '__main__':
    project_dir = '/tmp/sarif-agent/69181873-aa21-45d8-98b0-0145981a8a05/example-libpng/'
    sarif_path = 'tests/exemplar/example-libpng.sarif'
    logging.basicConfig(level=logging.DEBUG)
    sarif_result = parse_sarif_report(project_dir, sarif_path)
    # import IPython
    # IPython.embed()