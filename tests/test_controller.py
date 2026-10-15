import csv
import io
import json
import math
import random

import pytest

from waterjet_lab.core import (
    COMMAND_TIMEOUT,
    DT,
    SENSOR_TIMEOUT,
    Command,
    Fault,
    Mode,
    Simulator,
    angle_error,
    running_simulator,
)
from waterjet_lab.scenarios import advance, scenario


def test_cold_start_inhibits_every_output():
    sim = Simulator()
    sim.receive(Command(surge=1, turn=1))
    sim.step(10)
    assert sim.mode == Mode.DISARMED
    assert sim.port_output == sim.starboard_output == sim.nozzle_deg == 0
    assert sim.vessel.east_m == sim.vessel.north_m == 0


def test_run_requires_arm_and_arm_requires_neutral():
    sim = Simulator()
    assert not sim.action("run")
    sim.receive(Command(surge=0.3))
    assert not sim.action("arm")
    sim.receive(Command())
    assert sim.action("arm") and sim.mode == Mode.ARMED
    assert sim.port_output == 0
    assert sim.action("run") and sim.mode == Mode.RUNNING


def test_demand_changed_after_arming_requires_neutral_before_run():
    sim = Simulator()
    assert sim.action("arm")
    sim.receive(Command(surge=0.5))
    assert not sim.action("run")
    assert sim.mode == Mode.ARMED and sim.port_output == 0


@pytest.mark.parametrize("fault", [Fault.LOW_PRESSURE, Fault.OVERHEAT])
def test_bad_startup_permissives_inhibit_arm(fault):
    sim = Simulator()
    sim.inject(fault, True)
    assert not sim.action("arm")
    assert sim.mode == Mode.DISARMED


@pytest.mark.parametrize(
    "fault,code", [(Fault.LOW_PRESSURE, "LOW_PRESSURE"), (Fault.OVERHEAT, "OVER_TEMPERATURE")]
)
def test_sensor_trip_inhibits_outputs_in_next_scan_and_latches(fault, code):
    sim = running_simulator()
    sim.receive(Command(surge=0.8))
    advance(sim, 2)
    assert sim.port_output > 0.5
    sim.inject(fault, True)
    sim.step()
    assert sim.mode == Mode.FAULT and code in sim.latched
    assert sim.port_output == sim.starboard_output == 0
    sim.inject(fault, False)
    advance(sim, 1)
    assert sim.mode == Mode.FAULT
    assert not sim.action("run")


def test_emergency_stop_release_does_not_reset_or_restart():
    sim = running_simulator()
    sim.receive(Command(surge=0.5))
    advance(sim, 1)
    sim.action("estop")
    assert sim.mode == Mode.E_STOP and sim.port_output == 0
    assert not sim.action("reset")
    sim.action("release_estop")
    assert sim.mode == Mode.E_STOP
    assert not sim.action("reset")  # non-neutral demand
    sim.receive(Command())
    assert sim.action("reset")
    assert sim.mode == Mode.DISARMED
    assert not sim.action("run")
    assert sim.action("arm") and sim.action("run")


def test_reset_rejects_active_fault_even_if_controls_are_neutral():
    sim = scenario("pressure")
    sim.receive(Command())
    assert not sim.action("reset")
    sim.inject(Fault.LOW_PRESSURE, False)
    sim.step()
    assert sim.action("reset")
    assert sim.mode == Mode.DISARMED and not sim.latched


def test_reset_does_not_clear_a_stuck_actuator_fault():
    sim = running_simulator()
    sim.inject(Fault.PORT_STUCK, True)
    sim.receive(Command(surge=0.7))
    advance(sim, 2)
    assert "PORT_ACTUATOR_MISMATCH" in sim.latched
    sim.receive(Command())
    advance(sim, 0.5)
    assert not sim.action("reset")
    sim.inject(Fault.PORT_STUCK, False)
    advance(sim, 0.2)
    assert sim.action("reset")


def test_frozen_actuator_at_setpoint_requires_a_demand_change_to_be_observable():
    sim = running_simulator()
    sim.receive(Command(surge=0.5))
    advance(sim, 3)
    sim.inject(Fault.PORT_STUCK, True)
    advance(sim, 2)
    assert sim.mode == Mode.RUNNING
    sim.receive(Command(surge=-0.4))
    advance(sim, 2)
    assert sim.mode == Mode.FAULT and "PORT_ACTUATOR_MISMATCH" in sim.latched


def test_csv_includes_immediate_trip_between_telemetry_samples():
    sim = running_simulator()
    sim.receive(Command(surge=0.5))
    advance(sim, 1)
    sim.inject(Fault.LOW_PRESSURE, True)
    sim.step()
    last = list(csv.DictReader(io.StringIO(sim.csv())))[-1]
    assert last["mode"] == "FAULT" and last["alarm_codes"] == "LOW_PRESSURE"
    assert float(last["port_output"]) == 0


def test_command_watchdog_exact_boundary_and_recovery():
    sim = running_simulator()
    sim.receive(Command(surge=0.5))
    advance(sim, 2)
    sim.inject(Fault.COMMS_LOSS, True)
    last_received = sim.command_at
    while sim.time_s - last_received < COMMAND_TIMEOUT - DT - 1e-8:
        sim.step()
    assert sim.mode == Mode.RUNNING
    sim.step()
    assert sim.mode == Mode.FAULT
    assert sim.time_s - last_received == pytest.approx(COMMAND_TIMEOUT)
    assert sim.port_output == 0 and "COMMAND_STALE" in sim.latched
    assert not sim.receive(Command())
    sim.inject(Fault.COMMS_LOSS, False)
    assert sim.receive(Command())
    assert sim.action("reset")


def test_sensor_watchdog_independent_of_command_heartbeat():
    sim = running_simulator()
    advance(sim, 1)
    sim.inject(Fault.SENSOR_DROPOUT, True)
    before = sim.sensor_at
    advance(sim, SENSOR_TIMEOUT)
    assert sim.time_s - before == pytest.approx(SENSOR_TIMEOUT)
    assert sim.mode == Mode.FAULT and "SENSOR_STALE" in sim.latched


def test_ordinary_stop_zeroes_outputs_and_requires_rearming():
    sim = running_simulator()
    sim.receive(Command(surge=0.8))
    advance(sim, 2)
    assert sim.action("stop")
    assert sim.mode == Mode.DISARMED and sim.port_output == 0
    assert not sim.action("run")


def test_demand_slew_limit():
    sim = running_simulator()
    sim.receive(Command(surge=1))
    sim.step()
    assert sim.port_output == pytest.approx(sim.parameters.thrust_rate_per_s * DT)


def test_symmetric_thrust_drives_north_without_yaw_in_calm_water():
    sim = running_simulator()
    sim.receive(Command(surge=0.6))
    advance(sim, 8)
    assert sim.vessel.north_m > 2
    assert sim.vessel.east_m == pytest.approx(0)
    assert sim.vessel.heading_deg == pytest.approx(0)


def test_reverse_thrust_moves_astern():
    sim = running_simulator()
    sim.receive(Command(surge=-0.6))
    advance(sim, 8)
    assert sim.vessel.north_m < -2


def test_positive_turn_rotates_clockwise():
    sim = running_simulator()
    sim.receive(Command(surge=0.4, turn=0.4))
    advance(sim, 5)
    assert 0 < sim.vessel.heading_deg < 180


@pytest.mark.parametrize(
    "target,actual,expected", [(10, 350, 20), (350, 10, -20), (180, 0, -180), (0, 360, 0)]
)
def test_heading_error_uses_shortest_arc(target, actual, expected):
    assert angle_error(target, actual) == expected


def test_heading_hold_wraps_north_and_converges_in_documented_scenario():
    sim = scenario("heading")
    advance(sim, 55)
    assert sim.mode == Mode.RUNNING
    assert abs(angle_error(30, sim.vessel.heading_deg)) < 2
    assert abs(sim.pid.integral) <= 150


@pytest.mark.parametrize(
    "field,value",
    [
        ("surge", float("nan")),
        ("turn", float("inf")),
        ("heading_deg", float("-inf")),
        ("surge", 1.01),
        ("turn", -1.01),
        ("heading_deg", 360),
        ("control", "autonomous"),
    ],
)
def test_invalid_commands_rejected_without_changing_previous_command(field, value):
    sim = Simulator()
    with pytest.raises(ValueError):
        sim.receive(Command(**{field: value}))
    assert sim.command == Command()


@pytest.mark.parametrize("count", [0, -1, 201, 1.5, True])
def test_invalid_scan_requests_rejected(count):
    with pytest.raises(ValueError):
        Simulator().step(count)


def test_seeded_random_commands_preserve_bounds_and_finite_state():
    rng = random.Random(261015)
    sim = running_simulator()
    for _ in range(1200):
        sim.receive(Command(surge=rng.uniform(-1, 1), turn=rng.uniform(-1, 1)))
        sim.step()
        assert abs(sim.port_output) <= 1 and abs(sim.starboard_output) <= 1
        assert 0 <= sim.vessel.heading_deg < 360
        assert all(math.isfinite(v) for v in sim.record().values() if isinstance(v, (float, int)))
    assert sim.mode == Mode.RUNNING  # healthy movement must not cause false jam trips


def test_scenario_is_deterministic_and_csv_matches_actual_history():
    one, two = scenario("heading"), scenario("heading")
    advance(one, 2)
    advance(two, 2)
    assert one.csv() == two.csv()
    rows = list(csv.DictReader(io.StringIO(one.csv())))
    assert float(rows[-1]["heading_deg"]) == pytest.approx(one.vessel.heading_deg, abs=1e-6)
    assert float(rows[-1]["time_s"]) == one.time_s
    json.dumps(one.snapshot(), allow_nan=False)


def test_unknown_action_and_scenario_are_rejected():
    with pytest.raises(ValueError):
        Simulator().action("sail")
    with pytest.raises(ValueError):
        scenario("unknown")
