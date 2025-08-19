use std::{io, path::Path};

use super::OptionVisitor;
use crate::{compiler_option::CompilerOption, env::COMPILATION_DATABASE_DIR};
use uuid::Uuid;

pub struct CompilationDatabaseVisitor {
    compilation_database_dir: Option<String>,
}

impl Default for CompilationDatabaseVisitor {
    fn default() -> Self {
        Self::new()
    }
}

impl CompilationDatabaseVisitor {
    pub fn new() -> Self {
        CompilationDatabaseVisitor {
            compilation_database_dir: None,
        }
    }

    pub fn init(&mut self) {
        if std::env::var(COMPILATION_DATABASE_DIR).is_ok() {
            self.compilation_database_dir = Some(std::env::var(COMPILATION_DATABASE_DIR).unwrap());
        }
    }
}

fn prepare_compilation_database_folder(dir: &str) -> io::Result<()> {
    let path = Path::new(dir);
    if !path.exists() {
        std::fs::create_dir_all(path)?;
    }
    Ok(())
}

impl OptionVisitor for CompilationDatabaseVisitor {
    fn visit(&mut self, options: &mut Vec<CompilerOption>) {
        self.init();
        if let Some(dir) = &self.compilation_database_dir {
            if prepare_compilation_database_folder(dir).is_ok() {
                // get a UUID for the compilation database
                let uuid = Uuid::new_v4().to_string();
                options.push(CompilerOption::new("-MJ"));
                options.push(CompilerOption::new(&format!("{}/{}.json", dir, uuid)));
            } else {
                eprintln!(
                    "Failed to prepare compilation database folder: {}, ignoring",
                    dir
                );
            }
        }
    }
}
