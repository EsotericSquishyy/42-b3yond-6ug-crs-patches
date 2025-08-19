#!/bin/bash

# Define the input file
proj_input_file="/tmp/input.txt"
TO_GENERATED_FILE="/mydata/data/code/fuzzing/oss-fuzz/to_generated.txt"
to_count_cov_proj_file="/mydata/data/code/fuzzing/oss-fuzz/to_count_cov_proj.txt"
CSV_HARNESS_FILE="/mydata/data/code/fuzzing/filtered_harness.csv"
BENCHMARK_OSS_SEEDS_DIR="/mydata/data/code/fuzzing/oss-fuzz-gen"
OSSFUZZ_DIR="/mydata/data/code/fuzzing/oss-fuzz"
BUILTIN_COV_CSV="/tmp/oss-fuzz_builtin_cov.csv"
OSSFUZZ_AI_COV_CSV="/tmp/oss-fuzz_aigen_cov.csv"
CORPUS_SAVE_NAME="claude3-opus-aigen_corpus"
PARALLEL_JOBS=12
JAVA_CP_PATH="/mydata/data/code/fuzzing/java-cp-fullscan"

function get_proj_src() {
  project=$1
  src_path=$2
  docker run --rm --privileged --shm-size=2g --platform linux/amd64 -e FUZZING_ENGINE=libfuzzer -e SANITIZER=address -e ARCHITECTURE=x86_64 -e HELPER=True -e FUZZING_LANGUAGE=c++ -v "$OSSFUZZ_DIR/build/out/$1":/out -v "$OSSFUZZ_DIR/build/work/$1":/work -t "gcr.io/oss-fuzz/$1" cp -f $src_path /work/
}

function batch_extract_harnesses() {
  # Clear or create the output CSV file
  echo "" > "/mydata/data/code/fuzzing/filtered_harness.csv"
  
  pushd "$OSSFUZZ_DIR" || exit 1
  
  # Get the list of projects
  while IFS= read -r project; do
    # Skip empty lines and comments
    [[ "$project" =~ ^(//.*|[[:space:]]*)$ ]] && continue
    
    echo "Checking build for project: $project"
    
    # Run check_build and capture output
    output=$(python3 infra/helper.py check_build $project 2>&1)
    
    # Extract harness names using grep and sed
    echo "$output" | grep "performing bad build checks for" | while read -r line; do
      # Extract just the harness name from the line
      harness_name=$(echo "$line" | sed 's/.*\/\([^\/]*\)$/\1/')
      
      # Append to CSV
      echo "$project,$harness_name" >> "/mydata/data/code/fuzzing/filtered_harness.csv"
      echo "Found harness: $project,$harness_name"
    done
  done < "./jvm_projects.txt"
  
  popd || exit 1
  
  echo "Harness extraction complete. Results saved to /mydata/data/code/fuzzing/filtered_harness.csv"
}

function copy_src_from_docker() {
  # Iterate over each line in the file
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=' ' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    source_code_file_with_info="${fields[1]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    # Check if source_code_file is not empty
    if [[ -n "$source_code_file" ]]; then
      # Process the project_name and source_code_file
      echo "Processing project: $project_name, source file: $source_code_file"
      
      get_proj_src "$project_name" "$source_code_file"
    fi
  done < "$proj_input_file"
}

function batch_gen_seeds() {
  for harness in $(cat $TO_GENERATED_FILE); do
    IFS=',' read -r -a fields <<< "$harness"
    # IFS=$'\t' read -r -a fields <<< "$harness"
    project_name="${fields[0]}"
    src_path="${fields[1]}"
    echo "Generating... Project: $project_name,  Source Path: $src_path"
    # get_proj_src "$project_name" "$src_path"
    python test_one_corpus_generate.py $project_name $src_path
  done
}

function run_batch_build() {
  # Array to keep track of background process PIDs
  pids=()
  
  for project in $(cat $TO_GENERATED_FILE  | cut -d',' -f1 | sort -u); do
    echo "Running batch build for project: $project"
    
    # If we've reached the maximum number of parallel jobs, wait for one to finish
    while [ ${#pids[@]} -ge $PARALLEL_JOBS ]; do
      for i in "${!pids[@]}"; do
        if ! kill -0 ${pids[$i]} 2>/dev/null; then
          unset pids[$i]
          pids=("${pids[@]}")  # Re-index array
          break
        fi
      done
      # If we didn't find any completed jobs, sleep for a bit
      if [ ${#pids[@]} -ge $PARALLEL_JOBS ]; then
        sleep 1
      fi
    done
    
    # Run the build in the background with timeout
    (
      pushd "$OSSFUZZ_DIR" && \
        mkdir -p build/work/$project && \
        timeout 30m python infra/helper.py build_fuzzers $project
      
      # Check if timeout occurred
      if [ $? -eq 124 ]; then
        echo "Timeout reached for project $project after 30 minutes"
        # Kill any remaining docker containers that might be associated with this build
        docker ps -q | grep $project | xargs -r docker kill
      fi
      
      popd
    ) &
    
    # Store the PID of the background process
    pids+=($!)
    echo "Started build for $project (PID: ${pids[-1]}, active jobs: ${#pids[@]}/$PARALLEL_JOBS)"
  done
  
  # Wait for all remaining background jobs to finish
  echo "Waiting for all builds to complete..."
  for pid in "${pids[@]}"; do
    wait $pid
  done
  echo "All builds completed"
}

function batch_run_fuzzers() {
  # Array to keep track of background process PIDs
  pids=()
  
  # Create a log directory
  mkdir -p "$OSSFUZZ_DIR/logs"
  
  # Read the CSV file
  while IFS=, read -r project_name harness_name _rest; do
    # Skip empty lines
    [ -z "$project_name" ] && continue
    
    echo "Preparing to run fuzzer: $project_name/$harness_name"
    
    # If we've reached the maximum number of parallel jobs, wait for one to finish
    while [ ${#pids[@]} -ge $PARALLEL_JOBS ]; do
      for i in "${!pids[@]}"; do
        if ! kill -0 ${pids[$i]} 2>/dev/null; then
          unset pids[$i]
          pids=("${pids[@]}")  # Re-index array
          break
        fi
      done
      # If we didn't find any completed jobs, sleep for a bit
      if [ ${#pids[@]} -ge $PARALLEL_JOBS ]; then
        sleep 2
      fi
    done
    
    # Run the fuzzer in the background with timeout
    (
      log_file="$OSSFUZZ_DIR/logs/${project_name}_${harness_name}.log"
      corpus_dir="$OSSFUZZ_DIR/build/corpus/$project_name/$harness_name"
      echo "Starting fuzzer: $project_name/$harness_name (log: $log_file)"
      
      pushd "$OSSFUZZ_DIR" || exit 1
      

      mkdir -p "$corpus_dir"
      
      # Run fuzzer with timeout
      export OSS_FUZZ_SAVE_CONTAINERS_NAME="${project_name}_${harness_name}"
      timeout 1h python infra/helper.py run_fuzzer -e 'FUZZER_ARGS=--keep_going=0' --corpus-dir "$corpus_dir" "$project_name" "$harness_name" "-max_total_time=3500 -use_value_profile=1 -artifact_prefix=/out/artifacts/ -create_missing_dirs=1" > "$log_file" 2>&1
      
      # Check if timeout occurred
      if [ $? -eq 124 ]; then
        echo "Timeout reached for $project_name/$harness_name after 1 hour"
        # Kill any remaining docker containers associated with this project
        docker ps | grep "$harness_name" | awk '{print $1}' | xargs -r docker stop
      fi
      
      popd || exit 1
    ) &
    
    # Store the PID of the background process
    pids+=($!)
    echo "Started fuzzer for $project_name/$harness_name (PID: ${pids[-1]}, active jobs: ${#pids[@]}/$PARALLEL_JOBS)"
    
    # Small delay to prevent overwhelming the system
    sleep 1
    
  done < "$CSV_HARNESS_FILE"
  
  # Wait for all remaining background jobs to finish
  echo "Waiting for all fuzzer runs to complete..."
  for pid in "${pids[@]}"; do
    wait $pid
  done
  echo "All fuzzer runs completed"
}

function run_batch_seedgen_scripts() {
  for project in $(cat $TO_GENERATED_FILE  | cut -d',' -f1 | sort -u); do
    echo "Running batch seedgen for project: $project"
    pushd "$OSSFUZZ_DIR" && \
      mkdir -p build/work/$project && \
      python infra/helper.py build_image --no-pull $project && \
      # python infra/helper.py build_fuzzers --sanitizer=coverage $project && \
      echo "cp -f $BENCHMARK_OSS_SEEDS_DIR/save_ai_corpus.sh ./build/work/$project/" && \
      cp -f $BENCHMARK_OSS_SEEDS_DIR/save_ai_corpus.sh ./build/work/$project/ && \
      mkdir -p ./build/work/$project/corpus && \
      cp -f $BENCHMARK_OSS_SEEDS_DIR/benchmark-seedgen/$project/*.py ./build/work/$project/ && \
      docker run --rm --privileged --shm-size=2g --platform linux/amd64 -e FUZZING_ENGINE=libfuzzer -e SANITIZER=address -e ARCHITECTURE=x86_64 -e HELPER=True -e FUZZING_LANGUAGE=c++ -v "$OSSFUZZ_DIR/build/out/$project":/out -v "$OSSFUZZ_DIR/build/work/$project":/work -t "gcr.io/oss-fuzz/$project" "/work/save_ai_corpus.sh" && \
      popd
  done
}

function run_cmin_scripts() {
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"
    echo "Running cmin for project: $project_name, Binary: $binary_name"
    cp -f $BENCHMARK_OSS_SEEDS_DIR/cmin.sh $OSSFUZZ_DIR/build/out/$project_name/
    pushd "$OSSFUZZ_DIR" && \
      mkdir -p build/work/$project && \
      docker run --rm --privileged --shm-size=4g --platform linux/amd64 -e FUZZING_ENGINE=libfuzzer -e HELPER=True -e PROJECT="$project_name" -e SANITIZER=coverage -e 'COVERAGE_EXTRA_ARGS= ' -e ARCHITECTURE=x86_64 -v $OSSFUZZ_DIR/build/corpus/$project_name/aigen_corpus:/corpus -v $OSSFUZZ_DIR/build/out/$project_name:/out -t gcr.io/oss-fuzz-base/base-runner /out/cmin.sh $binary_name
    popd
  done < "$CSV_HARNESS_FILE"
}

function copy_generated_corpus() {
  # Find all aigen_corpus directories under build/work/
  pushd $OSSFUZZ_DIR
  find build/work/ -iname aigen_corpus | while read -r corpus_path; do
      # Extract the project name from the path
      project=$(basename "$(dirname "$corpus_path")")

      # Create the target directory for the project
      mkdir -p "build/corpus/$project"

      # Copy the aigen_corpus directory to the target directory
      cp -r "$corpus_path" "build/corpus/$project/"
  done
  popd
}

function count_builtin_cov() {
  pushd $OSSFUZZ_DIR
  find build/cov_report/builtin -name summary.json | grep report_target | while read -r summary_path; do
      binary_name=$(basename "$(dirname "$(dirname "$summary_path")")")
      project=$(basename "$(dirname "$(dirname "$(dirname "$(dirname "$summary_path")")")")")
      cov=$(jq .data[].totals.lines.percent < "$summary_path")
      printf "$project\t$binary_name\t$cov\n" | tee -a $BUILTIN_COV_CSV
  done

  popd
}

function count_aigen_cov() {
  pushd $OSSFUZZ_DIR

  echo > /tmp/filtered_harness.csv

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

    if [ -d "$OSSFUZZ_DIR/build/cov_report/aigen/$project_name/report_target/$binary_name/linux/" ] ; then
      # echo "Geting code coverage: $project_name, $binary_name"
      summary_path="$OSSFUZZ_DIR/build/cov_report/aigen/$project_name/report_target/$binary_name/linux/summary.json"
      cov=$(jq .data[].totals.lines.percent < "$summary_path")
    else
      # echo "No coverage report found for $project_name, $binary_name"
      cov="NA"
    fi

    echo "$project_name,$binary_name,$cov" | tee -a /tmp/filtered_harness.csv

  done < "$CSV_HARNESS_FILE"

  popd
}

function generate_cov() {
  # python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir=$corpus_dir $project --no-serve
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"

    if [ -d "$OSSFUZZ_DIR/build/corpus/$project_name/$CORPUS_SAVE_NAME" ] ; then
      echo "Generating code coverage: $project_name"
      # grep $project_name /tmp/last_project.txt || python infra/helper.py build_fuzzers --sanitizer=coverage $project_name
      echo $project_name > /tmp/last_project.txt
      timeout 20m python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir="$OSSFUZZ_DIR/build/corpus/$project_name/$CORPUS_SAVE_NAME" --no-serve $project_name 
      if [ $? -eq 124 ]; then
        echo "Timeout reached. Running another command..."
        docker stop $(docker ps -q)
      fi
      mkdir -p $OSSFUZZ_DIR/build/cov_report/aigen/$project_name
      cp -rf $OSSFUZZ_DIR/build/out/$project_name/report_target $OSSFUZZ_DIR/build/cov_report/aigen/$project_name/
    fi

  done < "$CSV_HARNESS_FILE"
}

function generate_cov_builtin_seeds() {
  # python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir=$corpus_dir $project --no-serve
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"

    # if build/cov_report/builtin/$project exists, skip
    if [ -d "$OSSFUZZ_DIR/build/corpus/$project_name/builtin_corpus" ] ; then
      echo "Generating code coverage: $project_name"
      if ! [ -d "$OSSFUZZ_DIR/build/out/$project_name/src" ] ; then
        python infra/helper.py build_fuzzers --sanitizer=coverage $project_name
      fi  
      timeout 30m python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir="$OSSFUZZ_DIR/build/corpus/$project_name/builtin_corpus" --no-serve $project_name 
      if [ $? -eq 124 ]; then
        echo "Timeout reached. Running another command..."
        docker stop $(docker ps -q)
      fi
      mkdir -p $OSSFUZZ_DIR/build/cov_report/builtin/$project_name
      cp -rf $OSSFUZZ_DIR/build/out/$project_name/report_target $OSSFUZZ_DIR/build/cov_report/builtin/$project_name/
    fi

  done < "$CSV_HARNESS_FILE"
}

function filter_builtin_cov() {
  pushd $OSSFUZZ_DIR
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"
    language=$(cat $OSSFUZZ_DIR/projects/$project_name/project.yaml | yq ".language")

    cov_per_text=$(grep $binary_name $BUILTIN_COV_CSV | grep $project_name)
    if [ $? -ne 0 ]; then
      cov_per="NA"
    else
      cov_per=$(echo $cov_per_text | head -n1 | awk '{print $3}')
    fi

    # echo $cov_per
    printf "$project_name,$language,$binary_name,${source_code_file_with_info}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tee -a /tmp/filtered_harness.csv
    echo ",$cov_per" | tee -a /tmp/filtered_harness.csv

  done < "$CSV_HARNESS_FILE"

  popd
}

function filter_ossfuzz_aigen_cov() {
  # TODO: Implement this function
  pushd $OSSFUZZ_DIR
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    cov_per_text=$(grep $binary_name $OSSFUZZ_AI_COV_CSV | grep $project_name)
    if [ $? -ne 0 ]; then
      cov_per="NA"
    else
      cov_per=$(echo $cov_per_text | head -n1 | awk '{print $3}')
    fi

    # echo $cov_per
    printf "$project_name,$binary_name,${source_code_file_with_info}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tee -a /tmp/filtered_harness.csv
    echo ,$cov_per | tee -a /tmp/filtered_harness.csv

  done < "$CSV_HARNESS_FILE"

  popd
}

function batch_reproduce() {
  # Create output directory and CSV file
  CRASH_SAVE_DIR="$OSSFUZZ_DIR/crash_saved"
  CRASH_CSV="$OSSFUZZ_DIR/security_crashes.csv"
  mkdir -p "$CRASH_SAVE_DIR"
  echo "project_name,harness_name,crash_filename" > "$CRASH_CSV"
  
  # Read the harness CSV to get project and harness mappings
  while IFS=, read -r project_name harness_name _rest; do
    # Skip empty lines
    [ -z "$project_name" ] && continue
    
    echo "Checking project: $project_name, harness: $harness_name"
    
    # Find all crash files for this project
    crash_dir="$OSSFUZZ_DIR/build/out/$project_name"
    if [ -d "$crash_dir" ]; then
      # Look for crash files in the project's output directory
      for crash_file in $(find "$crash_dir" -name "crash-*" 2>/dev/null); do
        if [ -f "$crash_file" ]; then
          crash_filename=$(basename "$crash_file")
          
          echo "Testing crash file: $crash_filename for harness: $harness_name"
          
          # Run the reproduce command and capture output
          pushd "$OSSFUZZ_DIR" > /dev/null
          reproduce_output=$(python3 infra/helper.py reproduce "$project_name" "$harness_name" "$crash_file" 2>&1)
          reproduce_exit_code=$?
          popd > /dev/null
          
          # Check if the security issue string is in the output
          if echo "$reproduce_output" | grep -q "com.code_intelligence.jazzer.api.FuzzerSecurityIssue"; then
            echo "Security issue found in $project_name/$harness_name with crash file $crash_filename"
            
            # Save the crash file
            mkdir -p "$CRASH_SAVE_DIR/$project_name"
            cp "$crash_file" "$CRASH_SAVE_DIR/$project_name/$crash_filename"
            
            # Log to CSV
            echo "$project_name,$harness_name,$crash_filename" >> "$CRASH_CSV"
          else
            echo "No security issue found or reproduction failed (exit code: $reproduce_exit_code)"
          fi
        fi
      done
    else
      echo "No output directory found for $project_name"
    fi
  done < "$CSV_HARNESS_FILE"
  
  echo "Reproduction test complete. Security issues logged to $CRASH_CSV"
}

function batch_triage() {
  # Check if an input CSV file is provided as an argument
  if [ $# -ne 1 ]; then
    echo "Usage: $0 input.csv"
    exit 1
  fi

  INPUT_FILE="$1"
  pushd "$OSSFUZZ_DIR" || exit 1

  # Process each line in the CSV file
  while IFS=, read -r project_name harnessname crash_file; do
    # Skip empty lines
    if [ -z "$project_name" ]; then
      continue
    fi

    # Define the meta folder path
    META_DIR="$JAVA_CP_PATH/${project_name}/meta"

    # Create the meta folder (including parent directories) if it doesn't exist
    mkdir -p "$META_DIR"

    # Run the reproduce command and save the output report to the meta folder
    python infra/helper.py reproduce "$project_name" "$harnessname" ./crash_saved/$project_name/$crash_file 2>&1 | \
     tee "$META_DIR/${harnessname}_report.txt"

    # Copy the crash file to the meta folder with the new name: harnessname_crash_file
    cp "./crash_saved/$project_name/$crash_file" "$META_DIR/${harnessname}_${crash_file}"

  done < "$INPUT_FILE"
  popd
}

# copy_src_from_docker
# batch_gen_seeds

# run_batch_seedgen_scripts

# generate_cov

# filter_builtin_cov

# filter_ossfuzz_aigen_cov

# generate_cov_builtin_seeds
# count_aigen_cov

# run_batch_build
# batch_extract_harnesses
# batch_run_fuzzers
batch_reproduce