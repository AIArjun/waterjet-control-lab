"""Short reproducible demonstrations, shared by desktop, web and verification."""

from .core import Command, Fault, Simulator, running_simulator

SCENARIOS = {
    "harbor": "Harbor manoeuvre",
    "heading": "Heading hold · 330° → 030°",
    "pressure": "Hydraulic pressure loss",
    "watchdog": "Command-link watchdog",
    "estop": "Emergency-stop recovery",
}


def advance(sim: Simulator, seconds: float, heartbeat: bool = True) -> None:
    for _ in range(round(seconds / 0.05)):
        if heartbeat:
            sim.receive(sim.command)
        sim.step()


def scenario(name: str) -> Simulator:
    if name not in SCENARIOS:
        raise ValueError("Unknown scenario")
    sim = running_simulator()
    if name == "heading":
        sim.vessel.heading_deg = 330
        sim.wind_east_n = 100
        sim.receive(Command(surge=0.35, control="heading", heading_deg=30))
    else:
        sim.receive(Command(surge=0.42, turn=0.08 if name == "harbor" else 0))
        sim.wind_east_n = 80 if name == "harbor" else 0
    advance(sim, 5)
    if name == "pressure":
        sim.inject(Fault.LOW_PRESSURE, True)
        sim.step()
    elif name == "watchdog":
        sim.inject(Fault.COMMS_LOSS, True)
        advance(sim, 0.8, heartbeat=False)
    elif name == "estop":
        sim.action("estop")
    sim.event("INFO", "SCENARIO", SCENARIOS[name])
    return sim
