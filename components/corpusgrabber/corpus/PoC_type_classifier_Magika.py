import os
from pathlib import Path
from magika import Magika

"""Classify PoCs' content types with Magika and create symbolic links
instead of copying the seed files.
"""

def detect(project_root_dir="projects"):
    magika = Magika()
    
    # Traverse all projects
    for project in os.listdir(project_root_dir):
        print(f"Processing project: {project}")
        project_dir = os.path.join(project_root_dir, project)
        for seed in os.listdir(project_dir):
            seed_path = os.path.join(project_dir, seed)
            magika_res = magika.identify_path(Path(seed_path))
            # Obtain the label
            seed_label = magika_res.dl.ct_label if magika_res.dl.ct_label is not None else magika_res.output.ct_label
            label_dir = os.path.join("extensions_magika", seed_label)
            os.makedirs(label_dir, exist_ok=True)
            link_path = os.path.join(label_dir, seed)

            # If a symlink or file already exists at the link path, remove it.
            if os.path.lexists(link_path):
                os.remove(link_path)
            
            # Compute the relative path from the label directory to the original seed file
            relative_seed_path = os.path.relpath(seed_path, start=label_dir)
            
            # Create a symbolic link using the relative path
            os.symlink(relative_seed_path, link_path)

if __name__ == "__main__":
    detect()