mod extract_functions;
mod uncovered;

pub use extract_functions::ExtractFunctionsAnalyzer;
pub use uncovered::UncoveredAnalyzer;

use crate::error::GetCovError;
use llvm_cov_json::CoverageReport;

pub trait Analyzer {
    fn analyze(&mut self, coverage_report: &CoverageReport) -> Result<(), GetCovError>;
    fn output_json(&self) -> Result<(), GetCovError>;
    fn output_text(&self);
}
