/*
 * Call graph construction
 *
 * Copyright (C) 2012 Xi Wang, Haogang Chen, Nickolai Zeldovich
 * Copyright (C) 2015 - 2016 Chengyu Song
 * Copyright (C) 2016 Kangjie Lu
 *
 * For licensing details see LICENSE
 */

#include <llvm/ADT/StringExtras.h>
#include <llvm/Analysis/CallGraph.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DebugInfo.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Module.h>
#include <llvm/Pass.h>
#include <llvm/Support/Debug.h>
#include "llvm/Support/FileSystem.h"

#include "Annotation.h"
#include "CallGraph.h"

#define TYPE_BASED

using namespace llvm;

// Function to find function definitions rather than declarations
Function *CallGraphPass::getFuncDef(Function *F) {
  FuncMap::iterator it = Ctx->Funcs.find(getScopeName(F));
  if (it != Ctx->Funcs.end())
    // If exists, return its definition
    return it->second;
  else
    return F;
}

// Function to compare if two types are compatible (matching)
bool CallGraphPass::isCompatibleType(Type *T1, Type *T2) {
  // Compare pointer types
  if (T1->isPointerTy()) {
    if (!T2->isPointerTy())
      return false;

    // Retrieve types of elements pointed
    Type *ElT1 = T1->getPointerElementType();
    Type *ElT2 = T2->getPointerElementType();
    // assume "void *" and "char *" are equivalent to any pointer type
    if (ElT1->isIntegerTy(8) /*|| ElT2->isIntegerTy(8)*/)
      return true;

    // Recursively compare the types of elements pointed
    return isCompatibleType(ElT1, ElT2);

  // Compare array types
  } else if (T1->isArrayTy()) {
    if (!T2->isArrayTy())
      return false;

    // Retrieve types of the array
    Type *ElT1 = T1->getArrayElementType();
    Type *ElT2 = T2->getArrayElementType();

    // Recursively compare the two array types
    return isCompatibleType(ElT1, ElT1);

  // Compare integer types
  } else if (T1->isIntegerTy()) {
    // assume pointer can be cased to the address space size
    if (T2->isPointerTy() &&
        T1->getIntegerBitWidth() == T2->getPointerAddressSpace())
      return true;

    // assume all integer type are compatible
    if (T2->isIntegerTy())
      return true;
    else
      return false;

  // Compare struct types
  } else if (T1->isStructTy()) {
    StructType *ST1 = cast<StructType>(T1);
    StructType *ST2 = dyn_cast<StructType>(T2);
    if (!ST2)
      return false;

    // literal has to be equal
    if (ST1->isLiteral() != ST2->isLiteral())
      return false;

    // literal, compare content
    if (ST1->isLiteral()) {
      // Check number of elements in struct
      unsigned numEl1 = ST1->getNumElements();
      if (numEl1 != ST2->getNumElements())
        return false;

      // Check the type of each element instruct
      for (unsigned i = 0; i < numEl1; ++i) {
        if (!isCompatibleType(ST1->getElementType(i), ST2->getElementType(i)))
          return false;
      }
      return true;
    }

    // not literal, use name?
    return ST1->getStructName().equals(ST2->getStructName());

  // Compare function types
  } else if (T1->isFunctionTy()) {
    FunctionType *FT1 = cast<FunctionType>(T1);
    FunctionType *FT2 = dyn_cast<FunctionType>(T2);
    if (!FT2)
      return false;

    // Check function return types
    if (!isCompatibleType(FT1->getReturnType(), FT2->getReturnType()))
      return false;

    // If both have variable number of arguments, assume they are compatible
    if (FT1->isVarArg()) {
      if (FT2->isVarArg())
        return true;
      else
        return false;
    }

    // Check number of parameters and types of each parameter
    unsigned numParam1 = FT1->getNumParams();
    if (numParam1 != FT2->getNumParams())
      return false;

    for (unsigned i = 0; i < numParam1; ++i) {
      if (!isCompatibleType(FT1->getParamType(i), FT2->getParamType(i)))
        return false;
    }
    return true;

  // Only check if type IDs are identical, no need to compare other misc types
  } else {
    return T1->getTypeID() == T2->getTypeID();
  }
}

// Function to find callees for indirect calls, function pointers etc., by type compatibility
bool CallGraphPass::findCalleesByType(CallBase *CB, FuncSet &FS) {

  // Iterate over all functions that are ever used indirectly, reducing FP
  for (Function *F : Ctx->AddressTakenFuncs) {

    // Only compare known args
    if (F->getFunctionType()->isVarArg()) {
    } else if (F->arg_size() != CB->arg_size()) {
      continue;
    } else if (!isCompatibleType(F->getReturnType(), CB->getType())) {
      continue;
    }

    // Skip LLVM intrinsic functions
    if (F->isIntrinsic()) {
      continue;
    }

    // Iterate over all parameters and compare the types of each parameter
    bool Matched = true;
    User::op_iterator AI = CB->arg_begin();
    for (Function::arg_iterator FI = F->arg_begin(), FE = F->arg_end();
         FI != FE; ++FI, ++AI) {
      // Check type mis-match
      Type *FormalTy = FI->getType();
      Type *ActualTy = (*AI)->getType();

      if (isCompatibleType(FormalTy, ActualTy))
        continue;
      else {
        Matched = false;
        break;
      }
    }

    // Insert to provided FuncSet (Set of all callee functions)
    if (Matched)
      FS.insert(F);
  }

  // Always return false, see findCallees and runOnFunction for details
  return false;
}

// Function to merge functions with associated with a specific symbolic identifier into a target function set
bool CallGraphPass::mergeFuncSet(FuncSet &S, const std::string &Id,
                                 bool InsertEmpty) {
  // Find the function set associated with the ID
  FuncPtrMap::iterator i = Ctx->FuncPtrs.find(Id);
  // If it exists, merge it into the target set
  if (i != Ctx->FuncPtrs.end())
    return mergeFuncSet(S, i->second);
  // Otherwise make an empty entry for the ID if needed
  else if (InsertEmpty)
    Ctx->FuncPtrs.insert(std::make_pair(Id, FuncSet()));
  return false;
}

// Function to merge target function set into the set associated with the ID
bool CallGraphPass::mergeFuncSet(std::string &Id, const FuncSet &S,
                                 bool InsertEmpty) {
// Find the function set associated with the ID
  FuncPtrMap::iterator i = Ctx->FuncPtrs.find(Id);
  // If it exists, merge the target set into it
  if (i != Ctx->FuncPtrs.end())
    return mergeFuncSet(i->second, S);
  // Otherwise if it does not exist, and the target set is not empty
  // Create a new entry of the target set for the function set associated with the ID
  else if (!S.empty())
    return mergeFuncSet(Ctx->FuncPtrs[Id], S);
  // If it does not exist and the target set is empty
  // Make an empty entry for the ID if needed
  else if (InsertEmpty)
    Ctx->FuncPtrs.insert(std::make_pair(Id, FuncSet()));
  return false;
}

// Function to merge a source function set into destination function set
bool CallGraphPass::mergeFuncSet(FuncSet &Dst, const FuncSet &Src) {
  bool Changed = false;
  // Loop through all elements of the source function set
  for (FuncSet::const_iterator i = Src.begin(), e = Src.end(); i != e; ++i) {
    assert(*i);
    // If there is at least one that has not been in destionation function set, return true
    Changed |= Dst.insert(*i).second;
  }

  // Otherwise, return false
  return Changed;
}

// Helper Function to resolve function pointers
bool CallGraphPass::findFunctions(Value *V, FuncSet &S) {
  // Initialize a visited set to avoid cycles
  SmallPtrSet<Value *, 4> Visited;
  // Calls findFunctions recursively with this visited set
  return findFunctions(V, S, Visited);
}

// Function to recursively collect functions into S that V (function pointer) could reference
bool CallGraphPass::findFunctions(Value *V, FuncSet &S,
                                  SmallPtrSet<Value *, 4> Visited) {
  // Skip if visited
  if (!Visited.insert(V).second)
    return false;

  // If V casts to a real function
  if (Function *F = dyn_cast<Function>(V)) {
    // Prefer the real definition to declarations
    F = getFuncDef(F);
    // S = S + {F}
    return S.insert(F).second;
  }

  // If V casts to a bitcast operation, ignore the cast
  if (CastInst *B = dyn_cast<CastInst>(V))
    // Recursively call findFunctions with the original value (function pointer)
    return findFunctions(B->getOperand(0), S, Visited);

  // If V casts to a constant that is a bitcast operation, ignore the cast
  if (ConstantExpr *C = dyn_cast<ConstantExpr>(V)) {
    if (C->isCast()) {
        // Recursively call findFunctions with the original value (function pointer)
      return findFunctions(C->getOperand(0), S, Visited);
    }
    // FIXME GEP
  }

  // If V casts to a pointer element access operation, skip
  if (GetElementPtrInst *G = dyn_cast<GetElementPtrInst>(V)) {
    return false;
  // Also skip if V is a aggregated type value extraction operation
  } else if (isa<ExtractValueInst>(V)) {
    return false;
  }

  // If V is an allocation operation, skip
  if (isa<AllocaInst>(V)) {
    return false;
  }

  // If V casts to a binary operator
  if (BinaryOperator *BO = dyn_cast<BinaryOperator>(V)) {
    Value *op0 = BO->getOperand(0);
    Value *op1 = BO->getOperand(1);
    // Only second operand is a constant type
    if (!isa<Constant>(op0) && isa<Constant>(op1))
      // Recursively call findFunctions with the first operand
      return findFunctions(op0, S, Visited);
    // Only first operand is a constant type
    else if (isa<Constant>(op0) && !isa<Constant>(op1))
      // Recursively call findFunctions with the second operand
      return findFunctions(op1, S, Visited);
    else
      return false;
  }

  // If V casts to a PHI node
  if (PHINode *P = dyn_cast<PHINode>(V)) {
    bool Changed = false;
    // Loop over all incoming values and recursively call findFunctions with each value's function pointer
    for (unsigned i = 0; i != P->getNumIncomingValues(); ++i)
      Changed |= findFunctions(P->getIncomingValue(i), S, Visited);
    // Return true if at least one recursive call returns true
    return Changed;
  }

  // If V casts to a Select Instruction
  if (SelectInst *SI = dyn_cast<SelectInst>(V)) {
    bool Changed = false;
    // Recursively call findFunctions with both true and false path
    Changed |= findFunctions(SI->getTrueValue(), S, Visited);
    Changed |= findFunctions(SI->getFalseValue(), S, Visited);
    return Changed;
  }

  // If V casts to an argument
  if (Argument *A = dyn_cast<Argument>(V)) {
    // If the argument is function pointer type, need to insert empty set
    bool InsertEmpty = isFunctionPointer(A->getType());
    // S = S + FuncPtrs[arg.ID]
    return mergeFuncSet(S, getArgId(A), InsertEmpty);
  }

  // If V casts to a return value 
  if (CallInst *CI = dyn_cast<CallInst>(V)) {
    // Update callsite info first
    FuncSet &FS = Ctx->Callees[CI];
    // FS.setCallerInfo(CI, &Ctx->Callers);

    // Recursively call findFunctions with the callee function
    findFunctions(CI->getCalledFunction(), FS);
    bool Changed = false;
    // Loop over all functions in the set of all functions CI might invoke
    for (Function *CF : FS) {
      // If the argument is function pointer type, need to insert empty set
      bool InsertEmpty = isFunctionPointer(CI->getType());
      // S = S + FuncPtrs[ret.ID]
      Changed |= mergeFuncSet(S, getRetId(CF), InsertEmpty);
    }
    return Changed;
  }

  // If V casts to a load instruction 
  if (LoadInst *L = dyn_cast<LoadInst>(V)) {
    std::string Id = getLoadId(L);
    // If the load has an ID
    if (!Id.empty()) {
      // If the load is function pointer type, need to insert empty set
      bool InsertEmpty = isFunctionPointer(L->getType());
      // S = S + FuncPtrs[struct.ID]
      return mergeFuncSet(S, Id, InsertEmpty);

    // Redundant code?
    } else {
      Function *f = L->getParent()->getParent();
      return false;
    }
  }

  // Ignore other constant (usually null), inline asm and inttoptr
  if (isa<Constant>(V) || isa<InlineAsm>(V) || isa<IntToPtrInst>(V))
    return false;

  return false;
}

// Function to find callee functions a call instruction invokes
bool CallGraphPass::findCallees(CallBase *CB, FuncSet &FS) {
  Function *CF = CB->getCalledFunction();
  // If callee is a real function 
  if (CF) {
    // Prefer the real definition to declarations
    CF = getFuncDef(CF);
    // S = S + {F}
    return FS.insert(CF).second;
  }

  // Save called values for point-to analysis
  Ctx->IndirectCallInsts.push_back(CB);

#ifdef TYPE_BASED
  // Use type matching to concervatively find possible targets of indirect call
  return findCalleesByType(CB, FS);
#else
  // use Assignments based approach to find possible targets
  return findFunctions(CB->getCalledFunction(), FS);
#endif
}



/************************************ Workflow Breakdown *************************************
1. doInitialization	    Preprocess global data (e.g., function pointers in global variables).
2. runOnFunction	    Analyze individual functions to resolve call sites (direct/indirect).
3. doModulePass	        Iteratively process all functions in a module until no changes occur.
4. doFinalization	    Postprocess data to finalize bidirectional caller-callee mappings.
*********************************************************************************************/


// Function to find all callee functions of a target function
bool CallGraphPass::runOnFunction(Function *F) {

  // Lewis: we don't give a shit to functions in .init.text
  // Skip
  if (F->hasSection() && F->getSection().str() == ".init.text")
    return false;
  bool Changed = false;

  // Loop over all instructions in a function
  for (inst_iterator i = inst_begin(F), e = inst_end(F); i != e; ++i) {
    Instruction *I = &*i;

    // Map callsite to possible callees
    if (auto *CB = dyn_cast<CallBase>(I)) {

      // Ignore inline asm or intrinsic calls
      if (CB->isInlineAsm() ||
          (CB->getCalledFunction() && CB->getCalledFunction()->isIntrinsic()))
        continue;

      // Might be an indirect call, find all possible callees
      FuncSet &FS = Ctx->Callees[CB];
      if (!findCallees(CB, FS))
        continue;

// Since TYPE_BASED is defined, ignore
#ifndef TYPE_BASED
      // looking for function pointer arguments
      for (unsigned no = 0, ne = CI->getNumOperands() - 1; no != ne; ++no) {
        Value *V = CI->getArgOperand(no);
        if (!isFunctionPointerOrVoid(V->getType()))
          continue;

        // find all possible assignments to the argument
        FuncSet VS;
        if (!findFunctions(V, VS))
          continue;

        // update argument FP-set for possible callees
        for (Function *CF : FS) {
          if (!CF) {
            WARNING("NULL Function " << *CI << "\n");
            assert(0);
          }
          std::string Id = getArgId(CF, no);
          Changed |= mergeFuncSet(Ctx->FuncPtrs[Id], VS);
        }
      }
#endif
    }
#ifndef TYPE_BASED
    if (StoreInst *SI = dyn_cast<StoreInst>(I)) {
      // stores to function pointers
      Value *V = SI->getValueOperand();
      if (isFunctionPointerOrVoid(V->getType())) {
        std::string Id = getStoreId(SI);
        if (!Id.empty()) {
          FuncSet FS;
          findFunctions(V, FS);
          Changed |= mergeFuncSet(Id, FS, isFunctionPointer(V->getType()));
        } else {
        }
      }
    } else if (ReturnInst *RI = dyn_cast<ReturnInst>(I)) {
      // function returns
      if (isFunctionPointerOrVoid(F->getReturnType())) {
        Value *V = RI->getReturnValue();
        std::string Id = getRetId(F);
        FuncSet FS;
        findFunctions(V, FS);
        Changed |= mergeFuncSet(Id, FS, isFunctionPointer(V->getType()));
      }
    }
#endif
  }

  return Changed;
}

// Function to collect function pointer assignments in global initializers
void CallGraphPass::processInitializers(Module *M, Constant *C, GlobalValue *V,
                                        std::string Id) {
  // If C casts to structs
  if (ConstantStruct *CS = dyn_cast<ConstantStruct>(C)) {
    StructType *STy = CS->getType();

    // If struct does not have name, provided ID is empty, and V is not null
    if (!STy->hasName() && Id.empty()) {
      if (V != nullptr)
        Id = getVarId(V);
      else
        Id = "bullshit"; // Lewis: quick fix for V is nullptr
    }

    // Loop over all elements of the struct
    for (unsigned i = 0; i != STy->getNumElements(); ++i) {
      // Retrieve the type of each element
      Type *ETy = STy->getElementType(i);

      // If it's a struct
      if (ETy->isStructTy()) {
        // Assign a new ID
        std::string new_id;
        if (Id.empty())
          new_id = STy->getStructName().str() + "," + std::to_string(i);
        else
          new_id = Id + "," + std::to_string(i);
        // Recursively call processInitializers with this element and its new ID
        processInitializers(M, CS->getOperand(i), NULL, new_id);

      // If it is an array
      } else if (ETy->isArrayTy()) {
        // Nested array of struct
        // Recursively call processInitializers with this element
        processInitializers(M, CS->getOperand(i), NULL, "");

      // If it is a function pointer
      } else if (isFunctionPointer(ETy)) {
        // Found function pointers in struct fields
        if (Function *F = dyn_cast<Function>(CS->getOperand(i))) {
          // Assign a new ID
          std::string new_id;
          if (!STy->isLiteral()) {
            if (STy->getStructName().startswith("struct.anon.") ||
                STy->getStructName().startswith("union.anon")) {
              if (Id.empty())
                new_id = getStructId(STy, M, i);
            } else {
              new_id = getStructId(STy, M, i);
            }
          }
          if (new_id.empty()) {
            assert(!Id.empty());
            new_id = Id + "," + std::to_string(i);
          }
          // Populate set of function pointers with its definition
          Ctx->FuncPtrs[new_id].insert(getFuncDef(F));
        }
      }
    }
  
  // If C casts to arrays
  } else if (ConstantArray *CA = dyn_cast<ConstantArray>(C)) {
    // Array, conservatively collects all possible pointers
    for (unsigned i = 0; i != CA->getNumOperands(); ++i)
      processInitializers(M, CA->getOperand(i), V, Id);
  } else if (Function *F = dyn_cast<Function>(C)) {
    // Global function pointer variables
    if (V) {
      std::string Id = getVarId(V);
      // Populate set of function pointers with its new definition
      Ctx->FuncPtrs[Id].insert(getFuncDef(F));
    }
  }
}

// Function to initialize the module by collecting function pointer assignments and functions
bool CallGraphPass::doInitialization(Module *M) {

  KA_LOGS(1, "[+] Initializing " << M->getModuleIdentifier());
  // Collect function pointer assignments in global initializers
  for (GlobalVariable &G : M->globals()) {
    if (G.hasInitializer())
      processInitializers(M, G.getInitializer(), &G, "");
  }

  for (Function &F : *M) {
    // Lewis: we don't give a shit to functions in .init.text
    if (F.hasSection() && F.getSection().str() == ".init.text")
      continue;
    // Collect address-taken functions
    if (F.hasAddressTaken())
      Ctx->AddressTakenFuncs.insert(&F);
  }

  return false;
}

// Function to finalise the module by establishing caller callee relationship
bool CallGraphPass::doFinalization(Module *M) {

  // Update callee and caller mapping

  // Loop over all functions in the module
  for (Function &F : *M) {
    // Loop over all instructions in the function
    for (inst_iterator i = inst_begin(F), e = inst_end(F); i != e; ++i) {
      // Map callsite to possible callees
      if (auto *CB = dyn_cast<CallBase>(&*i)) {
        // Filter out llvm debug
        if (isa<DbgInfoIntrinsic>(CB))
          continue;

        // Retrieve all callee functions invoked by the call instruction
        FuncSet &FS = Ctx->Callees[CB];
        // Loop over all such callee functions
        for (Function *CF : FS) {
          // Link the call instruction to the caller function
          // Ctx->Callers[F] == Set of call sites (Call Instruction) that calls F
          // Ctx->Callees[CI] == Set of functions that CI calls
          CallBaseSet &CBS = Ctx->Callers[CF];
          CBS.insert(CB);
        }
      }
    }
  }

  return false;
}

// Function to find callee functions of all functions in a given module
bool CallGraphPass::doModulePass(Module *M) {
  bool Changed = true, ret = false;
  // Loop until no changes occur
  while (Changed) {
    Changed = false;
    for (Function &F : *M)
      Changed |= runOnFunction(&F);
    ret |= Changed;
  }
  // If the module has changed, return true and false otherwise
  return ret;
}

// Debug function to dump all function pointers
void CallGraphPass::dumpFuncPtrs() {
  raw_ostream &OS = outs();
  for (FuncPtrMap::iterator i = Ctx->FuncPtrs.begin(), e = Ctx->FuncPtrs.end();
       i != e; ++i) {
    OS << i->first << "\n";
    FuncSet &v = i->second;
    for (FuncSet::iterator j = v.begin(), ej = v.end(); j != ej; ++j) {
      OS << "  " << ((*j)->hasInternalLinkage() ? "f" : "F") << " "
         << (*j)->getName().str() << "\n";
    }
  }
}

// Function to dump callee functions, deprecated. Use dumpCallers()
void CallGraphPass::dumpCallees() {
  // RES_REPORT("\n[dumpCallees]\n");
  raw_ostream &OS = outs();
  std::string outString;
  std::string callerInfo,calleeInfo;
  bool directCall = false;
  std::error_code EC;
  llvm::raw_fd_ostream outputFile("deprecated", EC, llvm::sys::fs::OF_Text);
  OS << "Num of Callees: " << Ctx->Callees.size() << "\n";


  // Loop over all callees
  for (CalleeMap::iterator i = Ctx->Callees.begin(), e = Ctx->Callees.end();
       i != e; ++i) {

    // Retrieve both the call site that invokes the callee function and the callee functions
    CallBase *CB = i->first;
    FuncSet &v = i->second;
    // only dump indirect call?
    
    // If call site is inline ASM, called function exists or callee function set exists 
    if (CB->isInlineAsm() || CB->getCalledFunction() || v.empty())
      directCall = true;

    // Retrieve enclosing function of the callsite
    Function *F = CB->getParent()->getParent();
    // Retrieve callsite line number
    auto loc = CB->getDebugLoc();
    if (loc) {
      if (loc->getLine() == 0) {
        continue;
      }
    }

    // Loop over all callee functions and output for each
    v = Ctx->Callees[CB];
    for (FuncSet::iterator j = v.begin(), ej = v.end(); j != ej; ++j) {
      llvm::DISubprogram *SP = F->getSubprogram();
      if (SP) {
        calleeInfo = SP->getFilename().str() + ":" + std::to_string(SP->getLine());
        if (!callerInfo.empty() && !calleeInfo.empty()) {
          outString += callerInfo + ":" + calleeInfo + ":" + (directCall ? "1" : "0") + "\n";
        }
      }
    }
  }

  // OS << outString;
  outputFile << outString;
  outputFile.close();
  // RES_REPORT("\n[End of dumpCallees]\n");
}

// Function to dump caller functions
void CallGraphPass::dumpCallers(const char* srcRoot) {

  std::string prefix(srcRoot);
  std::error_code EC;
  llvm::raw_fd_ostream outputFile(callGraphOutputFile, EC, llvm::sys::fs::OF_Text);
  std::string outString;
  std::string callerInfo,calleeInfo;
  bool directCall = false;

  auto getLocation = [this](const DebugLoc & loc, Function* F, bool directCall) {
    int lineNumber = loc->getLine();
    std::string file = loc->getFilename().str();
    if (file.find("..") != std::string::npos) {
      file = normalizePath(file);
    }
    std::string path = loc->getDirectory().str();
    return path + "/" + file + ":" + std::to_string(lineNumber);
  };

  // RES_REPORT("\n[dumpCallers]\n");

  // Loop over all callees
  for (auto M : Ctx->Callers) {

    // Retrieve both all call sites that invokes the caller function and the caller function
    Function *F = M.first;
    CallBaseSet &CBS = M.second;

    // Retrieve callee info
    DISubprogram *SP = F->getSubprogram();
    if (SP) {
      std::string filename = SP->getFilename().str();
      if (filename.find("..") != std::string::npos) {
        filename = normalizePath(filename);
      }
      calleeInfo = SP->getDirectory().str() + "/" + filename + ":" + std::to_string(SP->getLine());
    }
    
    // Loop over all call sites for the current function
    for (CallBase *CB : CBS) {
      // Retrieve caller info
      auto loc = CB->getDebugLoc();
      if (loc) {
        if (loc->getLine() == 0) {
          continue;
        }
        callerInfo = getLocation(loc,F,true);
        if (!callerInfo.empty() && !calleeInfo.empty()) {
          if (CB->isInlineAsm() || CB->getCalledFunction() || Ctx->Callees[CB].empty())
            directCall = true;
          else
            directCall = false;
          // Output format: Caller file : Caller line number : Callee file : Callee line number : 1/0 (direct/indirect call)
          outString += callerInfo + ":" + calleeInfo + ":" + (directCall ? "1" : "0") + "\n";
        }
      }
    }
  }
  // RES_REPORT("\n[End of dumpCallers]\n");
  
  outputFile << outString;
  outputFile.close();
}

// Function to normalize path
std::string CallGraphPass::normalizePath(const std::string& pathStr) {
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
