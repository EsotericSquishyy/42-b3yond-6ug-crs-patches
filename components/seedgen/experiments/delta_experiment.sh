#!/usr/bin/env bash

# CSV file with lines: project_name,binary_name
CSV_FILE="projects.csv"

# Directory to store logs, coverage, and crash artifacts
RESULTS_DIR="results"

# Duration for each fuzzing experiment (seconds)
# e.g., 6 hours = 21600
FUZZ_TIME=14400

# The 4 experiments we want to run in sequence
EXPERIMENTS=(
  "handpicked"
  "handpicked_and_pregenerated"
  "pregenerated"
  "random"
)

# Ensure the results directory exists
mkdir -p "$RESULTS_DIR"

# Iterate over experiments, one at a time
for EXP in "${EXPERIMENTS[@]}"; do
  echo "============================================"
  echo "Starting experiment: $EXP"
  echo "============================================"

  # Read each project/binary from CSV
  # (If you have a header line, either remove it or skip it in the script.)
  while IFS=, read -r PROJECT BINARY; do
    # Decide which corpus directories to use
    case "$EXP" in
      "handpicked")
        # Only the hand-picked corpus
        CORPUS_DIRS="userspace-fuzzing-corpus/projects/$PROJECT"
        ;;
      "handpicked_and_pregenerated")
        # Hand-picked + pre-generated
        CORPUS_DIRS="userspace-fuzzing-corpus/projects/$PROJECT .tmp/$PROJECT/0/seeds"
        ;;
      "pregenerated")
        # Only pre-generated
        CORPUS_DIRS=".tmp/$PROJECT/0/seeds"
        ;;
      "random")
        # Create an empty corpus directory for random seeds
        RANDOM_DIR=".tmp/$PROJECT/0/random_seeds"
        mkdir -p "$RANDOM_DIR"
        CORPUS_DIRS="$RANDOM_DIR"
        ;;
    esac

    # Filenames/paths for log, coverage, and crash artifacts
    LOG_FILE="$RESULTS_DIR/${PROJECT}_${EXP}.log"
    PROFRAW_FILE="$RESULTS_DIR/${PROJECT}_${EXP}.profraw"

    # Directory for crash artifacts
    # LibFuzzer will place any crash/timeout artifacts into this directory
    ARTIFACT_DIR="$RESULTS_DIR/${PROJECT}_${EXP}_artifacts"
    mkdir -p "$ARTIFACT_DIR"

    mkdir -p .tmp/dummy/"$PROJECT"

    # Start the fuzzer in the background (parallel per experiment)
    # 1) LLVM_PROFILE_FILE: coverage instrumentation output
    # 2) -artifact_prefix: store crash artifacts in ARTIFACT_DIR
    # 3) -print_final_stats=1: built-in LibFuzzer coverage stats at the end
    LLVM_PROFILE_FILE="$PROFRAW_FILE" \
    .tmp/"$PROJECT"/0/out/"$BINARY" \
      -seed=26710 \
      -max_total_time="$FUZZ_TIME" \
      -timeout=25 \
      -print_final_stats=1 \
      -artifact_prefix="$ARTIFACT_DIR/" \
      .tmp/dummy/"$PROJECT" $CORPUS_DIRS \
      2>&1 | tee /dev/tty | tail -n 100000 > "$LOG_FILE" &

  done < "$CSV_FILE"

  # Wait for all fuzzers (projects) in this experiment to finish
  wait

  rm -rf .tmp/dummy

  echo "============================================"
  echo "Finished experiment: $EXP"
  echo "============================================"
done

echo "All experiments completed!"