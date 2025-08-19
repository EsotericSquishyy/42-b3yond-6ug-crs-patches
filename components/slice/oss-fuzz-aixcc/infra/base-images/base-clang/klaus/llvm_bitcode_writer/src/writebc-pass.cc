#include "llvm/IR/Module.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/Support/FileSystem.h"
#include <fcntl.h>
#include <unistd.h>
#include <filesystem>
#include <iostream>
#include <fstream>
#include <sstream>
#include <cstdlib>
#include <iomanip>  // For std::hex, std::setw, std::setfill
#include <openssl/md5.h>  // For MD5 calculation
using namespace llvm;

#define BITCODE_FOLDER "42_aixcc_bitcode"

int lockFile(const std::string &path) {
    
    int fd = open(path.c_str(), O_RDWR | O_CREAT, 0644);
    if (fd == -1) {
        std::cerr << "[Error] Failed to open or create file: " << path << std::endl;
        return -1;
    }

    struct flock lock;
    lock.l_type = F_WRLCK;
    lock.l_whence = SEEK_SET;
    lock.l_start = 0;
    lock.l_len = 0;

    if (fcntl(fd, F_SETLK, &lock) == -1) {
        std::cerr << "[Error] Failed to lock file: " << path << std::endl;
        close(fd);
        return -1;
    }

    return fd;
}


void unlockFile(int fd) {
    if (fd != -1) {
        close(fd);
    }
}

#define DEBUG_LOG(stmt)                          \
    do {                                         \
        if (getenv("DEBUG_LLVM_BITCODE_WRITER")) \
            errs() << stmt << "\n";              \
    } while (0)

namespace {
class WriteBitcodePass : public PassInfoMixin<WriteBitcodePass> {
   public:
    PreservedAnalyses run(Module& M, ModuleAnalysisManager& MAM) {
        if (const char* env = getenv("OUT")) {
            // if (const char* project = getenv("PROJECT_NAME")) {
                std::filesystem::path outEnvPath = std::filesystem::absolute(env);
                std::filesystem::path projectPath = outEnvPath;
                DEBUG_LOG("[llvm_bitcode_writer] projectPath: " << projectPath.string());
                if (std::filesystem::exists(projectPath)) {
                    std::filesystem::path targetFolder = projectPath / BITCODE_FOLDER;
                    std::filesystem::create_directories(targetFolder);
                    
                    // Get source filename
                    std::string sourceFilePath = M.getSourceFileName();
                    std::string md5Hash = calculateMD5(sourceFilePath);
                    std::string bcName = md5Hash + ".bc";
                    
                    std::filesystem::path targetPath = targetFolder / bcName;
                    writeModuleBitcodeToFile(M, targetPath.string());
                    return PreservedAnalyses::all();
                }
                DEBUG_LOG("[llvm_bitcode_writer] SRC environment variable path is not valid");
            // } else {
            //     DEBUG_LOG("[llvm_bitcode_writer] PROJECT_NAME environment variable is not set");
            // }
        } else {
            DEBUG_LOG("[llvm_bitcode_writer] SRC environment variable is not set");
        }
        DEBUG_LOG("[llvm_bitcode_writer] Falling back to default method.");        
        // write out bitcode
        std::vector<std::string> validExtensions = {".c", ".cc", ".cpp"};
        do {
            std::string FileName = M.getSourceFileName();
            std::filesystem::path srcFilePath = std::filesystem::absolute(FileName);
            if (std::find(validExtensions.begin(), validExtensions.end(), srcFilePath.extension()) ==
                validExtensions.end()) {
                DEBUG_LOG("[llvm_bitcode_writer] Source code extension does not match");
                break;
            }

            writeModuleBitcodeToFile(M, srcFilePath.string() + ".bc");

            // Skip if the path is incorrect or starts with the /src directory
            if (std::distance(srcFilePath.begin(), srcFilePath.end()) < 2) {
                DEBUG_LOG("[llvm_bitcode_writer] The length of source code path is less than 2: " << srcFilePath.string());
                break;
            }

            auto srcPathIt = srcFilePath.begin();
            if (srcPathIt->string() == "/" && (++srcPathIt)->string() == "src") {
                DEBUG_LOG("[llvm_bitcode_writer] source code path is in the /src directory: " << srcFilePath.string());
                break;
            }

            std::filesystem::path srcRootPath, srcTestPath;
            auto srcPath = srcFilePath.parent_path();
            bool found_path = false;
            for (auto it = srcPath.begin(); it != srcPath.end(); ++it) {
                srcRootPath /= *it;
                srcTestPath = std::filesystem::path("/src") / std::filesystem::relative(srcFilePath, srcRootPath);
                if (std::filesystem::exists(srcTestPath)) {
                    DEBUG_LOG("[llvm_bitcode_writer] Locate the root directory of the 'copied source': "
                              << srcRootPath.string() << ", original source directory: " << srcTestPath.string());
                    writeModuleBitcodeToFile(M, srcTestPath.string() + ".bc");
                    writeFile("/tmp/copy_src_root", srcRootPath.string());
                    found_path = true;
                    break;
                }
            }

            if (found_path) {
                break;
            }
            auto copy_src_root = readFile("/tmp/copy_src_root");
            if (copy_src_root == "") {
                srcRootPath = "";
            } else {
                srcRootPath = std::filesystem::absolute(srcRootPath);
            }
            bool is_parent =
                std::filesystem::relative(srcPath, srcRootPath).string().find("..") == std::string::npos;
            if (srcRootPath.empty() || !is_parent) {
                auto findSrcPos = std::find(srcPath.begin(), srcPath.end(), "src");
                if (findSrcPos == srcPath.end()) {
                    DEBUG_LOG("[llvm_bitcode_writer] Could not find the original source directory to write Bitcode: "
                              << srcPath.string());
                    break;  // The path does not contain the src/ directory
                }
                // Create a new directory and copy the source files
                srcRootPath = "";
                for (auto it = srcFilePath.begin(); it != std::next(findSrcPos); ++it) {
                    srcRootPath /= *it;
                }
            }
            DEBUG_LOG(
                "[llvm_bitcode_writer] Guess the root directory of the 'copied source' is: " << srcRootPath.string());
            auto srcGuessPath = std::filesystem::path("/src") / std::filesystem::relative(srcFilePath, srcRootPath);
            std::filesystem::create_directories(srcGuessPath.parent_path());
            std::filesystem::copy(srcFilePath, srcGuessPath);  // copy source code
            writeModuleBitcodeToFile(M, srcGuessPath.string() + ".bc");

        } while (false);
        return PreservedAnalyses::all();
    }
    static bool isRequired() { return true; }

   private:
    // Calculate MD5 hash of file content
    std::string calculateMD5(const std::string& filePath) {
        std::ifstream file(filePath, std::ios::binary);
        if (!file.is_open()) {
            DEBUG_LOG("[llvm_bitcode_writer] Failed to open file for MD5 calculation: " << filePath);
            return std::filesystem::path(filePath).filename().string(); // Fallback to original filename
        }
        
        MD5_CTX md5Context;
        MD5_Init(&md5Context);
        
        char buffer[1024];
        while (file.good()) {
            file.read(buffer, sizeof(buffer));
            MD5_Update(&md5Context, buffer, file.gcount());
        }
        
        unsigned char result[MD5_DIGEST_LENGTH];
        MD5_Final(result, &md5Context);
        
        std::stringstream ss;
        for (int i = 0; i < MD5_DIGEST_LENGTH; i++) {
            ss << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(result[i]);
        }
        
        return ss.str();
    }

    void writeModuleBitcodeToFile(const llvm::Module& M, const std::string& path) {
        outs() << "[llvm_bitcode_writer] Writing bitcode to " << path << "\n";
        std::error_code EC;
        if (llvm::sys::fs::exists(path)) {
            llvm::outs() << "[llvm_bitcode_writer] Warning: File already exists and will return\n";
            return;
        }
        int fd = lockFile(path);
        if (fd != -1) {
            std::cout << "File locked successfully!\n";
            raw_fd_ostream out(path, EC, sys::fs::OF_None);
            if (EC) {
                errs() << "[llvm_bitcode_writer] Could not open file: " << path << ", " << EC.message() << "\n";
                return;
            }
            WriteBitcodeToFile(M, out);
            unlockFile(fd);
        } else {
            std::cout << "Failed to lock the file!\n";
        }
    }
    std::string readFile(const std::string& filePath) {
        std::ifstream file(filePath);
        std::stringstream buffer;
        if (!file.is_open()) {
            return "";
        }
        buffer << file.rdbuf();
        return buffer.str();
    }

    void writeFile(const std::string& filePath, const std::string& content, bool append = false) {
        std::ofstream file(filePath, append ? std::ios::app : std::ios::trunc);
        if (file.is_open()) {
            file << content;
        }
    }
};
}  // namespace

llvm::PassPluginLibraryInfo getWriteBitcodePluginInfo() {
    const auto callback = [](PassBuilder& PB) {
        PB.registerPipelineEarlySimplificationEPCallback([](llvm::ModulePassManager& PM, OptimizationLevel Level) {
            PM.addPass(WriteBitcodePass());
            return true;
        });
    };
    return {LLVM_PLUGIN_API_VERSION, "WriteBitcode", "v0.4", callback};
}

extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo llvmGetPassPluginInfo() {
    return getWriteBitcodePluginInfo();
}
