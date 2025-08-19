use std::path::PathBuf;

#[derive(Debug, PartialEq)]
pub enum RunningMode {
    Normal,
    Profdata,
}

#[derive(Debug, PartialEq)]
pub enum OutputFormat {
    Json,
    Text,
    Hybrid,
}

#[derive(Debug)]
pub struct Config {
    pub running_mode: RunningMode,
    pub running_options: RunningOptions,
    pub analysis_options: AnalysisOptions,
    pub profdata_file: Option<PathBuf>,
}

#[derive(Debug)]
pub struct RunningOptions {
    pub binary: String,
    pub args_list: Vec<Vec<String>>,
}

#[derive(Debug)]
pub struct AnalysisOptions {
    pub extract_all_functions: bool,
    pub output_format: OutputFormat,
}
