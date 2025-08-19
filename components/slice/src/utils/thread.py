import threading

class ExceptionThread(threading.Thread):
    def run(self):
        self.exc = None
        try:
            if self._target:
                self._target(*self._args, **self._kwargs)
        except Exception as e:
            self.exc = e

    def join(self, timeout=None):
        super().join(timeout)
        if self.exc:
            raise self.exc

def task():
    raise ValueError("An error occurred in the thread")

if __name__ == "__main__":
    thread = ExceptionThread(target=task)
    thread.start()
    try:
        thread.join()
    except Exception as e:
        print(f"Caught exception: {e}")