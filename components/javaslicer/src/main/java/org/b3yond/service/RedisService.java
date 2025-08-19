package org.b3yond.service;

import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisSentinelPool;
import redis.clients.jedis.JedisPoolConfig;
import redis.clients.jedis.exceptions.JedisConnectionException;
import redis.clients.jedis.util.Pool;
import com.google.gson.Gson;
import org.b3yond.model.Task;
import org.slf4j.LoggerFactory;
import org.slf4j.Logger;

import java.util.Set;
import java.util.List;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.HashSet;
import java.util.Arrays;

public class RedisService implements AutoCloseable {
    private static final Logger logger = LoggerFactory.getLogger(RedisService.class);
    private static final String TASK_STATUS_KEY = "primefuzz:task:task_status";
    private static final String JAVASLICE_TASK_STATUS_KEY = "javaslice:task:task_status";
    private static final String JAVASLICE_TASK_DONE_KEY = "javaslice:task:task_done";
    private static final String JAVASLICE_TASK_PREFIX = "javaslice:task:";
    private static final String PUBLIC_BACKUP_PREFIX = "public:build:";
    private static final String TASK_RESULT_SUFFIX = ":result";

    private final Gson gson;
    private Set<String> processedTaskIds;

    // Modified to support both direct Jedis and JedisSentinelPool
    private Jedis jedis;
    private Pool<Jedis> jedisPool;
    private boolean usingSentinel = true;

    // Store connection parameters for reconnection
    private String redisHost;
    private int redisPort;
    private String redisPassword;
    private String sentinelHosts;
    private String masterName;

    /**
     * Constructor using default Redis connection
     * 
     * @param host Redis host
     * @param port Redis port
     */
    public RedisService(String host, int port) {
        this(host, port, null, null, null);
    }

    /**
     * Default constructor that reads configuration from environment variables
     */
    public RedisService() {
        this(
                System.getenv("REDIS_HOST") != null ? System.getenv("REDIS_HOST") : "localhost",
                System.getenv("REDIS_PORT") != null ? Integer.parseInt(System.getenv("REDIS_PORT")) : 6379,
                System.getenv("REDIS_SENTINEL_HOSTS"),
                System.getenv("REDIS_MASTER"),
                System.getenv("REDIS_PASSWORD"));
    }

    /**
     * Constructor that supports Redis Sentinel configuration
     * 
     * @param host          Redis host (fallback)
     * @param port          Redis port (fallback)
     * @param sentinelHosts Comma-separated list of sentinel hosts
     * @param masterName    Redis master name
     * @param password      Redis password
     */
    public RedisService(String host, int port, String sentinelHosts, String masterName, String password) {
        this.gson = new Gson();
        this.processedTaskIds = new HashSet<>();

        // Store connection parameters for potential reconnection
        this.redisHost = host;
        this.redisPort = port;
        logger.info("default host" + this.redisHost);
        logger.debug("default port" + this.redisPort);
        this.redisPassword = password;
        this.sentinelHosts = sentinelHosts;
        this.masterName = masterName;

        // Try to use Sentinel if available
        if (sentinelHosts != null && !sentinelHosts.isEmpty() && masterName != null && !masterName.isEmpty()) {
            try {
                Set<String> sentinels = new HashSet<>(Arrays.asList(sentinelHosts.split(",")));
                JedisPoolConfig poolConfig = new JedisPoolConfig();

                logger.info("Attempting to connect to Redis using Sentinel, master: {}", masterName);

                // If password is provided, use it
                if (password != null && !password.isEmpty()) {
                    this.jedisPool = new JedisSentinelPool(masterName, sentinels, poolConfig, password);
                } else {
                    this.jedisPool = new JedisSentinelPool(masterName, sentinels, poolConfig);
                }

                // this.jedis = jedisPool.getResource();
                this.usingSentinel = true;
                logger.info("Successfully connected to Redis using Sentinel");
            } catch (Exception e) {
                logger.error("Failed to initialize Redis with Sentinel: {}", e.getMessage());
                dumpErrorsExit("Failed to initialize Redis with Sentinel: " + e.getMessage());
                // Fallback to direct connection
                // initDirectConnection(host, port, password);
            }
        } else {
            // Use direct connection
            System.err.println("Redis Sentinel configuration not provided, falling back to direct connection");
            initDirectConnection(host, port, password);
        }
    }

    /**
     * Initialize a direct connection to Redis
     */
    private void initDirectConnection(String host, int port, String password) {
        logger.info("Connecting to Redis directly at " + host + ":" + port);
        this.jedis = new Jedis(host, port);
        if (password != null && !password.isEmpty()) {
            jedis.auth(password);
        }
        logger.info("Successfully connected to Redis directly");
    }

    /**
     * Check if the Redis connection is still valid
     * 
     * @return true if connection is valid, false otherwise
     */
    private boolean isConnectionValid() {
        if (jedis == null) {
            return false;
        }

        try {
            String response = jedis.ping();
            return "PONG".equals(response);
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Reconnect to Redis if the connection is broken
     */
    private synchronized void reconnect() {
        logger.warn("Attempting to reconnect to Redis...");

        // Close existing connection if it exists
        if (jedis != null) {
            try {
                jedis.close();
            } catch (Exception e) {
                // Ignore exceptions during close
            }
        }

        // If we were using sentinel, try to reconnect with sentinel first
        if (usingSentinel && sentinelHosts != null && masterName != null) {
            try {
                // If pool is closed or null, recreate it
                if (jedisPool == null || jedisPool.isClosed()) {
                    Set<String> sentinels = new HashSet<>(Arrays.asList(sentinelHosts.split(",")));
                    JedisPoolConfig poolConfig = new JedisPoolConfig();

                    if (redisPassword != null && !redisPassword.isEmpty()) {
                        this.jedisPool = new JedisSentinelPool(masterName, sentinels, poolConfig, redisPassword);
                    } else {
                        this.jedisPool = new JedisSentinelPool(masterName, sentinels, poolConfig);
                    }
                }

                this.jedis = jedisPool.getResource();
                logger.info("Successfully reconnected to Redis using Sentinel");
                return;
            } catch (Exception e) {
                logger.error("Failed to reconnect using Sentinel: {}", e.getMessage());
            }
        }

        // Never try direct connection as fallback
        // try {
        // initDirectConnection(redisHost, redisPort, redisPassword);
        // usingSentinel = false; // We're now using direct connection
        // } catch (Exception e) {
        // System.err.println("Failed to reconnect directly: " + e.getMessage());
        // throw new RuntimeException("Could not reconnect to Redis", e);
        // }
    }

    /**
     * Execute a Redis operation with automatic reconnection on failure
     */
    private <T> T executeWithReconnection(RedisOperation<T> operation) {
        int maxRetries = 3;
        int retryDelayMs = 2000;

        for (int attempt = 0; attempt <= maxRetries; attempt++) {
            Jedis jedis = null;
            try {
                // Get a fresh connection from pool for each operation
                jedis = jedisPool.getResource();
                return operation.execute(jedis);
            } catch (JedisConnectionException e) {
                logger.info("Redis connection error (attempt " + (attempt + 1) + "): " + e.getMessage());
                if (attempt == maxRetries) {
                    throw e;
                }
                try {
                    Thread.sleep(retryDelayMs);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException("Thread interrupted during Redis retry", ie);
                }
                retryDelayMs *= 2;
            } finally {
                // Always return connection to pool
                if (jedis != null) {
                    jedis.close();
                }
            }
        }
        throw new RuntimeException("Unexpected error in Redis retry mechanism");
    }

    /**
     * Functional interface for Redis operations
     */
    @FunctionalInterface
    private interface RedisOperation<T> {
        T execute(Jedis jedis);
    }

    /**
     * Helper method to safely get string value, handling potential data type issues
     */
    private String safeGetString(Jedis jedis, String key) {
        try {
            // First check if key exists and its type
            if (!jedis.exists(key)) {
                return null;
            }

            String keyType = jedis.type(key);

            // Handle different data types that might be stored
            switch (keyType) {
                case "string":
                    return jedis.get(key);
                case "hash":
                    // If it's a hash, try to get a specific field or convert to string
                    logger.warn("Key '{}' is a hash, attempting to retrieve as string", key);
                    return null;
                case "list":
                    logger.warn("Key '{}' is a list, cannot retrieve as string", key);
                    return null;
                case "set":
                    logger.warn("Key '{}' is a set, cannot retrieve as string", key);
                    return null;
                case "zset":
                    logger.warn("Key '{}' is a sorted set, cannot retrieve as string", key);
                    return null;
                case "none":
                    logger.debug("Key '{}' does not exist", key);
                    return null;
                default:
                    logger.warn("Key '{}' has unknown type: {}", key, keyType);
                    // Try to delete the corrupted key and return null
                    try {
                        // jedis.del(key);
                        logger.info("pls deleted corrupted key: {}", key);
                    } catch (Exception deleteEx) {
                        logger.error("Failed to delete corrupted key '{}': {}", key, deleteEx.getMessage());
                    }
                    return null;
            }
        } catch (ClassCastException e) {
            logger.error("ClassCastException when getting string value for key '{}': {}", key, e.getMessage());
            // Try to delete the corrupted key
            try {
                // jedis.del(key);
                logger.info("Pls deleted corrupted key after ClassCastException: {}", key);
            } catch (Exception deleteEx) {
                logger.error("Failed to delete corrupted key '{}' after ClassCastException: {}", key,
                        deleteEx.getMessage());
            }
            return null;
        } catch (Exception e) {
            logger.error("Error getting string value for key '{}': {}", key, e.getMessage());
            return null;
        }
    }

    /**
     * Helper method to safely get set members, handling potential data type issues
     */
    private Set<String> safeGetSetMembers(Jedis jedis, String key) {
        try {
            // First check if key exists
            if (!jedis.exists(key)) {
                return new HashSet<>();
            }

            String keyType = jedis.type(key);
            if (!"set".equals(keyType)) {
                logger.error("Warning: Expected set for key '" + key + "' but found type: {}", keyType);
                return new HashSet<>();
            }

            return jedis.smembers(key);
        } catch (Exception e) {
            logger.error("Error getting set members for key '" + key + "': {}", e.getMessage());
            return new HashSet<>();
        }
    }

    /**
     * Helper method to safely add to set, handling potential data type issues
     */
    private Long safeSetAdd(Jedis jedis, String key, String value) {
        try {
            // Check if key exists and has wrong type
            if (jedis.exists(key)) {
                String keyType = jedis.type(key);
                if (!"set".equals(keyType)) {
                    logger.error("Warning: Key '" + key + "' has type '" + keyType
                            + "', expected 'set'. Deleting and recreating.");
                    jedis.del(key);
                }
            }

            return jedis.sadd(key, value);
        } catch (Exception e) {
            logger.error("Error adding to set for key '" + key + "': " + e.getMessage());
            return 0L;
        }
    }

    /**
     * Gets the set of processed task IDs
     * 
     * @return Set of processed task IDs
     */
    public Set<String> getProcessedTaskIds() {
        return processedTaskIds;
    }

    /**
     * Sets the processed task IDs
     * 
     * @param processedTaskIds The set of task IDs to set
     */
    public void setProcessedTaskIds(Set<String> processedTaskIds) {
        this.processedTaskIds = processedTaskIds;
    }

    /**
     * Adds a task ID to the set of processed/completed tasks
     * 
     * @param taskId The task ID to add
     */
    public void addProcessedTaskId(String taskId) {
        this.processedTaskIds.add(taskId);
    }

    /**
     * Retrieves the public build information for a task.
     * 
     * @param taskId The task ID
     * @return The JSON string containing public build information, or null if not
     *         found
     */
    public String getPublicBuildInfo(String taskId) {
        return executeWithReconnection(j -> {
            String key = PUBLIC_BACKUP_PREFIX + taskId;
            return safeGetString(j, key);
        });
    }

    /**
     * Checks if the public build was successful based on the JSON response.
     * 
     * @param jsonData The JSON string from public build info
     * @return true if status is "success", false otherwise
     */
    public boolean isPublicBuildSuccessful(String jsonData) {
        if (jsonData == null || jsonData.isEmpty()) {
            return false;
        }

        try {
            // Parse JSON using Gson
            com.google.gson.JsonObject jsonObject = gson.fromJson(jsonData, com.google.gson.JsonObject.class);

            // Check if status field exists and equals "success"
            if (jsonObject.has("status")) {
                String status = jsonObject.get("status").getAsString();
                return "success".equals(status);
            }

            return false;
        } catch (Exception e) {
            System.err.println("Error parsing public build JSON: " + e.getMessage());
            return false;
        }
    }

    public String getNextTaskId() {
        return executeWithReconnection(j -> {
            Set<String> tasks = safeGetSetMembers(j, TASK_STATUS_KEY);
            if (tasks.isEmpty()) {
                return null;
            }
            return tasks.iterator().next();
        });
    }

    /**
     * Gets up to the specified number of available task IDs.
     * 
     * @param maxTasks Maximum number of tasks to retrieve
     * @return List of task IDs
     */
    public List<String> getNextTaskIds(int maxTasks) {
        return executeWithReconnection(j -> {
            List<String> taskIds = new ArrayList<>();
            Set<String> tasks = safeGetSetMembers(j, TASK_STATUS_KEY);

            // for local thread
            if (!processedTaskIds.isEmpty()) {
                System.out.println("Skip completed tasks:");
                for (String taskId : processedTaskIds) {
                    System.out.println("\t" + taskId);
                }
                tasks.removeAll(processedTaskIds);
            }

            // for global tasks
            Set<String> doneTasks = getAllDoneTasks();
            if (!doneTasks.isEmpty()) {
                System.out.println("Removing already done tasks from consideration:");
                for (String doneTaskId : doneTasks) {
                    if (tasks.contains(doneTaskId)) {
                        System.out.println("\t" + doneTaskId);
                    }
                }
                tasks.removeAll(doneTasks);
            }

            if (tasks.isEmpty()) {
                return taskIds;
            }

            Iterator<String> iterator = tasks.iterator();
            int count = 0;

            // Get tasks up to the maximum or as many as are available
            while (iterator.hasNext() && count < maxTasks) {
                taskIds.add(iterator.next());
                count++;
            }

            // Shuffle the taskIds before returning
            java.util.Collections.shuffle(taskIds);

            return taskIds;
        });
    }

    public void markTaskStatus(String taskId) {
        executeWithReconnection(j -> {
            safeSetAdd(j, JAVASLICE_TASK_STATUS_KEY, taskId);
            return null;
        });
    }

    public void markTaskDone(String taskId) {
        executeWithReconnection(j -> {
            safeSetAdd(j, JAVASLICE_TASK_DONE_KEY, taskId);
            return null;
        });
    }

    /**
     * Gets all task IDs that are marked as done.
     *
     * @return A set of task IDs that are done.
     */
    public Set<String> getAllDoneTasks() {
        return executeWithReconnection(j -> safeGetSetMembers(j, JAVASLICE_TASK_DONE_KEY));
    }

    /**
     * Dumps error message to log file and exits with code 255.
     *
     * @param errorMessage The error message to log
     */
    public void dumpErrorsExit(String errorMessage) {
        try {
            java.nio.file.Path logPath = java.nio.file.Paths.get("/crs/javaslice/last_exception.log");
            java.nio.file.Files.createDirectories(logPath.getParent());
            java.nio.file.Files.write(logPath, (errorMessage + "\n").getBytes(),
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND);
        } catch (Exception e) {
            System.err.println("Failed to write error to log file: " + e.getMessage());
        }
        System.exit(255);
    }

    public Task getTaskDetails(String taskId) {
        return executeWithReconnection(j -> {
            String key = JAVASLICE_TASK_PREFIX + taskId;
            String jsonData = safeGetString(j, key);
            if (jsonData == null) {
                return null;
            }
            try {
                return gson.fromJson(jsonData, Task.class);
            } catch (Exception e) {
                System.err.println("Error parsing task JSON for " + taskId + ": " + e.getMessage());
                System.err.println("JSON data: " + jsonData);
                dumpErrorsExit(
                        "Error parsing task JSON for " + taskId + ": " + e.getMessage() + "\nJSON data: " + jsonData);
                return null;
            }
        });
    }

    /**
     * Saves a result string for a specific task.
     *
     * @param taskId The task ID
     * @param result The result string to save
     */
    public void saveTaskResult(String taskId, String result) {
        executeWithReconnection(j -> {
            String key = JAVASLICE_TASK_PREFIX + taskId + TASK_RESULT_SUFFIX;
            j.set(key, result);
            return null;
        });
    }

    /**
     * Retrieves the result string for a specific task.
     *
     * @param taskId The task ID
     * @return The result string, or null if not found
     */
    public String getTaskResult(String taskId) {
        return executeWithReconnection(j -> {
            String key = JAVASLICE_TASK_PREFIX + taskId + TASK_RESULT_SUFFIX;
            return safeGetString(j, key);
        });
    }

    /**
     * Process a single task (kept for backward compatibility)
     */
    public void processNextTask(TaskProcessor processor) {
        String taskId = getNextTaskId();
        if (taskId == null) {
            System.out.println("No tasks available");
            return;
        }

        // Mark task status
        markTaskStatus(taskId);

        // Get task details
        Task task = getTaskDetails(taskId);
        if (task == null) {
            System.out.println("[OLD VERSION LOG]Task details not found for ID: " + taskId);
            return;
        }

        // Process the task
        processor.processTask(task);
    }

    @Override
    public void close() {
        if (jedis != null) {
            jedis.close();
        }

        // Close the pool if we're using sentinel
        if (usingSentinel && jedisPool != null) {
            jedisPool.close();
        }
    }

    @FunctionalInterface
    public interface TaskProcessor {
        void processTask(Task task);
    }
}
