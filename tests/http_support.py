from contextlib import contextmanager
import socket
import threading
import time

import uvicorn

import first_step
from api import create_app
from api_client import ApiClient

WAIT_TIMEOUT = 10
POLL_INTERVAL = 0.005


def wait_until(check):
    deadline = time.monotonic() + WAIT_TIMEOUT

    while time.monotonic() < deadline:
        result = check()

        if result:
            return result

        time.sleep(POLL_INTERVAL)

    raise AssertionError("HTTP test timed out")


@contextmanager
def running_api(test_mode=True):
    first_step.actors.clear()
    first_step.instructions.clear()
    first_step.responses.clear()

    application = create_app(test_mode=test_mode)
    config = uvicorn.Config(
        application, log_level="error", access_log=False,
        loop="asyncio", ws="none",
    )
    server = uvicorn.Server(config)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True,
        )
        thread.start()
        client = ApiClient(f"http://127.0.0.1:{port}")

        try:
            wait_until(lambda: server.started)
            yield client
        finally:
            client.close()
            server.should_exit = True
            thread.join(timeout=WAIT_TIMEOUT)
            if thread.is_alive():
                raise AssertionError("HTTP test server did not stop")
