use super::model::PartiallyCoveredFunction;
use std::fs;

/// Read the file and return the part of the file specified by the start and end lines and columns.
pub fn get_file_part(
    file_path: &str,
    start_line: u64,
    start_column: u64,
    end_line: u64,
    end_column: u64, // exclusive
) -> String {
    let file_content = fs::read_to_string(file_path).expect("Failed to read file");
    let lines = file_content.split('\n').collect::<Vec<&str>>();

    // Handle empty file case
    if lines.is_empty() {
        return "[!] Empty file".to_string();
    }

    // Clamp line indices to valid range
    let start_index = (start_line as usize).saturating_sub(1).min(lines.len() - 1);
    let end_index = (end_line as usize).saturating_sub(1).min(lines.len() - 1);
    let mut has_error =
        start_index != start_line as usize - 1 || end_index != end_line as usize - 1;

    let mut result = String::new();

    for (i, line) in lines[start_index..=end_index].iter().enumerate() {
        let mut start = if i == 0 { start_column as usize - 1 } else { 0 };
        let mut end = if i == end_index - start_index {
            end_column as usize - 1
        } else {
            line.len()
        };

        // Clamp column indices to valid range
        if start > line.len() {
            start = line.len();
            has_error = true;
        }
        if end > line.len() {
            end = line.len();
            has_error = true;
            eprintln!(
                "Warning: End column out of range for file: {}({}:{} - {}:{})",
                file_path, start_line, start_column, end_line, end_column
            );
        }
        if end < start {
            end = start;
            has_error = true;
        }

        if i > 0 {
            result.push('\n');
        }
        result.push_str(&line[start..end]);
    }

    if has_error {
        format!(
            "[!] {}  // warn: try to access file {} ({}:{} - {}:{}), but some lines are out of range",
            result, file_path, start_line, start_column, end_line, end_column
        )
    } else {
        result
    }
}

/// Pretty print the uncovered functions.
pub fn print_uncovered(uncovered_functions: &Vec<PartiallyCoveredFunction>) {
    if uncovered_functions.is_empty() {
        println!("No partially covered functions found.");
        return;
    }

    println!("\nPartially Covered Functions Report");
    println!("=================================\n");

    for function in uncovered_functions {
        println!("Function: {}", function.function_name);
        println!("Location: {}", function.file_path);

        if let Some(whole_function) = &function.whole_function {
            println!(
                "{}",
                get_file_part(
                    &whole_function.file_path,
                    whole_function.start_line,
                    whole_function.start_column,
                    whole_function.end_line,
                    whole_function.end_column
                )
            );
        }

        if !function.partially_covered_predicates.is_empty() {
            println!("\nPartially Covered Predicates:");
            println!("----------------------------");
            for (i, pred) in function.partially_covered_predicates.iter().enumerate() {
                let status = if pred.true_count == 0 && pred.false_count == 0 {
                    "never executed"
                } else if pred.true_count == 0 {
                    "always false"
                } else {
                    "always true"
                };

                println!(
                    "  {}. {} ({})",
                    i + 1,
                    get_file_part(
                        &function.file_path, // it's nearly impossible that the predicate is in a different file
                        pred.start_line,
                        pred.start_column,
                        pred.end_line,
                        pred.end_column
                    ),
                    status
                );
            }
        }

        if !function.uncovered_regions.is_empty() {
            println!("\nUncovered Regions:");
            println!("-----------------");
            let mut display_index = 1;
            for region in function.uncovered_regions.iter() {
                let file_part = get_file_part(
                    &region.file_path,
                    region.start_line,
                    region.start_column,
                    region.end_line,
                    region.end_column,
                );

                // Skip if file part only contains whitespace
                if file_part.trim().is_empty() {
                    continue;
                }

                println!(
                    "  {}. {} ({}:{}:{} - {}:{})",
                    display_index,
                    file_part,
                    region.file_path,
                    region.start_line,
                    region.start_column,
                    region.end_line,
                    region.end_column
                );

                display_index += 1;
            }
        }

        println!("\n---------------------------------\n");
    }
}
