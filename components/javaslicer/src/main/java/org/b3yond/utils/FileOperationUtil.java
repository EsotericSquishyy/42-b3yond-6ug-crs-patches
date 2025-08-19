package org.b3yond.utils;

import java.io.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.apache.commons.compress.compressors.gzip.GzipCompressorInputStream;

public class FileOperationUtil {

    /**
     * Creates a directory if it doesn't exist.
     *
     * @param path The path of the directory to create
     * @return true if directory was created or already existed, false otherwise
     */
    public static boolean createDirectoryIfNotExists(String path) {
        File dir = new File(path);
        if (!dir.exists()) {
            if (dir.mkdirs()) {
                System.out.println("Created directory: " + path);
                return true;
            } else {
                System.err.println("Failed to create directory: " + path);
                return false;
            }
        }
        return true;
    }

    /**
     * Extracts a file to the output directory.
     * This handles tar, gz, and tgz files by extracting their contents.
     *
     * @param filePath  The path or URL of the file to extract
     * @param outputDir The directory to extract to
     * @param purpose   A descriptor for the purpose of this file (used in naming)
     * @return The path where the file was extracted (first directory in archive if
     *         found)
     * @throws IOException If there was an issue with file operations
     */
    public static String extractFile(String filePath, String outputDir, String purpose) throws IOException {
        // Create output directory path
        Path outputPath = Paths.get(outputDir, purpose);
        System.out.println("Extracting " + filePath + " for " + purpose + " to " + outputPath);

        // Check if source file exists and is readable
        File sourceFile = new File(filePath);
        if (!sourceFile.exists()) {
            throw new IOException("Source file does not exist: " + filePath);
        }
        if (!sourceFile.canRead()) {
            throw new IOException("Cannot read source file: " + filePath);
        }
        if (sourceFile.length() == 0) {
            throw new IOException("Source file is empty: " + filePath);
        }
        
        System.out.println("Source file verified - exists: " + sourceFile.exists() + 
                          ", readable: " + sourceFile.canRead() + 
                          ", size: " + sourceFile.length() + " bytes");

        // Ensure the directory exists
        createDirectoryIfNotExists(outputPath.toString());

        Path filePathObj = Paths.get(filePath);
        String fileName = filePathObj.getFileName().toString().toLowerCase();

        // If it's a tar, gz, or tgz file, extract it
        if (fileName.endsWith(".tar") || fileName.endsWith(".gz") || fileName.endsWith(".tgz")
                || isGzipCompressed(filePath)) {
            
            System.out.println("Detected archive file, attempting to extract...");
            Path firstDir = null;

            // Find the first directory in the archive that doesn't start with '.'
            try (TarArchiveInputStream tarIn = createTarInputStream(filePathObj.toFile())) {
                TarArchiveEntry entry;
                while ((entry = (TarArchiveEntry) tarIn.getNextEntry()) != null) {
                    if (entry.isDirectory()) {
                        // Normalize path to remove ./ and split
                        String normalizedPath = new File(entry.getName()).getPath().replace('\\', '/');
                        String[] pathParts = normalizedPath.split("/");
                        if (pathParts.length > 0 && !pathParts[0].isEmpty() && !pathParts[0].startsWith(".")) {
                            firstDir = outputPath.resolve(pathParts[0]);
                            break;
                        }
                    }
                }
            } catch (IOException e) {
                System.err.println("Error reading archive entries: " + e.getMessage());
                throw new IOException("Failed to read archive entries from " + filePath + ": " + e.getMessage(), e);
            }

            // Extract the archive
            try (TarArchiveInputStream tarIn = createTarInputStream(filePathObj.toFile())) {
                extractTarArchive(tarIn, outputPath.toFile());
            } catch (IOException e) {
                System.err.println("Error extracting archive: " + e.getMessage());
                throw new IOException("Failed to extract archive " + filePath + ": " + e.getMessage(), e);
            }

            // Return first directory if found and it exists
            if (firstDir != null && Files.exists(firstDir) && Files.isDirectory(firstDir)) {
                return firstDir.toString();
            }
        } else {
            // For regular files, just copy them to the output directory
            Path destPath = outputPath.resolve(filePathObj.getFileName());
            Files.copy(filePathObj, destPath, StandardCopyOption.REPLACE_EXISTING);
        }

        return outputPath.toString();
    }

    /**
     * Creates a TarArchiveInputStream based on the file extension.
     */
    private static TarArchiveInputStream createTarInputStream(File file) throws IOException {
        String fileName = file.getName().toLowerCase();
        if (fileName.endsWith(".tar.gz") || fileName.endsWith(".tgz") || isGzipCompressed(file)) {
            return new TarArchiveInputStream(
                    new GzipCompressorInputStream(
                            new BufferedInputStream(
                                    new FileInputStream(file))));
        } else if (fileName.endsWith(".tar")) {
            return new TarArchiveInputStream(
                    new BufferedInputStream(
                            new FileInputStream(file)));
        } else if (fileName.endsWith(".gz")) {
            // Assume it's a gzipped tar file
            return new TarArchiveInputStream(
                    new GzipCompressorInputStream(
                            new BufferedInputStream(
                                    new FileInputStream(file))));
        } else {
            throw new IOException("Unsupported archive format: " + fileName);
        }
    }

    /**
     * Extracts all entries from a tar archive.
     */
    private static void extractTarArchive(TarArchiveInputStream tarIn, File outputDir) throws IOException {
        TarArchiveEntry entry;
        while ((entry = (TarArchiveEntry) tarIn.getNextEntry()) != null) {
            File outputFile = new File(outputDir, entry.getName());

            if (entry.isDirectory()) {
                if (!outputFile.exists() && !outputFile.mkdirs()) {
                    throw new IOException("Failed to create directory: " + outputFile);
                }
            } else {
                File parent = outputFile.getParentFile();
                if (!parent.exists() && !parent.mkdirs()) {
                    throw new IOException("Failed to create directory: " + parent);
                }

                try (FileOutputStream outputStream = new FileOutputStream(outputFile)) {
                    byte[] buffer = new byte[8192];
                    int length;
                    while ((length = tarIn.read(buffer)) != -1) {
                        outputStream.write(buffer, 0, length);
                    }
                }
            }
        }
    }

    /**
     * Applies a patch file to a base directory using the patch command.
     *
     * @param baseDir       The directory to apply the patch to
     * @param patchFilePath The path to the patch file
     * @return true if patch was applied successfully, false otherwise
     * @throws IOException          If there was an issue with file operations
     * @throws InterruptedException If the patch process was interrupted
     */
    public static boolean applyPatch(String baseDir, String patchFilePath) throws IOException, InterruptedException {
        ProcessBuilder processBuilder = new ProcessBuilder(
                "patch", "-p1", "-i", patchFilePath);
        processBuilder.directory(new File(baseDir));

        // Redirect error stream to output stream
        processBuilder.redirectErrorStream(true);

        System.out.println("Applying patch: " + patchFilePath + " to directory: " + baseDir);

        Process process = processBuilder.start();
        int exitCode = process.waitFor();

        if (exitCode == 0) {
            System.out.println("Patch applied successfully");
            return true;
        } else {
            System.err.println("Failed to apply patch. Exit code: " + exitCode);
            return false;
        }
    }

    /**
     * Copies a file or directory from source to destination.
     *
     * @param source          The source file or directory
     * @param destination     The destination file or directory
     * @param replaceExisting Whether to replace existing files
     * @throws IOException If there was an issue with file operations
     */
    public static void copyFile(String source, String destination, boolean replaceExisting) throws IOException {
        Path sourcePath = Paths.get(source);
        Path destPath = Paths.get(destination);

        if (Files.isDirectory(sourcePath)) {
            copyDirectory(sourcePath, destPath, replaceExisting);
        } else {
            if (replaceExisting) {
                Files.copy(sourcePath, destPath, StandardCopyOption.REPLACE_EXISTING);
            } else {
                Files.copy(sourcePath, destPath);
            }
            System.out.println("Copied file from: " + source + " to: " + destination);
        }
    }

    /**
     * Recursively copies a directory.
     *
     * @param source          The source directory
     * @param destination     The destination directory
     * @param replaceExisting Whether to replace existing files
     * @throws IOException If there was an issue with file operations
     */
    private static void copyDirectory(Path source, Path destination, boolean replaceExisting) throws IOException {
        if (!Files.exists(destination)) {
            Files.createDirectories(destination);
        }

        Files.list(source).forEach(sourcePath -> {
            try {
                Path destPath = destination.resolve(source.relativize(sourcePath));
                if (Files.isDirectory(sourcePath)) {
                    copyDirectory(sourcePath, destPath, replaceExisting);
                } else {
                    if (replaceExisting) {
                        Files.copy(sourcePath, destPath, StandardCopyOption.REPLACE_EXISTING);
                    } else {
                        if (!Files.exists(destPath)) {
                            Files.copy(sourcePath, destPath);
                        }
                    }
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });

        // System.out.println("Copied directory from: " + source + " to: " + destination);
    }

    /**
     * Moves a file or directory from source to destination.
     *
     * @param source          The source file or directory
     * @param destination     The destination file or directory
     * @param replaceExisting Whether to replace existing files
     * @throws IOException If there was an issue with file operations
     */
    public static void moveFile(String source, String destination, boolean replaceExisting) throws IOException {
        Path sourcePath = Paths.get(source);
        Path destPath = Paths.get(destination);

        if (replaceExisting) {
            Files.move(sourcePath, destPath, StandardCopyOption.REPLACE_EXISTING);
        } else {
            Files.move(sourcePath, destPath);
        }

        System.out.println("Moved file from: " + source + " to: " + destination);
    }

    /**
     * Deletes a file or directory.
     *
     * @param path      The path to delete
     * @param recursive Whether to delete recursively (for directories)
     * @return true if deletion was successful, false otherwise
     * @throws IOException If there was an issue with file operations
     */
    public static boolean deleteFile(String path, boolean recursive) throws IOException {
        Path filePath = Paths.get(path);

        if (!Files.exists(filePath)) {
            System.out.println("Path does not exist: " + path);
            return true;
        }

        if (Files.isDirectory(filePath) && recursive) {
            Files.walk(filePath)
                    .sorted((p1, p2) -> -p1.compareTo(p2)) // Sort in reverse order to delete children before parents
                    .forEach(p -> {
                        try {
                            Files.delete(p);
                        } catch (IOException e) {
                            throw new RuntimeException(e);
                        }
                    });
            System.out.println("Deleted directory recursively: " + path);
            return true;
        } else {
            boolean result = Files.deleteIfExists(filePath);
            if (result) {
                System.out.println("Deleted file: " + path);
            }
            return result;
        }
    }

    /**
     * Finds all .diff files under the given directory.
     * 
     * @param directory The directory to search in
     * @return A list of paths to .diff files
     * @throws IOException If there was an issue accessing the files
     */
    public static List<Path> findDiffFiles(String directory) throws IOException {
        try (Stream<Path> walk = Files.walk(Paths.get(directory))) {
            return walk
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().toLowerCase().endsWith(".diff"))
                    .collect(Collectors.toList());
        }
    }

    /**
     * Gets the preferred diff file from a list of diff files.
     * If "ref.diff" exists, it is returned. Otherwise, the first diff file is
     * returned.
     * 
     * @param diffFiles List of diff files
     * @return The preferred diff file path, or null if the list is empty
     */
    public static Path getPreferredDiffFile(List<Path> diffFiles) {
        if (diffFiles == null || diffFiles.isEmpty()) {
            return null;
        }

        // Check if ref.diff exists
        for (Path diffFile : diffFiles) {
            if (diffFile.getFileName().toString().equals("ref.diff")) {
                System.out.println("Found preferred diff file: " + diffFile);
                return diffFile;
            }
        }

        // If ref.diff doesn't exist, return the first diff file
        System.out.println("Using first available diff file: " + diffFiles.get(0));
        return diffFiles.get(0);
    }

    /**
     * Checks if a file is gzip compressed by inspecting its magic numbers.
     *
     * @param filePath The path to the file to check
     * @return true if the file is gzip compressed, false otherwise
     * @throws IOException If there was an issue reading the file
     */
    public static boolean isGzipCompressed(String filePath) throws IOException {
        Path path = Paths.get(filePath);
        if (!Files.exists(path) || Files.isDirectory(path)) {
            return false;
        }

        try (InputStream in = new FileInputStream(filePath)) {
            // Gzip files start with the magic bytes 0x1F 0x8B
            byte[] signature = new byte[2];
            int bytesRead = in.read(signature);

            if (bytesRead == 2) {
                return (signature[0] & 0xFF) == 0x1F && (signature[1] & 0xFF) == 0x8B;
            }
        }

        return false;
    }

    /**
     * Checks if a file is gzip compressed by inspecting its magic numbers.
     *
     * @param file The file object to check
     * @return true if the file is gzip compressed, false otherwise
     * @throws IOException If there was an issue reading the file
     */
    public static boolean isGzipCompressed(File file) throws IOException {
        if (!file.exists() || file.isDirectory()) {
            return false;
        }

        try (InputStream in = new FileInputStream(file)) {
            // Gzip files start with the magic bytes 0x1F 0x8B
            byte[] signature = new byte[2];
            int bytesRead = in.read(signature);

            if (bytesRead == 2) {
                return (signature[0] & 0xFF) == 0x1F && (signature[1] & 0xFF) == 0x8B;
            }
        }

        return false;
    }
}
