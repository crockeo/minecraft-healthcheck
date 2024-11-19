from pathlib import Path

TEMPLATE = """\
[Unit]
Description=Minecraft Server Healthcheck
After=network-online.target

[Service]
User=minecraft
Group=minecraft
Restart=on-failure
ExecStart=uv {directory}/healthcheck.py
WorkingDirectory={directory}
Environment="PYTHONPATH={directory}"

[Install]
WantedBy=multi-user.target
"""


def main() -> None:
    cwd = Path.cwd()
    (cwd / "minecraft_healthcheck.service").write_text(TEMPLATE.format(directory=cwd))


if __name__ == "__main__":
    main()
