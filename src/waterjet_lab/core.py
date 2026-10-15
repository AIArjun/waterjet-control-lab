"""Deterministic scan controller and deliberately simplified marine plant.

Coordinates: east/north in metres; heading clockwise from north in degrees.
Body velocities: forward/starboard in m/s; yaw rate clockwise in rad/s.
No manufacturer's calibration or real-time/safety certification is implied.
"""

from __future__ import annotations

import csv
import io
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import StrEnum

DT = 0.05
COMMAND_TIMEOUT = 0.75
SENSOR_TIMEOUT = 0.25


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def angle_error(target: float, actual: float) -> float:
    return (target - actual + 180.0) % 360.0 - 180.0


class Mode(StrEnum):
    DISARMED = "DISARMED"
    ARMED = "ARMED"
    RUNNING = "RUNNING"
    FAULT = "FAULT"
    E_STOP = "E_STOP"


class Fault(StrEnum):
    LOW_PRESSURE = "low_pressure"
    OVERHEAT = "overheat"
    SENSOR_DROPOUT = "sensor_dropout"
    PORT_STUCK = "port_stuck"
    COMMS_LOSS = "comms_loss"


@dataclass(frozen=True)
class Parameters:
    mass_kg: float = 2200.0
    yaw_inertia_kgm2: float = 5500.0
    max_jet_force_n: float = 6000.0
    jet_half_spacing_m: float = 0.85
    jet_stern_offset_m: float = 2.0
    actuator_rate_per_s: float = 1.2
    thrust_rate_per_s: float = 0.8
    pressure_trip_bar: float = 60.0
    temperature_trip_c: float = 85.0
    jam_delay_s: float = 0.60


@dataclass
class Command:
    surge: float = 0.0
    turn: float = 0.0
    control: str = "manual"
    heading_deg: float = 0.0

    def validate(self) -> None:
        if not all(math.isfinite(v) for v in (self.surge, self.turn, self.heading_deg)):
            raise ValueError("Commands must be finite numbers")
        if not -1 <= self.surge <= 1 or not -1 <= self.turn <= 1:
            raise ValueError("Surge and turn must be in [-1, 1]")
        if not 0 <= self.heading_deg < 360 or self.control not in {"manual", "heading"}:
            raise ValueError("Invalid heading or control mode")


@dataclass
class Vessel:
    east_m: float = 0.0
    north_m: float = 0.0
    heading_deg: float = 0.0
    surge_mps: float = 0.0
    sway_mps: float = 0.0
    yaw_rad_s: float = 0.0
    port_feedback: float = 0.0
    starboard_feedback: float = 0.0


@dataclass
class HeadingPID:
    """PI plus derivative-on-measurement, bounded integral and conditional anti-windup."""

    integral: float = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def update(self, error_deg: float, yaw_deg_s: float, dt: float) -> float:
        candidate = clamp(self.integral + error_deg * dt, -150.0, 150.0)
        raw = 0.025 * error_deg + 0.0008 * candidate - 0.08 * yaw_deg_s
        if abs(raw) <= 1 or raw * error_deg < 0:
            self.integral = candidate
        return clamp(raw)


@dataclass
class Simulator:
    parameters: Parameters = field(default_factory=Parameters)
    vessel: Vessel = field(default_factory=Vessel)
    command: Command = field(default_factory=Command)
    mode: Mode = Mode.DISARMED
    time_s: float = 0.0
    command_at: float = 0.0
    sensor_at: float = 0.0
    estop_pressed: bool = False
    port_output: float = 0.0
    starboard_output: float = 0.0
    nozzle_deg: float = 0.0
    wind_east_n: float = 0.0
    wind_north_n: float = 0.0
    jam_timer_s: float = 0.0
    previous_port_feedback: float = 0.0
    faults: set[Fault] = field(default_factory=set)
    latched: tuple[str, ...] = ()
    events: deque = field(default_factory=lambda: deque(maxlen=200))
    history: deque = field(default_factory=lambda: deque(maxlen=6000))
    pid: HeadingPID = field(default_factory=HeadingPID)
    scans: int = 0

    def __post_init__(self) -> None:
        self.event("INFO", "BOOT", "Simulation initialized; outputs inhibited")

    def event(self, level: str, code: str, message: str) -> None:
        self.events.append(
            {"time_s": round(self.time_s, 3), "level": level, "code": code, "message": message}
        )

    def receive(self, command: Command) -> bool:
        command.validate()
        if Fault.COMMS_LOSS in self.faults:
            return False
        if command.control != self.command.control:
            self.pid.reset()
        self.command = Command(**asdict(command))
        self.command_at = self.time_s
        return True

    def inject(self, fault: Fault, enabled: bool) -> None:
        if enabled == (fault in self.faults):
            return
        self.faults.add(fault) if enabled else self.faults.discard(fault)
        self.event(
            "WARN" if enabled else "INFO",
            "INJECTION",
            f"{fault.value}: {'introduced' if enabled else 'cleared'}",
        )

    @property
    def pressure_bar(self) -> float:
        return 35.0 if Fault.LOW_PRESSURE in self.faults else 110.0

    @property
    def temperature_c(self) -> float:
        return 96.0 if Fault.OVERHEAT in self.faults else 46.0 + 8 * abs(self.vessel.port_feedback)

    def health(self) -> list[str]:
        reasons = []
        if self.pressure_bar < self.parameters.pressure_trip_bar:
            reasons.append("LOW_PRESSURE")
        if self.temperature_c >= self.parameters.temperature_trip_c:
            reasons.append("OVER_TEMPERATURE")
        if self.time_s - self.sensor_at >= SENSOR_TIMEOUT - 1e-9:
            reasons.append("SENSOR_STALE")
        if self.time_s - self.command_at >= COMMAND_TIMEOUT - 1e-9:
            reasons.append("COMMAND_STALE")
        if self.jam_timer_s >= self.parameters.jam_delay_s - 1e-9:
            reasons.append("PORT_ACTUATOR_MISMATCH")
        return reasons

    def _transition(self, mode: Mode, message: str) -> None:
        if self.mode != mode:
            self.mode = mode
            self.event("ALARM" if mode in {Mode.FAULT, Mode.E_STOP} else "INFO", mode.value, message)

    def _inhibit(self) -> None:
        self.port_output = self.starboard_output = self.nozzle_deg = 0.0
        self.pid.reset()

    def action(self, action: str) -> bool:
        """Operator actions; E-stop release and fault reset are deliberately distinct."""
        if action == "estop":
            self.estop_pressed = True
            self.latched = tuple(dict.fromkeys((*self.latched, "E_STOP_PRESSED")))
            self._transition(Mode.E_STOP, "Simulated emergency stop latched")
            self._inhibit()
            return True
        if action == "release_estop":
            self.estop_pressed = False
            self.event("INFO", "E_STOP_RELEASED", "Stop input released; reset still required")
            return True
        if action == "stop":
            self._inhibit()
            if self.mode not in {Mode.FAULT, Mode.E_STOP}:
                self._transition(Mode.DISARMED, "Operator stopped and disarmed")
            return True
        if action == "reset":
            if self.mode not in {Mode.FAULT, Mode.E_STOP}:
                return False
            reasons = self.health()
            if (
                self.estop_pressed
                or reasons
                or Fault.PORT_STUCK in self.faults
                or abs(self.command.surge) > 0.02
                or abs(self.command.turn) > 0.02
            ):
                self.event(
                    "WARN", "RESET_REJECTED", "Clear fault, release stop and neutralize controls before reset"
                )
                return False
            self.latched = ()
            self._inhibit()
            self._transition(Mode.DISARMED, "Fault reset accepted; explicit arm and run required")
            return True
        if action == "arm":
            neutral = abs(self.command.surge) <= 0.02 and abs(self.command.turn) <= 0.02
            if self.mode != Mode.DISARMED or self.estop_pressed or self.health() or not neutral:
                self.event("WARN", "ARM_REJECTED", "Check healthy inputs, released stop and neutral controls")
                return False
            self._transition(Mode.ARMED, "Permissives satisfied; waiting for run command")
            return True
        if action == "run":
            if (
                self.mode != Mode.ARMED
                or self.health()
                or self.estop_pressed
                or abs(self.command.surge) > 0.02
                or abs(self.command.turn) > 0.02
            ):
                self.event("WARN", "RUN_REJECTED", "Arm with healthy inputs before running")
                return False
            self._transition(Mode.RUNNING, "Controller running")
            return True
        raise ValueError(f"Unknown action: {action}")

    def step(self, count: int = 1) -> dict:
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 200:
            raise ValueError("Scan count must be an integer in [1, 200]")
        for _ in range(count):
            self.time_s = round(self.time_s + DT, 9)
            self.scans += 1
            if Fault.SENSOR_DROPOUT not in self.faults:
                self.sensor_at = self.time_s
            unchanged = abs(self.vessel.port_feedback - self.previous_port_feedback) < 1e-5
            mismatch = abs(self.port_output - self.vessel.port_feedback) > 0.20
            self.jam_timer_s = self.jam_timer_s + DT if mismatch and unchanged else 0.0
            self.previous_port_feedback = self.vessel.port_feedback
            reasons = self.health()
            if self.estop_pressed:
                self._transition(Mode.E_STOP, "Simulated emergency stop active")
            elif reasons and self.mode in {Mode.ARMED, Mode.RUNNING}:
                self.latched = tuple(reasons)
                self._transition(Mode.FAULT, ", ".join(reasons))
            if self.mode == Mode.RUNNING:
                turn = self.command.turn
                if self.command.control == "heading":
                    turn = self.pid.update(
                        angle_error(self.command.heading_deg, self.vessel.heading_deg),
                        math.degrees(self.vessel.yaw_rad_s),
                        DT,
                    )
                port = clamp(self.command.surge + 0.50 * turn)
                starboard = clamp(self.command.surge - 0.50 * turn)
                limit = self.parameters.thrust_rate_per_s * DT
                self.port_output += clamp(port - self.port_output, -limit, limit)
                self.starboard_output += clamp(starboard - self.starboard_output, -limit, limit)
                self.nozzle_deg = -25.0 * turn
            else:
                self._inhibit()
            self._plant()
            if self.scans % 2 == 0:
                self.history.append(self.record())
        return self.snapshot()

    def _plant(self) -> None:
        p, v = self.parameters, self.vessel
        limit = p.actuator_rate_per_s * DT
        if Fault.PORT_STUCK not in self.faults:
            v.port_feedback += clamp(self.port_output - v.port_feedback, -limit, limit)
        v.starboard_feedback += clamp(self.starboard_output - v.starboard_feedback, -limit, limit)
        # A fault inhibits commanded thrust immediately. Hydraulic feedback still decays.
        enabled = self.mode == Mode.RUNNING
        port = p.max_jet_force_n * v.port_feedback * abs(v.port_feedback) if enabled else 0.0
        starboard = p.max_jet_force_n * v.starboard_feedback * abs(v.starboard_feedback) if enabled else 0.0
        theta = math.radians(self.nozzle_deg)
        fx = (port + starboard) * math.cos(theta)
        fy = (port + starboard) * math.sin(theta)
        moment = p.jet_half_spacing_m * (port - starboard) - p.jet_stern_offset_m * fy
        heading = math.radians(v.heading_deg)
        wind_forward = self.wind_east_n * math.sin(heading) + self.wind_north_n * math.cos(heading)
        wind_starboard = self.wind_east_n * math.cos(heading) - self.wind_north_n * math.sin(heading)
        du = (fx + wind_forward - 220 * v.surge_mps - 180 * v.surge_mps * abs(v.surge_mps)) / p.mass_kg
        dv = (fy + wind_starboard - 500 * v.sway_mps - 350 * v.sway_mps * abs(v.sway_mps)) / p.mass_kg
        dr = (moment - 4500 * v.yaw_rad_s - 1200 * v.yaw_rad_s * abs(v.yaw_rad_s)) / p.yaw_inertia_kgm2
        v.surge_mps += du * DT
        v.sway_mps += dv * DT
        v.yaw_rad_s += dr * DT
        v.heading_deg = (v.heading_deg + math.degrees(v.yaw_rad_s) * DT) % 360.0
        v.east_m += (v.surge_mps * math.sin(heading) + v.sway_mps * math.cos(heading)) * DT
        v.north_m += (v.surge_mps * math.cos(heading) - v.sway_mps * math.sin(heading)) * DT

    def record(self) -> dict:
        return {
            "time_s": round(self.time_s, 3),
            "mode": self.mode.value,
            **{k: round(v, 6) for k, v in asdict(self.vessel).items()},
            "port_output": round(self.port_output, 6),
            "starboard_output": round(self.starboard_output, 6),
            "nozzle_deg": round(self.nozzle_deg, 6),
            "pressure_bar": self.pressure_bar,
            "temperature_c": round(self.temperature_c, 3),
            "demand_surge": self.command.surge,
            "demand_turn": self.command.turn,
            "control": self.command.control,
            "target_heading_deg": self.command.heading_deg,
            "alarm_codes": "|".join(self.latched),
            "injected_faults": "|".join(sorted(f.value for f in self.faults)),
            "estop_pressed": self.estop_pressed,
        }

    def snapshot(self) -> dict:
        return {
            **self.record(),
            "command": asdict(self.command),
            "faults": sorted(f.value for f in self.faults),
            "latched": list(self.latched),
            "health": self.health(),
            "estop_pressed": self.estop_pressed,
            "sensor_age_s": round(self.time_s - self.sensor_at, 3),
            "command_age_s": round(self.time_s - self.command_at, 3),
            "scan_period_ms": int(DT * 1000),
            "events": list(reversed(self.events)),
            "scans": self.scans,
            "wind": {"east_n": self.wind_east_n, "north_n": self.wind_north_n},
        }

    def records(self) -> list[dict]:
        rows = list(self.history)
        current = self.record()
        if not rows or rows[-1] != current:
            rows.append(current)
        return rows

    def csv(self) -> str:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(self.record()))
        writer.writeheader()
        writer.writerows(self.records())
        return stream.getvalue()


def running_simulator() -> Simulator:
    sim = Simulator()
    sim.receive(Command())
    assert sim.action("arm") and sim.action("run")
    return sim
