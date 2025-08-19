use super::model::get_uncovered;
use super::model::PartiallyCoveredFunction;
use super::report::print_uncovered;
use crate::error::GetCovError;
use crate::Analyzer;
use llvm_cov_json::CoverageReport;
use serde::{Deserialize, Serialize};
#[derive(Debug, Serialize, Deserialize)]
pub struct Coverage {
    covered_branches: u64,
    total_branches: u64,
    covered_functions: u64,
    total_functions: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Output {
    coverage: Coverage,
    uncovered_functions: Vec<PartiallyCoveredFunction>,
}

pub struct UncoveredAnalyzer {
    results: Option<Output>,
}

impl UncoveredAnalyzer {
    pub fn new() -> Self {
        Self { results: None }
    }
}

impl Analyzer for UncoveredAnalyzer {
    fn analyze(&mut self, coverage_report: &CoverageReport) -> Result<(), GetCovError> {
        let program_report = &coverage_report.data[0];
        let uncovered_functions = get_uncovered(coverage_report);

        self.results = Some(Output {
            coverage: Coverage {
                covered_branches: program_report.summary.branches.covered,
                total_branches: program_report.summary.branches.count,
                covered_functions: program_report.summary.functions.covered,
                total_functions: program_report.summary.functions.count,
            },
            uncovered_functions,
        });
        Ok(())
    }

    fn output_json(&self) -> Result<(), GetCovError> {
        serde_json::to_writer_pretty(std::io::stdout(), self.results.as_ref().unwrap())?;
        Ok(())
    }

    fn output_text(&self) {
        print_uncovered(&self.results.as_ref().unwrap().uncovered_functions);
    }
}
