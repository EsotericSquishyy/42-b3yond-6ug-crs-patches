# JAVA SLICER

A Java program slicer that uses WALA for static analysis.

## Build

Build the project using Maven:

```bash
mvn clean package
```

This will create two JAR files in the `target` directory:
- `java-signature-generator-1.0-SNAPSHOT.jar`
- `java-signature-generator-1.0-SNAPSHOT-jar-with-dependencies.jar`

## Usage

Run the slicer with the following command:

```bash
java -jar target/java-signature-generator-1.0-SNAPSHOT-jar-with-dependencies.jar 
```

### Workflow

1. Task Processing Loop:

* The service connects to Redis and polls for slicing tasks
* Tasks are processed one at a time with a configurable interval between polls

2. Task Processing Steps:

* Validates that the task's public build was successful
* Extracts repositories, diff files, and tooling resources
* Locates the focus directory and applies patches
* Finds and processes all Java class files in the focus directory
* Generates slicing results for each class file
* Copies results to a shared location

3. Task Results:

* Results are stored in a shared location (configured by CRS_MOUNT_PATH)
* The path to results is saved back to Redis for retrieval

### Environment Configuration

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `REDIS_HOST` | Redis server hostname | localhost |
| `REDIS_PORT` | Redis server port | 6379 |
| `WORK_DIR` | Working directory for task processing | /tmp/javaslice |
| `POLL_INTERVAL_SECONDS` | Time between task checks (in seconds) | 60 |
| `CRS_MOUNT_PATH` | Path to CRS mount point | /crs |

### Example

Test as a cli program.

```bash
java  -XX:+ShowCodeDetailsInExceptionMessages -cp <dependencies.jar> org.b3yond.SliceCmdGenerator -cp ./src/main/resources/hikari/ ./src/main/resources/diff/hikari/ref.diff ./src/main/resources/hikari/PropertyElfFuzzer.class ./output/slice_hikaricp_PropertyElfFuzzer 
```

This will:
1. Analyze the code in the specified classpath
2. Generate slicing results based on the diff file
3. Write the results to the output file with extensions `.args` and `.results.txt`

Run as a service

```
java -jar target/java-signature-generator-1.0-SNAPSHOT-jar-with-dependencies.jar
```

## Output

The slicer generates two files:
- `<output_name>.args`: Contains command arguments for further processing
- `<output_name>.results.txt`: Contains the slicing results