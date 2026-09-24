from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import timedelta, timezone

from ..models import EdgeRiskEvent
from .catalog import region_definition
from .service import DEMO_LABEL


CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"


def _iso(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def export_cap(event: EdgeRiskEvent) -> str:
    ET.register_namespace("", CAP_NS)
    tag = lambda name: f"{{{CAP_NS}}}{name}"  # noqa: E731
    root = ET.Element(tag("alert"))
    values = {
        "identifier": f"aapadsnehi-sim-{event.id}",
        "sender": "demo@aapadsnehi.local",
        "sent": _iso(event.updated_at),
        "status": "Test",
        "msgType": "Alert",
        "scope": "Restricted",
        "restriction": "SIMULATED / DEMO ONLY - no public dissemination",
    }
    for key, value in values.items():
        ET.SubElement(root, tag(key)).text = value
    info = ET.SubElement(root, tag("info"))
    mapping = {
        "category": "Geo",
        "event": f"SIMULATED estimated {event.hazard} risk",
        "urgency": "Immediate" if event.state == "CRITICAL" else "Expected",
        "severity": "Extreme" if event.state == "CRITICAL" else "Severe" if event.state == "WARNING" else "Moderate",
        "certainty": "Likely" if event.confidence >= 0.8 else "Possible" if event.confidence >= 0.5 else "Unlikely",
        "effective": _iso(event.last_transition_at),
        "expires": _iso(event.last_transition_at + timedelta(hours=2)),
        "headline": f"{DEMO_LABEL}: estimated {event.hazard} risk {event.state}",
        "description": "Synthetic edge telemetry generated this research-prototype risk event. It is not an official warning.",
        "instruction": "Demo operators should inspect the evidence bundle and follow the human review workflow. Do not disseminate publicly.",
    }
    for key, value in mapping.items():
        ET.SubElement(info, tag(key)).text = value
    area = ET.SubElement(info, tag("area"))
    region = region_definition(event.region_id)
    ET.SubElement(area, tag("areaDesc")).text = str(region["name"])
    ET.SubElement(area, tag("circle")).text = f"{region['latitude']},{region['longitude']} 25"
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
