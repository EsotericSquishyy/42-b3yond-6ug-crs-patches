#ifndef SLICING_H
#define SLICING_H

#include "Common.h"
#include "GlobalCtx.h"

#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <queue>
#include <map>
// #include <thread>
// #include <shared_mutex>

using namespace llvm;

class Slicing {

private:
  GlobalContext *Ctx_;
  // int slicedFuncCnt_;
  std::string srcRoot_;
  std::map<std::tuple<std::string, int>, Function*> *fullFuncMap_;
  std::map<std::tuple<std::string, int>, CallBase*> *fullCallBaseMap_;
  std::set<std::string> *fullFunc_;

public:
  Slicing(GlobalContext *Ctx, std::string srcRoot) {
    Ctx_ = Ctx;
    slicedFuncCnt_ = 1;
    srcRoot_ = srcRoot;
  }
  int slicedFuncCnt_; // tmp
  std::set<Function*> visitedF_; // if reuse, need to clear
  std::set<Function*> verboseF_; // function by verbose method
  std::set<BasicBlock*> visitedBB_; // if reuse, need to clear
  std::set<Function*> fVisitedF_; // if reuse, need to clear
  std::set<BasicBlock*> verboseBB_;
  void slicing(char *funcName);
  void sliceFunction(Function *F);
  void addToVerbose(Function *F);
  bool intraCanReach(BasicBlock *src, BasicBlock *dst);
  void backtracking(BasicBlock *BB);
  void forwardSlicingFunctionWithDepth(Function* F, int depth, std::set<Function*> *visited);
  void forwardSlicingFunction(Function* F);
  void forwardSlicingFunctionStub(std::string funcName);
  BasicBlock *findTargetByLine(const char *fileName, int line);
  Function *findTargetByFunctionName(const char *fileName, const char *funcName);
  Function *findFunctionByLine(const char *fileName, int line);
  CallInst *findCallInstByLine(const char *fileName, int line);
  void updateCallersfromDisk(std::string srcRoot);
  void dump(std::string Output, std::string file, std::string funcName);
  int funcCount();
  void dumpCallers();
  void cacheAllLLVMObjects();
  std::string normalizePath(const std::string& pathStr);
  void clear();
};

#endif
