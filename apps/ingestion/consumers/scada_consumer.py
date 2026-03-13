"""
Kelmarsh SCADA Kafka consumer.

Consumes messages from the `scada.raw.10min` topic and writes validated
SCADAReading objects to TimescaleDB via the REST ingest endpoint.

A second consumer group also subscribes to `scada.anomalies` and logs
detected anomaly events.

Usage:
    python -m consumers.scada_consumer
    python -m consumers.scada_consumer --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import httpx
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared.config.settings import settings
from shared.models.domain import SCADAReading, AnomalyEvent
from shared.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────
API_BASE_URL = "http://localhost:8000"
INGEST_ENDPOINT = f"{API_BASE_URL}/api/v1/scada/ingest"
BATCH_SIZE = 50          # readings to accumulate before flushing to API
FLUSH_INTERVAL_S = 30.0  # also flush every N seconds even if batch not full


# ─────────────────────────────────────────────────────────────
#  SCADA readings consumer
# ─────────────────────────────────────────────────────────────

async def consume_scada(dry_run: bool = False) -> None:
    """
    Consume SCADA readings from Kafka and batch-ingest them into TimescaleDB.

    Reads from: settings.kafka_topic_scada_raw  (default: scada.raw.10min)
    Writes to:  POST /api/v1/scada/ingest
    """
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_scada_raw,
        bootstrap_servers=settings.kafka_brokers,
        group_id=f"{settings.kafka_consumer_group}.scada-ingest",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        session_timeout_ms=30_000,
        heartbeat_interval_ms=10_000,
    )

    try:
        await consumer.start()
        logger.info(
            "SCADA consumer started",
            topic=settings.kafka_topic_scada_raw,
            brokers=settings.kafka_brokers,
        )
    except KafkaConnectionError as exc:
        logger.error("Cannot connect to Kafka", error=str(exc))
        sys.exit(1)

    batch: List[dict] = []
    last_flush = asyncio.get_event_loop().time()
    total_ingested = 0

    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            async for msg in consumer:
                try:
                    reading_data = msg.value
                    # Validate with Pydantic before forwarding
                    reading = SCADAReading(**reading_data)
                    batch.append(reading.model_dump(mode="json"))
                except Exception as exc:
                    logger.warning(
                        "Invalid reading — skipped",
                        offset=msg.offset,
                        partition=msg.partition,
                        error=str(exc),
                    )
                    continue

                now = asyncio.get_event_loop().time()
                should_flush = (
                    len(batch) >= BATCH_SIZE
                    or (now - last_flush) >= FLUSH_INTERVAL_S
                )

                if should_flush and batch:
                    if dry_run:
                        logger.info("DRY RUN — would ingest", count=len(batch))
                    else:
                        ingested = await _flush_batch(http, batch)
                        total_ingested += ingested
                        logger.info(
                            "Batch flushed",
                            ingested=ingested,
                            total=total_ingested,
                            lag=msg.offset,
                        )
                    batch = []
                    last_flush = now

        except asyncio.CancelledError:
            # Flush any remaining readings before shutdown
            if batch and not dry_run:
                await _flush_batch(http, batch)
            logger.info("Consumer cancelled", total_ingested=total_ingested)
        finally:
            await consumer.stop()
            logger.info("Consumer stopped", total_ingested=total_ingested)


async def _flush_batch(http: httpx.AsyncClient, batch: List[dict]) -> int:
    """POST a batch of readings to the ingest endpoint; returns accepted count."""
    try:
        response = await http.post(
            INGEST_ENDPOINT,
            json={"readings": batch, "source": "kafka-consumer"},
        )
        response.raise_for_status()
        result = response.json()
        if result.get("rejected", 0) > 0:
            logger.warning(
                "Some readings rejected by API",
                rejected=result["rejected"],
                accepted=result["accepted"],
            )
        return result.get("accepted", 0)
    except httpx.HTTPError as exc:
        logger.error("HTTP error during batch ingest", error=str(exc), batch_size=len(batch))
        return 0


# ─────────────────────────────────────────────────────────────
#  Anomaly events consumer
# ─────────────────────────────────────────────────────────────

async def consume_anomalies(dry_run: bool = False) -> None:
    """
    Consume anomaly events from Kafka and log / acknowledge them.

    Reads from: settings.kafka_topic_anomalies  (default: scada.anomalies)
    """
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_anomalies,
        bootstrap_servers=settings.kafka_brokers,
        group_id=f"{settings.kafka_consumer_group}.anomaly-log",
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    try:
        await consumer.start()
        logger.info("Anomaly consumer started", topic=settings.kafka_topic_anomalies)
    except KafkaConnectionError as exc:
        logger.error("Cannot connect to Kafka (anomaly consumer)", error=str(exc))
        return

    try:
        async for msg in consumer:
            try:
                event = AnomalyEvent(**msg.value)
                logger.warning(
                    "Anomaly event received",
                    turbine=event.turbine_id,
                    severity=event.severity.value,
                    score=event.score,
                    model=event.model_name,
                    description=event.description,
                )
            except Exception as exc:
                logger.error("Invalid anomaly event", error=str(exc))
    except asyncio.CancelledError:
        logger.info("Anomaly consumer cancelled")
    finally:
        await consumer.stop()


# ─────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────

async def main(mode: str, dry_run: bool) -> None:
    if mode == "scada":
        await consume_scada(dry_run=dry_run)
    elif mode == "anomalies":
        await consume_anomalies(dry_run=dry_run)
    else:
        # Run both consumers concurrently
        await asyncio.gather(
            consume_scada(dry_run=dry_run),
            consume_anomalies(dry_run=dry_run),
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SCADA / anomaly Kafka consumer")
    p.add_argument(
        "--mode",
        choices=["scada", "anomalies", "all"],
        default="all",
        help="Which consumer(s) to run (default: all)",
    )
    p.add_argument("--dry-run", action="store_true", help="Parse only — do not write to API")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        asyncio.run(main(mode=args.mode, dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
