use colored::*;

// Define a macro to create environment variables and their descriptions
macro_rules! define_env_vars {
    ($($name:ident: $value:expr => $description:expr),* $(,)?) => {
        $(
            pub const $name: &str = $value;
        )*

        pub const ARGUS_ENVS: &[(&str, &str)] = &[
            $(
                ($value, $description),
            )*
        ];
    };
}

// Use the macro to define environment variables and their descriptions
define_env_vars! {
    ARGUS_DEBUG: "ARGUS_DEBUG" => "Enable debugging for Argus.",

    // options to enable visitors
    ADD_DRIVER: "ADD_DRIVER" => "Enable harness support, replace libFuzzer options with driver.",
    ADD_RUNTIME: "ADD_RUNTIME" => "Enable runtime linking.",
    ADD_ADDITIONAL_PASSES: "ADD_ADDITIONAL_PASSES" => "Enable additional passes.",
    ADD_ADDITIONAL_OBJECTS: "ADD_ADDITIONAL_OBJECTS" => "Enable additional object files.",
    PROFILING: "BANDFUZZ_PROFILE" => "Enable profiling.",
    GENERATE_COMPILATION_DATABASE: "GENERATE_COMPILATION_DATABASE" => "Enable compilation database generation.",

    // options to control visitors
    RUNTIME: "BANDFUZZ_RUNTIME" => "File path to runtime linked to the target.",
    DRIVER: "BANDFUZZ_DRIVER" => "Library used as the fuzzer driver (libFuzzer mode).",
    ENABLE_ASAN: "AFL_USE_ASAN" => "Enable AddressSanitizer.",
    ENABLE_COVSAN: "BANDFUZZ_USECOV" => "Enable coverage sanitizer.",
    ENABLE_MSAN: "AFL_USE_MSAN" => "Enable MemorySanitizer.",
    ENABLE_UBSAN: "AFL_USE_UBSAN" => "Enable UndefinedBehaviorSanitizer.",
    NOSANITIZER: "BANDFUZZ_NOSAN" => "Disable all sanitizers.",
    OPT_LEVEL: "BANDFUZZ_OPT" => "Optimization level for the target.",
    COMPILATION_DATABASE_DIR: "COMPILATION_DATABASE_DIR" => "Directory to write the compilation database to.",
}

pub fn print_envs() {
    for (env, description) in ARGUS_ENVS.iter() {
        println!(
            "{}: {}",
            env.bold().cyan(),
            std::env::var(env).unwrap_or_else(|_| String::from("-")),
        );
        println!("  {}", description.italic().dimmed());
    }
}
