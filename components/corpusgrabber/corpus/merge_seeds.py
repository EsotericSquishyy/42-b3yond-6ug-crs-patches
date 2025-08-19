#!/usr/bin/env python3
import os
import argparse
import shutil
import hashlib

def compute_file_hash(file_path, block_size=65536):
    """
    Compute SHA256 hash of a file.
    Reads the file in binary mode in blocks of block_size bytes.
    """
    hash_obj = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            hash_obj.update(data)
    return hash_obj.hexdigest()

def merge_project_files(project_dirs, dest_project_dir):
    """
    Merge all seed files from the provided project directories into dest_project_dir.
    
    This function recursively searches each given project directory (including any nested subdirectories)
    for seed files. Duplicate files are detected based on their SHA256 hash so that even if files 
    have different names but identical content, only one copy is merged. Also, the output directory 
    is flat—files are copied directly into dest_project_dir without retaining their original folder structure.
    
    :param project_dirs: List of directories (strings) for a given project. Some entries may be None.
    :param dest_project_dir: Destination directory (flat) for the merged seed files.
    """
    unique_hashes = {}
    used_names = set()
    
    for project_dir in project_dirs:
        if project_dir is None or not os.path.isdir(project_dir):
            continue
        
        # Recursively walk through the directory—including nested subdirectories.
        for root, _, files in os.walk(project_dir):
            for file in files:
                src_file = os.path.join(root, file)
                try:
                    file_hash = compute_file_hash(src_file)
                except Exception as e:
                    print(f"Error computing hash for {src_file}: {e}")
                    continue

                # Skip already added files (same contents)
                if file_hash in unique_hashes:
                    continue

                # Use the raw file name only so that the merged destination is flat.
                candidate = file
                base, ext = os.path.splitext(candidate)
                counter = 1
                while candidate in used_names:
                    candidate = f"{base}_{counter}{ext}"
                    counter += 1

                unique_hashes[file_hash] = (src_file, candidate)
                used_names.add(candidate)
    
    # Copy each unique file to the destination project directory.
    for _, (src_file, dest_file_name) in unique_hashes.items():
        dest_file = os.path.join(dest_project_dir, dest_file_name)
        try:
            shutil.copy2(src_file, dest_file, follow_symlinks=False)
        except Exception as e:
            print(f"Error copying {src_file} to {dest_file}: {e}")

def merge_seeds(seed_dirs, dest_dir):
    """
    Merge fuzzing seeds from multiple directories into a single destination.
    
    Each provided seed directory is expected to have a subdirectory per project.
    Note that within each project directory, seed files may reside in further nested subdirectories.
    The final merged directory created for each project is flat (all files are copied
    directly into it) and duplicate files (by hash) are eliminated.
    
    :param seed_dirs: List of paths (strings) to seed directories.
    :param dest_dir: Destination directory where merged seeds per project will be stored.
    """
    # Identify the union of project names present in any of the seed directories.
    projects = set()
    for seed_dir in seed_dirs:
        if os.path.isdir(seed_dir):
            projects.update([
                d for d in os.listdir(seed_dir)
                if os.path.isdir(os.path.join(seed_dir, d))
            ])
    
    if not projects:
        print("No project directories found in the provided seed directories.")
        return
    
    print("Merging seeds for projects:", projects)
    
    for project in projects:
        print(f"Merging seeds for project: {project}")
        dest_project_dir = os.path.join(dest_dir, project)
        os.makedirs(dest_project_dir, exist_ok=True)
        
        # Gather the project directories from each seed directory.
        project_source_dirs = []
        for seed_dir in seed_dirs:
            project_path = os.path.join(seed_dir, project)
            if os.path.isdir(project_path):
                project_source_dirs.append(project_path)
        
        merge_project_files(project_source_dirs, dest_project_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge fuzzing seeds from multiple directories and remove duplicate files based on content hash. " +
                    "Each provided seed directory should contain subdirectories for individual projects, and the merged output " +
                    "will be flat (no subdirectories)."
    )
    parser.add_argument("--seeds", required=True, nargs="+",
                        help="Paths to seed directories. Each directory should contain project subdirectories.")
    parser.add_argument("--dest", required=True,
                        help="Path to the destination directory where merged seeds (flat per project) will be stored.")
    
    args = parser.parse_args()
    merge_seeds(args.seeds, args.dest)