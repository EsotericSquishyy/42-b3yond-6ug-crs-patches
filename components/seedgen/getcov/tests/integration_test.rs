use std::process::Command;
use serial_test::serial;

fn run_make() {
    let status = Command::new("make")
        .current_dir("tests/c_code")
        .status()
        .expect("Failed to compile C program");
    assert!(status.success());
}

fn run_make_clean() {
    let status = Command::new("make")
        .arg("clean")
        .current_dir("tests/c_code")
        .status()
        .expect("Failed to run make clean");
    assert!(status.success());
}

#[test]
#[serial]
fn test_llvm_cov_integration() {
    run_make();

    // Run 'getcov' to execute the binary and process coverage
    let output = Command::new("cargo")
        .args(&["run", "--", "--", "tests/c_code/main"])
        .output()
        .expect("Failed to run 'getcov'");
    assert!(output.status.success());

    // Check the output
    let stdout = String::from_utf8(output.stdout).expect("Failed to convert stdout to string");
    println!("{}", stdout);

    run_make_clean();
}

#[test]
#[serial]
fn test_text_output_format() {
    run_make();

    let output = Command::new("cargo")
        .args(&["run", "--", "--text", "--", "tests/c_code/main"])
        .output()
        .expect("Failed to run 'getcov'");
    assert!(output.status.success());

    let stdout = String::from_utf8(output.stdout).expect("Failed to convert stdout to string");
    // Text format should not contain JSON markers
    assert!(stdout.contains("Partially Covered Functions Report"));

    run_make_clean();
}

#[test]
#[serial]
fn test_all_functions_flag() {
    run_make();

    let output = Command::new("cargo")
        .args(&["run", "--", "--all", "--", "tests/c_code/main"])
        .output()
        .expect("Failed to run 'getcov'");
    assert!(output.status.success());

    let stdout = String::from_utf8(output.stdout).expect("Failed to convert stdout to string");
    // When using --all, output should contain more function coverage data
    assert!(stdout.contains("function"));

    run_make_clean();
}

#[test]
#[serial]
fn test_input_directory() {
    run_make();

    // First create a test directory with input files
    std::fs::create_dir_all("tests/inputs").expect("Failed to create test directory");
    std::fs::write("tests/inputs/test1.txt", "test input 1").expect("Failed to write test file");
    std::fs::write("tests/inputs/test2.txt", "test input 2").expect("Failed to write test file");

    let output = Command::new("cargo")
        .args(&[
            "run",
            "--",
            "--input",
            "tests/inputs",
            "--",
            "tests/c_code/main",
            "@@",
        ])
        .output()
        .expect("Failed to run 'getcov'");
    assert!(output.status.success());

    // Clean up
    std::fs::remove_dir_all("tests/inputs").expect("Failed to clean up test directory");

    run_make_clean();
}

#[test]
#[serial]
fn test_invalid_binary() {
    run_make();

    let output = Command::new("cargo")
        .args(&["run", "--", "--", "nonexistent_binary"])
        .output()
        .expect("Failed to run 'getcov'");

    assert!(!output.status.success());
    let stderr = String::from_utf8(output.stderr).expect("Failed to convert stderr to string");
    assert!(stderr.contains("Binary 'nonexistent_binary' not found"));

    run_make_clean();
}
