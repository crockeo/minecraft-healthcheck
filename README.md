# Minecraft Healthcheck

A simple, dumb health checker for a Minecraft Bedrock server.
Checks that the port used by IPv4 connections is open and accessible.
Publishes information to Prometheus so that you can alert if your server goes offline.

## Usage

Designed to be run with [uv](https://github.com/astral-sh/uv):

```shell
$ uv run healthcheck.py
```

Available configuration:

- `MINECRAFT_HOST` = the IPv4 address of the Minecraft server to check. `127.0.0.1` by default.
- `MINECRAFT_PORT` = the port of the Minecraft server to check. `19132` by default.
- `PROMETHEUS_HOST` = the host of the Prometheus server. `127.0.0.1` by default.
- `PROMETHEUS_PORT` = the port of the Prometheus server. `9001` by default.

## License

MIT Open Source license. Check [LICENSE](./LICENSE) for more information.
