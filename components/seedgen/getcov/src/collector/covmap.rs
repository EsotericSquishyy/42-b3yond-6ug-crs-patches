use crate::error::GetCovError;
use goblin::Object;
use std::fs;
use std::path::Path;

/// Checks if the binary contains LLVM coverage instrumentation.
///
/// # Arguments
///
/// * `binary` - The path to the binary.
///
/// # Returns
///
/// A `Result` indicating whether the binary contains LLVM coverage data.
fn contains_llvm_covmap<P: AsRef<Path>>(binary_path: P) -> Result<bool, GetCovError> {
    // Read the binary file into a buffer
    let buffer = fs::read(binary_path)?;

    // Parse the binary using goblin
    if let Object::Elf(elf) = Object::parse(&buffer)? {
        for section in elf.section_headers.iter() {
            if let Some(name) = elf.shdr_strtab.get_at(section.sh_name) {
                if name.contains("__llvm_covmap") {
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}

/// Checks if the binary has LLVM coverage instrumentation and reports errors.
///
/// # Arguments
///
/// * `binary` - The path to the binary.
///
/// # Returns
///
/// A `Result` indicating success or a `GetCovError`.
pub fn check_covmap(binary: &str) -> Result<(), GetCovError> {
    if contains_llvm_covmap(binary)? {
        Ok(())
    } else {
        Err(GetCovError::Coverage(format!(
            "Binary '{}' does not contain LLVM coverage instrumentation.",
            binary
        )))
    }
}
