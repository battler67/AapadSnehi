from __future__ import annotations

import argparse
import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import EdgeSimulationRun
from .catalog import profile_definition, region_definition, scenario_catalog
from .schemas import DeviceCreate, EdgeLocation, SimulationCreate, TelemetryEnvelope
from .service import EdgeConflictError, ingest_telemetry, register_device


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _progress(step: int, total: int) -> float:
    return step / max(1, total - 1)


def _state(scenario: str, progress: float) -> str:
    if scenario == "normal-operation":
        return "normal"
    if scenario == "sensor-failure-001":
        return "failure" if 0.35 < progress < 0.75 else "normal"
    if progress < 0.22:
        return "normal"
    if progress < 0.42:
        return "watch"
    if progress < 0.72:
        return "warning"
    if "recovery" in scenario or progress > 0.88:
        return "recovery"
    return "critical"


def _measurements(
    device_type: str,
    scenario: str,
    progress: float,
    step: int,
    rng: random.Random,
    device_index: int,
) -> dict[str, float | None]:
    wave = math.sin(step / 8 + device_index) * 0.08
    noise = lambda scale: rng.gauss(0, scale)  # noqa: E731
    event = _clamp((progress - 0.20) / 0.58, 0, 1)
    if "recovery" in scenario and progress > 0.68:
        event *= max(0, 1 - (progress - 0.68) / 0.32)
    if scenario == "false-spike-001":
        event = 1.0 if abs(progress - 0.55) < 0.025 else 0.02
    if scenario == "conflicting-sensors-001" and device_index % 2:
        event *= 0.12
    if scenario == "normal-operation":
        event = 0.0

    if device_type == "river_gauge":
        flash = 1.35 if scenario == "flash-flood-001" else 1.0
        rainfall = 4 + 74 * event * flash + wave * 8 + noise(1.2)
        water = 2.1 + 5.8 * event * flash + wave + noise(0.04)
        return {
            "rainfallMmH": _clamp(rainfall, 0, 500),
            "cumulativeRainfallMm": _clamp(10 + step * max(0, rainfall) / 60, 0, 3000),
            "waterLevelM": _clamp(water, -2, 30),
            "waterLevelRiseMPerH": _clamp(0.05 + 1.8 * event * flash + noise(0.03), -10, 20),
            "flowVelocityMps": _clamp(0.8 + 4.7 * event + noise(0.08), 0, 25),
            "soilMoisturePct": _clamp(42 + 50 * event + noise(1), 0, 100),
            "temperatureC": 27 + math.sin(step / 14) * 1.2 + noise(0.15),
            "atmosphericPressureHpa": 1008 - event * 7 + noise(0.4),
        }
    if device_type == "hillslope_station":
        slope_only = scenario == "landslide-slope-001"
        intensity = event if scenario.startswith("landslide") else event * 0.2
        rainfall = 3 + (5 if slope_only else 72) * intensity + noise(1)
        return {
            "rainfallMmH": _clamp(rainfall, 0, 500),
            "cumulativeRainfallMm": _clamp(15 + step * max(0, rainfall) / 60, 0, 3000),
            "soilMoisturePct": _clamp(48 + (20 if slope_only else 47) * intensity + noise(0.7), 0, 100),
            "poreWaterPressureKpa": _clamp(24 + 170 * intensity + noise(1.5), -20, 1000),
            "groundTiltXDeg": _clamp(0.03 + 2.1 * intensity + noise(0.015), -45, 45),
            "groundTiltYDeg": _clamp(0.02 + 1.5 * intensity + noise(0.015), -45, 45),
            "vibrationRmsMmS": _clamp(1.2 + 25 * intensity + noise(0.4), 0, 500),
            "slopeAngleDeg": _clamp(34 + device_index % 4 + noise(0.1), 0, 90),
            "temperatureC": 19 + math.sin(step / 13) + noise(0.1),
        }
    tsunami = event if scenario == "tsunami-seismic-001" else event * 0.08
    pulse = math.sin(max(0, progress - 0.28) * 38) * tsunami
    return {
        "bottomPressureKpa": _clamp(10120 + 13 * pulse + noise(0.12), 0, 120000),
        "seaLevelAnomalyM": _clamp(1.35 * pulse + noise(0.015), -20, 20),
        "seaLevelRateMPerMin": _clamp(0.16 * math.cos(max(0, progress - 0.28) * 38) * tsunami + noise(0.004), -10, 10),
        "waveHeightM": _clamp(0.8 + 5.2 * abs(pulse) + noise(0.08), 0, 60),
        "waterTemperatureC": 27.4 + noise(0.06),
        "earthquakeMagnitude": _clamp(4.2 + 3.5 * tsunami, 0, 10),
        "earthquakeDepthKm": _clamp(35 - 20 * tsunami, 0, 800),
        "earthquakeDistanceKm": _clamp(1200 - 900 * tsunami, 0, 20000),
    }


def provision_devices(db: Session, run: EdgeSimulationRun, request: SimulationCreate) -> list[DeviceCreate]:
    region = region_definition(request.region)
    scenario = next(item for item in scenario_catalog() if item["id"] == request.scenario)
    preferred = {"flood": "river_gauge", "landslide": "hillslope_station", "tsunami": "coastal_buoy"}.get(scenario["hazard"])
    types = [preferred] * request.number_of_devices if preferred else ["river_gauge", "hillslope_station", "coastal_buoy"]
    devices: list[DeviceCreate] = []
    for index in range(request.number_of_devices):
        device_type = types[index % len(types)]
        profile = profile_definition(device_type)
        angle = index * 2.39996
        radius = 0.015 + (index % 4) * 0.006
        payload = DeviceCreate(
            deviceId=f"sim-{run.run_id[:8]}-{index + 1:02d}",
            name=f"{profile['purposes'][0].title()} demo station {index + 1}",
            deviceType=device_type,
            installedPurposes=profile["purposes"],
            capabilities=profile["capabilities"],
            regionId=request.region,
            expectedIntervalSeconds=request.timestep_seconds,
            simulationOnly=True,
            location=EdgeLocation(
                latitude=region["latitude"] + math.cos(angle) * radius,
                longitude=region["longitude"] + math.sin(angle) * radius,
                elevationM=region["elevationM"],
            ),
        )
        register_device(db, payload, idempotent=True)
        devices.append(payload)
    return devices


class SimulationManager:
    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.paused: set[str] = set()

    async def start(self, request: SimulationCreate, db: Session | None = None) -> str:
        scenario = next(item for item in scenario_catalog() if item["id"] == request.scenario)
        run_id = uuid4().hex
        def create_run(active_db: Session) -> None:
            run = EdgeSimulationRun(
                run_id=run_id,
                scenario_id=request.scenario,
                region_id=request.region,
                seed=request.seed,
                number_of_devices=request.number_of_devices,
                speed_multiplier=request.speed_multiplier,
                timestep_seconds=request.timestep_seconds,
                total_steps=int(scenario["durationSteps"]),
                config_json=request.model_dump_json(by_alias=True),
                status="running",
            )
            active_db.add(run)
            active_db.commit()
        if db is None:
            with SessionLocal() as active_db:
                create_run(active_db)
        else:
            create_run(db)
        self.tasks[run_id] = asyncio.create_task(self._run(run_id, request), name=f"edge-sim-{run_id[:8]}")
        return run_id

    async def _run(self, run_id: str, request: SimulationCreate) -> None:
        rng = random.Random(request.seed)
        replayed_outage: set[int] = set()
        duplicate_attempted = False
        try:
            with SessionLocal() as db:
                run = db.get(EdgeSimulationRun, run_id)
                devices = provision_devices(db, run, request)
                start_time = datetime.now(timezone.utc) - timedelta(seconds=run.total_steps * request.timestep_seconds)
            for step in range(run.total_steps):
                while run_id in self.paused:
                    await asyncio.sleep(0.1)
                with SessionLocal() as db:
                    run = db.get(EdgeSimulationRun, run_id)
                    if not run or run.status == "stopped":
                        return
                    progress = _progress(step, run.total_steps)
                    for index, device in enumerate(devices):
                        if request.scenario == "outage-recovery-001" and 0.38 < progress < 0.60:
                            continue
                        values = _measurements(device.device_type, request.scenario, progress, step, rng, index)
                        if request.scenario == "sensor-failure-001" and index == 0 and 0.35 < progress < 0.75:
                            values = {name: (None if pos % 2 else value) for pos, (name, value) in enumerate(values.items())}
                        packet = TelemetryEnvelope(
                            schemaVersion="1.0",
                            messageId=uuid4(),
                            deviceId=device.device_id,
                            deviceType=device.device_type,
                            timestamp=start_time + timedelta(seconds=step * request.timestep_seconds),
                            sequenceNumber=step,
                            location=device.location,
                            measurements=values,
                            deviceHealth={
                                "batteryPct": _clamp(96 - step * 0.45 - (25 if request.scenario == "sensor-failure-001" else 0), 3, 100),
                                "signalQualityPct": 18 if request.scenario == "outage-recovery-001" and progress < 0.7 else _clamp(82 + rng.gauss(0, 4), 1, 100),
                            },
                            simulation={"scenarioId": request.scenario, "groundTruthState": _state(request.scenario, progress), "runId": run_id},
                        )
                        try:
                            ingest_telemetry(db, packet, source_protocol="simulator")
                            run = db.get(EdgeSimulationRun, run_id)
                            run.emitted_count += 1
                            if request.scenario == "outage-recovery-001" and progress >= 0.60 and index not in replayed_outage:
                                delayed_step = int(run.total_steps * 0.45)
                                delayed = packet.model_copy(update={
                                    "message_id": uuid4(),
                                    "timestamp": start_time + timedelta(seconds=delayed_step * request.timestep_seconds),
                                    "sequence_number": delayed_step,
                                })
                                ingest_telemetry(db, delayed, source_protocol="simulator-buffer-replay")
                                replayed_outage.add(index)
                                run = db.get(EdgeSimulationRun, run_id)
                                run.emitted_count += 1
                            if request.scenario == "false-spike-001" and not duplicate_attempted and progress >= 0.55 and index == 0:
                                duplicate_attempted = True
                                try:
                                    ingest_telemetry(db, packet, source_protocol="simulator-duplicate")
                                except EdgeConflictError:
                                    db.rollback()
                                    run = db.get(EdgeSimulationRun, run_id)
                                    run.rejected_count += 1
                        except EdgeConflictError:
                            db.rollback()
                            run = db.get(EdgeSimulationRun, run_id)
                            run.rejected_count += 1
                    run.cursor_step = step + 1
                    db.commit()
                await asyncio.sleep(max(0.05, request.timestep_seconds / request.speed_multiplier))
            with SessionLocal() as db:
                run = db.get(EdgeSimulationRun, run_id)
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive task boundary
            with SessionLocal() as db:
                run = db.get(EdgeSimulationRun, run_id)
                if run:
                    run.status = "failed"
                    run.error = str(exc)[:1000]
                    run.completed_at = datetime.now(timezone.utc)
                    db.commit()

    def pause(self, run_id: str, db: Session | None = None) -> None:
        self.paused.add(run_id)
        self._status(run_id, "paused", db=db)

    def resume(self, run_id: str, db: Session | None = None) -> None:
        self.paused.discard(run_id)
        self._status(run_id, "running", db=db)

    def stop(self, run_id: str, db: Session | None = None) -> None:
        self.paused.discard(run_id)
        self._status(run_id, "stopped", completed=True, db=db)

    def _status(self, run_id: str, status: str, *, completed: bool = False, db: Session | None = None) -> None:
        def update(active_db: Session) -> None:
            run = active_db.get(EdgeSimulationRun, run_id)
            if not run:
                raise LookupError("Simulation run not found")
            run.status = status
            if completed:
                run.completed_at = datetime.now(timezone.utc)
            active_db.commit()
        if db is None:
            with SessionLocal() as active_db:
                update(active_db)
        else:
            update(db)

    async def shutdown(self) -> None:
        tasks = [task for task in self.tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


simulation_manager = SimulationManager()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AapadSnehi deterministic edge simulator")
    parser.add_argument("--scenario", default="flood-gradual-001")
    parser.add_argument("--devices", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--region", default="visakhapatnam")
    parser.add_argument("--speed", type=float, default=60)
    args = parser.parse_args()
    request = SimulationCreate(scenario=args.scenario, numberOfDevices=args.devices, seed=args.seed, region=args.region, speedMultiplier=args.speed)

    async def launch() -> None:
        run_id = await simulation_manager.start(request)
        await simulation_manager.tasks[run_id]
        print(run_id)

    asyncio.run(launch())


if __name__ == "__main__":
    main()
