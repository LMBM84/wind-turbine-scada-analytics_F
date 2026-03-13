#!/usr/bin/env python3
"""
Create required Kafka/Redpanda topics with correct partition and retention settings.
Run once after infrastructure starts: python infra/kafka/create_topics.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Dict

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

sys.path.insert(0, "../../")
from packages.shared.shared.config.settings import settings


@dataclass
class TopicSpec:
    name: str
    partitions: int = 6
    replication_factor: int = 1
    config: Dict[str, str] = field(default_factory=dict)


TOPICS = [
    TopicSpec(
        name=settings.kafka_topic_scada_raw,
        partitions=6,
        config={
            "retention.ms": str(7 * 24 * 3600 * 1000),   # 7 days
            "cleanup.policy": "delete",
            "compression.type": "gzip",
        },
    ),
    TopicSpec(
        name=settings.kafka_topic_anomalies,
        partitions=3,
        config={
            "retention.ms": str(30 * 24 * 3600 * 1000),  # 30 days
            "cleanup.policy": "delete",
        },
    ),
    TopicSpec(
        name=settings.kafka_topic_cms,
        partitions=3,
        config={
            "retention.ms": str(7 * 24 * 3600 * 1000),
            "cleanup.policy": "delete",
            "compression.type": "gzip",
        },
    ),
    TopicSpec(
        name="scada.anomaly.dlq",
        partitions=1,
        config={"retention.ms": str(90 * 24 * 3600 * 1000)},  # 90 days DLQ
    ),
]


def create_topics() -> None:
    admin = KafkaAdminClient(
        bootstrap_servers=settings.kafka_brokers_list,
        client_id="scada-admin",
    )

    new_topics = [
        NewTopic(
            name=t.name,
            num_partitions=t.partitions,
            replication_factor=t.replication_factor,
            topic_configs=t.config,
        )
        for t in TOPICS
    ]

    for topic in TOPICS:
        try:
            admin.create_topics([
                NewTopic(
                    name=topic.name,
                    num_partitions=topic.partitions,
                    replication_factor=topic.replication_factor,
                    topic_configs=topic.config,
                )
            ])
            print(f"  ✅  Created topic: {topic.name} ({topic.partitions} partitions)")
        except TopicAlreadyExistsError:
            print(f"  ⏭   Already exists: {topic.name}")
        except Exception as exc:
            print(f"  ❌  Failed to create {topic.name}: {exc}")

    admin.close()
    print("\nDone.")


if __name__ == "__main__":
    create_topics()
