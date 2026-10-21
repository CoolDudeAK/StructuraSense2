"""Tiny in-process pub/sub used for Server-Sent Events (live dashboard updates)."""
import json
import queue
import threading

_subs = set()
_lock = threading.Lock()


def publish(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
    with _lock:
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass  # slow client: drop, it will resync on next event


def stream():
    q = queue.Queue(maxsize=300)
    with _lock:
        _subs.add(q)
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                yield q.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"
    finally:
        with _lock:
            _subs.discard(q)


def subscriber_count():
    with _lock:
        return len(_subs)
