mod covmap;
mod execution;

pub use covmap::check_covmap;
pub use execution::{get_coverage_report_json, get_coverage_report_json_by_profdata};
