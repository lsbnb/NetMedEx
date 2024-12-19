from queue import Queue


def run_thread_with_error_notification(func, queue: Queue):
    """Add None to the queue if any exception occurs."""

    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as e:
            queue.put(None)
            raise e

    return wrapper
