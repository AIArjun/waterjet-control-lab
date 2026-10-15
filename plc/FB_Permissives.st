(* UNCOMPILED / UNEXECUTED REFERENCE. Educational logic only; no safety rating.
   CODESYS: create FB_Permissives (ST), paste declaration through END_VAR in
   the declaration pane; paste the rest in the implementation pane.
   Mode: 0=Disarmed, 1=Armed, 2=Running, 3=Fault, 4=EStop.
   This is a subset, not an executable equivalent of core.py. *)
FUNCTION_BLOCK FB_Permissives
VAR_INPUT
    ArmButton : BOOL;
    RunButton : BOOL;
    StopButton : BOOL;
    ResetButton : BOOL;
    EmergencyStop : BOOL;
    PressureBar : REAL := 110.0;
    TemperatureC : REAL := 46.0;
    SurgeDemand : REAL;
    TurnDemand : REAL;
    CommandFresh : BOOL := TRUE;
    SensorsFresh : BOOL := TRUE;
END_VAR
VAR_OUTPUT
    Mode : INT := 0;
    EnableThrust : BOOL := FALSE;
    TripLatched : BOOL := FALSE;
END_VAR
VAR
    PreviousArm, PreviousRun, PreviousReset : BOOL;
    ArmEdge, RunEdge, ResetEdge : BOOL;
    Healthy, Neutral : BOOL;
END_VAR

ArmEdge := ArmButton AND NOT PreviousArm;
RunEdge := RunButton AND NOT PreviousRun;
ResetEdge := ResetButton AND NOT PreviousReset;
PreviousArm := ArmButton;
PreviousRun := RunButton;
PreviousReset := ResetButton;

Healthy := (PressureBar >= 60.0) AND (TemperatureC < 85.0)
           AND CommandFresh AND SensorsFresh;
Neutral := (ABS(SurgeDemand) <= 0.02) AND (ABS(TurnDemand) <= 0.02);

IF EmergencyStop THEN
    Mode := 4;
    TripLatched := TRUE;
ELSIF ((Mode = 1) OR (Mode = 2)) AND NOT Healthy THEN
    Mode := 3;
    TripLatched := TRUE;
ELSIF ((Mode = 3) OR (Mode = 4)) THEN
    IF ResetEdge AND Healthy AND Neutral THEN
        Mode := 0;
        TripLatched := FALSE;
    END_IF;
ELSIF StopButton THEN
    Mode := 0;
ELSIF (Mode = 0) AND ArmEdge AND Healthy AND Neutral THEN
    Mode := 1;
ELSIF (Mode = 1) AND RunEdge AND Healthy AND Neutral THEN
    Mode := 2;
END_IF;

EnableThrust := (Mode = 2) AND Healthy AND NOT EmergencyStop AND NOT TripLatched;
END_FUNCTION_BLOCK
