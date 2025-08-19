#include "clang/Tooling/CommonOptionsParser.h"
#include "clang/Tooling/Tooling.h"
#include "clang/Frontend/FrontendActions.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Rewrite/Core/Rewriter.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Error.h"
#include <iostream>

using namespace clang;
using namespace clang::tooling;
using namespace llvm;

static cl::OptionCategory InjectorCategory("code-injector options");

// Define command-line options for TargetLine and CodeToInject
static cl::opt<unsigned> TargetLineOpt(
    "line",
    cl::desc("Specify the target line number for code injection"),
    cl::value_desc("line number"),
    cl::Required,
    cl::cat(InjectorCategory));

static cl::opt<std::string> CodeToInjectOpt(
    "target",
    cl::desc("Specify the target id to inject"),
    cl::value_desc("target id"),
    cl::Required,
    cl::cat(InjectorCategory));

static cl::opt<std::string> OutputFileOpt(
    "outfile",
    cl::desc("Specify the path to the output file"),
    cl::value_desc("output file"),
    cl::Required,
    cl::cat(InjectorCategory));

class CodeInjectorASTConsumer : public ASTConsumer {
public:
    CodeInjectorASTConsumer(Rewriter &R, unsigned TargetLine, const std::string &CodeToInject)
        : TheRewriter(R), TargetLine(TargetLine), CodeToInject(CodeToInject) {}

    void HandleTranslationUnit(ASTContext &Context) override {
        SourceManager &SM = Context.getSourceManager();
        FileID MainFileID = SM.getMainFileID();
        // Get source location corresponding to the beginning of the target line.
        SourceLocation InjectLoc = SM.translateLineCol(MainFileID, TargetLine, 1);
        while (!InjectLoc.isValid() && TargetLine > 1) {
            llvm::errs() << "Invalid injection location at line " << TargetLine << ", trying previous line\n";
            --TargetLine;
            InjectLoc = SM.translateLineCol(MainFileID, TargetLine, 1);
            // TODO: if reached the beginning of the function, exit.
        }
        // Insert the injection code before the target line.
        TheRewriter.InsertText(InjectLoc, CodeToInject + "\n", /*InsertAfter=*/false, /*IndentNewLines=*/true);
    }

private:
    Rewriter &TheRewriter;
    unsigned TargetLine;
    std::string CodeToInject;
};

class CodeInjectorFrontendAction : public ASTFrontendAction {
public:
    CodeInjectorFrontendAction(unsigned TargetLine, const std::string &CodeToInject)
        : TargetLine(TargetLine), CodeToInject(CodeToInject) {}

    std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &CI, StringRef File) override {
        TheRewriter.setSourceMgr(CI.getSourceManager(), CI.getLangOpts());
        return std::make_unique<CodeInjectorASTConsumer>(TheRewriter, TargetLine, CodeToInject);
    }

    void EndSourceFileAction() override {
        SourceManager &SM = TheRewriter.getSourceMgr();
        // write the modified source code to the output file.
        std::error_code EC;
        llvm::raw_fd_ostream OS(OutputFileOpt, EC, llvm::sys::fs::OF_Text);
        if (EC) {
            llvm::errs() << "Error opening output file: " << EC.message() << "\n";
            return;
        }
        TheRewriter.getEditBuffer(SM.getMainFileID()).write(OS);
    }

private:
    Rewriter TheRewriter;
    unsigned TargetLine;
    std::string CodeToInject;
};

// Custom FrontendActionFactory that passes parameters to CodeInjectorFrontendAction.
class CodeInjectorFrontendActionFactory : public FrontendActionFactory {
public:
    CodeInjectorFrontendActionFactory(unsigned TargetLine, std::string CodeToInject)
        : TargetLine(TargetLine), CodeToInject(std::move(CodeToInject)) {}

    std::unique_ptr<FrontendAction> create() override {
        return std::make_unique<CodeInjectorFrontendAction>(TargetLine, CodeToInject);
    }

private:
    unsigned TargetLine;
    std::string CodeToInject;
};

int main(int argc, const char **argv) {
    auto ExpectedParser = CommonOptionsParser::create(argc, argv, InjectorCategory);
    if (!ExpectedParser) {
        llvm::errs() << "Error parsing options: " 
                     << toString(ExpectedParser.takeError()) << "\n";
        return 1;
    }
    CommonOptionsParser &OptionsParser = ExpectedParser.get();
    ClangTool Tool(OptionsParser.getCompilations(), OptionsParser.getSourcePathList());

    unsigned TargetLine = TargetLineOpt; 
    // std::string CodeToInject = "fprintf(stderr, \"AIXCC_REACH_TARGET_" + CodeToInjectOpt + "\\n\");";
    std::string CodeToInject = "const char* msg=\"AIXCC_REACH_TARGET_" + CodeToInjectOpt + "\\n\"; __asm__ __volatile__(\"mov $1, %%rax; mov $2, %%rdi; mov %[buf], %%rsi; mov $21, %%rdx; syscall\": :[buf] \"r\" (msg) : \"rax\", \"rdi\", \"rsi\", \"rdx\", \"rcx\", \"r11\", \"memory\"); ";
    // Use the custom factory.
    return Tool.run(new CodeInjectorFrontendActionFactory(TargetLine, CodeToInject));
    return 0;
}
