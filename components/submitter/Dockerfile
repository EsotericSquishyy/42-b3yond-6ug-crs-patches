FROM alpine:latest

# Install required packages
RUN apk add --no-cache \
    bash \
    python3 \
    py3-pip

# Install python packages
RUN pip3 install --upgrade pip --break-system-packages
RUN pip3 install --break-system-packages \
    redis \
    requests \
    sqlalchemy \
    psycopg2-binary \
    openlit \
    opentelemetry-api \
    opentelemetry-sdk 


# Copy the source code
COPY . /app

# Set the working directory
WORKDIR /app

# Run the application
CMD ["python3", "app.py"]