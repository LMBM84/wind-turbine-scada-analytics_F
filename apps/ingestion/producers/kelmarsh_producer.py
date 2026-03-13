"""
Kelmarsh SCADA Kafka producer.

Reads Kelmarsh CSV data and publishes 10-minute readings to the
`scada.raw.10min` Kafka topic as JSON-serialised SCADAReading objects.

Modes:
  --replay   : Publish historical data in time-order (simulates real-time replay)
  --live     : Poll a CSV/API source for new records (used with OPC-UA bridge)

Usage:
    python -m producers.kelmarsh_producer --turbine K1 --replay --speed 60
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError

# Add project root to path so packages resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from connectors.kelmarsh.loader import KelmarshConnector
from shared.config.settings import settings
from shared.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


async def produce(
    turbine_id: str,
    data_path: Path,
    speed_multiplier: float = 1.0,
    dry_run: bool = False,
) -> None:
    """
    Replay Kelmarsh data into Kafka.

    Parameters
    ----------
    speed_multiplier : float
        How many real seconds correspond to one 10-minute interval.
        speed=60 → 1 second per interval (600× speedup).
        speed=0  → as fast as possible.
    """
    connector = KelmarshConnector(data_path)
    logger.info("Starting Kelmarsh producer", turbine=turbine_id, speed=speed_multiplier)

    if dry_run:
        logger.info("DRY RUN — no Kafka messages will be sent")
        count = 0
        for reading in connector.stream_readings(turbine_id):
            count += 1
            if count % 1000 == 0:
                logger.info("Dry run progress", count=count, ts=reading.timestamp)
        logger.info("Dry run complete", total=count)
        return

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_brokers,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        compression_type="gzip",
        enable_idempotence=True,
        acks="all",
    )

    try:
        await producer.start()
        logger.info("Connected to Kafka", brokers=settings.kafka_brokers)
    except KafkaConnectionError as exc:
        logger.error("Cannot connect to Kafka", error=str(exc))
        sys.exit(1)

    count = 0
    try:
        for reading in connector.stream_readings(turbine_id):
            payload = reading.model_dump()
            await producer.send_and_wait(
                topic=settings.kafka_topic_scada_raw,
                key=turbine_id,
                value=payload,
            )
            count += 1

            if count % 100 == 0:
                logger.info("Published readings", count=count, ts=reading.timestamp)

            if speed_multiplier > 0:
                await asyncio.sleep(speed_multiplier)

    except asyncio.CancelledError:
        logger.info("Producer cancelled", count=count)
    finally:
        await producer.stop()
        logger.info("Producer stopped", total_published=count)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kelmarsh SCADA Kafka producer")
    p.add_argument("--turbine", default="K1", help="Turbine ID (K1–K6)")
    p.add_argument(
        "--data-path",
        default=str(Path(__file__).resolve().parents[3] / "data" / "raw"),
        help="Path to Kelmarsh ZIP or extracted directory",
    )
    p.add_argument(
        "--speed",
        type=float,
        default=0.0,
        help="Seconds to sleep between messages (0=as fast as possible, 1=real-time replay)",
    )
    p.add_argument("--replay", action="store_true", help="Replay historical data")
    p.add_argument("--dry-run", action="store_true", help="Parse only, do not publish")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        produce(
            turbine_id=args.turbine.upper(),
            data_path=Path(args.data_path),
            speed_multiplier=args.speed,
            dry_run=args.dry_run,
        )
    )
