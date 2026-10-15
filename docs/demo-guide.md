# Demonstration and learning guide

## Five-minute technical walkthrough

**0:00 — Purpose.** “I built an educational twin-jet control and verification simulator to learn marine control software. The focus is observable behaviour, failure handling and deliberate recovery. The sensors, vessel and actuators are virtual.”

**0:30 — Start sequence.** Show that Run before Arm does not work. Set a non-neutral demand; Arm is rejected. Neutralize, Arm, Run, then apply thrust. Explain demand versus feedback and the two slew rates.

**1:15 — Heading control.** Choose Heading hold. Explain crossing north from 330° toward 30°, shortest-arc error, measured-yaw derivative and bounded integral. Show the scenario trace and the 60-second acceptance check; do not claim those gains apply to real vessels.

**2:00 — Failure and recovery.** Choose Pressure loss. Show zero commands, the latched alarm and retained movement from inertia. Clear the injection, neutralize and reset. Point out the Disarmed state. Release of an emergency-stop input likewise cannot automatically restart.

**3:00 — A less obvious case.** At steady thrust freeze the port feedback. Keeping exactly the same demand cannot expose the failure. Change demand; the mismatch persists and trips. Explain the excitation requirement and why threshold/delay selection must trade false positives against detection latency.

**4:00 — Evidence.** Export CSV. Show a transition and the corresponding test. Explain that the browser clock is request-driven and that PLC/fieldbus, real hardware, calibration and certification remain outside this version.

**4:45 — Ownership and next step.** State which parts you can explain and modify yourself. The code was developed with AI assistance. Explain one change you made, one bug you reproduced, and the next experiment you would run. Do not present generated code as prior industrial experience.

## Learning tasks before presenting it as your project

1. Run all five scenarios yourself. Recover from each without reloading the page.
2. In `core.py`, trace one full scan with a pencil: input → health → state → allocation → actuator → plant → telemetry.
3. Change the pressure threshold to 65 bar. Find the affected requirement/test and update them deliberately. Restore the original after the experiment.
4. Change a PID gain. Predict the effect, run the heading scenario, and compare overshoot and final error. Keep the evidence of one unsuccessful tuning too.
5. Write a new test for a case you can explain, such as port turn sign or temperature exactly at the boundary.
6. Explain why a real frozen actuator may continue producing thrust even though this model suppresses force on trip.
7. Compile and exercise the Structured Text reference in an actual PLC development environment. Only then add that experience to your CV.

## Accurate portfolio wording after completing those tasks

“Built and evaluated an educational marine control simulator with a Qt HMI, a browser console, heading control, interlocks and fault-injection scenarios; recorded automated verification traces. Software simulation only, with no vessel or PLC runtime integration.”

Do not describe it as deployed vessel software, certified controls, hardware testing, a commercial production system, or an MJP digital twin. A portfolio project supports the conversation; it cannot guarantee an interview or offer.
