package org.b3yond;

import org.b3yond.model.Task;
import org.b3yond.service.RedisService;
import org.b3yond.utils.FileOperationUtil;
import org.b3yond.utils.OpenTelemetryUtil;

import java.nio.file.Paths;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.List;
import java.util.ArrayList;
import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.util.regex.Pattern;
import java.util.regex.Matcher;
import java.util.Set;
import java.util.HashSet;
import java.util.jar.JarFile;
import java.util.jar.JarEntry;
import java.util.Enumeration;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.BufferedReader;
import java.io.FileReader;

/**
 * A processor class that handles Java code slicing tasks from a Redis queue.
 * This class is responsible for processing tasks that involve analyzing Java
 * code,
 * applying patches, and generating slice outputs for code analysis.
 * 
 * The processor:
 * 1. Connects to a Redis server to fetch tasks
 * 2. Processes each task by:
 * - Validating task requirements
 * - Extracting necessary resources (repositories, diffs, tooling)
 * - Applying patches if available
 * - Running the code slicer on Java class files
 * - Copying results to a shared location
 * 
 * Configuration is handled through environment variables:
 * - REDIS_HOST: Redis server hostname (default: localhost)
 * - REDIS_PORT: Redis server port (default: 6379)
 * - WORK_DIR: Working directory for task processing (default: /tmp/javaslice)
 * - POLL_INTERVAL_SECONDS: Time between task checks (default: 60)
 * - CRS_MOUNT_PATH: Path to CRS mount point (default: /crs)
 * - MAX_CONCURRENT_TASKS: Maximum number of tasks to process concurrently
 * (default: 4)
 * - OTEL_EXPORTER_OTLP_ENDPOINT: OpenTelemetry endpoint
 * - OTEL_EXPORTER_OTLP_PROTOCOL: OpenTelemetry protocol
 * - OTEL_EXPORTER_OTLP_HEADERS: OpenTelemetry headers
 * 
 * The processor runs in an infinite loop, processing tasks as they become
 * available
 * and sleeping for a configured interval between checks.
 * 
 * @see Task
 * @see RedisService
 * @see FileOperationUtil
 * @see SliceCmdGenerator
 * @see OpenTelemetryUtil
 * 
 * @author b3yond Java team
 * @version 1.0
 */
public class SliceTaskProcessor {

    // private static final String ENV_REDIS_HOST = "REDIS_HOST";
    // private static final String ENV_REDIS_PORT = "REDIS_PORT";
    private static final String ENV_WORK_DIR = "WORK_DIR";
    private static final String ENV_POLL_INTERVAL = "POLL_INTERVAL_SECONDS";
    private static final String ENV_CRS_MOUNT_PATH = "CRS_MOUNT_PATH";
    private static final String ENV_MAX_CONCURRENT_TASKS = "MAX_CONCURRENT_TASKS";

    // private static final String DEFAULT_REDIS_HOST = "localhost";
    // private static final int DEFAULT_REDIS_PORT = 6379;
    private static final String DEFAULT_WORK_DIR = "/tmp/javaslice";
    private static final int DEFAULT_POLL_INTERVAL = 60;
    private static final String DEFAULT_CRS_MOUNT_PATH = "/crs";
    private static final int DEFAULT_MAX_CONCURRENT_TASKS = 4;
    private static final String NO_RESULT_PATH = "/no_results";

    private static final ConcurrentHashMap<String, Object> tasksCurrentlySubmitted = new ConcurrentHashMap<>();
    private static final Object SUBMITTED_PLACEHOLDER = new Object();

    public static void main(String[] args) {
        // Load configuration from environment variables
        // String redisHost = getEnv(ENV_REDIS_HOST, DEFAULT_REDIS_HOST);
        // int redisPort = getEnvInt(ENV_REDIS_PORT, DEFAULT_REDIS_PORT);
        String workDir = getEnv(ENV_WORK_DIR, DEFAULT_WORK_DIR);
        RedisService mainRedisService = new RedisService(); // mainRedisService is effectively final
                                                            // for lambda
        int pollInterval = getEnvInt(ENV_POLL_INTERVAL, DEFAULT_POLL_INTERVAL);
        int maxConcurrentTasks = getEnvInt(ENV_MAX_CONCURRENT_TASKS, DEFAULT_MAX_CONCURRENT_TASKS);

        System.out.println("Starting Redis Task Processor with configuration:");
        System.out.println("Work Directory: " + workDir);
        System.out.println("Poll Interval: " + pollInterval + " seconds");
        System.out.println("Max Concurrent Tasks: " + maxConcurrentTasks);

        // Log the service startup with OpenTelemetry
        // OpenTelemetryUtil.logTaskAction("java_slicer_started", "service_init",
        // "work dir: " + workDir);

        // Ensure work directory exists
        FileOperationUtil.createDirectoryIfNotExists(workDir);

        // Create thread pool for parallel task processing
        ExecutorService executor = Executors.newFixedThreadPool(maxConcurrentTasks);

        // Initialize Redis service
        try {
            System.out.println("Connected to Redis. Starting task processing loop...");

            while (true) {
                try {
                    // Process multiple tasks in parallel
                    List<String> taskIds = mainRedisService.getNextTaskIds(maxConcurrentTasks);

                    if (taskIds.isEmpty()) {
                        System.out.println("No tasks available. Waiting...");
                    } else {
                        System.out.println("Processing " + taskIds.size() + " tasks in parallel");

                        for (String taskId : taskIds) {
                            // Attempt to mark this task as submitted by this instance
                            System.out.println("[parallels v1.0.0] Attempting to submit task: " + taskId);
                            if (tasksCurrentlySubmitted.putIfAbsent(taskId, SUBMITTED_PLACEHOLDER) == null) {
                                // This instance is the first to try and submit this taskId
                                mainRedisService.markTaskStatus(taskId); // Mark status in Redis

                                Task task = mainRedisService.getTaskDetails(taskId);

                                if (task != null) {
                                    executor.submit(() -> {
                                        try {
                                            // Create a separate Redis service for each thread
                                            RedisService threadRedisService = new RedisService();
                                            processTask(task, workDir, threadRedisService);
                                            threadRedisService.close(); // Clean up
                                        } catch (Exception e) {
                                            System.err.println("Error processing " + taskId + ": " + e.getMessage());
                                            e.printStackTrace();
                                        } finally {
                                            tasksCurrentlySubmitted.remove(taskId); // Remove from tracking when
                                        }
                                    });
                                } else {
                                    System.err.println("[BEAT] General task runs for ID: " + taskId
                                            + ". Not for slicing. Removing from local submission tracking.");
                                    tasksCurrentlySubmitted.remove(taskId); // Remove if task details not found
                                    // Optionally, clear any status marked by markTaskStatus if appropriate
                                    // mainRedisService.clearTaskStatus(taskId); // If markTaskStatus is not
                                    // idempotent or needs cleanup
                                }
                            } else {
                                System.out.println("Task " + taskId
                                        + " is already submitted for processing by this instance. Skipping.");
                            }
                        }
                    }

                } catch (Exception e) {
                    System.err.println("Error getting tasks: " + e.getMessage());
                    e.printStackTrace();
                }

                // Sleep for the configured interval before checking for more tasks
                System.out.println("Sleeping for " + pollInterval + " seconds before next poll...");
                try {
                    TimeUnit.SECONDS.sleep(pollInterval);
                } catch (InterruptedException e) {
                    System.err.println("Sleep interrupted: " + e.getMessage());
                    Thread.currentThread().interrupt();
                    executor.shutdownNow();
                    break;
                }
            }
        } finally { // Ensure mainRedisService is closed if the loop exits
            mainRedisService.close();
        }
    }

    private static void processTask(Task task, String workDir, RedisService redisService) {
        if (task == null) {
            System.err.println("Cannot process null task");
            return;
        }

        String taskId = task.getTask_id();
        System.out.println("Processing task: " + taskId);
        System.out.println("Project: " + task.getProject_name());

        // Check if public build was successful
        if (!checkPublicBuildStatus(taskId, redisService)) {
            return;
        }

        try {
            // Create task-specific directory
            String taskDir = createTaskDirectory(workDir, taskId);

            // Validate required fields
            validateTaskRequirements(task);

            // Extract all necessary files
            TaskResources resources = extractTaskResources(task, taskDir);

            // Find focus directory and apply patches
            String focusDir = findFocusDirectory(resources.getRepoPaths(), task.getFocus());
            Path diffPatchFile = applyDiffIfAvailable(resources.getDiffPath(), focusDir);
            if (diffPatchFile == null) {
                System.err.println("No valid diff patch file found, cannot continue processing task " + taskId);
                return;
            }

            String parentDir = new File(focusDir).getParent();
            if (parentDir == null) {
                System.err.println("Could not determine parent directory of focus directory: " + focusDir);
                return;
            }

            // Prepare output and run slicer
            String outputPath = prepareOutputPath(taskDir);
            // Pass task.getProject_name() to runSlicer
            runSlicer(resources, focusDir, diffPatchFile, outputPath, taskId, task.getProject_name());
            String crsMountPath = getEnv(ENV_CRS_MOUNT_PATH, DEFAULT_CRS_MOUNT_PATH);
            int copiedFiles = 0; // Placeholder
            String sliceSavedPath = Paths.get(crsMountPath, "javaslice", taskId).toString();
            // checkAndCopyResults
            copiedFiles = checkAndCopyResults(outputPath, sliceSavedPath);
            System.out.println("Results copied successfully to " + sliceSavedPath);

            // Save the result path to Redis
            try {
                if (copiedFiles > 0) { // This logic should be inside your main try block for processTask
                    redisService.saveTaskResult(taskId, sliceSavedPath);
                    redisService.addProcessedTaskId(taskId); // Uses the passed redisService instance
                    System.out.println("Task " + taskId + " marked as done in Redis");
                    redisService.markTaskDone(taskId); // Uses the passed redisService instance
                } else {
                    System.err.println("No results found for task " + taskId + ", saving NO_RESULT_PATH");
                    redisService.saveTaskResult(taskId, NO_RESULT_PATH); // Uses the passed redisService instance
                }

                // Log the successful task result save with OpenTelemetry
                OpenTelemetryUtil.logTaskAction("java_slicing", taskId, sliceSavedPath);
                System.out.println("Saved result path to Redis for task " + taskId);
            } catch (Exception e) {
                System.err.println("Failed to save result path to Redis: " + e.getMessage());
                // Log the failure
                OpenTelemetryUtil.logTaskAction("java_save_result_failed", taskId, null);
            }

            System.out.println("Task " + taskId + " completed. Output: " + outputPath);
        } catch (TaskValidationException e) {
            System.err.println("Task validation error: " + e.getMessage());
        } catch (ResourceExtractionException e) {
            System.err.println("Resource extraction error: " + e.getMessage());
        } catch (Exception e) {
            System.err.println("Error processing task " + taskId + ": " + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * Checks if the public build was successful for the given task
     * Also checks if the task has already been processed
     * 
     * @param taskId The ID of the task to check
     * @return true if the public build was successful and task hasn't been
     *         processed yet, false otherwise
     */
    private static boolean checkPublicBuildStatus(String taskId, RedisService redisService) {
        try {
            String existingResult = redisService.getTaskResult(taskId);
            if (existingResult != null) {
                System.out.println("Task " + taskId + " has already been processed. Result path: " + existingResult);
                System.out.println("Skipping duplicate processing.");
                return false;
            }

            String buildInfo = redisService.getPublicBuildInfo(taskId);
            if (!redisService.isPublicBuildSuccessful(buildInfo)) {
                System.err.println("Task was not built (successful or never started) " + taskId + ", skipping");
                return false;
            }

            System.out.println("Public build verified as successful for task " + taskId);
            return true;
        } catch (Exception e) { // Catching general exception, consider more specific ones if appropriate
            System.err.println("Error checking public build status for task " + taskId + ": " + e.getMessage());
            e.printStackTrace();
            return false; // Fail safe
        }
    }

    private static String createTaskDirectory(String workDir, String taskId) {
        String taskDir = Paths.get(workDir, taskId).toString();
        FileOperationUtil.createDirectoryIfNotExists(taskDir);
        return taskDir;
    }

    private static void validateTaskRequirements(Task task) throws TaskValidationException {
        // Validate focus is provided
        if (task.getFocus() == null || task.getFocus().isEmpty()) {
            throw new TaskValidationException("Focus is required for task " + task.getTask_id());
        }

        // Add additional validations as needed
        if (task.getRepo() == null || task.getRepo().length == 0) {
            throw new TaskValidationException("Repository data is required for task " + task.getTask_id());
        }
    }

    private static TaskResources extractTaskResources(Task task, String taskDir) throws ResourceExtractionException {
        try {
            String diffPath = null;
            if (task.getDiff() != null) {
                System.out.println("Extracting diff data, length: " + task.getDiff().length());
                try {
                    diffPath = FileOperationUtil.extractFile(task.getDiff(), taskDir, "diff");
                } catch (Exception e) {
                    System.err.println("Failed to extract diff: " + e.getMessage());
                    throw new ResourceExtractionException("Failed to extract diff: " + e.getMessage(), e);
                }
            }

            String[] repoPaths = new String[task.getRepo().length];
            for (int i = 0; i < task.getRepo().length; i++) {
                System.out.println("Extracting repo " + i + ", data length: " +
                        (task.getRepo()[i] != null ? task.getRepo()[i].length() : "null"));
                System.out.println("Repo " + i + " file path: " + task.getRepo()[i]); // Add this debug line
                try {
                    // Check if file exists before extraction
                    File repoFile = new File(task.getRepo()[i]);
                    System.out.println(
                            "Repo " + i + " file exists: " + repoFile.exists() + ", size: " + repoFile.length());

                    repoPaths[i] = FileOperationUtil.extractFile(task.getRepo()[i], taskDir, "repo" + i);
                } catch (Exception e) {
                    System.err.println("Failed to extract repo " + i + ": " + e.getMessage());
                    e.printStackTrace(); // Add stack trace for debugging
                    throw new ResourceExtractionException("Failed to extract repo " + i + ": " + e.getMessage(), e);
                }
            }

            String toolingPath = null;
            if (task.getFuzzing_tooling() != null) {
                System.out.println("Extracting tooling data, length: " + task.getFuzzing_tooling().length());
                try {
                    toolingPath = FileOperationUtil.extractFile(task.getFuzzing_tooling(), taskDir, "tooling");
                } catch (Exception e) {
                    System.err.println("Failed to extract tooling: " + e.getMessage());
                    throw new ResourceExtractionException("Failed to extract tooling: " + e.getMessage(), e);
                }
            }

            return new TaskResources(diffPath, repoPaths, toolingPath);
        } catch (ResourceExtractionException e) {
            throw e; // Re-throw our custom exceptions
        } catch (Exception e) {
            throw new ResourceExtractionException("Failed to extract task resources: " + e.getMessage(), e);
        }
    }

    private static String findFocusDirectory(String[] repoPaths, String focus) {
        if (focus == null || repoPaths == null) {
            return null;
        }

        for (String repoPath : repoPaths) {
            File repoDir = new File(repoPath);
            String lastPathComponent = repoDir.getName();

            if (lastPathComponent.equals(focus) && repoDir.exists() && repoDir.isDirectory()) {
                System.out.println("Found focus directory: " + repoPath);
                return repoPath;
            }
        }

        System.err.println("Could not find directory matching focus: " + focus);
        return null;
    }

    private static Path applyDiffIfAvailable(String diffPath, String focusDir) {
        if (diffPath == null || focusDir == null) {
            return null;
        }

        try {
            List<Path> diffFiles = FileOperationUtil.findDiffFiles(diffPath);
            Path preferredDiffFile = FileOperationUtil.getPreferredDiffFile(diffFiles);

            if (preferredDiffFile != null) {
                FileOperationUtil.applyPatch(focusDir, preferredDiffFile.toString());
                System.out.println("Successfully applied patch: " + preferredDiffFile);
                return preferredDiffFile;
            } else {
                System.err.println("No diff files found in: " + diffPath);
            }
        } catch (Exception e) {
            System.err.println("Error applying patch to focus directory: " + e.getMessage());
        }

        return null;
    }

    private static String prepareOutputPath(String taskDir) {
        return Paths.get(taskDir, "slice_output").toString();
    }

    private static void runSlicer(TaskResources resources, String focusDir, Path diffFile, String outputPath,
            String taskId, String projectName) { // Added projectName parameter
        System.out.println("Running slicer with parameters:");
        System.out.println("Diff: " + (diffFile != null ? diffFile.toString() : resources.getDiffPath()));
        System.out.println("Repo: " + Arrays.toString(resources.getRepoPaths()));
        System.out.println("Tooling: " + resources.getToolingPath());
        System.out.println("Focus directory: " + focusDir);
        System.out.println("Output: " + outputPath);
        System.out.println("Task ID: " + taskId);
        System.out.println("Project Name: " + projectName);

        try {
            // 1. Get the mount path from environment variable
            String crsMountPath = getEnv(ENV_CRS_MOUNT_PATH, DEFAULT_CRS_MOUNT_PATH);
            System.out.println("CRS Mount Path: " + crsMountPath);

            // Using the project name from the task parameter instead of the focus directory
            System.out.println("Project Name: " + projectName);

            // 2. Copy files from the build directory to focusDir - updated path with taskId
            String buildPath = Paths.get(crsMountPath, "public_build", taskId, "build", "out", projectName).toString();
            System.out.println("Copying build files from: " + buildPath);

            // Check if the build path exists
            File buildDir = new File(buildPath);
            if (buildDir.exists() && buildDir.isDirectory()) {
                try {
                    // Copy all files from the build directory to focusDir
                    FileOperationUtil.copyFile(buildPath, focusDir, true);
                    System.out.println("Successfully copied build files to focus directory");
                } catch (IOException e) {
                    System.err.println("Failed to copy build files: " + e.getMessage());
                }
            } else {
                System.err.println("Build directory does not exist: " + buildPath);
            }

            // 3. Find all .class files in focusDir and run the slicer for each one
            List<String> classFiles = findClassFiles(focusDir);

            if (classFiles.isEmpty()) {
                System.err.println("No .class files found directly in: " + focusDir);
                System.err.println("Searching from .jar files " + focusDir);
                List<String> jarClassFiles = extractClassFilesFromJar(focusDir);
                classFiles.addAll(jarClassFiles);
                if (classFiles.isEmpty()) {
                    System.err.println("No .class files found in JAR files in: " + focusDir);
                    return;
                }
            }

            // Create output directory if it doesn't exist
            FileOperationUtil.createDirectoryIfNotExists(outputPath);

            // For each class file, run SliceCmdGenerator
            for (String classFilePath : classFiles) {
                if (classFilePath.contains("$")) {
                    // System.out.println("Skipping anonymous class: " + classFilePath);
                    continue;
                }

                System.out.println("Processing class file: " + classFilePath);

                File classFile = new File(classFilePath);
                String outputFilename = classFile.getName().replace(".class", "");
                String targetOutputFile = Paths.get(outputPath, outputFilename).toString();

                // Prepare args for SliceCmdGenerator.run
                String[] slicerArgs = new String[] {
                        "-cp", focusDir,
                        diffFile != null ? diffFile.toString() : resources.getDiffPath(),
                        classFilePath,
                        targetOutputFile
                };

                // Run SliceCmdGenerator
                try {
                    System.out.println("Current thread ID: " + Thread.currentThread().getId());
                    System.out.println("Running slicer with args: " + Arrays.toString(slicerArgs));
                    SliceCmdGenerator.run(slicerArgs);
                } catch (Exception e) {
                    System.err.println("Error running slicer for " + classFilePath + ": " + e.getMessage());
                }
            }

        } catch (Exception e) {
            System.err.println("Error running slicer: " + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * Recursively finds all .class files in a directory
     * 
     * @param directory The directory to search
     * @return A list of paths to .class files
     */
    private static List<String> findClassFiles(String directory) {
        List<String> classFiles = new ArrayList<>();
        File dir = new File(directory);

        if (!dir.exists() || !dir.isDirectory()) {
            return classFiles;
        }

        File[] files = dir.listFiles();
        if (files != null) {
            for (File file : files) {
                if (file.isDirectory()) {
                    classFiles.addAll(findClassFiles(file.getAbsolutePath()));
                } else if (file.getName().endsWith(".class")) {
                    classFiles.add(file.getAbsolutePath());
                }
            }
        }

        return classFiles;
    }

    /**
     * 1. find text/script files end with *Fuzzer that contain "--target_class="
     * 2. extract target class name from the files that match the pattern
     * "\s--target_class=(className)\s+"
     * 3. search all the jar files in the directory for jars that contain the target
     * class name
     * 4. extract all class files from the jar files (ignore ignore_path)
     * 5. return a list of class files
     * 
     * @param directory
     * @return A list of class files extracted from a JAR file
     */
    private static List<String> extractClassFilesFromJar(String directory) {
        List<String> classFiles = new ArrayList<>();
        File dir = new File(directory);
        String ignorePath = "IGNORE-ME/"; // Ignore specific directory

        if (!dir.exists() || !dir.isDirectory()) {
            System.err.println("Directory does not exist: " + directory);
            return classFiles;
        }

        try {
            // Step 1: Find fuzzer files and extract target class names
            Set<String> targetClasses = new HashSet<>();
            Pattern targetClassPattern = Pattern.compile("\\s--target_class=([\\w\\.\\$]+)\\s*");

            File[] files = dir.listFiles();
            if (files != null) {
                for (File file : files) {
                    if (file.isFile() && file.getName().endsWith("Fuzzer")) {
                        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
                            String line;
                            while ((line = reader.readLine()) != null) {
                                if (line.contains("--target_class=")) {
                                    Matcher matcher = targetClassPattern.matcher(line);
                                    while (matcher.find()) {
                                        String className = matcher.group(1);
                                        targetClasses.add(className);
                                        System.out.println(
                                                "Found target class: " + className + " in file: " + file.getName());
                                    }
                                }
                            }
                        } catch (IOException e) {
                            System.err.println("Error reading fuzzer file: " + file.getName() + " - " + e.getMessage());
                        }
                    }
                }
            }

            if (targetClasses.isEmpty()) {
                System.out.println("No target classes found in fuzzer files");
                return classFiles;
            }

            // Step 2: Find JAR files in the directory
            List<File> jarFiles = new ArrayList<>();
            if (files != null) {
                for (File file : files) {
                    if (file.isFile() && file.getName().endsWith(".jar")) {
                        jarFiles.add(file);
                    }
                }
            }

            if (jarFiles.isEmpty()) {
                System.out.println("No JAR files found in directory: " + directory);
                return classFiles;
            }

            // Step 3: Check each JAR for target classes and extract class files
            String extractDir = directory + File.separator + "extracted_classes";
            FileOperationUtil.createDirectoryIfNotExists(extractDir);

            for (File jarFile : jarFiles) {
                boolean containsTargetClass = false;

                // First pass: check if JAR contains any target classes
                try (JarFile jar = new JarFile(jarFile)) {
                    Enumeration<JarEntry> entries = jar.entries();
                    while (entries.hasMoreElements() && !containsTargetClass) {
                        JarEntry entry = entries.nextElement();
                        if (entry.getName().endsWith(".class") && !entry.getName().startsWith(ignorePath)) {
                            String className = entry.getName().replace(".class", "").replace("/", ".");
                            for (String targetClass : targetClasses) {
                                if (className.equals(targetClass) || className.contains(targetClass)) {
                                    containsTargetClass = true;
                                    break;
                                }
                            }
                        }
                    }
                } catch (IOException e) {
                    System.err.println("Error reading JAR file: " + jarFile.getName() + " - " + e.getMessage());
                    continue;
                }

                // Second pass: extract all class files if JAR contains target classes
                if (containsTargetClass) {
                    System.out.println("Extracting class files from JAR: " + jarFile.getName());
                    try (JarFile jar = new JarFile(jarFile)) {
                        Enumeration<JarEntry> entries = jar.entries();
                        while (entries.hasMoreElements()) {
                            JarEntry entry = entries.nextElement();
                            if (entry.getName().endsWith(".class") && !entry.getName().startsWith("META-INF/")) {
                                // Create directory structure for the class file
                                String entryPath = entry.getName();
                                File outputFile = new File(extractDir, entryPath);
                                File parentDir = outputFile.getParentFile();
                                if (parentDir != null && !parentDir.exists()) {
                                    parentDir.mkdirs();
                                }

                                // Extract the class file
                                try (InputStream inputStream = jar.getInputStream(entry);
                                        FileOutputStream outputStream = new FileOutputStream(outputFile)) {
                                    byte[] buffer = new byte[1024];
                                    int bytesRead;
                                    while ((bytesRead = inputStream.read(buffer)) != -1) {
                                        outputStream.write(buffer, 0, bytesRead);
                                    }
                                    classFiles.add(outputFile.getAbsolutePath());
                                } catch (IOException e) {
                                    System.err.println(
                                            "Error extracting class file: " + entryPath + " - " + e.getMessage());
                                }
                            }
                        }
                    } catch (IOException e) {
                        System.err.println(
                                "Error extracting from JAR file: " + jarFile.getName() + " - " + e.getMessage());
                    }
                }
            }

            System.out.println("Extracted " + classFiles.size() + " class files from JAR files");
        } catch (Exception e) {
            System.err.println("Error in extractClassFilesFromJar: " + e.getMessage());
            e.printStackTrace();
        }

        return classFiles;
    }

    /**
     * Checks for result files in the output path and copies them to the shared
     * result path if all required files exist
     * 
     * @param outputPath       The directory where result files are located
     * @param sharedResultPath The target directory to copy the files to
     * @return The number of files copied
     */
    private static int checkAndCopyResults(String outputPath, String sharedResultPath) {
        if (outputPath == null || sharedResultPath == null) {
            System.err.println("Output path or shared result path is null, cannot copy results");
            return 0;
        }

        File outputDir = new File(outputPath);
        if (!outputDir.exists() || !outputDir.isDirectory()) {
            System.err.println("Output directory does not exist: " + outputPath);
            return 0;
        }

        // Create the shared result directory if it doesn't exist
        FileOperationUtil.createDirectoryIfNotExists(sharedResultPath);

        // Get all files in the output directory
        File[] files = outputDir.listFiles();
        if (files == null) {
            System.err.println("Failed to list files in output directory: " + outputPath);
            return 0;
        }

        System.out.println("Found " + files.length + " files in output directory: " + outputPath);
        for (File file : files) {
            System.out.println("File in output directory: " + file.getName());
        }

        // Find all results.txt files
        int copiedFilesCount = 0;
        for (File file : files) {
            if (file.getName().endsWith(".results.txt")) {
                String baseName = file.getName().replace(".results.txt", "");

                // Check for the other required files
                File filteredClassesFile = new File(outputPath, baseName + ".filtered_classes.txt");
                File instrumentationIncludesFile = new File(outputPath, baseName + ".instrumentation_includes.txt");

                if (filteredClassesFile.exists() && instrumentationIncludesFile.exists()) {
                    System.out.println("Found complete result set for " + baseName);

                    try {
                        // Check if file already exists in the destination
                        Path destPath = Paths.get(sharedResultPath, file.getName());
                        if (!new File(destPath.toString()).exists()) {
                            FileOperationUtil.copyFile(file.getAbsolutePath(), destPath.toString(), false);
                            copiedFilesCount++;
                            System.out.println("Copied: " + file.getName());
                        } else {
                            System.out.println("Skipped existing file: " + file.getName());
                        }

                        // Check if filtered classes file already exists in the destination
                        destPath = Paths.get(sharedResultPath, filteredClassesFile.getName());
                        if (!new File(destPath.toString()).exists()) {
                            FileOperationUtil.copyFile(filteredClassesFile.getAbsolutePath(), destPath.toString(),
                                    false);
                            copiedFilesCount++;
                            System.out.println("Copied: " + filteredClassesFile.getName());
                        } else {
                            System.out.println("Skipped existing file: " + filteredClassesFile.getName());
                        }

                        // Check if instrumentation includes file already exists in the destination
                        destPath = Paths.get(sharedResultPath, instrumentationIncludesFile.getName());
                        if (!new File(destPath.toString()).exists()) {
                            FileOperationUtil.copyFile(instrumentationIncludesFile.getAbsolutePath(),
                                    destPath.toString(), false);
                            copiedFilesCount++;
                            System.out.println("Copied: " + instrumentationIncludesFile.getName());
                        } else {
                            System.out.println("Skipped existing file: " + instrumentationIncludesFile.getName());
                        }

                        System.out.println(
                                "Successfully copied result files for " + baseName + " to " + sharedResultPath);
                    } catch (IOException e) {
                        System.err.println("Error copying result files for " + baseName + ": " + e.getMessage());
                        e.printStackTrace();
                        System.err.println("not completed: " + baseName);
                    }
                } else {
                    System.out.println("Incomplete result set for " + baseName + ", skipping");
                }
            }
        }
        return copiedFilesCount;
    }

    private static String getEnv(String key, String defaultValue) {
        String value = System.getenv(key);
        return value != null && !value.isEmpty() ? value : defaultValue;
    }

    private static int getEnvInt(String key, int defaultValue) {
        String value = System.getenv(key);
        if (value != null && !value.isEmpty()) {
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException e) {
                System.err.println(
                        "Invalid number format for " + key + ": " + value + ". Using default: " + defaultValue);
            }
        }
        return defaultValue;
    }

    /**
     * Data class to hold extracted resources for a task
     */
    private static class TaskResources {
        private final String diffPath;
        private final String[] repoPaths;
        private final String toolingPath;

        public TaskResources(String diffPath, String[] repoPaths, String toolingPath) {
            this.diffPath = diffPath;
            this.repoPaths = repoPaths;
            this.toolingPath = toolingPath;
        }

        public String getDiffPath() {
            return diffPath;
        }

        public String[] getRepoPaths() {
            return repoPaths;
        }

        public String getToolingPath() {
            return toolingPath;
        }
    }

    /**
     * Exception for task validation failures
     */
    private static class TaskValidationException extends Exception {
        public TaskValidationException(String message) {
            super(message);
        }
    }

    /**
     * Exception for resource extraction failures
     */
    private static class ResourceExtractionException extends Exception {
        public ResourceExtractionException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
