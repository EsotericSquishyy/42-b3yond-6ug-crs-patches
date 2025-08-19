
def get_path_list(project_dir):
    """
    Recursively get all the files in a directory.

    :param project_dir: Path to the project directory.
    :return: A list of file paths.
    """
    import os
    from collections import defaultdict
    paths = []
    for root, dirs, files in os.walk(project_dir):
        for file in files:
            paths.append(os.path.join(root, file))
    return paths

class TrieNode:
    def __init__(self):
        # Children nodes: key is segment, value is TrieNode
        self.children = {}
        # List of full paths that end at this node
        self.paths = []

class ReverseTrie:
    def __init__(self):
        self.root = TrieNode()
    
    def insert(self, path: str):
        """
        Inserts a path into the trie in reverse order of its segments.
        """
        segments = path.strip('/').split('/')
        current = self.root
        # Insert segments in reverse order
        for segment in reversed(segments):
            if segment not in current.children:
                current.children[segment] = TrieNode()
            current = current.children[segment]
            # At the leaf node, store the original path
            current.paths.append(path)
    

def make_path_trie(path_list):
    trie = ReverseTrie()
    for path in path_list:
        trie.insert(path)
    return trie

def match_file_in_path_trie(trie, target_path):
    """
    Searches for paths in the trie that have the longest common trailing segments with the given path.
    
    Returns a list of matching paths.
    """
    segments = target_path.strip('/').split('/')
    current = trie.root
    matched_paths = []
    max_depth = 0
    current_depth = 0
    
    for segment in reversed(segments):
        if segment in current.children:
            current = current.children[segment]
            current_depth += 1
            # Update matched_paths and max_depth
            if current.paths:
                if current_depth > max_depth:
                    max_depth = current_depth
                    matched_paths = current.paths.copy()
                elif current_depth == max_depth:
                    matched_paths.extend(current.paths)
        else:
            break  # No further matching segments
    
    return matched_paths

def truncate_sarif_path(path):
    # Infer
    if path.startswith("file:"):
        return path[5:]
    # TODO: Add more cases for other tools that generate SARIF files
    return path

if __name__ == "__main__":

    project_dir = "../libxml2"  # Path to your project directory
    paths = get_path_list(project_dir)
    print(f"Found {len(paths)} files in project directory")