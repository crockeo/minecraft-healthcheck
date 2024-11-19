import logging
import os
import signal
import socket
import time
from dataclasses import dataclass
from threading import Event, Thread
from typing import Callable, Self

import prometheus_client

logger = logging.getLogger(__name__)


@dataclass
class Environ:
    minecraft_host: str
    minecraft_port: int
    prometheus_host: str
    prometheus_port: int

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            minecraft_host=os.environ.get("MINECRAFT_HOST", "127.0.0.1"),
            minecraft_port=int(os.environ.get("MINECRAFT_PORT", "19132")),
            prometheus_host=os.environ.get("PROMETHEUS_HOST", "127.0.0.1"),
            prometheus_port=int(os.environ.get("PROMETHEUS_PORT", "9001")),
        )


class HealthcheckResult:
    def __init__(self, prefix: str) -> None:
        self.attempt_counter = prometheus_client.Counter(
            f"{prefix}:attempt", "Number of attempted healthchecks."
        )
        self.healthy_gauge = prometheus_client.Gauge(
            f"{prefix}:healthy",
            "1 if the server is healthy. 0 if the server is unhealthy or not checked.",
        )
        self.unhealthy_gauge = prometheus_client.Gauge(
            f"{prefix}:unhealthy",
            "1 if the server is unhealthy. 0 if the server is unhealthy or not checked.",
        )

    def mark_attempt(self) -> None:
        self.attempt_counter.inc()

    def mark_healthy(self) -> None:
        self.healthy_gauge.set(1)
        self.unhealthy_gauge.set(0)

    def mark_unhealthy(self) -> None:
        self.healthy_gauge.set(0)
        self.unhealthy_gauge.set(1)


def ping_minecraft_server_main(environ: Environ, shutdown: Event) -> None:
    healthcheck_result = HealthcheckResult("minecraft:healthcheck")
    time_since_last_ping = 0.0
    last_time = time.monotonic()
    while not shutdown.is_set():
        now = time.monotonic()
        time_since_last_ping += now - last_time
        last_time = now

        if time_since_last_ping > 5.0:
            time_since_last_ping = 0.0
            logger.info("Attempting healthcheck")
            healthcheck_result.mark_attempt()
            try:
                sock = socket.socket(socket.AF_INET)
                sock.connect((environ.minecraft_host, environ.minecraft_port))
                sock.close()
                logger.info("Healthcheck succeeded")
                healthcheck_result.mark_healthy()
            except ConnectionRefusedError:
                logger.error("Healthcheck failed", exc_info=True)
                healthcheck_result.mark_unhealthy()

        time.sleep(0.1)


def signal_handler(shutdown: Event) -> Callable[..., None]:
    def _signal_handler(*args, **kwargs):
        print("Shutting down...")
        shutdown.set()

    return _signal_handler


def main() -> None:
    environ = Environ.from_env()
    shutdown = Event()

    handler = signal_handler(shutdown)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    server, server_thread = prometheus_client.start_http_server(
        addr=environ.prometheus_host,
        port=environ.prometheus_port,
    )

    healthcheck_thread = Thread(
        target=ping_minecraft_server_main,
        args=[environ, shutdown],
    )
    healthcheck_thread.start()

    shutdown.wait()

    print("Shutting down prometheus server...")
    server.shutdown()
    server_thread.join()

    print("Shutting down healthcheck thread...")
    healthcheck_thread.join()


if __name__ == "__main__":
    main()
