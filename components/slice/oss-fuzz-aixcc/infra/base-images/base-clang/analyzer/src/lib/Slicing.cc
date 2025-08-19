#include <llvm/ADT/StringExtras.h>
#include <llvm/Analysis/CallGraph.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DebugInfo.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/TypeFinder.h>
#include <llvm/Pass.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/IR/IntrinsicInst.h>
#include "llvm/Support/FileSystem.h"
#include "llvm/IR/CFG.h"



#include "Slicing.h"
#include <stack>
#include <set>
#include <iostream>
#include <fstream>

using namespace llvm;
using namespace std;

// Redundant, to remove
void Slicing::slicing(char *funcName) {
    Function *targetFunc = nullptr;
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *m = i->first;
        targetFunc = m->getFunction(funcName);
        if (targetFunc)
            break;
    }

    if (targetFunc == nullptr) {
        errs() << "target function not found\n";
        return;
    } else {
        errs() << "target found\n";
    }
    this->sliceFunction(targetFunc);
}


// Function to check if basic block 'src' can reach 'dst' within a function body
bool Slicing::intraCanReach(BasicBlock *src, BasicBlock *dst) {
    // DFS explore paths from 'src' to 'dst'
    std::set<BasicBlock*> visited;
    std::stack<BasicBlock*> toVisit;
    toVisit.push(src);
    while (!toVisit.empty()) {
        BasicBlock *current = toVisit.top();
        toVisit.pop();
        if (visited.insert(current).second) {
            if (current == dst) {
                return true;
            }

            // Find all successor basic blocks of 'current', and mark them as to visit
            for (BasicBlock *Succ : successors(current)) {
                toVisit.push(Succ);
            }
        }
    }
    return false;
}

// Function to add functions related to verbose slice result
void Slicing::addToVerbose(Function *F) {

    // Avoid reprocessing the same function
    if ( !verboseF_.insert(F).second ) {
        return;
    }
    // std::string funcName = F->getName().str();
    // std::string funcPath = F->getSubprogram()->getFilename().str();
    // std::cout << "addToVerbose: " << funcPath << "/" << funcName << "\n";

    // Find all call instructions that invoke 'F'
    CallBaseSet CBS = Ctx_->Callers[F];
    if (!CBS.empty()) {
        for (CallBase *CB : CBS) {
            if(CB) {
                BasicBlock *fBB = CB->getParent();
                if (fBB) {

                    // Enclosing function of F's call instruction
                    Function *enclosingF = fBB->getParent(); 
                    if (enclosingF) {
                        for (auto &BB : *enclosingF) {
                            
                            // Find other call instructions inside this enclosing function
                            for (auto &I : BB) { 
                                if (CallBase *CB_ = dyn_cast<CallBase>(&I)) {

                                    // Skip llvm intrinsic functions
                                    if (auto *intrinsics = dyn_cast<IntrinsicInst>(CB_)) {
                                        continue;
                                    }

                                    // If there is a path between other Fs' call instructions and F's call instruction
                                    // Then they are also considered to be part of the verbose slice
                                    BasicBlock *otherBB = CB_->getParent();
                                    bool canReach = this->intraCanReach(otherBB, fBB);
                                    if (canReach) {
                                        Function *otherF = CB_->getCalledFunction();
                                        if (otherF) {
                                            verboseF_.insert(otherF);
                                        }
                                        // std::string srcName = srcF->getName().str();
                                        // std::string dstName = F->getName().str();
                                        // std::string ownerName = ownerF->getName().str();
                                        // std::string ownerFilePath = ownerF->getSubprogram()->getFilename().str();
                                        // std::cout << "src: " << srcName << " dst: " << dstName << " owner: "
                                        // << ownerName << " ownerPath: " << ownerFilePath << "\n";
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// Function to perform function-level slicing to identify relavent basic blocks
void Slicing::sliceFunction(Function *F) { 

    // Prevent redundant processing of the same function
    if (!visitedF_.insert(F).second) {
        return;
    }

    // Mark all current function's basic blocks as visited
    for (auto &BB : *F) {
        visitedBB_.insert(&BB);
    }

    // Add current function and its relevant functions to verbose output
    addToVerbose(F);

    // Collect all CallInstSets that match F's name, because Ctx_->Callers might exist multiple F with different CIS
    std::vector<CallBaseSet*> matchingCBS;
    for (auto &entry : Ctx_->Callers) {
        Function *storedFunc = entry.first;
        if (storedFunc->getName() == F->getName()) {
            matchingCBS.push_back(&entry.second);
        }
    }

    // Exit early if no valid function is found
    if (matchingCBS.empty()) {
        return; 
    }

    // Process all matched CallBaseSets iteratively to avoid infinite recursion and other LLVM bugs
    std::queue<BasicBlock*> toProcess;

    for (CallBaseSet *CBS : matchingCBS) {
        if (!CBS->empty()) {
            for (CallBase *CB : *CBS) {
                if (!CB || !CB->getParent()) {
                    continue;
                }
                BasicBlock *BB = CB->getParent();
                if (BB && visitedBB_.find(BB) == visitedBB_.end()) {
                    toProcess.push(BB);
                }
            }
        }
    }

    // Backward slice each basic block in the queue
    while (!toProcess.empty()) {
        BasicBlock *BB = toProcess.front();
        toProcess.pop();
        backtracking(BB);
    }

    // Only increment once if at least one match had calls
    for (CallBaseSet *CBS : matchingCBS) {
        if (!CBS->empty()) {
            slicedFuncCnt_++;
            break;
        }
    }
}

// Function to backward slice basic blocks to refine slicing
void Slicing::backtracking(BasicBlock *BB) {

    // DFS traverse the CFG in reverse
    std::stack<BasicBlock*> toVisit;
    toVisit.push(BB);
    while (!toVisit.empty()) {
        BasicBlock *current = toVisit.top();
        toVisit.pop();

        // Handle edge cases
        if (!current || !current->getParent()) {
            continue;
        }

        // Mark current basic block as visited
        if (visitedBB_.insert(current).second) {
            BasicBlock * lastPred = nullptr;
            // Find all predecessor basic blocks of current
            for (BasicBlock *Pred : predecessors(current)) {
                // std::cout << "Pred: " << Pred << "/" << current << std::endl;
                // Handle edge case of self loop
                if (Pred == lastPred) { 
                    break;
                }
                lastPred = Pred;

                // If predecessor basic blocks have not been visited yet
                if (visitedBB_.find(Pred) == visitedBB_.end()) {
                    toVisit.push(Pred);
                }
            }
        }
    }

    // Recursively slice BB's enclosing function
    sliceFunction(BB->getParent());
    return;
}

// Function to slice against 'LLVMFuzzerInitialize', 'LLVMFuzzerTestOneInput' and 'LLVMFuzzerRunDriver'
void Slicing::forwardSlicingFunctionStub(std::string funcName) {
    Function *F = nullptr;

    // Iterate through all modules to find the function
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *m = i->first;
        F = m->getFunction(funcName); // ?
        if (F)
            break;
    }
    if (F == nullptr) {
        errs() << "forward target function not found: " << funcName << "\n";
        return;
    }

    // Include LibFuzzer functions directly as part of thin slice
    /*
    for (auto &BB : *F) {
        visitedBB_.insert(&BB);
    }
    */
    
    // Forward slice against the designated LibFuzzer functions
    this->forwardSlicingFunction(F);
}

void Slicing::forwardSlicingFunctionWithDepth(Function *F, int depth, std::set<Function*> *visited) {
    // if (visited->find(F) != visited->end()) {
    //     return;
    // }
    visited->insert(F);
    if (depth == 0) {
        return;
    }
    for (auto &BB : *F) {
        for (auto &I : BB) {
            if (CallBase *CB = dyn_cast<CallBase>(&I)) {
                auto funcSet = Ctx_->Callees.find(CB);
                if (funcSet == Ctx_->Callees.end()) {
                    continue;
                }
                for (Function *callee : funcSet->second) {
                    forwardSlicingFunctionWithDepth(callee, depth - 1, visited);
                }
            }
        }
    }
    return;
}

// Function to perform forward slicing
void Slicing::forwardSlicingFunction(Function *F) {

    // BFS explore all basic blocks
    std::queue<BasicBlock*> toVisit;
    std::set<BasicBlock*> visited;

    // Mark each basic block of current function as to visit
    for (auto &BB : *F) {
        toVisit.push(&BB);
    }

    while (!toVisit.empty()) {
        
        // Visit all basic blocks and consider each as part of verbose slice
        BasicBlock *current = toVisit.front();
        toVisit.pop();
        verboseBB_.insert(current);

        // If current basic block hasn't been visited, visit it and iterate over its instructions
        if (visited.insert(current).second) {
            for (auto &I : *current) {

                // If the instruction is a function call, if so, retrieve all callee functions
                if (CallBase *CB = dyn_cast<CallBase>(&I)) {
                    auto funcSet = Ctx_->Callees.find(CB);
                    if (funcSet == Ctx_->Callees.end()) {
                        continue;
                    }

                    // If the callee function has not been visited, visit it and recursively visit its basic blocks
                    for (Function *callee : funcSet->second) {
                        if (fVisitedF_.insert(callee).second) {
                            for (auto &BB : *callee) {
                                toVisit.push(&BB);
                            }
                        }
                    }
                }
            }
        }
    }
    // for (auto it = fVisitedF_.begin(); it != fVisitedF_.end(); ++it) {
    //     DISubprogram *SP = (*it)->getSubprogram();
    //     if (SP) {
    //         std::string file = SP->getFilename().str();
    //         std::string path = SP->getDirectory().str();
    //         std::string name = (*it)->getName().str();
    //         std::cout << ">" << path << "/" << file << ":" << name << "\n";
    //     }
    // }
    return;
}

// Function to remove directory path, removes the file extension to extract filename
std::string extractFilenameWithoutExtension(const std::string& path) {

    // Find last occurrence of a path separator
    size_t lastSlash = path.find_last_of("/\\");
    std::string filenameWithExtension;

    // If no path separator found, entire string is filename
    if (lastSlash == std::string::npos) {
        filenameWithExtension = path; 
    } else {
        // Otherwise, extract the substring after the last path separator
        filenameWithExtension = path.substr(lastSlash + 1);
    }

    // Find the last occurrence of a dot '.' to locate file extension
    size_t lastDot = filenameWithExtension.find_last_of(".");

    // If no dot found, entire string is filename
    if (lastDot == std::string::npos) {
        return filenameWithExtension; 
    } else {
        // Otherwise, extract the substring before the dot
        return filenameWithExtension.substr(0, lastDot);
    }
}

// Function to output slicing results to files
void Slicing::dump(std::string outputPath, std::string filePath, std::string funcName) {
    std::error_code EC;

    // std::string filename = extractFilenameWithoutExtension(filePath);
    // std::cout << outputPath+"/"+filename+"."+funcName+"."+slicingOutputFile << "\n";
    llvm::raw_fd_ostream outputFile(outputPath+"/"+funcName+"."+slicingOutputFile, EC, llvm::sys::fs::OF_Text);
    llvm::raw_fd_ostream outputFileVerbose(outputPath+"/"+funcName+"."+slicingOutputFileVerbose, EC, llvm::sys::fs::OF_Text);
    llvm::raw_fd_ostream outputFileFunc(outputPath+"/"+funcName+"."+slicingFuncOutputFile, EC, llvm::sys::fs::OF_Text);
    llvm::raw_fd_ostream outputFileFuncVerbose(outputPath+"/"+funcName+"."+slicingFuncOutputFileVerbose, EC, llvm::sys::fs::OF_Text);
    llvm::raw_fd_ostream outputFileFuncBlacklist(outputPath+"/"+funcName+"."+slicingFuncBlacklist, EC, llvm::sys::fs::OF_Text);
    std::set<llvm::Function*> *visitedFuncs = new std::set<llvm::Function*>();

    std::set<std::string> uniqueOutputs;
    std::set<std::string> uniqueOutputsVerbose;
    std::set<std::string> uniqueOutputsFunc;
    std::set<std::string> uniqueOutputsFuncVerbose;

    if (EC) {
        errs() << "Error opening file: " << EC.message() << "\n";
        return;
    }

    std::cout << "sliced block " << visitedBB_.size() << "\n";
    std::cout << "sliced function " << slicedFuncCnt_ << "\n";
    //errs() << "sliced function " << visitedF_.size() << "\n";

    // add verbose func
    for (auto it = verboseF_.begin(); it != verboseF_.end(); ++it) {
        forwardSlicingFunction(*it);
    }

    std::set<Function*> visitedFuncsWithDepth;
    int depth = 1;
    for (auto it = verboseF_.begin(); it != verboseF_.end(); ++it) {
        uniqueOutputsFunc.insert((*it)->getName().str() + "\n");
        forwardSlicingFunctionWithDepth(*it, depth, &visitedFuncsWithDepth);
    }
    for (auto it = visitedFuncsWithDepth.begin(); it != visitedFuncsWithDepth.end(); ++it) {
        // std::cout << "visitedFuncsWithDepth: " << (*it)->getName().str() << "\n";
        uniqueOutputsFunc.insert((*it)->getName().str() + "\n");
    }

    int extraCnt = 0;
    for (auto it = visitedBB_.begin(); it != visitedBB_.end(); ++it) {
        BasicBlock *BB = *it;
        Function *F = BB->getParent();
        visitedFuncs->insert(F);
        uniqueOutputsFunc.insert(F->getName().str() + "\n");
        uniqueOutputsFuncVerbose.insert(F->getName().str() + "\n");
        bool printFunc = false;
        if (printFunc) {
                DISubprogram *SP = F->getSubprogram();
            if (SP) {
                std::string file = SP->getFilename().str();
                std::string path = SP->getDirectory().str();
                unsigned line = SP->getLine();
                if (file.find("..") != std::string::npos) {
                    file = normalizePath(file);
                }
                // if (file.size() >= 2 && file.substr(0, 2) == "./")
                //     file = file.substr(2);
                // if (path.rfind(srcRoot_,0) == 0)
                uniqueOutputs.insert("func:" + path + "/" + file + ":" + std::to_string(line) + ":100" + "\n");
                uniqueOutputsVerbose.insert("func:" + path + "/" + file + ":" + std::to_string(line) + ":100" + "\n");
            }
        }

        for (auto &I : *BB) { // visited BB
            const llvm::DebugLoc &loc = I.getDebugLoc(); // Use reference to DebugLoc
            if (loc) { // Check if loc is valid
                unsigned line = loc->getLine();
                if (line) {
                    std::string file = loc->getFilename().str();
                    std::string path = loc->getDirectory().str();
                    if (file.find("..") != std::string::npos) {
                        file = normalizePath(file);
                    }
                    uniqueOutputs.insert("block:" + path + "/" + file + ":" + std::to_string(line) + ":100" + "\n");
                    uniqueOutputsVerbose.insert("block:" + path + "/" + file + ":" + std::to_string(line) + ":100" + "\n");
                    break;
                }
            }
        }
    }

    for (auto it = verboseBB_.begin(); it != verboseBB_.end(); ++it) {
        BasicBlock *BB = *it;
        Function *F = BB->getParent();
        visitedFuncs->insert(F);
        uniqueOutputsFuncVerbose.insert(F->getName().str() + "\n");
    }

    for (auto it = uniqueOutputs.begin(); it != uniqueOutputs.end(); ++it) {
        outputFile << *it;
    }
    outputFile.close();
    for (auto it = uniqueOutputsVerbose.begin(); it != uniqueOutputsVerbose.end(); ++it) {
        outputFileVerbose << *it;
    }
    outputFileVerbose.close();

    std::cout << "uniqueOutputsFunc count: " << uniqueOutputsFunc.size() << "\n";
    for (auto it = uniqueOutputsFunc.begin(); it != uniqueOutputsFunc.end(); ++it) {
        outputFileFunc << *it;
    }
    outputFileFunc.close();

    std::cout << "uniqueOutputsFuncVerbose count: " << uniqueOutputsFuncVerbose.size() << "\n";
    for (auto it = uniqueOutputsFuncVerbose.begin(); it != uniqueOutputsFuncVerbose.end(); ++it) {
        outputFileFuncVerbose << *it;
    }
    outputFileFuncVerbose.close();

    std::cout << "fullFunc_ count: " << fullFunc_->size() << "\n";
    int blacklist_cnt = 0;
    for (auto it = fullFunc_->begin(); it != fullFunc_->end(); ++it) {
        if (uniqueOutputsFuncVerbose.find(*it) == uniqueOutputsFuncVerbose.end()) {
            outputFileFuncBlacklist << *it;
            blacklist_cnt++;
        }
    }
    std::cout << "blacklist count: " << blacklist_cnt << "\n";
    outputFileFuncBlacklist.close();

    std::cout << "Extra count: " << extraCnt << "\n";
    std::cout << "Visited function count: " << visitedFuncs->size() << "\n";
    // std::cout << "***for google sheet*** " << this->funcCount() << " " << slicedFuncCnt_ << "(" << visitedFuncs->size() << ")\n";
    return;
}

// Function to count number of total functions in project
int Slicing::funcCount() {
    int cnt = 0;
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;
        for (Function &F : *M)  {
            cnt++;
        }
    }
    // outs() << "total function counts : " << cnt << "\n";
    return cnt;
}

// Function to find target basic block by provided line number
BasicBlock *Slicing::findTargetByLine(const char *fileName, int line) {
    // Iterate over all modules in the context
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;
        // Check if target file is in the module name
        if (M->getName().str().find(fileName) != std::string::npos) {
            // Iterate through all functions in this module
            for (Function &F : *M)  {
                // Iterate through all basic blocks in this function
                for (auto &BB : F) {
                    // Iterate through all instructions in this basic block
                    for (auto &I : BB) {
                        // Retrieve debug location info and the scope
                        if (const DebugLoc &Loc = I.getDebugLoc()) {
                            auto *Scope = cast<DIScope>(Loc.getScope());
                            // If this instruction's line number matches the provided line number
                            if (Loc.getLine() == line) {
                                // Return the first matching basic block
                                return &BB;
                            }
                        }
                    }
                }
            }
        }
    }

    // No matching basic block found, return NULL
    return NULL;
}

// Function to find target function by provided name
Function *Slicing::findTargetByFunctionName(const char *fileName, const char *funcName) {
    // Iterate through all modules in the context
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;
        // Check if target file is in the module name
        // if (M->getName().str().find(fileName) != std::string::npos) {
            // Iterate through all functions in this module
            for (Function &F : *M)  {
                // Iterate through all basic blocks in this function
                for (auto &BB : F) {
                    // If this function's name matches target function's directly or mangled
                    if (F.getName().str() == funcName
                    // drity solution for C++ demangled name
                    || (F.getName().str().find(funcName) != std::string::npos
                    && F.getName().str().find("_Z") != std::string::npos)) {
                        // Return this function
                        return &F;
                    }
                }
            }
        // }
    }

    // No matching function found, return NULL
    return NULL;
}

// Function to find function calls by provided line number
CallInst *Slicing::findCallInstByLine(const char *fileName, int line) {
    std::string inputFile = fileName;

    // Iterate over all modules in the context
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;
        // Extract module name and trim unnecessary chars
        std::string t = M->getName().str().substr(2, M->getName().str().length() - 7);

        // Check if module name matches the provided filename
        if (inputFile.find(t) != std::string::npos) {
            // Iterate over all functions in this module
            for (Function &F : *M)  {
                // Iterate over all basic blocks in this function
                for (auto &BB : F) {
                    // Iterate over all instructions in this basic block
                    for (auto &I : BB) {
                        // If this instruction is a function call
                        if (CallInst *CI = dyn_cast<CallInst>(&I)) {
                            // Retrieve debug location metadata
                            if (const DebugLoc &Loc = CI->getDebugLoc()) {
                                // If the line number of this instruction matches the provided line number
                                if (Loc.getLine() == line &&
                                    inputFile.find(normalizePath(Loc->getFilename().str())) != std::string::npos) {
                                    // Return first matching function call (Call Instruction)
                                    return CI;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    // No matching function call found, return NULL
    return NULL;
}

// Function to find a function by provided line number
Function *Slicing::findFunctionByLine(const char *fileName, int line) {
    std::string inputFile = fileName;
    // Iterate over all modules in the context
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;
        // Extract module name and trim unnecessary chars
        std::string t = M->getName().str().substr(2, M->getName().str().length() - 7);
        // If the module name matches the input file
        if (inputFile.find(t) != std::string::npos) {
            // Iterate over all functions in this module
            for (Function &F : *M)  {
                // Retrieve debug info of this function
                auto *SP = F.getSubprogram();
                if (SP) {
                    // If this function's declared line number matches the provided line number
                    if (SP->getLine() == line && 
                        inputFile.find(normalizePath(SP->getFilename().str())) != std::string::npos) {
                        // Return the first matching function
                        return &F;
                    }
                }
            }
        }
    }

    // No matching function found, return NULL
    return NULL;
}

// Function to cache all functions and call isntructions from LLVM modules
void Slicing::cacheAllLLVMObjects() {
    fullFuncMap_ = new std::map<std::tuple<std::string, int>, Function*>();
    fullCallBaseMap_ = new std::map<std::tuple<std::string, int>, CallBase*>();
    fullFunc_ = new std::set<std::string>();

    // Iterate over all modules in the context
    for (auto i = Ctx_->Modules.begin(), e = Ctx_->Modules.end(); i != e; ++i) {
        Module *M = i->first;

        // Iterate over all functions in this module
        for (Function &F : *M)  {

            // Retrieve debug info of this function
            auto *SP = F.getSubprogram();

            // If it has debug info, normalize file path
            if (SP) {
                std::string file = SP->getFilename().str();
                std::string path = SP->getDirectory().str();
                unsigned line = SP->getLine();
                if (file.find("..") != std::string::npos) {
                    file = normalizePath(file);
                }

                // Store file paths + line numbers and functions in the function map
                fullFuncMap_->insert(std::make_pair(std::make_tuple(path + "/" + file, line), &F)); // absolute path
                // Store function names in the function set
                fullFunc_->insert(F.getName().str()+"\n");
                // std::cout << F.getName().str() << " " << path + "/" + file << " " << line << std::endl;
            }

            // Iterate over all basic blocks in this function
            for (auto &BB : F) {
                // Iterate over all instructions in this basic block
                for (auto &I : BB) {
                    // If this instruction is a function call
                    auto *CB = dyn_cast<CallBase>(&I);
                    if (CB) {
                        // Retrieve its debug info and normalise file path
                        if (const DebugLoc &Loc = CB->getDebugLoc()) {
                            std::string file = Loc->getFilename().str();
                            std::string path = Loc->getDirectory().str();
                            unsigned line = Loc->getLine();
                            if (file.find("..") != std::string::npos) {
                                file = normalizePath(file);
                            }

                            // Store file paths + line numbers and function calls (Call Instructions) in the call instruction map
                            fullCallBaseMap_->insert(std::make_pair(std::make_tuple(path + "/" + file, line), CB)); // absolute path
                        }
                    }
                }
            }
        }
    
    }
    std::cout << "Done Cache" << std::endl;
}

// dirty for debug
// Function to generate a scope-aware name for a global value
static inline std::string getScopeName(const llvm::GlobalValue *GV) {
  // If this global value is globally accessible (isExternalLinkage)
  if (llvm::GlobalValue::isExternalLinkage(GV->getLinkage()))
    // Return its name directly
    return GV->getName().str();
  else {
    // Otherwise, extract module name (without path and extension) from the global value's parent module
    llvm::StringRef moduleName =
        llvm::sys::path::stem(GV->getParent()->getModuleIdentifier());
    // Return a scoped name, e.g. : _ModuleName.GlobalValueName
    return "_" + moduleName.str() + "." + GV->getName().str();
  }
}

// Function to print all recorded caller functions and their corresponding call instructions to LLVM err stream
void Slicing::dumpCallers() {
  RES_REPORT("\n[dumpCallers]\n");
  for (auto M : Ctx_->Callers) {
    Function *F = M.first;
    CallBaseSet &CBS = M.second;
    RES_REPORT("F : " << getScopeName(F) << "\n");

    for (CallBase *CB : CBS) {
      Function *CallerF = CB->getParent()->getParent();
      RES_REPORT("\t");
      if (CallerF && CallerF->hasName()) {
        RES_REPORT("(" << getScopeName(CallerF) << ") ");
      } else {
        RES_REPORT("(anonymous) ");
      }

      RES_REPORT(*CB << "\n");
    }
  }
  RES_REPORT("\n[End of dumpCallers]\n");
}

// Function to normalize file paths 
std::string Slicing::normalizePath(const std::string& pathStr) {
    // Store valid path components
    std::vector<std::string> components;
    std::stringstream ss(pathStr);
    std::string component;

    // Split the path by '/'
    while (std::getline(ss, component, '/')) {
        if (component == "..") {
            // If path contains a component of "..", remove the last valid component
            // e.g. /home/user/../docs/./file.txt becomes /home/docs/file.txt
            if (!components.empty()) {
                components.pop_back();
            }
        } else if (component != "." && !component.empty()) {
            // Ignore '.' and empty components
            // e.g. /usr//local/./bin becomes /usr/local/bin
            components.push_back(component);
        }
    }

    // Reconstruct normalized path
    std::string normalizedPath;
    for (const auto& comp : components) {
        normalizedPath += comp + "/";
    }

    // Preserve leading slash for absolute paths
    if (!pathStr.empty() && pathStr.front() == '/') {
        normalizedPath = "/" + normalizedPath;
    }
    // Remove the trailing slash
    return normalizedPath.substr(0, normalizedPath.size() - 1);
}

// Function to reset all stored slicing data before a new slicing analysis (When multi target pairs from KAMain.cc is used)
void Slicing::clear() {
    visitedF_.clear();
    verboseF_.clear();
    visitedBB_.clear();
    fVisitedF_.clear();
    verboseBB_.clear();
    slicedFuncCnt_ = 1;
    return;
}
