use regex::Regex;
use std::collections::HashMap;

/// Analysis the uncovered parts in the program.
/// In detail, it will find out:
/// 1. Partially covered predicates in each function. It means the predicate always outputs the same value in current coverage.
/// 2. Uncovered regions in each function.
use llvm_cov_json::{Branch, CoverageReport, FunctionMetrics, RegionKind};

use crate::analyzer::uncovered::report::get_file_part;

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct PartiallyCoveredPredicate {
    pub file_path: String,
    pub start_line: u64,
    pub start_column: u64,
    pub end_line: u64,
    pub end_column: u64,
    pub true_count: u64,
    pub false_count: u64,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct CodeRegion {
    pub file_path: String,
    pub start_line: u64,
    pub start_column: u64,
    pub end_line: u64,
    pub end_column: u64, // Exclusive
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct PartiallyCoveredFunction {
    pub function_name: String,
    pub file_path: String,
    pub partially_covered_predicates: Vec<PartiallyCoveredPredicate>,
    pub uncovered_regions: Vec<CodeRegion>,
    pub whole_function: Option<CodeRegion>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
struct Position {
    line: u64,
    column: u64,
}

impl CodeRegion {
    fn start(&self) -> Position {
        Position {
            line: self.start_line,
            column: self.start_column,
        }
    }

    fn end(&self) -> Position {
        Position {
            line: self.end_line,
            column: self.end_column, // Exclusive
        }
    }
}

fn can_merge(a: &CodeRegion, b: &CodeRegion) -> bool {
    // Assuming a.start <= b.start
    // We can merge if a.end (exclusive) >= b.start
    a.end() >= b.start()
}

fn is_fully_covered(a: &CodeRegion, b: &CodeRegion) -> bool {
    // a fully covers b if:
    // a.start <= b.start and a.end >= b.end
    a.start() <= b.start() && a.end() >= b.end()
}

fn merge_regions_in_place(a: &mut CodeRegion, b: &CodeRegion) {
    let start_pos = a.start().min(b.start());
    let end_pos = a.end().max(b.end());

    a.start_line = start_pos.line;
    a.start_column = start_pos.column;
    a.end_line = end_pos.line;
    a.end_column = end_pos.column;
    // file_path remains the same
}

fn merge_uncovered_regions(uncovered_regions: Vec<CodeRegion>) -> Vec<CodeRegion> {
    let mut regions_by_file: HashMap<String, Vec<CodeRegion>> = HashMap::new();

    // Group regions by file path
    for region in uncovered_regions {
        regions_by_file
            .entry(region.file_path.clone())
            .or_default()
            .push(region);
    }

    let mut merged_regions_all_files = Vec::new();

    // Process regions for each file
    for (_file_path, mut regions) in regions_by_file {
        // Sort regions by start position
        regions.sort_by_key(|r| (r.start_line, r.start_column));

        let mut merged_regions = Vec::new();

        for region in regions {
            if let Some(last_region) = merged_regions.last_mut() {
                if is_fully_covered(last_region, &region) {
                    // Current region is fully covered, skip it
                    continue;
                } else if can_merge(last_region, &region) {
                    // Merge regions
                    merge_regions_in_place(last_region, &region);
                } else {
                    // No overlap, add the current region
                    merged_regions.push(region);
                }
            } else {
                // First region, add it
                merged_regions.push(region);
            }
        }

        // Add the merged regions of this file to the result
        merged_regions_all_files.extend(merged_regions);
    }

    merged_regions_all_files
}

/// Checks if a function is partially covered and returns uncovered branches if any.
/// A function is partially covered if it is called at least once and has at least one branch that is partially covered.
/// A branch is partially covered if it has either an uncovered true or false execution count.
fn get_partially_covered_predicates(
    function: &FunctionMetrics,
) -> Option<Vec<PartiallyCoveredPredicate>> {
    // first we check if the function is called at least once
    if function.count == 0 {
        return None;
    }

    // collect uncovered branches
    let uncovered_branches: Vec<&Branch> = function
        .branches
        .iter()
        .filter(|branch| {
            (branch.execution_count == 0 && branch.false_execution_count > 0)
                || (branch.execution_count > 0 && branch.false_execution_count == 0)
        })
        .collect();

    if uncovered_branches.is_empty() {
        None
    } else {
        Some(
            uncovered_branches
                .iter()
                .map(|branch| PartiallyCoveredPredicate {
                    file_path: function.filenames[branch.file_id as usize].to_string(),
                    start_line: branch.line_start,
                    start_column: branch.column_start,
                    end_line: branch.line_end,
                    end_column: branch.column_end,
                    true_count: branch.execution_count,
                    false_count: branch.false_execution_count,
                })
                .collect(),
        )
    }
}

fn is_pure_comment(region: &CodeRegion) -> bool {
    // get the file content with get_file_part
    let mut snippet = get_file_part(
        &region.file_path,
        region.start_line,
        region.start_column,
        region.end_line,
        region.end_column,
    );

    // Remove block comments
    let block_comment_re = Regex::new(r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/").unwrap();
    snippet = block_comment_re.replace_all(&snippet, "").to_string();

    // Remove line comments
    let line_comment_re = Regex::new(r"//[^\n]*(?:\n|$)").unwrap();
    snippet = line_comment_re.replace_all(&snippet, "").to_string();

    snippet.trim().is_empty()
}

fn get_uncovered_regions(function: &FunctionMetrics) -> Vec<CodeRegion> {
    // if a function has partially covered predicates, it must have uncovered regions, so we can always return something
    let uncovered_regions: Vec<CodeRegion> = function
        .regions
        .iter()
        .filter(|region| region.kind == RegionKind::Code && region.execution_count == 0)
        .map(|region| CodeRegion {
            file_path: function.filenames[region.file_id as usize].to_string(),
            start_line: region.line_start,
            start_column: region.column_start,
            end_line: region.line_end,
            end_column: region.column_end,
        })
        .collect();

    // run a simple region merge to combine adjacent uncovered regions
    // this merge do the following:
    // 1. if two regions are adjacent, merge them into one
    // 2. if a region is fully covered by another region, remove the covered region
    // 3. repeat 1 and 2 until no more regions can be merged
    let merged_uncovered_regions = merge_uncovered_regions(uncovered_regions);

    // run a simple region identification to remove the regions that are purely comment
    // this is to avoid reporting the comment regions as uncovered regions
    merged_uncovered_regions
        .into_iter()
        .filter(|region| !is_pure_comment(region))
        .collect()
}

/// Identify partially covered functions, and get the uncovered areas.
pub fn get_uncovered(coverage_report: &CoverageReport) -> Vec<PartiallyCoveredFunction> {
    let mut uncovered_functions = Vec::new();

    for function in &coverage_report.data[0].functions {
        if let Some(uncovered_branches) = get_partially_covered_predicates(function) {
            // file path is the first code region's file path
            let first_code_region = function.regions.iter().find(|r| r.kind == RegionKind::Code);
            if first_code_region.is_none() {
                continue;
            }

            let first_code_region = first_code_region.unwrap();
            uncovered_functions.push(PartiallyCoveredFunction {
                function_name: function.name.to_string(),
                file_path: function.filenames[first_code_region.file_id as usize].to_string(),
                partially_covered_predicates: uncovered_branches,
                uncovered_regions: get_uncovered_regions(function),
                whole_function: Some(CodeRegion {
                    file_path: function.filenames[first_code_region.file_id as usize].to_string(),
                    start_line: first_code_region.line_start,
                    start_column: first_code_region.column_start,
                    end_line: first_code_region.line_end,
                    end_column: first_code_region.column_end,
                }),
            });
        }
    }

    uncovered_functions
}
