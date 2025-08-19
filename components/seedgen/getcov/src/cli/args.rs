use clap::ArgMatches;

use crate::config::{AnalysisOptions, Config, OutputFormat, RunningMode, RunningOptions};
use crate::error::GetCovError;
use clap::{Arg, Command};
use std::fs;
use std::path::{Path, PathBuf};

fn create_cli() -> Command {
    Command::new("getcov")
        .version("1.0")
        .author("Wenxuan Shi")
        .about("Coverage analysis tool")
        .arg(
            Arg::new("input")
                .short('i')
                .long("input")
                .value_name("DIRECTORY")
                .help("Sets the seed directory")
                .required(false),
        )
        .arg(
            Arg::new("all")
                .long("all")
                .help("Extract all functions")
                .action(clap::ArgAction::SetTrue)
                .required(false),
        )
        .arg(
            Arg::new("text")
                .long("text")
                .help("Output in text format")
                .action(clap::ArgAction::SetTrue)
                .required(false),
        )
        .arg(
            Arg::new("hybrid")
                .long("hybrid")
                .help("Output in hybrid format")
                .action(clap::ArgAction::SetTrue)
                .required(false),
        )
        .arg(
            Arg::new("profdata")
                .long("profdata")
                .help("Use the provided profdata file")
                .value_name("FILE")
                .required(false)
                .action(clap::ArgAction::Set),
        )
        .arg(
            Arg::new("executable")
                .help("The command to run")
                .required(true)
                .num_args(1..)
                .last(true),
        )
}

/// Parses the command-line arguments and constructs a `Config` instance.
///
/// # Returns
///
/// A `Result` containing `Config` or a `GetCovError`.
pub fn parse_arguments() -> Result<Config, GetCovError> {
    let matches = create_cli().get_matches();
    let (binary, args) = parse_executable(&matches)?;

    let binary = if Path::new(&binary).exists() {
        fs::canonicalize(&binary)
            .map_err(GetCovError::Io)?
            .to_str()
            .ok_or_else(|| GetCovError::ArgParse("Path contains invalid Unicode".into()))?
            .to_string()
    } else {
        return Err(GetCovError::ArgParse(format!(
            "Binary '{}' not found",
            binary
        )));
    };

    let profdata_file = matches.get_one::<String>("profdata").map(PathBuf::from);

    let running_mode = if profdata_file.is_some() {
        RunningMode::Profdata
    } else {
        RunningMode::Normal
    };

    let running_options = if let Some(input_dir) = matches.get_one::<String>("input") {
        create_options_from_input_dir(input_dir, &binary, &args)?
    } else {
        RunningOptions {
            binary,
            args_list: vec![args],
        }
    };

    let analysis_options = AnalysisOptions {
        extract_all_functions: matches.get_flag("all"),
        output_format: if matches.get_flag("text") {
            OutputFormat::Text
        } else if matches.get_flag("hybrid") {
            OutputFormat::Hybrid
        } else {
            OutputFormat::Json
        },
    };

    Ok(Config {
        running_mode,
        running_options,
        analysis_options,
        profdata_file,
    })
}

/// Creates `RunningOptions` by reading input files from a directory.
///
/// # Arguments
///
/// * `input_dir` - The directory containing input files.
/// * `binary` - The binary to execute.
/// * `args` - The list of arguments for the binary.
///
/// # Returns
///
/// A `Result` containing `RunningOptions` or a `GetCovError`.
fn create_options_from_input_dir(
    input_dir: &str,
    binary: &str,
    args: &[String],
) -> Result<RunningOptions, GetCovError> {
    let input_dir = PathBuf::from(input_dir);
    if !input_dir.is_dir() {
        return Err(GetCovError::ArgParse("Input directory not found".into()));
    }

    let mut args_list = Vec::new();
    let files = fs::read_dir(&input_dir)?;

    for entry in files {
        let file = entry?;
        if file.file_type()?.is_file() {
            let new_args = create_args_with_file(args, &file);
            args_list.push(new_args);
        }
    }

    if args_list.is_empty() {
        Err(GetCovError::ArgParse(
            "No input files found in the directory".into(),
        ))
    } else {
        Ok(RunningOptions {
            binary: binary.to_string(),
            args_list,
        })
    }
}

/// Creates a new set of arguments by replacing placeholders with file paths.
///
/// # Arguments
///
/// * `args` - The original list of arguments.
/// * `file` - The directory entry of the input file.
///
/// # Returns
///
/// A new `Vec<String>` containing the arguments with placeholders replaced.
fn create_args_with_file(args: &[String], file: &fs::DirEntry) -> Vec<String> {
    let file_path = file.path().to_string_lossy().into_owned();
    let has_placeholder = args.iter().any(|arg| arg == "@@");

    if has_placeholder {
        args.iter()
            .map(|arg| {
                if arg == "@@" {
                    file_path.clone()
                } else {
                    arg.clone()
                }
            })
            .collect()
    } else {
        let mut new_args = args.to_vec();
        new_args.push(file_path);
        new_args
    }
}
/// Parses the executable and its arguments from the CLI matches.
///
/// # Arguments
///
/// * `matches` - The `ArgMatches` from Clap.
///
/// # Returns
///
/// A `Result` containing a tuple of binary and arguments, or a `GetCovError`.
fn parse_executable(matches: &ArgMatches) -> Result<(String, Vec<String>), GetCovError> {
    let executable: Vec<String> = matches
        .get_many::<String>("executable")
        .map(|vals| vals.map(String::from).collect())
        .unwrap_or_default();

    match executable.split_first() {
        Some((bin, args)) => Ok((bin.clone(), args.to_vec())),
        None => Err(GetCovError::ArgParse("No executable provided".into())),
    }
}
