package org.b3yond;

import org.b3yond.utils.JavaBinLoader;
import org.b3yond.utils.JazzerSliceInputGen;
import org.b3yond.utils.DiffParser;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Paths;
import java.util.List;
import java.util.ArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.ExecutionException;

public class SliceCmdGenerator {
    final static String JAZZER_CLS_PREFIX = "Lcom/code_intelligence/";

    // File suffix constants
    final static String SUFFIX_METHODS = ".methods.txt";
    final static String SUFFIX_RESULTS = ".results.txt";
    final static String SUFFIX_ARGS = ".args";
    final static String SUFFIX_INSTRUMENTATION = ".instrumentation_includes.txt";
    final static String SUFFIX_FILTERED_CLASSES = ".filtered_classes.txt";
    final static String FUZZ_ENTRY_FUNC = "fuzzerTestOneInput";
    // Add new variable for modified pattern
    final static String PATTERN_SUFFIX = ".**";

    public static String[] findFuzzerTestMethod(String classFilePath) {
        try {
            JavaBinLoader loader = new JavaBinLoader(classFilePath);
            return loader.findFuzzerTestMethod();
        } catch (Exception e) {
            e.printStackTrace();
        }
        return null;
    }

    public static String findFirstMethodWithKeyword(String classFilePath, String keyword) {
        try {
            JavaBinLoader loader = new JavaBinLoader(classFilePath);
            return loader.findFirstMethodWithKeyword(keyword);
        } catch (Exception e) {
            e.printStackTrace();
        }
        return null;
    }

    public static String[] findAllMethodsWithKeyword(String classFilePath, String keyword) {
        try {
            JavaBinLoader loader = new JavaBinLoader(classFilePath);
            return loader.findAllMethodsWithKeyword(keyword);
        } catch (Exception e) {
            e.printStackTrace();
        }
        return new String[0];
    }

    public static String[] getFilteredClassNames(String classFilePath, String[] exclusions) {
        try {
            JavaBinLoader loader = new JavaBinLoader(classFilePath);
            String[] allClasses = loader.getAllClassNames();
            List<String> filteredClasses = new ArrayList<>();

            outer: for (String className : allClasses) {
                for (String exclusion : exclusions) {
                    String normalizedExclusion = exclusion.replace('.', '/');
                    // skip anonymous inner class
                    if (className.contains("$")) {
                        continue outer;
                    }
                    if (className.contains(normalizedExclusion) || className.startsWith(JAZZER_CLS_PREFIX)) {
                        continue outer;
                    }
                }
                filteredClasses.add(className);
            }

            // Transform class names before returning
            List<String> normalizedClasses = new ArrayList<>();
            for (String className : filteredClasses) {
                // Remove first char and replace '/' with '.'
                String normalized = className.substring(1).replace('/', '.');
                normalizedClasses.add(normalized);
            }

            return normalizedClasses.toArray(new String[0]);
        } catch (Exception e) {
            e.printStackTrace();
        }
        return new String[0];
    }

    public static void main(String[] args) {
        // Verify arguments in main method
        if (args.length < 5 || !args[0].equals("-cp")) {
            System.out.println(args.length);
            System.out.println(
                    "Usage: SliceCmdGenerator -cp <classpath> <patch_file> <source_class_file(harness)> <target_output_file>");
            return;
        }

        // Call run only if arguments are valid
        run(args);
    }

    public static void run(String[] args) {
        run(args, 7200); // Default 2 hour timeout (7200 seconds)
    }

    public static void run(String[] args, int timeoutSeconds) {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<?> future = executor.submit(() -> {
            runWithoutTimeout(args);
        });

        try {
            future.get(timeoutSeconds, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            System.err.println("Slicing operation timed out after " + timeoutSeconds + " seconds");
            future.cancel(true);
        } catch (InterruptedException | ExecutionException e) {
            System.err.println("Slicing operation failed: " + e.getMessage());
        } finally {
            executor.shutdownNow();
        }
    }

    private static void runWithoutTimeout(String[] args) {
        // Arguments have been validated in main, so we can directly use them
        String classpath = args[1];
        String patchFile = args[2];
        String sourceClassFile = args[3];
        String targetOutputFile = args[4];
        String targetMethodListFile = targetOutputFile + SUFFIX_METHODS;
        String targetSliceResultFile = targetOutputFile + SUFFIX_RESULTS;

        try {
            // Find fuzzer test method
            String[] fuzzerMethod = findFuzzerTestMethod(sourceClassFile);
            if (fuzzerMethod == null || fuzzerMethod.length < 1) {
                System.err.println("Could not find fuzzer test method");
                return;
            }
            String entryClass = fuzzerMethod[0];

            // Get methods from patch
            DiffParser parser = new DiffParser(patchFile, Paths.get(classpath));
            List<String> methods = parser.parse();

            // Write methods to target file
            try (PrintWriter methodWriter = new PrintWriter(new FileWriter(targetMethodListFile))) {
                for (String method : methods) {
                    System.err.println("Debug: Processing target method: " + method);
                    // Extract method name without class and package
                    String clsMethodName = method;
                    // Find all matching signatures for this method
                    // org.apache.zookeeper.server.util.MessageTrackerTest.testIPv6TooManyColons
                    String[] signatures = findAllMethodsWithKeyword(classpath, clsMethodName);
                    if (signatures != null && signatures.length > 0) {
                        for (String signature : signatures) {
                            methodWriter.println(signature);
                        }
                    } else {
                        // Try with just the method name (without class/package)
                        String[] parts = clsMethodName.split("\\.");
                        String simpleMethodName = parts[parts.length - 1];
                        System.out.println("Debug: fallback to search simple method name: " + simpleMethodName);
                        String[] fallbackSignatures = findAllMethodsWithKeyword(classpath, simpleMethodName);
                        if (fallbackSignatures != null && fallbackSignatures.length > 0) {
                            for (String signature : fallbackSignatures) {
                                methodWriter.println(signature);
                            }
                        } else {
                            System.err.println("Warning: No matching signature found for method: " + method);
                        }
                    }
                }
            }

            // Write command to output file
            String commandFormat = "-appClass %s -jarPath %s -mainClass %s -mainMethod fuzzerTestOneInput -targetMethodFile %s -outputFile %s";
            String command = String.format(commandFormat, classpath, classpath, entryClass, targetMethodListFile,
                    targetSliceResultFile);

            try (PrintWriter cmdWriter = new PrintWriter(new FileWriter(targetOutputFile + SUFFIX_ARGS))) {
                cmdWriter.println(command);
            }
            System.out.println("Command written to: " + targetOutputFile + SUFFIX_ARGS);

            // Execute slice directly
            try {
                AIXCCJavaSlice.run(
                        classpath, // appClass
                        classpath, // jarPath
                        entryClass, // mainClass
                        FUZZ_ENTRY_FUNC, // entrypoint
                        targetMethodListFile, // targetMethodFile
                        targetSliceResultFile // outputFile
                );
                System.out.println("Slicing completed. Results written to: " + targetSliceResultFile);

                // Check if the result file exists before processing
                File resultFile = new File(targetSliceResultFile);
                if (!resultFile.exists() || resultFile.length() == 0) {
                    System.err.println("Warn: Nothing to slice for " + entryClass);
                    return;
                }

                // Process slicing results to get exclusions
                String slicerResult = JazzerSliceInputGen.processTargets(targetSliceResultFile);
                String[] exclusions = slicerResult.split(":");

                // Create a modified version with ".**" appended to each exclusion
                StringBuilder modifiedSlicerResult = new StringBuilder();
                for (int i = 0; i < exclusions.length; i++) {
                    modifiedSlicerResult.append(exclusions[i]).append(PATTERN_SUFFIX);
                    if (i < exclusions.length - 1) {
                        modifiedSlicerResult.append(":");
                    }
                }

                // Save slicer result with modified pattern
                String slicerResultFile = targetOutputFile + SUFFIX_INSTRUMENTATION;
                try (PrintWriter slicerWriter = new PrintWriter(new FileWriter(slicerResultFile))) {
                    slicerWriter.println(modifiedSlicerResult.toString());
                }
                System.out.println("Slicer exclusions written to: " + slicerResultFile);

                // Get filtered class names (still using original exclusions)
                String[] filteredClasses = getFilteredClassNames(classpath, exclusions);

                // Save filtered class names
                String filteredClassFile = targetOutputFile + SUFFIX_FILTERED_CLASSES;
                try (PrintWriter classWriter = new PrintWriter(new FileWriter(filteredClassFile))) {
                    for (String className : filteredClasses) {
                        classWriter.println(className);
                    }
                }
                System.out.println("Filtered class names written to: " + filteredClassFile);

            } catch (Exception e) {
                System.err.println("Error during slicing: " + e.getMessage());
                e.printStackTrace();
            }

        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
        }
    }
}
