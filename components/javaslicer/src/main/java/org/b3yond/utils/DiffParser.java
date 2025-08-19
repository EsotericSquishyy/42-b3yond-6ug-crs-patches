package org.b3yond.utils;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class DiffParser {
    private static final Pattern DIFF_HEADER_PATTERN = Pattern.compile("^diff --git a/(.+) b/(.+)$");
    private final String diffFilePath;
    private final Path baseDir;
    private final List<String> methodNames = new ArrayList<>();
    // private final List<String> diffContent = new ArrayList<>();

    private static class MethodInfo {
        final String packageName;
        final String className;
        final String methodName;
        final int startLine;
        final int endLine;

        MethodInfo(String packageName, String className, String methodName, int startLine, int endLine) {
            this.packageName = packageName;
            this.className = className;
            this.methodName = methodName;
            this.startLine = startLine;
            this.endLine = endLine;
        }

        String getFullName() {
            String fullClassName = packageName.isEmpty() ? className : packageName + "." + className;
            return fullClassName.isEmpty() ? methodName : fullClassName + "." + methodName;
        }
    }

    private final List<MethodInfo> methodInfos = new ArrayList<>();
    private final Map<String, List<Integer>> diffContentLines = new HashMap<>();
    private String currentFile = "";

    public DiffParser(String diffFilePath) {
        this(diffFilePath, Paths.get("."));
    }

    public DiffParser(String diffFilePath, Path baseDir) {
        this.diffFilePath = diffFilePath;
        this.baseDir = baseDir.toAbsolutePath().normalize();
    }

    public List<String> parse() throws IOException {
        List<String> sourceFiles = loadAndParseDiff();
        for (String sourceFile : sourceFiles) {
            parseJavaFile(sourceFile);
        }
        return filterMethodsByDiffContent(methodNames);
    }

    private List<String> loadAndParseDiff() throws IOException {
        List<String> sourceFiles = new ArrayList<>();
        List<String> lines = Files.readAllLines(Paths.get(diffFilePath));
        boolean inDiff = false;
        int currentLine = 0;
        String currentSourceFile = "";

        for (String line : lines) {
            Matcher matcher = DIFF_HEADER_PATTERN.matcher(line);
            if (matcher.matches()) {
                String sourceFile = matcher.group(1);
                if (sourceFile.endsWith(".java")) {
                    sourceFiles.add(sourceFile);
                    currentSourceFile = sourceFile;
                    diffContentLines.put(currentSourceFile, new ArrayList<>());
                } else {
                    // Reset current source file if not a Java file
                    currentSourceFile = "";
                }
                inDiff = true;
                currentLine = 0;
                continue;
            }

            if (inDiff && !currentSourceFile.isEmpty()) {
                if (line.startsWith("@@")) {
                    // Parse the @@ -l,s +l,s @@ line to get the starting line number
                    String[] parts = line.split(" ")[2].substring(1).split(",");
                    currentLine = Integer.parseInt(parts[0]);
                } else if (line.startsWith("+")) {
                    // Add safety check before accessing the list
                    List<Integer> linesList = diffContentLines.get(currentSourceFile);
                    if (linesList != null) {
                        linesList.add(currentLine);
                    }
                    currentLine++;
                } else if (line.startsWith(" ")) {
                    currentLine++;
                }
            }
        }
        return sourceFiles;
    }

    private void parseJavaFile(String sourceFilePath) {
        try {
            Path fullPath = baseDir.resolve(sourceFilePath).normalize();

            // Security check to prevent path traversal
            if (!fullPath.startsWith(baseDir)) {
                System.err.println("Security warning: Path traversal attempt detected for: " + sourceFilePath);
                return;
            }

            if (!Files.exists(fullPath)) {
                System.err.println("Source file not found: " + fullPath);
                return;
            }

            JavaParser parser = new JavaParser();
            ParseResult<CompilationUnit> parseResult = parser.parse(fullPath);

            if (!parseResult.isSuccessful()) {
                System.err.println("Failed to parse: " + sourceFilePath);
                return;
            }

            CompilationUnit cu = parseResult.getResult().get();
            cu.accept(new MethodNameCollector(), null);

        } catch (IOException e) {
            System.err.println("Error parsing file " + sourceFilePath + ": " + e.getMessage());
        }
        currentFile = sourceFilePath;
    }

    private List<String> filterMethodsByDiffContent(List<String> methods) {
        return methodInfos.stream()
                .filter(methodInfo -> {
                    List<Integer> changedLines = diffContentLines.get(currentFile);
                    if (changedLines == null)
                        return false;

                    return changedLines.stream()
                            .anyMatch(line -> line >= methodInfo.startLine && line <= methodInfo.endLine);
                })
                .map(MethodInfo::getFullName)
                .distinct()
                .collect(Collectors.toList());
    }

    private class MethodNameCollector extends VoidVisitorAdapter<Void> {
        @Override
        @SuppressWarnings("unchecked")
        public void visit(MethodDeclaration md, Void arg) {
            String packageName = md.findCompilationUnit()
                    .flatMap(cu -> cu.getPackageDeclaration())
                    .map(pd -> pd.getNameAsString())
                    .orElse("");

            String className = md.findAncestor(com.github.javaparser.ast.body.ClassOrInterfaceDeclaration.class)
                    .map(c -> c.getNameAsString())
                    .orElse("");

            int startLine = md.getBegin().get().line;
            int endLine = md.getEnd().get().line;

            methodInfos.add(new MethodInfo(
                    packageName,
                    className,
                    md.getNameAsString(),
                    startLine,
                    endLine));

            super.visit(md, arg);
        }
    }

    public static void main(String[] args) {
        if (args.length < 1 || args.length > 2) {
            System.out.println("Usage: DiffParser <diff-file-path> [base-directory]");
            return;
        }

        try {
            DiffParser parser = args.length == 2
                    ? new DiffParser(args[0], Paths.get(args[1]))
                    : new DiffParser(args[0]);
            List<String> methods = parser.parse();
            System.out.println("Found methods:");
            methods.forEach(System.out::println);
        } catch (IOException e) {
            System.err.println("Error: " + e.getMessage());
        }
    }
}
