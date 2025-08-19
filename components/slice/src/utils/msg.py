import pika
import logging
import functools
import threading
import traceback

class MsgQueue:
    def __init__(self, url, queue, debug = False):
        if debug:
            logging.debug('Connecting to RabbitMQ at %s', url)
        self.queue = queue
        self.connection = pika.BlockingConnection(pika.URLParameters(url))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=queue, durable = True)
        self.threads = []

    def send(self, msg):
        self.channel.basic_publish(exchange='', routing_key=self.queue, body=msg)

    def close(self):
        self.connection.close()

    def consume(self, callback):
        self.channel.basic_consume(queue=self.queue, on_message_callback=callback, auto_ack=True)
        self.channel.start_consuming()

    def _ack_message(self, ch, delivery_tag, nack = False):
        if ch.is_open:
            if nack:
                ch.basic_nack(delivery_tag, requeue=True)
            else:
                ch.basic_ack(delivery_tag)
                logging.debug('Acknowledged message %s', delivery_tag)
        else:
            logging.error('Channel is closed, cannot acknowledge message')
            # then do what?
    
    def _callback_wrapper(self, callback):
        # we need functional programming here!
        # callback: (channel, method, properties, body) -> None
        def _thread_callback_wrapper(callback):
            def __thread_callback(connection, ch, method, properties, body):
                try:
                    # raise Exception('test')
                    callback(ch, method, properties, body)
                except Exception as e:
                    logging.error('Failed to process message: %s', e)
                    logging.error('Trackbace %s', traceback.format_exc())
                    cb = functools.partial(self._ack_message, ch, method.delivery_tag, nack=True)
                    connection.add_callback_threadsafe(cb)
                    return 
                cb = functools.partial(self._ack_message, ch, method.delivery_tag)
                connection.add_callback_threadsafe(cb)
            return __thread_callback
        def __callback(ch, method, properties, body, args):
            (connection, threads) = args
            # delivery_tag = method.delivery_tag
            t = threading.Thread(target=_thread_callback_wrapper(callback), args=(connection, ch, method, properties, body))
            t.start()
            threads.append(t)
        return __callback
    
    def threaded_consume(self, callback):
        # TODO: modify this number
        self.channel.basic_qos(prefetch_count=3)
        on_message_callback = functools.partial(self._callback_wrapper(callback), args=(self.connection, self.threads))
        self.channel.basic_consume(queue=self.queue, on_message_callback=on_message_callback)
        self.channel.start_consuming()