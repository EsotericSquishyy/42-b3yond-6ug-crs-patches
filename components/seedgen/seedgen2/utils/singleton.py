import threading
import functools

def singleton(cls):
    """
    A singleton decorator for classes.
    """

    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

def tls_singleton(cls):
    """
    A thread-local singleton decorator for classes.
    Every thread will have its own instance of the singleton.
    """
    local = threading.local()

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if not hasattr(local, 'instances'):
            local.instances = {}
        if cls not in local.instances:
            local.instances[cls] = cls(*args, **kwargs)
        return local.instances[cls]
    
    return get_instance