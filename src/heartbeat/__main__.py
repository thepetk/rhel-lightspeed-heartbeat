import argparse
import asyncio
import sys

from heartbeat.config import HeartbeatConfig
from heartbeat.runner import HeartbeatRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check probe for services with Slack alerting")
    parser.add_argument("config", help="Path to YAML configuration file")
    args = parser.parse_args()

    config = HeartbeatConfig.from_file(args.config)
    runner = HeartbeatRunner(config)
    results = asyncio.run(runner.run())
    if config.fail_on_unhealthy and any(not r.is_ok for r in results):
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
