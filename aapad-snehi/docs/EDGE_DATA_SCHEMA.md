# Edge telemetry data contract

> **SIMULATED / DEMO ONLY.** This schema supports a research prototype, not a public-warning system.

The accepted media type is JSON and the current `schemaVersion` is `1.0`. The shape is inspired by OGC SensorThings: the registry row is a **Thing** with a **Location**; its explicit capabilities describe **Sensors**, **ObservedProperties**, and **Datastreams**; normalized measurement rows are **Observations**. This is internal alignment, not a complete SensorThings API implementation. See the [OGC SensorThings standard](https://www.ogc.org/standards/sensorthings/).

```json
{
  "schemaVersion": "1.0",
  "messageId": "7d21d75c-7c41-469d-8a98-a0ae0c2537ad",
  "deviceId": "river-vizag-01",
  "deviceType": "river_gauge",
  "timestamp": "2026-09-02T09:30:00Z",
  "sequenceNumber": 1024,
  "location": {"latitude": 17.6868, "longitude": 83.2185, "elevationM": 12},
  "measurements": {"rainfallMmH": 24.5, "waterLevelM": 4.2},
  "deviceHealth": {"batteryPct": 81, "signalQualityPct": 73},
  "simulation": {"scenarioId": "flood-gradual-001", "groundTruthState": "warning", "runId": "..."}
}
```

## Validation and normalization

- Pydantic rejects unknown fields, unsupported schema versions, timezone-free timestamps, non-finite/impossible measurements, invalid coordinates, and invalid health percentages.
- Registry validation rejects unknown devices, type mismatches, readings farther than 500 m from registration, unsupported capabilities, timestamps over five minutes in the future or 24 hours stale, duplicate UUIDs, and duplicate per-device sequences.
- Sequence gaps, out-of-order packets, low battery, weak signal, and missing measurements are accepted with quality flags so their impact is visible.
- Measurement values and their configured units are stored in normalized rows. The complete sanitized envelope is retained for evidence.
- `simulation.scenarioId` and `groundTruthState` are stored separately as evaluation metadata. Feature/model code is passed measurements, quality and geographic context only, preventing label leakage.

Units, plausible bounds, demo assumptions, profiles and regions are in [`backend/app/edge/data/edge_config.json`](../backend/app/edge/data/edge_config.json). None of its thresholds are official scientific warning levels.

## Device profiles

| Type | Installed purpose | Properties |
|---|---|---|
| `river_gauge` | flood | rainfall, cumulative rainfall, level, rise rate, flow, soil moisture, temperature, pressure |
| `hillslope_station` | landslide | rainfall, accumulation, soil moisture, pore pressure, two-axis tilt, vibration, slope angle, temperature |
| `coastal_buoy` | tsunami | bottom pressure, sea anomaly/rate, wave height, temperature and optional simulated seismic corroboration |

Register first with `POST /api/edge/devices`, then publish to `POST /api/edge/telemetry`. MQTT uses `aapadsnehi/edge/<deviceId>/telemetry` and the identical JSON body.
