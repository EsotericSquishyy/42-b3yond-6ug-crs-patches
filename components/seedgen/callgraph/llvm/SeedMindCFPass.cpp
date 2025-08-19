// Wenxuan Shi <wenxuan.shi@northwestern.edu>
// 2024, Northwestern University. All rights reserved.

#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Module.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include <llvm/IR/PassManager.h>
#include <llvm/Passes/OptimizationLevel.h>
#include <llvm/Support/Compiler.h>

using namespace llvm;

bool should_skip(const Function *func) {
  if (llvm::DISubprogram *SP = func->getSubprogram()) {
    std::string Filename = SP->getFilename().str();
    std::string Directory = SP->getDirectory().str();
    std::string FullPath =
        Directory.empty() ? Filename : Directory + "/" + Filename;
    return FullPath.compare(0, 4, "/usr") == 0;
  }
  return false;
}

class SeedMindCFPass : public PassInfoMixin<SeedMindCFPass> {
public:
  static char ID;
  explicit SeedMindCFPass() {}
  static bool isRequired() { return true; }

  PreservedAnalyses run(Module &M, ModuleAnalysisManager &AM) {

    // we don't care about the function type of caller and callee, we just
    // need the function pointer, so we can just use void * as the function
    // pointer type
    FunctionCallee hookFunc = M.getOrInsertFunction(
        "__seedmind_record_func_call",
        FunctionType::get(
            Type::getVoidTy(M.getContext()),
            {PointerType::get(
                 FunctionType::get(Type::getVoidTy(M.getContext()), {}, false),
                 0),
             PointerType::get(
                 FunctionType::get(Type::getVoidTy(M.getContext()), {}, false),
                 0)},
            false));

    for (auto &F : M.functions()) {
      if (should_skip(&F)) {
        continue;
      }

      for (auto &BB : F) {
        for (auto &I : BB) {
          if (auto *callBase = dyn_cast<CallBase>(&I)) {
            Value *callee = nullptr;
            if (callBase->isIndirectCall()) {
              callee = callBase->getCalledOperand();
            } else {
              Function *calleeFunc = callBase->getCalledFunction();
              if (calleeFunc == nullptr || callBase->isInlineAsm()
                  || calleeFunc->isIntrinsic() || should_skip(calleeFunc)) {
                continue;
              }
              callee = calleeFunc;
            }
            Function *caller = callBase->getCaller();
            // inject the call to the hook function, with caller and callee
            IRBuilder<> Builder(callBase);
            Builder.CreateCall(hookFunc, {caller, callee});
          }
        }
      }
    }

    return PreservedAnalyses::all();
  };
};

extern "C" ::llvm::PassPluginLibraryInfo LLVM_ATTRIBUTE_WEAK
llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "SeedMindCFPass", LLVM_VERSION_STRING,
          [](PassBuilder &PB) {
            PB.registerOptimizerLastEPCallback(
                [](ModulePassManager &MPM, OptimizationLevel Level) {
                  MPM.addPass(SeedMindCFPass());
                });
          }};
}