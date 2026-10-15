"""Session-isolated web adapter. No hardware, credentials or persistent user data."""

from __future__ import annotations

import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .core import Command, Fault, Simulator
from .scenarios import SCENARIOS, scenario

WEB = Path(__file__).parent / "web"
app = FastAPI(title="Waterjet Control Lab", version=__version__, docs_url=None, redoc_url=None)
MAX_SESSIONS = 64
SESSION_TTL_S = 1800


class CommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    surge: float = Field(default=0, ge=-1, le=1)
    turn: float = Field(default=0, ge=-1, le=1)
    control: Literal["manual", "heading"] = "manual"
    heading_deg: float = Field(default=0, ge=0, lt=360)


class TickInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: CommandInput
    scans: int = Field(default=2, ge=1, le=20, strict=True)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["arm", "run", "stop", "reset", "estop", "release_estop"]


class FaultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fault: Fault
    enabled: bool


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["harbor", "heading", "pressure", "watchdog", "estop"]


class WindInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    east_n: float = Field(ge=-1000, le=1000)
    north_n: float = Field(ge=-1000, le=1000)


@dataclass
class Session:
    sim: Simulator = field(default_factory=Simulator)
    touched: float = field(default_factory=time.monotonic)
    lock: threading.RLock = field(default_factory=threading.RLock)


sessions: dict[str, Session] = {}
sessions_lock = threading.Lock()


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo raw non-finite JSON values or arbitrary request bodies into responses.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()
            ]
        },
    )


def get_session(session_id: str) -> Session:
    with sessions_lock:
        item = sessions.get(session_id)
        if item is None or time.monotonic() - item.touched > SESSION_TTL_S:
            sessions.pop(session_id, None)
            raise HTTPException(404, "Session expired; reload to start a new simulation")
        item.touched = time.monotonic()
        return item


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__, "simulation_only": True}


@app.post("/api/sessions", status_code=201)
def create_session():
    with sessions_lock:
        now = time.monotonic()
        for key in [key for key, value in sessions.items() if now - value.touched > SESSION_TTL_S]:
            del sessions[key]
        if len(sessions) >= MAX_SESSIONS:
            raise HTTPException(503, "Demo is busy; please try again shortly")
        session_id = secrets.token_urlsafe(24)
        item = Session()
        sessions[session_id] = item
        return {"session_id": session_id, "state": item.sim.snapshot(), "scenarios": SCENARIOS}


@app.get("/api/sessions/{session_id}")
def read_session(session_id: str):
    item = get_session(session_id)
    with item.lock:
        return item.sim.snapshot()


@app.post("/api/sessions/{session_id}/tick")
def tick(session_id: str, data: TickInput):
    item = get_session(session_id)
    with item.lock:
        item.sim.receive(Command(**data.command.model_dump()))
        return item.sim.step(data.scans)


@app.post("/api/sessions/{session_id}/action")
def action(session_id: str, data: ActionInput):
    item = get_session(session_id)
    with item.lock:
        accepted = item.sim.action(data.action)
        return {"accepted": accepted, "state": item.sim.snapshot()}


@app.post("/api/sessions/{session_id}/fault")
def fault(session_id: str, data: FaultInput):
    item = get_session(session_id)
    with item.lock:
        item.sim.inject(data.fault, data.enabled)
        return item.sim.snapshot()


@app.post("/api/sessions/{session_id}/wind")
def wind(session_id: str, data: WindInput):
    item = get_session(session_id)
    with item.lock:
        item.sim.wind_east_n, item.sim.wind_north_n = data.east_n, data.north_n
        return item.sim.snapshot()


@app.post("/api/sessions/{session_id}/scenario")
def load_scenario(session_id: str, data: ScenarioInput):
    item = get_session(session_id)
    with item.lock:
        item.sim = scenario(data.name)
        return item.sim.snapshot()


@app.get("/api/sessions/{session_id}/history")
def history(session_id: str):
    item = get_session(session_id)
    with item.lock:
        return item.sim.records()


@app.get("/api/sessions/{session_id}/export.csv")
def export_csv(session_id: str):
    item = get_session(session_id)
    with item.lock:
        return Response(
            item.sim.csv(),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="waterjet-simulation.csv"',
            },
        )


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    with sessions_lock:
        sessions.pop(session_id, None)
    return Response(status_code=204)


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


@app.get("/api/docs", include_in_schema=False)
def reference():
    return FileResponse(WEB / "reference.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


def main():
    uvicorn.run(
        "waterjet_lab.api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8787")),
        workers=1,
    )


if __name__ == "__main__":
    main()
