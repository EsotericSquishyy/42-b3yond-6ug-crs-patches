use dashmap::{DashMap, DashSet};
use lazy_static::lazy_static;
use std::{
    cell::Cell,
    env,
    fs::{File, OpenOptions},
    io::Write,
    os::raw::c_void,
    path::PathBuf,
    sync::Mutex,
};

mod error;
use error::CallGraphError;

type Result<T> = std::result::Result<T, CallGraphError>;
type FunctionName = Option<String>;
type FunctionPair = (FunctionName, FunctionName);

/// Configuration for the call graph logging
#[derive(Debug)]
struct Config {
    enabled: bool,
    log_path: PathBuf,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            enabled: env::var("EXPORT_CALLS").is_ok(),
            log_path: PathBuf::from("/tmp/callgraph.log"),
        }
    }
}

lazy_static! {
    static ref CONFIG: Config = Config::default();
    static ref LOG_FILE: Mutex<Option<File>> = Mutex::new(None);
    static ref SEEN_PAIRS: DashSet<FunctionPair> = DashSet::new();
    static ref SYMBOL_CACHE: DashMap<usize, FunctionName> = DashMap::new();
}

/// Thread-local storage to prevent recursion and track thread IDs
mod thread_locals {
    use super::*;

    thread_local! {
        pub static PREVENT_RECURSION: Cell<bool> = const { Cell::new(false) };
        pub static THREAD_ID: Cell<i64> = const { Cell::new(-1) };
    }
}

/// RAII guard to prevent recursion
struct RecursionGuard;

impl RecursionGuard {
    fn new() -> Option<Self> {
        if thread_locals::PREVENT_RECURSION.get() {
            None
        } else {
            thread_locals::PREVENT_RECURSION.set(true);
            Some(RecursionGuard)
        }
    }
}

impl Drop for RecursionGuard {
    fn drop(&mut self) {
        thread_locals::PREVENT_RECURSION.set(false);
    }
}

/// Records a function call for call graph generation
#[no_mangle]
pub extern "C" fn __seedmind_record_func_call(caller: *mut c_void, callee: *mut c_void) {
    if !CONFIG.enabled {
        return;
    }

    // Early return if we're in a recursive call
    let _guard = match RecursionGuard::new() {
        Some(guard) => guard,
        None => {
            eprintln!("Recursion detected in __seedmind_record_func_call");
            return;
        }
    };

    if let Err(e) = record_call(caller, callee) {
        eprintln!("Error recording function call: {}", e);
    }
}

/// Records a single function call to the log file
fn record_call(caller: *mut c_void, callee: *mut c_void) -> Result<()> {
    static INITIALIZED: std::sync::Once = std::sync::Once::new();
    INITIALIZED.call_once(|| {
        if CONFIG.enabled {
            if let Err(e) = initialize_logging() {
                eprintln!("Failed to initialize logging: {}", e);
            }
        }
    });

    let tid = get_thread_id();
    let callee = symbolize_pc(callee);
    let caller = symbolize_pc(caller);

    // Skip if either symbol resolution failed
    let (Some(callee_name), Some(caller_name)) = (callee.as_ref(), caller.as_ref()) else {
        return Ok(());
    };

    let pair = (callee.clone(), caller.clone());
    if !SEEN_PAIRS.insert(pair) {
        return Ok(());
    }

    write_log_entry(tid, callee_name, caller_name)
}

/// Gets or initializes the thread ID
fn get_thread_id() -> i64 {
    thread_locals::THREAD_ID.with(|tid| {
        let current = tid.get();
        if current == -1 {
            let new_tid = unsafe { libc::syscall(libc::SYS_gettid) };
            tid.set(new_tid);
            new_tid
        } else {
            current
        }
    })
}

/// Writes a single entry to the log file
fn write_log_entry(tid: i64, callee: &str, caller: &str) -> Result<()> {
    let mut file_guard = LOG_FILE.lock().map_err(|_| CallGraphError::LockError)?;
    let file = file_guard.as_mut().ok_or(CallGraphError::NoLogFile)?;

    writeln!(file, "{:?}|{}|{}", tid, callee, caller)?;
    file.sync_all()?;
    Ok(())
}

/// Resolves a program counter to a function name, using cache
#[inline]
fn symbolize_pc(pc: *mut c_void) -> Option<String> {
    let pc_usize = pc as usize;
    if let Some(cache) = SYMBOL_CACHE.get(&pc_usize) {
        return cache.clone();
    }

    let symbol = resolve_symbol(pc);
    SYMBOL_CACHE.insert(pc_usize, symbol.clone());
    symbol
}

/// Actually performs the symbol resolution
#[inline]
fn resolve_symbol(pc: *mut c_void) -> Option<String> {
    let mut function_name = None;

    // backtrace resolve subtracts 1 from the frame pc to get the caller
    // but we are using the call instruction pc, so we need to add 1 back to get correct function
    backtrace::resolve(unsafe { (pc as *mut c_void).add(1) }, |symbol| {
        if let Some(symbol_filename) = symbol.filename() {
            if symbol_filename.starts_with("/usr") {
                return; // skip system libraries
            }
        }
        if let Some(symbol_name) = symbol.name() {
            function_name = Some(symbol_name.to_string()); // for C++ symbols, it's demangled automatically
        }
    });

    function_name
}

/// Initializes the log file
fn initialize_logging() -> Result<()> {
    let file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&CONFIG.log_path)?;

    *LOG_FILE.lock().map_err(|_| CallGraphError::LockError)? = Some(file);
    Ok(())
}
