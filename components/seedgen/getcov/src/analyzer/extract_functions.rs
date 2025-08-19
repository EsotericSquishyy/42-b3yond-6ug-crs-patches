use super::Analyzer;
use crate::error::GetCovError;
use llvm_cov_json::CoverageReport;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct FunctionInfo {
    pub name: String,
    pub file_path: String,
    pub start_line: u64,
    pub start_column: u64,
    pub end_line: u64,
    pub end_column: u64,
}

pub struct ExtractFunctionsAnalyzer {
    results: Option<Vec<FunctionInfo>>
}

impl ExtractFunctionsAnalyzer {
    pub fn new() -> Self {
        Self { results: None }
    }
}

impl Analyzer for ExtractFunctionsAnalyzer {
    fn analyze(&mut self, coverage_report: &CoverageReport) -> Result<(), GetCovError> {
        self.results = Some(coverage_report.data[0]
            .functions
            .iter()
            .map(|f| FunctionInfo {
                name: f.name.to_string(),
                file_path: f.filenames[f.regions[0].file_id as usize].to_string(),
                start_line: f.regions[0].line_start,
                start_column: f.regions[0].column_start,
                end_line: f.regions[0].line_end,
                end_column: f.regions[0].column_end,
            })
            .collect());
        Ok(())
    }

    fn output_json(&self) -> Result<(), GetCovError> {
        serde_json::to_writer_pretty(std::io::stdout(), self.results.as_ref().unwrap())?;
        Ok(())
    }

    fn output_text(&self) {
        let data = self.results.as_ref().unwrap();
        println!("Functions found in the program:");
        println!("==============================\n");

        for (i, function) in data.iter().enumerate() {
            println!(
                "{}. {} ({}:{}:{})",
                i + 1,
                function.name,
                function.file_path,
                function.start_line,
                function.start_column
            );
        }
    }
}
