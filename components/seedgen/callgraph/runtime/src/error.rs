use std::fmt;
use std::io;

#[derive(Debug)]
pub enum CallGraphError {
    IoError(io::Error),
    LockError,
    NoLogFile,
}

impl std::error::Error for CallGraphError {}

impl fmt::Display for CallGraphError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CallGraphError::IoError(e) => write!(f, "I/O error: {}", e),
            CallGraphError::LockError => write!(f, "Failed to acquire lock"),
            CallGraphError::NoLogFile => write!(f, "Log file not initialized"),
        }
    }
}

impl From<io::Error> for CallGraphError {
    fn from(error: io::Error) -> Self {
        CallGraphError::IoError(error)
    }
} 