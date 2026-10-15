# Model, units and architecture

## Scope

An original low-order, planar plant is integrated using a fixed 50 ms step. It is chosen for understandable control experiments, not hydrodynamic prediction. All parameters are illustrative and visible in `Parameters` in `core.py`.

| Quantity | Convention |
| --- | --- |
| Position | east E and north N, metres |
| Heading ψ | clockwise from north, degrees in [0, 360) |
| Body velocity | forward u, starboard v, m/s |
| Yaw rate r | clockwise rad/s |
| Thrust/feedback | signed normalized values in [-1, 1] |
| Wind | constant external east/north force, N; no wind-speed aerodynamics |
| Nozzle | shared angle, ±25°; negative angle creates port-directed lateral force |

The illustrative mass is 2200 kg, yaw inertia 5500 kg·m² and maximum force per jet 6000 N. Jet lateral spacing is ±0.85 m and their longitudinal offset is 2 m behind the centre. None are manufacturer specifications.

## Scan order

1. Advance simulation time; accept sensor freshness unless dropout is injected.
2. Compare previous requested and measured actuator values for a persistent mismatch.
3. Evaluate health; latch an active trip in Armed/Running. Emergency stop has priority.
4. If Running, calculate manual/PID turn and rate-limited thrust commands. Otherwise inhibit commands and clear the PID integral.
5. Move the virtual actuators toward the requested values, integrate forces and vessel motion.
6. Record every second scan (10 Hz); append the current state when exporting if it differs from the latest sample.

`receive()` validates a complete command and records its simulation timestamp. Command-loss injection prevents that timestamp being refreshed. Sensor loss leaves an independent timestamp stale. The UI does not set controller mode or raw actuator outputs directly.

## Allocation and plant

For normalized surge s and turn t:

```text
port_target      = clip(s + 0.5 t, -1, 1)
starboard_target = clip(s - 0.5 t, -1, 1)
nozzle_angle     = -25 t degrees
```

Thrust demand slews at 0.8/s; healthy actuator feedback moves at 1.2/s. A port-stuck injection freezes that feedback. The simplified jet force is `6000 f |f|` N for feedback f while enabled. Disabling the controller removes propulsive force immediately in this plant, even if a frozen actuator indication remains high. This is an explicit idealization of an independent shutdown, not a simulation of its hardware.

```text
Fx = (Fp + Fs) cos(nozzle)
Fy = (Fp + Fs) sin(nozzle)
Mz = 0.85 (Fp - Fs) - 2 Fy

du/dt = (Fx + wind_forward - 220 u - 180 u |u|) / 2200
dv/dt = (Fy + wind_starboard - 500 v - 350 v |v|) / 2200
dr/dt = (Mz - 4500 r - 1200 r |r|) / 5500

dE/dt = u sin(ψ) + v cos(ψ)
dN/dt = u cos(ψ) - v sin(ψ)
```

Velocity and yaw are stepped before the position update; the position transform uses the heading at the beginning of the scan. No Coriolis coupling, added mass, waves, current, roll/pitch/heave, saturation-dependent hydraulics, engine dynamics, or reversing-bucket kinematics are modelled. Signed thrust abstracts ahead/astern mechanisms.

## Heading controller

`e = (target - actual + 180) mod 360 - 180` degrees. The control law is `0.025 e + 0.0008 integral(e) - 0.08 yaw_deg_s`, clipped to [-1, 1]. The integral is bounded to ±150 degree-seconds and conditionally updated to avoid driving further into saturation. Derivative on measured yaw rate avoids a derivative kick on a target step. Controller gains are tuned for this one illustrative plant; no robustness/stability proof is claimed.

## Runtime boundaries

The core has no web/Qt dependency. Adapters own operator input and scheduling. The web server runs one worker and protects each session with a lock; session state is in memory. Requests advance time; a lost browser connection freezes that session's simulated clock. In the Qt app a regular 50 ms GUI timer drives scans. Neither is a real-time control task, and neither can operate real equipment.

The same deterministic scenario gives the same traces for a fixed runtime/math implementation. Tiny floating-point differences across platforms are possible; CI accepts measured thresholds, not a hard-coded cross-platform CSV hash. The JSON report hashes the trace generated in that particular run.
