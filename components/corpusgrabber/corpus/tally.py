import os
import csv
import sys
import hashlib
from pathlib import Path
from tabulate import tabulate
from PoC_crawler import *
import argparse

DOWNLOAD_DIR = Path(__file__).resolve().parent / "seeds"

"""Count the # of seeds (actually PoCs) for each project.
Results are saved in a CSV file named "seeds_count.csv".
"""
def seeds_counter(prev_project_root_dir, current_project_root_dir):
    tallies = []
    project_list = oss_fuzz_projects()

    # Conduct preliminary stats
    more_than_prev = 0
    less_than_prev = 0
    same_as_prev = 0
    zero_to_non_zero = 0
    prev_projects = 0
    curr_projects = 0

    for project in project_list:
        prev_seeds_dir = prev_project_root_dir / project
        current_seeds_dir = current_project_root_dir / project
        
        if prev_seeds_dir.exists() and prev_seeds_dir.is_dir():
            prev_seeds_count = sum(1 for seed in os.scandir(prev_seeds_dir) if seed.is_file())
            prev_projects += 1
        else:
            prev_seeds_count = 0
        
        if current_seeds_dir.exists() and current_seeds_dir.is_dir():
            current_seeds_count = sum(1 for seed in os.scandir(current_seeds_dir) if seed.is_file())
            curr_projects += 1
        else:
            current_seeds_count = 0
        tallies.append([project, prev_seeds_count, current_seeds_count])

        if current_seeds_count > prev_seeds_count:
            more_than_prev += 1
        elif current_seeds_count < prev_seeds_count:
            less_than_prev += 1
        else:
            same_as_prev += 1
        if prev_seeds_count == 0 and current_seeds_count > 0:
            zero_to_non_zero += 1

    tallies.sort(key=lambda x: x[0])  
    with open(Path(__file__).resolve().parent / "seeds_count.csv", mode="w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["Project", "Prev Seeds #", "Current Seeds #"])
        writer.writerows(tallies)

    print(f"Previous corpus contains {prev_projects} projects")
    print(f"New corpus contains {curr_projects} projects")
    print(f"There are more seeds for {more_than_prev} projects")
    print(f"There are less seeds for {less_than_prev} projects")
    print(f"{zero_to_non_zero} more projects have seeds.")

"""Eliminate redundant PoCs (seeds) for each project. (?)
"""
def dedup_seeds(project_testcase_dir):
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count seeds differences between projects.")
    parser.add_argument("--prev", type=Path, required=True, 
                        help="Directory for previous seeds.")
    parser.add_argument("--current", type=Path, required=True, 
                        help="Directory for current seeds.")
    args = parser.parse_args()

    seeds_counter(args.prev, args.current)