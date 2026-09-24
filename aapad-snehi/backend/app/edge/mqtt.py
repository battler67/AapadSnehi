from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from ..config import settings
from ..database import SessionLocal
from .schemas import TelemetryEnvelope
from .service import EdgeConflictError, EdgeNotFoundError, EdgeValidationError, ingest_telemetry


logger = logging.getLogger(__name__)


class MQTTIngestionAdapter:
    """Optional broker adapter; HTTP and the in-process simulator remain the default."""

    def __init__(self) -> None:
        self.client: Any | None = None

    def start(self) -> None:
        if not settings.edge_mqtt_enabled:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:  # pragma: no cover - optional dependency boundary
            logger.warning("MQTT requested but paho-mqtt is unavailable")
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aapadsnehi-edge-ingestion")

        def on_connect(active_client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
            if int(reason_code) == 0:
                active_client.subscribe(settings.edge_mqtt_topic, qos=1)
            else:
                logger.error("MQTT connection failed: %s", reason_code)

        def on_message(_client: Any, _userdata: Any, message: Any) -> None:
            try:
                payload = TelemetryEnvelope.model_validate_json(message.payload)
                with SessionLocal() as db:
                    ingest_telemetry(db, payload, source_protocol="mqtt")
            except (ValidationError, EdgeConflictError, EdgeNotFoundError, EdgeValidationError) as exc:
                logger.warning("Rejected MQTT telemetry on %s: %s", message.topic, exc)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.warning("Invalid MQTT JSON on %s: %s", message.topic, exc)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect_async(settings.edge_mqtt_host, settings.edge_mqtt_port, keepalive=30)
        client.loop_start()
        self.client = client

    def stop(self) -> None:
        if self.client is not None:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None


mqtt_ingestion = MQTTIngestionAdapter()
