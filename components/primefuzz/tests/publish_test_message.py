import pika
import json
import sys

# RabbitMQ credentials
RABBITMQ_USER = "user"
RABBITMQ_PASSWORD = "secret"

# Define the connection parameters with credentials
connection_parameters = pika.ConnectionParameters(
    host="localhost",
    credentials=pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD),
)

def consume_and_requeue():
    """
    Consumes a single message from java_directed_fuzzing_queue and puts it back.
    """
    # Establish connection
    connection = pika.BlockingConnection(connection_parameters)
    channel = connection.channel()
    
    # Declare the queue to ensure it exists
    channel.queue_declare(queue="java_directed_fuzzing_queue", durable=True)
    
    # Get a single message
    method_frame, header_frame, body = channel.basic_get(
        queue="java_directed_fuzzing_queue", auto_ack=True
    )
    
    if method_frame:
        print(f"Message received from java_directed_fuzzing_queue:")
        print(body.decode())

        print("Message header:")
        print(header_frame)
        
        # Print headers in a more readable format
        if hasattr(header_frame, 'headers'):
            print("Headers dictionary:")
            print(header_frame.headers)
        
        # Publish the message back to the queue with headers properly included in properties
        channel.basic_publish(
            exchange="",
            routing_key="java_directed_fuzzing_queue",
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
                headers=header_frame.headers if hasattr(header_frame, 'headers') else None,
                message_id=header_frame.message_id if hasattr(header_frame, 'message_id') else None
            ),
        )
        print("Message requeued to java_directed_fuzzing_queue")
    else:
        print("No message available in java_directed_fuzzing_queue")
    
    # Close the connection
    connection.close()

if len(sys.argv) > 1:
    if sys.argv[1] == "consume":
        consume_and_requeue()
        exit(0)

# Establish a connection to RabbitMQ
connection = pika.BlockingConnection(connection_parameters)
channel = connection.channel()

# Declare the queue (it will only be created if it doesn't exist)
# channel.queue_declare(
#     queue="general_fuzzing_queue", durable=True, arguments={"x-max-priority": 10}
# )
channel.queue_declare(
    queue="general_fuzzing_queue", durable=True
)

# Convert the message to a JSON string
# message_json = '{"diff":"https://mocktasksdev.blob.core.windows.net/mock-tasks/5cda94e7d7d735f26f7945a57a8e17a13c735295826642838399ff660ff5e772.tar.gz?se=2025-01-31T04%3A45%3A13Z&sp=r&sv=2022-11-02&sr=b&sig=xFJ34M2f6A%2FfI%2B9l2QpvVerqzpGFhShdGzZgHYHdifM%3D","focus":"example-libpng","fuzzing_tooling":"https://mocktasksdev.blob.core.windows.net/mock-tasks/5422baa73b6294e4c4b630213041ac32a490fbd1d43a0dff917a6ed4a11ada41.tar.gz?se=2025-01-31T04%3A45%3A16Z&sp=r&sv=2022-11-02&sr=b&sig=YxVRWWczhWdmw8utu2NdeA3x1H0HnTnSuMbSJ2Axjw0%3D","project_name":"libpng","repo":["https://mocktasksdev.blob.core.windows.net/mock-tasks/e498fc9776c700bfa1e383c7e5aff6c72f4027bd0fa5dcfc8377a72430fc917e.tar.gz?se=2025-01-31T04%3A45%3A14Z&sp=r&sv=2022-11-02&sr=b&sig=8htDGGlT99ROE6UD6w8sUssQgl4v3beQoPDeXZagOZc%3D"],"task_id":"51f81839-7dab-4295-b05b-d67ecdbe35c7","task_type":"delta"}'
message_json = '{"diff":"/crs/3d4d50f9-a8fd-4144-afb5-dde1ed642126/62b11c9f-2443-4ed6-916c-53b484fe3230","focus":"example-libpng","fuzzing_tooling":"/crs/3d4d50f9-a8fd-4144-afb5-dde1ed642126/c6903463-ed73-4d2c-8c08-5c7309d98caa","project_name":"libpng","repo":["/crs/3d4d50f9-a8fd-4144-afb5-dde1ed642126/4db3b1e9-4329-4ac5-8238-04e08ce01106"],"task_id":"3d4d50f9-a8fd-4144-afb5-dde1ed642126","task_type":"delta"}'

message_json = '{"diff":"/crs/7b64a242-5c0f-4d45-ad7d-40fd325deb17/DIFF.tar.gz","focus":"flac","fuzzing_tooling":"/crs/7b64a242-5c0f-4d45-ad7d-40fd325deb17/fuzz-tooling.tar.gz","project_name":"flac","repo":["/crs/7b64a242-5c0f-4d45-ad7d-40fd325deb17/flac.tar.gz"],"task_id":"7b64a242-5c0f-4d45-ad7d-40fd325deb17","task_type":"delta"}'

message_json_java = '{"diff":"/crs/b112a8fe-b98e-44f9-b94b-305a3dba82a0/72e33a98-a5d6-41e4-a6e1-ff7973bbab05","focus":"buggy-exemplar-challenge-jvm-jedis","fuzzing_tooling":"/crs/b112a8fe-b98e-44f9-b94b-305a3dba82a0/02255551-55ab-4f6b-8374-2383a5a40c3a","project_name":"jedis","repo":["/crs/b112a8fe-b98e-44f9-b94b-305a3dba82a0/d6d3e1ee-1017-4422-b270-684dae64e1ef"],"task_id":"b112a8fe-b98e-44f9-b94b-305a3dba82a0","task_type":"delta"}'

message_json_java = '{"diff":"/crs/2b8cb6fc-f3a8-4d15-aaf3-403238a456ea/72e33a98-a5d6-41e4-a6e1-ff7973bbab05","focus":"java-cp-hikaricp","fuzzing_tooling":"/crs/2b8cb6fc-f3a8-4d15-aaf3-403238a456ea/02255551-55ab-4f6b-8374-2383a5a40c3a","project_name":"hikaricp","repo":["/crs/2b8cb6fc-f3a8-4d15-aaf3-403238a456ea/d6d3e1ee-1017-4422-b270-684dae64e1ef"],"task_id":"2b8cb6fc-f3a8-4d15-aaf3-403238a456ea","task_type":"delta"}'


message_json_java_large = '{"diff":"/crs/f64b1422-42ad-406f-b503-74b9f037a4ff/DIFF.tar.gz","focus":"java-cp-logback","fuzzing_tooling":"/crs/f64b1422-42ad-406f-b503-74b9f037a4ff/tooling.tar.gz","project_name":"logback","repo":["/crs/f64b1422-42ad-406f-b503-74b9f037a4ff/59c4b825b6cff07a37e2a8d6a8edcf266ccd6e6b261cd635514575858027fe2f.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"delta"}'

message_json_java_large = '{"diff":"/crs/0195f1f6-117a-788f-aa72-a2365eade509/5b692f153bf7031dcbaa5e68048a6d4615eac5cfd4ca3b66412e8d086d1fcf1b","focus":"round-exhibition1-zookeeper","fuzzing_tooling":"/crs/0195f1f6-117a-788f-aa72-a2365eade509/257f7f81fa92308472c322b78f9753b6a15e7e93608bea1156c07d88883cc1dc","project_name":"zookeeper","repo":["/crs/0195f1f6-117a-788f-aa72-a2365eade509/e3fec6e35acfb015cf93a913ecc355074f596796b18443f9a9bde679fab92068"],"task_id":"0195f1f6-117a-788f-aa72-a2365eade509","task_type":"delta"}'

message_json_java_large = '{"diff":"/crs/81dbd73c-adbf-4f22-a867-5d3948469638/diff.tar.gz","focus":"round-exhibition2-commons-compress","fuzzing_tooling":"/crs/81dbd73c-adbf-4f22-a867-5d3948469638/fuzz-tooling.tar.gz","project_name":"apache-commons-compress","repo":["/crs/81dbd73c-adbf-4f22-a867-5d3948469638/round-exhibition2-commons-compress.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"delta"}'

# message_json_java_large = '{"diff":"/crs/ff3c350a-cc00-4fb3-ac3c-630c2643d844/diff.tar.gz","focus":"round-exhibition3-tika","fuzzing_tooling":"/crs/ff3c350a-cc00-4fb3-ac3c-630c2643d844/fuzz-tooling.tar.gz","project_name":"tika","repo":["/crs/ff3c350a-cc00-4fb3-ac3c-630c2643d844/round-exhibition3-tika.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"delta"}'

# message_json_java_large = '{"focus":"round-exhibition2-commons-compress","fuzzing_tooling":"/crs/81dbd73c-adbf-4f22-a867-5d3948469638/fuzz-tooling.tar.gz","project_name":"apache-commons-compress","repo":["/crs/81dbd73c-adbf-4f22-a867-5d3948469638/round-exhibition2-commons-compress.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"full"}'

# message_json_java_large = '{"focus":"round-exhibition3-tika","fuzzing_tooling":"/crs/e64f8de1-59b5-4ec7-bc09-587bebe0a0c4/fuzz-tooling.tar.gz","project_name":"tika","repo":["/crs/e64f8de1-59b5-4ec7-bc09-587bebe0a0c4/round-exhibition3-tika.tar.gz"],"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"full"}'

if len(sys.argv) > 1:
    message_json = (
        '{"task_id":"3d4d50f9-a8fd-4144-afb5-dde1ed642126","task_type":"cancel"}'
    )
    message_json = (
        '{"task_id":"7b64a242-5c0f-4d45-ad7d-40fd325deb17","task_type":"cancel"}'
    )
    message_json_java = (
        '{"task_id":"2b8cb6fc-f3a8-4d15-aaf3-403238a456ea","task_type":"cancel"}'
    )
    message_json_java_large = (
        '{"task_id":"f64b1422-42ad-406f-b503-74b9f037a4ff","task_type":"cancel"}'
    )
    message_json_java_large = (
        '{"task_id":"0195f1f6-117a-788f-aa72-a2365eade509","task_type":"cancel"}'
    )
    message_json_java_large = (
        '{"task_id":"81dbd73c-adbf-4f22-a867-5d3948469638","task_type":"cancel"}'
    )

# Publish the message to the queue
channel.basic_publish(
    exchange="",
    routing_key="general_fuzzing_queue",
    body=message_json_java_large,
    properties=pika.BasicProperties(
        # priority=0,  # Set the priority of the message
        delivery_mode=2,  # Make message persistent
    ),
)

print("Message published to queue 'general_fuzzing_queue'")

# Close the connection
connection.close()

# Uncomment to consume and requeue a message
# consume_and_requeue()
# curl -u user:secret -H "Content-Type: application/json" \
#  -d '{"count":1,"ackmode":"ack_requeue_false","encoding":"auto"}' \
#  http://localhost:15672/api/queues/%2F/general_fuzzing_queue/get