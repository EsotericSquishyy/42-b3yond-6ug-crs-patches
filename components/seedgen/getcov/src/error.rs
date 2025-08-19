use std::{io, string::FromUtf8Error};
use thiserror::Error;

/// Custom error type for the application.
#[derive(Debug, Error)]
pub enum GetCovError {
    #[error("I/O Error: {0}")]
    Io(#[from] io::Error),

    #[error("Goblin Error: {0}")]
    Goblin(#[from] goblin::error::Error),

    #[error("Coverage Error: {0}")]
    Coverage(String),

    #[error("Argument Parsing Error: {0}")]
    ArgParse(String),

    #[error("LLVM Coverage Parsing Error: {0}")]
    LlvmCovParse(#[from] FromUtf8Error),

    #[error("Json Parsing Error: {0}")]
    JsonParse(#[from] serde_json::Error),
}
