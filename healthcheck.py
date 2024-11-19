import logging
import os
import random
import secrets
import signal
import socket
import struct
import time
from dataclasses import dataclass
from io import BytesIO
from threading import Event, Thread
from typing import Callable, Self

import prometheus_client

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Magic value defined in the RakNet protocol.
# Don't ask me where it's from...
MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")


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


def build_ping_packet() -> bytes:
    buf = BytesIO()
    buf.write(b"\x01")
    buf.write(int(time.time()).to_bytes(8, "big"))
    buf.write(MAGIC)
    buf.write(random.randbytes(8))
    return buf.getvalue()


def create_unconnected_ping_frame(start_time: int):
    packet = bytearray(33)
    packet[0] = 0x01
    struct.pack_into("<Q", packet, 1, int((time.time() * 1000) - start_time))
    packet[9:25] = MAGIC
    packet[25:33] = secrets.token_bytes(8)
    return bytes(packet)


def ping_bedrock(environ: Environ, start_time: int, timeout: float = 1.0) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    try:
        ping_packet = create_unconnected_ping_frame(start_time)
        sock.sendto(ping_packet, (environ.minecraft_host, environ.minecraft_port))

        pong_packet, _ = sock.recvfrom(1024)
        if pong_packet[0] == 0x1C:
            return True
        return False
    finally:
        sock.close()


def ping_minecraft_server_main(environ: Environ, shutdown: Event) -> None:
    healthcheck_result = HealthcheckResult("minecraft:healthcheck")
    start_time = int(time.time() * 1000)
    time_since_last_ping = 0.0
    last_time = time.monotonic()
    while not shutdown.is_set():
        now = time.monotonic()
        time_since_last_ping -= now - last_time
        last_time = now

        if time_since_last_ping <= 0.0:
            time_since_last_ping = 1.0
            logger.info(
                f"Attempting healthcheck {environ.minecraft_host}:{environ.minecraft_port}"
            )
            healthcheck_result.mark_attempt()
            try:
                healthy = ping_bedrock(environ, start_time)
            except ConnectionRefusedError:
                healthy = False

            if healthy:
                logger.info("Healthcheck succeeded")
                healthcheck_result.mark_healthy()
            else:
                logger.error("Healthcheck failed", exc_info=True)
                healthcheck_result.mark_unhealthy()

        time.sleep(0.1)


def signal_handler(shutdown: Event) -> Callable[..., None]:
    def _signal_handler(*args, **kwargs):
        if shutdown.is_set():
            exit(1)

        logger.info("Shutting down...")
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

    logger.info("Shutting down prometheus server...")
    server.shutdown()
    server_thread.join()

    logger.info("Shutting down healthcheck thread...")
    healthcheck_thread.join()


if __name__ == "__main__":
    main()
