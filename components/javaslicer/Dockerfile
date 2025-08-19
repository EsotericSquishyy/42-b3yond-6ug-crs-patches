# Use a Java base image
FROM ghcr.io/aixcc-finals/afc-crs-42-b3yond-6ug/base-builder-jvm:latest

# Install Maven
RUN apt-get update && apt-get install -y maven

# Set Java 17 as default
RUN update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-17-openjdk-amd64/bin/java 1700 && \
    update-alternatives --set java /usr/lib/jvm/java-17-openjdk-amd64/bin/java && \
    update-alternatives --install /usr/bin/javac javac /usr/lib/jvm/java-17-openjdk-amd64/bin/javac 1700 && \
    update-alternatives --set javac /usr/lib/jvm/java-17-openjdk-amd64/bin/javac

# Set the working directory
WORKDIR /app

# Copy the project files to the container
COPY . .

# Build the project
RUN mvn clean package

# Make sure output directory exists
RUN mkdir -p ./output

# Set the entrypoint command - without specific arguments that will be provided by users
ENTRYPOINT ["java", "-jar", "target/java-signature-generator-1.0-SNAPSHOT-jar-with-dependencies.jar"]

LABEL org.opencontainers.image.source=https://github.com/aixcc-finals/afc-crs-42-b3yond-6ug
LABEL org.opencontainers.image.authors="CRS Java Team"

