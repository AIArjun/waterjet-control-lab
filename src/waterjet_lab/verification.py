"""Generate measured, repeatable simulation evidence; no invented pass counts."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .core import DT, Command, Fault, Mode, angle_error, running_simulator
from .scenarios import advance, scenario


def run_verification(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    checks = []

    def result(name: str, passed: bool, measurements: dict):
        checks.append({"scenario": name, "passed": bool(passed), "measurements": measurements})

    heading = scenario("heading")
    advance(heading, 55)
    error = abs(angle_error(30, heading.vessel.heading_deg))
    result(
        "Heading hold across north",
        heading.mode == Mode.RUNNING and error < 2,
        {
            "duration_s": heading.time_s,
            "target_deg": 30,
            "final_heading_deg": heading.vessel.heading_deg,
            "absolute_error_deg": error,
            "wind_east_n": heading.wind_east_n,
            "acceptance_error_deg": 2,
        },
    )
    traces = {"heading-hold.csv": heading.csv()}

    for fault, code in [
        (Fault.LOW_PRESSURE, "LOW_PRESSURE"),
        (Fault.OVERHEAT, "OVER_TEMPERATURE"),
        (Fault.COMMS_LOSS, "COMMAND_STALE"),
        (Fault.SENSOR_DROPOUT, "SENSOR_STALE"),
        (Fault.PORT_STUCK, "PORT_ACTUATOR_MISMATCH"),
    ]:
        sim = running_simulator()
        sim.receive(Command(surge=0.6))
        advance(sim, 4)
        sim.inject(fault, True)
        if fault == Fault.PORT_STUCK:
            # A frozen actuator at its existing setpoint is unobservable until demand changes.
            sim.receive(Command(surge=-0.4))
        started = sim.time_s
        for _ in range(60):
            sim.receive(sim.command)
            sim.step()
            if sim.mode == Mode.FAULT:
                break
        delay = round(sim.time_s - started, 3)
        result(
            fault.value,
            sim.mode == Mode.FAULT and code in sim.latched and sim.port_output == sim.starboard_output == 0,
            {
                "fault_response_s": delay,
                "alarm": list(sim.latched),
                "port_output": sim.port_output,
                "starboard_output": sim.starboard_output,
            },
        )
        traces[f"{fault.value}.csv"] = sim.csv()

    sim = scenario("estop")
    sim.action("release_estop")
    released_mode = sim.mode
    sim.receive(Command())
    accepted = sim.action("reset")
    result(
        "Emergency stop recovery",
        released_mode == Mode.E_STOP and accepted and sim.mode == Mode.DISARMED,
        {
            "mode_after_release": released_mode.value,
            "mode_after_reset": sim.mode.value,
            "automatic_restart": False,
        },
    )
    traces["emergency-stop.csv"] = sim.csv()
    hashes = {}
    for name, content in traces.items():
        raw = content.encode("utf-8")
        (output / name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    report = {
        "version": __version__,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "scope": "Deterministic software simulation only; no real-time, hardware or vessel validation",
        "scan_period_s": DT,
        "parameters": asdict(heading.parameters),
        "checks": checks,
        "all_passed": all(c["passed"] for c in checks),
        "trace_sha256": hashes,
    }
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification"))
    args = parser.parse_args()
    report = run_verification(args.output)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["all_passed"] else 1)


if __name__ == "__main__":
    main()
