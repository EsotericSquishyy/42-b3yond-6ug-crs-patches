/*
 * main function
 *
 * Copyright (C) 2012 Xi Wang, Haogang Chen, Nickolai Zeldovich
 * Copyright (C) 2015 Byoungyoung Lee
 * Copyright (C) 2015 - 2019 Chengyu Song
 * Copyright (C) 2016 Kangjie Lu
 * Copyright (C) 2019 Yueqi Chen
 *
 * For licensing details see LICENSE
 */

#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/Support/FileSystem.h>
#include <llvm/Support/ManagedStatic.h>
#include <llvm/Support/Path.h>
#include <llvm/Support/PrettyStackTrace.h>
#include <llvm/Support/Signals.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/SystemUtils.h>
#include <llvm/Support/ToolOutputFile.h>
#include "llvm/Support/raw_ostream.h"

#include <fstream>
#include <memory>
#include <sstream>
#include <sys/resource.h>
#include <vector>
#include <chrono>
#include <iomanip>

#include "Slicing.h"
#include "CallGraph.h"
#include "GlobalCtx.h"

using namespace llvm;

cl::list<std::string> InputFilenames(cl::Positional, cl::OneOrMore,
                                     cl::desc("<input bitcode files>"));

cl::opt<unsigned>
    VerboseLevel("debug-verbose",
                 cl::desc("Print information about actions taken"),
                 cl::init(0));

cl::opt<std::string>
    StructAlloc("struct", cl::desc("locate the allocation site of structure"),
                cl::NotHidden, cl::init(""));


cl::opt<std::string> TargetName("file",
                                  cl::desc("set target file name"),
                                  cl::NotHidden, cl::init(""));

cl::opt<std::string> SrcRoot("srcroot",
                                  cl::desc("set target source root directory "),
                                  cl::NotHidden, cl::init(""));

cl::opt<bool> CallGraph("callgraph",
                                  cl::desc("set call graph analysis option"),
                                  cl::NotHidden, cl::init(false));

cl::opt<bool> ProgramSlicing("slicing",
                                  cl::desc("set program slicing option"),
                                  cl::NotHidden, cl::init(false));

cl::opt<int> TargetLine("line",
                                  cl::desc("set target line number"),
                                  cl::NotHidden, cl::init(0));

cl::opt<std::string> TargetFunc("func",
                                  cl::desc("set target function name"),
                                  cl::NotHidden, cl::init(""));

cl::opt<std::string> MultiTargetPairsConfig("multi",
                                  cl::desc("set multi-target pairs config file"),
                                  cl::NotHidden, cl::init(""));

cl::opt<std::string> OutputPath("output",
                                  cl::desc("set output path"),
                                  cl::NotHidden, cl::init(""));
GlobalContext GlobalCtx;

void IterativeModulePass::run(ModuleList &modules) {

  ModuleList::iterator i, e;

  KA_LOGS(3, "[" << ID << "] Initializing " << modules.size() << " modules.");
  
  // Initialize all modules
  bool again = true;
  while (again) {
    again = false;
    for (i = modules.begin(), e = modules.end(); i != e; ++i) {
      KA_LOGS(3, "[" << i->second << "]");
      again |= doInitialization(i->first);
    }
  }

  KA_LOGS(3, "[" << ID << "] Processing " << modules.size() << " modules.");

  // Process modules iteratively until no further changes occur
  unsigned iter = 0, changed = 1;
  while (changed) {
    ++iter;
    changed = 0;
    for (i = modules.begin(), e = modules.end(); i != e; ++i) {
      KA_LOGS(3, "[" << ID << " / " << iter << "] ");
      // FIXME: Seems the module name is incorrect, and perhaps it's a bug.
      KA_LOGS(3, "[" << i->second << "]");

      // Check if module is changed
      bool ret = doModulePass(i->first);
      if (ret) {
        ++changed;
        KA_LOGS(3, "\t [CHANGED]");
      } else {
        KA_LOGS(3, " ");
      }
    }
    KA_LOGS(3, "[" << ID << "] Updated in " << changed << " modules.");
  }

  KA_LOGS(3, "[" << ID << "] Finalizing " << modules.size() << " modules.");

  // Updates caller callee function mapping
  again = true;
  while (again) {
    again = false;
    for (i = modules.begin(), e = modules.end(); i != e; ++i) {
      again |= doFinalization(i->first);
    }
  }

  KA_LOGS(3, "[" << ID << "] Done!\n");
  return;
}

void doBasicInitialization(Module *M) {

  // collect global object definitions
  for (GlobalVariable &G : M->globals()) {
    if (G.hasExternalLinkage())
      GlobalCtx.Gobjs[G.getName().str()] = &G;
  }

  // collect global function definitions
  for (Function &F : *M) {
    if (F.hasExternalLinkage() && !F.empty()) {
      // external linkage always ends up with the function name
      StringRef FNameRef = F.getName();
      std::string FName = "";
      if (FNameRef.startswith("__sys_"))
        FName = "sys_" + FNameRef.str().substr(6);
      else
        FName = FNameRef.str();
      GlobalCtx.Funcs[FName] = &F;
    }
  }

  return;
}

int main(int argc, char **argv) {

#ifdef SET_STACK_SIZE
  struct rlimit rl;
  if (getrlimit(RLIMIT_STACK, &rl) == 0) {
    rl.rlim_cur = SET_STACK_SIZE;
    setrlimit(RLIMIT_STACK, &rl);
  }
#endif

  // Print a stack trace if we signal out.
#if LLVM_VERSION_MAJOR == 3 && LLVM_VERSION_MINOR < 9
  sys::PrintStackTraceOnErrorSignal();
#else
  sys::PrintStackTraceOnErrorSignal(StringRef());
#endif
  PrettyStackTraceProgram X(argc, argv);

  // Call llvm_shutdown() on exit.
  llvm_shutdown_obj Y;

  // Set up configuration options
  cl::ParseCommandLineOptions(argc, argv, "global analysis");
  SMDiagnostic Err;

  // Validate required arguments
  if (TargetName == "" && MultiTargetPairsConfig == "") {
    errs() << "Please provide the target file name with --file or -multi.\n";
    return -1;
  }
  if (!TargetLine && TargetFunc == "" && MultiTargetPairsConfig == "") {
    errs() << "Please provide the target line number or target func name with --line or --func or -multi.\n";
    return -1;
  }
  if (SrcRoot == "") {
    errs() << "Please provide the target source directory with --srcroot.\n";
    return -1;
  }

  KA_LOGS(0, "Total " << InputFilenames.size() << " file(s)");

  // Load and parse llvm .bc files into llvm modules
  for (unsigned i = 0; i < InputFilenames.size(); ++i) {
    
    // Use separate LLVMContext to avoid type renaming
    KA_LOGS(1, "[" << i << "] " << InputFilenames[i] << "");
    LLVMContext *LLVMCtx = new LLVMContext();
    std::unique_ptr<Module> M = parseIRFile(InputFilenames[i], Err, *LLVMCtx);

    if (M == NULL) {
      errs() << "[-] error loading file '" << InputFilenames[i]
             << "'\n";
      Err.print(argv[0],errs());
      continue;
    }

    // Store parsed module in global context
    Module *Module = M.release();
    StringRef MName = StringRef(strdup(InputFilenames[i].data()));
    GlobalCtx.Modules.push_back(std::make_pair(Module, MName));
    GlobalCtx.ModuleMaps[Module] = InputFilenames[i];

    // Collect global function & object definitions)
    doBasicInitialization(Module);
  }

  // Create total_basicblock file to count all basic blocks in the parsed modules
  std::ifstream bblFile("./total_basicblock");
  if (!bblFile.good()) {
    std::ofstream bblOutfile("./total_basicblock");
    int cnt = 0;
    int func_cnt = 0;
    // count all basic blocks
    for (auto M : GlobalCtx.Modules) {
      for (auto &F : M.first->functions()) {
        func_cnt++;
        for (auto &BB : F) {
          cnt++;
        }
      }
    }
    bblOutfile << cnt << std::endl;
    bblOutfile.close();
    std::cout << "Total function count: " << GlobalCtx.Funcs.size() << std::endl;
    std::cout << "Total function count: " << func_cnt << std::endl;
  }

  std::ostringstream stream;

  // Perform call graph analysis if enabled
  if (CallGraph)
  {
    auto start = std::chrono::high_resolution_clock::now();

    // Create a CallGraphPass instance from the global context
    CallGraphPass CGPass(&GlobalCtx);

    // Process the modules
    CGPass.run(GlobalCtx.Modules);
    auto stop = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(stop - start);
    stream << std::fixed << std::setprecision(2) <<  duration.count()/1000000.0;
    errs() << "Time taken by call graph generation : " << stream.str() << " seconds\n";

    // Output callgraph_result to project sourcefile
    CGPass.dumpCallees();
    CGPass.dumpCallers(SrcRoot.c_str());
  }

  // Perform program slicing if enabled
  if (ProgramSlicing)
  {
    auto start = std::chrono::high_resolution_clock::now();
    Slicing Sl(&GlobalCtx, SrcRoot);

    // Cache all llvm objects for analysis
    Sl.cacheAllLLVMObjects();

    // Slicing works on callgraph
    if(!CallGraph)
    {
      errs() << "Please set callgraph to true!\n";
      return -1;
    }

    int cnt = 0;

    // Handle multi target pairs arguments of target functions
    if (MultiTargetPairsConfig != "") { // format: file funcname
      std::ifstream targets(MultiTargetPairsConfig);
      std::string line;
      int lnum = 0;
      while (std::getline(targets, line)) {
        std::istringstream iss(line);
        std::string file_;
        std::string func_;
        if (std::getline(iss, file_, ' ') &&
            std::getline(iss, func_)) {

              // Find target function by its name
              Function *targetFunc = Sl.findTargetByFunctionName(file_.c_str(), func_.c_str());

              // Skip if target function not found
              if (targetFunc == nullptr) {
                std::cout << "Can't find the targetFunc " << file_.c_str() << ":" << func_.c_str()  << "\n";
                continue;
              }

              // If target function found, retrieve debug info
              else {
                std::cout << lnum++ << " Find the target function: " << file_.c_str() << ":"
                    << targetFunc->getName().str() << ":";
                    if (targetFunc->getSubprogram() != nullptr)
                      std::cout << targetFunc->getSubprogram()->getLine() << "\n";
                    else
                      std::cout << "(No debug info)\n";
              }

              // Backward slicing
              Sl.sliceFunction(targetFunc);
              // additional slice for early termination
              // Forward slicing
              Sl.forwardSlicingFunction(targetFunc);
              Sl.forwardSlicingFunctionStub("LLVMFuzzerInitialize");
              Sl.forwardSlicingFunctionStub("LLVMFuzzerTestOneInput");
              Sl.forwardSlicingFunctionStub("LLVMFuzzerRunDriver");
              // Sl.dump(OutputPath,file_,func_);
              // Sl.clear();
        }
      }
      Sl.dump(OutputPath,"NOT USED","merged");
    }
    
    else {
      Function *targetFunc = nullptr;

      // Find target function by line argument if specified
      if (TargetLine) {
        BasicBlock *targetBB = Sl.findTargetByLine(TargetName.c_str(), TargetLine);
        if (targetBB == nullptr) {
          std::cout << "Can't find the target. Retry with the target function name\n";
          return -1;
        }
        // Backward slice the basic block enclosing target function directly
        Sl.backtracking(targetBB);

        // If line argument not specified, find target function by name
      } else if (TargetFunc != "") {
        targetFunc = Sl.findTargetByFunctionName(TargetName.c_str(), TargetFunc.c_str());
        if (targetFunc == nullptr) {
          std::cout << "Can't find the targetFunc " << TargetName.c_str() << ":" << TargetFunc.c_str()  << "\n";
          return -1;
        }
        else {
          std::cout << "Find the target function: " << TargetName.c_str() << ":"
              << targetFunc->getName().str() << ":";

              // Retrieve debug info
              if (targetFunc->getSubprogram() != nullptr)
                std::cout << targetFunc->getSubprogram()->getLine() << "\n";
              else
                std::cout << "(No debug info)\n";
        }

        // Backward slicing
        Sl.sliceFunction(targetFunc);
        // additional slice for early termination
        // Forward slicing
        Sl.forwardSlicingFunction(targetFunc);
        Sl.forwardSlicingFunctionStub("LLVMFuzzerInitialize");
        Sl.forwardSlicingFunctionStub("LLVMFuzzerTestOneInput");
        Sl.forwardSlicingFunctionStub("LLVMFuzzerRunDriver");
      } else {
        std::cout << "Unreachable\n";
        return -1;
      }

      stream.str("");
      auto stop = std::chrono::high_resolution_clock::now();
      auto duration = std::chrono::duration_cast<std::chrono::microseconds>(stop - start);
      stream << std::fixed << std::setprecision(2) <<  duration.count()/1000000.0;
      std::cout << "Time taken by slice : " << stream.str() << " seconds\n";

      // Output slicing results to user output path
      Sl.dump(OutputPath,TargetName.c_str(),TargetFunc.c_str());
    }

    
  }
  
  return 0;
}
