use crate::config::RunningOptions;
use crate::error::GetCovError;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;
use tempfile::TempDir;
use uuid::Uuid;
use wait_timeout::ChildExt;

#[derive(Debug)]
pub struct CoverageResult {
    pub json: String,
    pub profdata_path: PathBuf,
}

/// Generates a coverage report in JSON format by running the binary with coverage instrumentation
/// and processing the results.
///
/// # Arguments
/// * `options` - Configuration options for running the binary
///
/// # Returns
/// * `Result<String, GetCovError>` - JSON coverage report or error
pub fn get_coverage_report_json(options: &RunningOptions) -> Result<CoverageResult, GetCovError> {
    let profdata_path = run_with_coverage(options)?;
    let result = generate_coverage_report_json(options, &profdata_path)?;
    Ok(CoverageResult {
        json: result,
        profdata_path,
    })
}

/// Generates a coverage report in JSON format from an existing profdata file.
///
/// # Arguments
/// * `options` - Configuration options for running the binary
/// * `profdata_file` - Path to the existing profdata file
pub fn get_coverage_report_json_by_profdata(
    options: &RunningOptions,
    profdata_file: &Path,
) -> Result<CoverageResult, GetCovError> {
    let result = generate_coverage_report_json(options, profdata_file)?;
    Ok(CoverageResult {
        json: result,
        profdata_path: profdata_file.to_path_buf(),
    })
}

fn run_with_coverage(options: &RunningOptions) -> Result<PathBuf, GetCovError> {
    let temp_dir = TempDir::new().map_err(GetCovError::Io)?;
    let coverage_id = Uuid::new_v4();
    let profraw_prefix = format!("getcov_{}_", coverage_id);

    // Create profraw file path inside temp directory
    let profraw_pattern = temp_dir
        .path()
        .join(format!("{}%m.profraw", profraw_prefix));

    // Run the binary for each set of arguments
    for args in &options.args_list {
        let mut command = Command::new(&options.binary)
            .args(args)
            .env(
                "LLVM_PROFILE_FILE",
                profraw_pattern.to_str().ok_or_else(|| {
                    GetCovError::Coverage("Invalid profraw file path".to_string())
                })?,
            )
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;

        match command.wait_timeout(Duration::from_secs(5 * 60))? {
            Some(status) => status,
            None => {
                let _ = command.kill(); // ignore the error anyway
                continue;
            }
        };
    }

    // Collect profraw files
    let profraw_files: Vec<_> = collect_profraw_files(temp_dir.path(), &profraw_prefix)?;

    // Verify we have exactly one profraw file
    if profraw_files.len() != 1 {
        return Err(GetCovError::Coverage(format!(
            "Expected 1 profraw file, found {}",
            profraw_files.len()
        )));
    }

    let profdata_path = PathBuf::from("/tmp").join(format!("getcov_{}.profdata", coverage_id));
    merge_profraw_to_profdata(&profraw_files[0], &profdata_path)?;

    Ok(profdata_path)
}

fn collect_profraw_files(dir: &Path, prefix: &str) -> Result<Vec<PathBuf>, GetCovError> {
    Ok(std::fs::read_dir(dir)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .and_then(|os_str| os_str.to_str())
                .map_or(false, |name| name.starts_with(prefix))
        })
        .collect())
}

fn merge_profraw_to_profdata(profraw_file: &Path, profdata_path: &Path) -> Result<(), GetCovError> {
    let status = Command::new("llvm-profdata")
        .arg("merge")
        .arg("-sparse")
        .arg(profraw_file)
        .arg("-o")
        .arg(profdata_path)
        .spawn()?
        .wait()?;

    if !status.success() {
        return Err(GetCovError::Coverage(
            "Failed to merge profraw data".to_string(),
        ));
    }

    Ok(())
}

fn generate_coverage_report_json(
    options: &RunningOptions,
    profdata_file: &Path,
) -> Result<String, GetCovError> {
    let output = Command::new("llvm-cov")
        .arg("export")
        .arg(format!("--instr-profile={}", profdata_file.display()))
        .arg(&options.binary)
        .output()?;

    if !output.status.success() {
        return Err(GetCovError::Coverage(
            String::from_utf8_lossy(&output.stderr).to_string(),
        ));
    }

    String::from_utf8(output.stdout).map_err(GetCovError::from)
}
