#!/bin/bash

CSV_HARNESS_FILE="/workspaces/sunflower/projects.csv"
OSSFUZZ_DIR="/workspaces/sunflower/oss-fuzz"
COV_CSV_FILE="/tmp/oss-fuzz_seedgen_cov.csv"
SEED_RESULT_DIR="/workspaces/sunflower/.tmp"

function pre_build_project() {
    pushd $OSSFUZZ_DIR
    for project in $(cat $CSV_HARNESS_FILE | cut -d, -f1 | sort -u); do
        python infra/helper.py build_image --no-pull $project
        python infra/helper.py build_fuzzers --sanitizer=coverage $project
    done
    popd
}

function count_seedgen_cov() {
  pushd $OSSFUZZ_DIR

  echo > "$COV_CSV_FILE"

  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    # echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"
    summary_path="$OSSFUZZ_DIR/build/cov_report/seedgen/$project_name/report_target/$binary_name/linux/summary.json"

    if [ -d "$SEED_RESULT_DIR/$project_name" ] && [ -f "$summary_path" ] ; then
      # echo "Geting code coverage: $project_name, $binary_name"
      cov=$(jq .data[].totals.lines.percent < "$summary_path")
    else
      # echo "No coverage report found for $project_name, $binary_name"
      cov="NA"
    fi

    echo "$project_name,$binary_name,$cov" | tee -a $COV_CSV_FILE

  done < "$CSV_HARNESS_FILE"

  popd
}

function generate_cov() {
  pushd $OSSFUZZ_DIR
  # python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir=$corpus_dir $project --no-serve
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    # source_code_file_with_info="${fields[2]}"

    # # Remove the line number and column number from source_code_file
    # source_code_file="${source_code_file_with_info%:*:*}"

    echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"

    # Run seed generation
    pushd ..
    python3 oss-fuzz.py $project_name $binary_name
    # result_dir=0
    # for subdir in "$SEED_RESULT_DIR/$project_name"/*; do
    #   name=$(basename "$subdir")
    #   if [[ "$name" =~ ^[0-9]+$ ]]; then
    #     # If it's bigger than our current largest, update it
    #     if (( name > result_dir )); then
    #       result_dir=$name
    #     fi
    #   fi
    # done
    popd

    # if [ -d "$SEED_RESULT_DIR/$project_name/$result_dir/seeds" ] ; then
    #   echo "Generating code coverage: $project_name"
    #   #   python infra/helper.py build_fuzzers --sanitizer=coverage $project_name
    #   echo "python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir="$SEED_RESULT_DIR/$project_name/$result_dir/seeds" --no-serve $project_name "
    #   timeout 30m python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir="$SEED_RESULT_DIR/$project_name/$result_dir/seeds" --no-serve $project_name 
    #   if [ $? -eq 124 ]; then
    #     echo "Timeout reached. Running another command..."
    #     docker stop $(docker ps -q)
    #   fi
    #   mkdir -p $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name
    #   cp -rf $OSSFUZZ_DIR/build/out/$project_name/report_target $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name/
    # fi

  done < "$CSV_HARNESS_FILE"
  popd
}

# 1. build targets
#pre_build_project
# 2. collect coverage
generate_cov
# 3. save the output to a csv
#count_seedgen_cov