package org.b3yond.utils;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Collectors;

public class JazzerSliceInputGen {
    public static String processTargets(String filePath) throws IOException {
        List<String> lines = Files.readAllLines(Paths.get(filePath));
        return lines.stream()
                .flatMap(line -> Arrays.stream(line.split(",")))
                .map(JazzerSliceInputGen::extractClass)
                .distinct()
                .collect(Collectors.joining(":"));
    }

    private static String extractClass(String fullPath) {
        String classPath = fullPath.contains("(") ? fullPath.substring(0, fullPath.lastIndexOf('.')) : fullPath;
        return classPath; // + ".*";
    }

    public static void writeResult(String filePath, String result) throws IOException {
        Path outputPath = Paths.get(filePath);
        Files.writeString(outputPath, result);
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java SliceJazzer <input-file-path>");
            System.exit(1);
        }

        try {
            String inputPath = args[0];
            String result = processTargets(inputPath);
            System.out.println(result);
        } catch (IOException e) {
            System.err.println("Error processing file: " + e.getMessage());
            System.exit(1);
        }
    }
}
