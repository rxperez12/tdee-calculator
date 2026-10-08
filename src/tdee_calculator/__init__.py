import os
import sys
import threading
import time
import webbrowser
from urllib import request

import uvicorn

from tdee_calculator.app import create_app
from tdee_calculator.config import load_config
from tdee_calculator.db import prepare


def _open_browser_when_ready(
    url: str,
    *,
    timeout: float = 10,
    poll_interval: float = 0.1,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with request.urlopen(url, timeout=1):
                webbrowser.open(url)
                return
        except OSError:
            # URLError, timeouts, and connection resets while uvicorn starts.
            time.sleep(poll_interval)

    print(f"Open {url} in your browser.", file=sys.stderr)


def main() -> None:
    config = load_config()
    prepare(config)
    url = f"http://{config.host}:{config.port}"

    if os.environ.get("TDEE_NO_BROWSER") != "1":
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url,),
            daemon=True,
        ).start()

    uvicorn.run(create_app(config), host=config.host, port=config.port)
