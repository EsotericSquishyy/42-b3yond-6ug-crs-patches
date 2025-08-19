// AIxCC: Change LLVM_PASS_DIR
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>
#include <sys/stat.h>
#include <limits.h>
#include <libgen.h>
#include <fcntl.h>
#include <sys/wait.h>

#define LLVM_PASS_DIR std::string("/usr/local/lib/")
std::string get_env(const std::string& var, const std::string& default_value) {
    const char* val = getenv(var.c_str());
    return val == nullptr ? default_value : std::string(val);
}

std::string realpath(const std::string& path) {
    char real_path[PATH_MAX];
    if (::realpath(path.c_str(), real_path)) {
        return std::string(real_path);
    } else {
        throw std::runtime_error("[sancc] Failed to resolve real path for " + path);
    }
}

std::string get_executable_dir() {
    char result[PATH_MAX];
    ssize_t count = readlink("/proc/self/exe", result, PATH_MAX);
    if (count > 0) {
        result[count] = '\0'; // Null-terminate the result
        return std::string(dirname(result)); // Use dirname to remove the executable name
    }
    return std::string();
}


int execute_command(const std::string& compiler_path, const std::vector<std::string>& argv) {
    std::vector<char*> args;
    args.push_back(const_cast<char*>(compiler_path.c_str()));
    for (const auto& arg : argv) {
        args.push_back(const_cast<char*>(arg.c_str()));
    }
    args.push_back(nullptr);

    std::string command = compiler_path;
    for (const auto& arg : argv) {
        command += " " + arg;
    }

    pid_t pid = fork();
    if (pid == -1) {
        std::cerr << "[sancc] Fork failed\n";
        return -1;
    } else if (pid == 0) {
        execvp(compiler_path.c_str(), args.data());
        std::cerr << "[sancc] Execvp failed\n";
        std::cerr << "[sancc] Failed command: " << command << std::endl;
        exit(EXIT_FAILURE);
    } else {
        int status;
        if (waitpid(pid, &status, 0) == -1) {
            std::cerr << "[sancc] Waitpid failed\n";
            return -1;
        }
        if (WIFEXITED(status)) {
            int exit_status = WEXITSTATUS(status);
            if (exit_status != 0) {
                std::cerr << "[sancc] Compilation failed with error code: " << exit_status << "\n";
                std::cerr << "[sancc] Failed command: " << command << std::endl;
                return exit_status;
            }
        } else {
            std::cerr << "[sancc] Process did not exit normally\n";
            return -1;
        }
    }
    return 0;
}

void build(const std::string& compiler_path, const std::vector<std::string>& orig_argv) {
    std::vector<std::string> filtered_argv;
    std::vector<std::string> no_werror_argv;
    for (const auto& arg : orig_argv) {
        if (!arg.starts_with("-O") && !arg.starts_with("-g") && 
            !(arg.starts_with("-fsanitize=") && !arg.starts_with("-fsanitize=fuzzer")) && 
            !arg.starts_with("-Werror")) {
            filtered_argv.push_back(arg);
        }
        if (!arg.starts_with("-Werror")) {
            no_werror_argv.push_back(arg);
        }
    }

    std::string compiler_name = compiler_path.substr(compiler_path.find_last_of('/') + 1);
    std::string exe_dir = get_executable_dir();
    std::string llvm_pass = get_env("LLVM_PASS", realpath(LLVM_PASS_DIR + std::string("/writebc.so")));
    std::map<std::string, std::vector<std::string>> compiler_settings = {
        {"gcc", {"-O0", "-g", "-fsanitize-coverage=trace-pc"}},
        {"g++", {"-O0", "-g", "-fsanitize-coverage=trace-pc"}},
        {"clang", {"-O2", "-g", "-fpass-plugin=" + llvm_pass, "-lpthread"}},
        {"clang++", {"-O2", "-g", "-fpass-plugin=" + llvm_pass, "-lpthread"}},
    };

    if (compiler_settings.find(compiler_name) == compiler_settings.end()) {
        throw std::runtime_error("[sancc] Original compiler does not support");
    }

    std::vector<std::string> argv = filtered_argv;
    argv.insert(argv.end(), compiler_settings[compiler_name].begin(), compiler_settings[compiler_name].end());

    int result = execute_command(compiler_path, argv);
    if (result == 0) {
        return;
    }
    std::cerr << "[sancc] Attempting recompilation with original settings..." << std::endl;

    result = execute_command(compiler_path, no_werror_argv); // Use original arguments for recompilation
    if (result == 0) {
        return;
    }
    std::cerr << "[sancc] Original compilation failed with error code: " << result << std::endl;
    exit(result);
}

int main(int argc, char* argv[]) {
    std::string link_name = std::string(argv[0]);
    size_t pos = link_name.find_last_of('/');
    if (pos != std::string::npos) {
        link_name = link_name.substr(pos + 1);
    }

    std::vector<std::pair<std::string, std::string>> compiler_mapping = {
        {"clang++", "BAKCXX"},
        {"clang", "BAKCC"},
        {"g++", "BAKCXX"},
        {"gcc", "BAKCC"}
    };

    std::map<std::string, std::string> compiler_mapping_default = {
        {"clang++", "clang++"},
        {"clang", "clang"},
        {"g++", "g++"},
        {"gcc", "gcc"}
    };

    std::string compiler_path;
    bool found = false;
    for (const auto& [key, env] : compiler_mapping) {
        if (link_name.find(key) != std::string::npos) {
            compiler_path = get_env(env, compiler_mapping_default[key]);
            found = true;
            break;
        }
    }

    if (!found) {
        std::cerr << "[sancc] Script linked with an unsupported name" << std::endl;
        return 1;
    }

    std::vector<std::string> args(argv + 1, argv + argc);
    build(compiler_path, args);
    return 0;
}
