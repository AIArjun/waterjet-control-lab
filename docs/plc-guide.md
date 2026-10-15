# PLC learning stage — not executed in this release

The running controller is Python. The `.st` file in `plc/` is a **draft reference for translating startup and fault permissives into Structured Text**. It is neither the complete Python controller nor a tested PLC program. There is no Modbus/CAN/OPC UA connection to the HMI.

## Suggested next software

- [CODESYS Development System](https://www.codesys.com/products/engineering/development-system/) — suitable for learning IEC 61131-3 and compiling/simulating a block without hardware. Read the vendor's licensing/installation terms yourself when installing.
- [CODESYS simulation documentation](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_cmd_simulation.html) — ordinary IDE simulation does **not** evaluate fieldbus stacks or physical I/O updates. Do not assume it exposes a usable fieldbus service to this Python HMI.
- [OpenPLC runtime](https://github.com/Autonomy-Logic/openplc-runtime) — another option for a later softPLC experiment. Docker is not required for the current simulator.

## CODESYS exercise

1. Create a local Standard Project and add a Structured Text function block named `FB_Permissives`. Replace the declaration pane with the header through the final `END_VAR`. In the implementation pane paste `ArmEdge := ...` through the `EnableThrust := ...;` assignment. Omit the final `END_FUNCTION_BLOCK` wrapper, which is for the standalone source file, not the IDE implementation pane.
2. Add an instance in `PLC_PRG`, call it from a cyclic 50 ms task and create watch variables for its inputs and outputs.
3. Build and resolve compiler diagnostics for the selected toolchain. This reference deliberately avoids fieldbus addresses and devices.
4. Enter simulation mode using the official documentation. Toggle momentary button inputs back to false between presses, and observe Mode, TripLatched and EnableThrust.
5. Record compiler/runtime versions and run every sequence below. Until these checks pass, keep its status “unverified reference.”

| Sequence | Expected observation |
| --- | --- |
| Cold start | Mode 0, EnableThrust false |
| Run before Arm | Remains Mode 0 |
| Non-neutral demands then Arm | Arm rejected |
| Healthy + neutral, Arm then Run | Mode 1 then Mode 2 |
| Pressure 59 bar while Running | Mode 3; thrust disabled |
| Clear pressure, Reset with non-neutral demand | Remains Mode 3 |
| Healthy + neutral then Reset | Mode 0; no restart |
| EmergencyStop true then false | Mode 4 remains after release |
| Released + healthy + neutral then Reset | Mode 0 |
| CommandFresh false / SensorsFresh false while Running | Mode 3 |

This block takes freshness as a Boolean input; it does not implement the Python watchdog timers, actuator mismatch detection, thrust allocation, PID or plant. A later runtime integration must define I/O mapping, timestamp ownership, task timing, communication loss behaviour and integration tests before any equivalence claim.
