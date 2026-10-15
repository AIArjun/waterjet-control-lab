"use strict";
const $ = id => document.getElementById(id);
let session = null, state = null, paused = false, controlMode = "manual", trail = [], trend = [];
let queue = Promise.resolve(), eventSignature = "", lastTime = -1;

function request(path, body, method = "POST") {
  const task = queue.then(async () => {
    const response = await fetch(path, {method, headers: {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(6000)});
    if (!response.ok) {
      const error = await response.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "Request rejected; check input values.");
    }
    return response.status === 204 ? null : response.json();
  });
  queue = task.catch(() => {});
  return task;
}
const endpoint = suffix => `/api/sessions/${session}/${suffix}`;
function feedback(message, alarm = false) {$("notice").textContent = message; $("notice").classList.toggle("alarm", alarm);}
function command() {return {surge: Number($("surge").value) / 100, turn: Number($("turn").value) / 100,
  control: controlMode, heading_deg: Number($("target-heading").value)};}
function setMode(mode) {
  controlMode = mode;
  $("manual-mode").classList.toggle("selected", mode === "manual");
  $("heading-mode").classList.toggle("selected", mode === "heading");
  $("turn-control").hidden = mode === "heading";
  $("heading-control").hidden = mode !== "heading";
}
function syncControls(s) {
  $("surge").value = s.command.surge * 100; $("turn").value = s.command.turn * 100;
  $("target-heading").value = Math.round(s.command.heading_deg); setMode(s.command.control); labels();
}
function labels() {
  $("surge-value").textContent = `${$("surge").value}%`; $("turn-value").textContent = `${$("turn").value}%`;
  $("target-value").textContent = `${String($("target-heading").value).padStart(3, "0")}°`;
}
function render(s) {
  state = s;
  $("speed").textContent = (Math.hypot(s.surge_mps, s.sway_mps) * 1.943844).toFixed(2);
  $("heading").textContent = s.heading_deg.toFixed(1).padStart(5, "0");
  $("pressure").textContent = s.pressure_bar.toFixed(0); $("temperature").textContent = s.temperature_c.toFixed(1);
  $("heading-detail").textContent = s.command.control === "heading" ? `Holding ${s.command.heading_deg.toFixed(0).padStart(3, "0")}° · PID controller` : "Manual control";
  $("pressure-card").classList.toggle("alarm", s.pressure_bar < 60); $("temp-card").classList.toggle("alarm", s.temperature_c >= 85);
  $("mode").textContent = s.mode; $("mode").className = `mode ${s.mode}`;
  const minutes = Math.floor(s.time_s / 60), seconds = s.time_s % 60;
  $("elapsed").textContent = `${String(minutes).padStart(2, "0")}:${seconds.toFixed(1).padStart(4, "0")}`;
  for (const jet of ["port", "starboard"]) {
    const value = s[`${jet}_feedback`], demand = s[`${jet}_output`];
    $(`${jet}-number`).textContent = `${Math.round(value * 100)}%`;
    $(`${jet}-demand`).textContent = `Demand ${Math.round(demand * 100)}%`;
    $(`${jet}-direction`).textContent = Math.abs(value) < .02 ? "NEUTRAL" : value > 0 ? "AHEAD" : "ASTERN";
    const bar = $(`${jet}-bar`); bar.style.width = `${Math.abs(value) * 50}%`;
    bar.style.left = `${value < 0 ? 50 + value * 50 : 50}%`;
  }
  for (const checkbox of document.querySelectorAll("[data-fault]")) checkbox.checked = s.faults.includes(checkbox.dataset.fault);
  if (s.latched.length) feedback(`Latched: ${s.latched.join(" · ")}. Clear the cause, select Neutral, release stop if needed, then Reset fault.`, true);
  else if (s.mode === "RUNNING") feedback(s.command.control === "heading" ? "Heading controller engaged. Compare the vessel response with the target heading." : "Controller running. Change thrust and turn demand, or introduce a fault.");
  else if (s.mode === "ARMED") feedback("Controller armed. Select Run to enable commanded thrust.");
  else feedback("Outputs inhibited. Keep controls neutral, select Arm, then Run.");
  if (s.time_s < lastTime) {trail = []; trend = [];}
  if (s.time_s !== lastTime) {
    trail.push([s.east_m, s.north_m]); if (trail.length > 1800) trail.shift();
    trend.push(s); if (trend.length > 600) trend.shift();
  }
  lastTime = s.time_s;
  const signature = JSON.stringify(s.events);
  if (signature !== eventSignature) {
    eventSignature = signature; $("event-count").textContent = s.events.length;
    $("event-list").replaceChildren(...s.events.slice(0, 40).map(e => {
      const row = document.createElement("div"); row.className = `event ${e.level}`;
      const stamp = document.createElement("time"); stamp.textContent = e.time_s.toFixed(1);
      const dot = document.createElement("span"); dot.className = "dot";
      const text = document.createElement("span"); text.className = "event-text"; text.textContent = e.message;
      row.append(stamp, dot, text); return row;
    }));
  }
  drawSea(); drawTrend();
}
function context(id) {
  const canvas = $(id), rect = canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
    canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
  }
  const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
  return {ctx, w: rect.width, h: rect.height};
}
function drawSea() {
  if (!state) return;
  const {ctx: c, w, h} = context("sea"), s = state;
  const range = Math.max(45, ...trail.map(p => Math.max(Math.abs(p[0]), Math.abs(p[1])) + 12));
  const scale = Math.min(w, h) / (range * 2), cx = w * .5, cy = h * .57;
  const X = x => cx + x * scale, Y = y => cy - y * scale;
  c.fillStyle = "#eaf2f3"; c.fillRect(0, 0, w, h);
  const grid = 20 * Math.max(1, Math.ceil(range / 120)); c.strokeStyle = "#d9e7e9"; c.lineWidth = .6;
  for (let x = -Math.ceil(w / scale / grid) * grid; x < w / scale; x += grid) {c.beginPath(); c.moveTo(X(x), 0); c.lineTo(X(x), h); c.stroke();}
  for (let y = -Math.ceil(h / scale / grid) * grid; y < h / scale; y += grid) {c.beginPath(); c.moveTo(0, Y(y)); c.lineTo(w, Y(y)); c.stroke();}
  c.fillStyle = "#d0dfe2"; c.fillRect(0, h - 40, w * .23, 40); c.fillRect(w * .07, h - 90, 15, 90); c.fillRect(w * .18, h - 75, 13, 75);
  c.fillStyle = "#91aab2"; c.font = "8px Segoe UI"; c.fillText("VIRTUAL HARBOR", 13, h - 15);
  c.save(); c.setLineDash([3, 4]); c.strokeStyle = "#b2cbd0"; c.beginPath(); c.arc(cx, cy, 18, 0, Math.PI * 2); c.stroke(); c.restore();
  c.fillStyle = "#8fa8b2"; c.fillText("ORIGIN", cx + 24, cy + 4);
  if (trail.length > 1) {c.beginPath(); trail.forEach((p, i) => i ? c.lineTo(X(p[0]), Y(p[1])) : c.moveTo(X(p[0]), Y(p[1]))); c.lineWidth = 2; c.strokeStyle = "#379eaa"; c.stroke();}
  const x = X(s.east_m), y = Y(s.north_m);
  if (s.command.control === "heading") {const target = s.command.heading_deg * Math.PI / 180; c.save(); c.setLineDash([5, 5]); c.strokeStyle = "#ba9a5f"; c.beginPath(); c.moveTo(x, y); c.lineTo(x + Math.sin(target) * 85, y - Math.cos(target) * 85); c.stroke(); c.restore();}
  c.save(); c.translate(x, y); c.rotate(s.heading_deg * Math.PI / 180);
  c.shadowBlur = 12; c.shadowColor = "#19465830"; c.shadowOffsetY = 5;
  c.beginPath(); c.moveTo(0, -29); c.bezierCurveTo(8, -22, 13, -10, 13, 15); c.lineTo(10, 24); c.lineTo(-10, 24); c.lineTo(-13, 15); c.bezierCurveTo(-13, -10, -8, -22, 0, -29); c.closePath(); c.fillStyle = "#fff"; c.fill(); c.shadowBlur = 0; c.shadowOffsetY = 0; c.strokeStyle = "#245467"; c.lineWidth = 1.5; c.stroke();
  c.fillStyle = "#225164"; c.fillRect(-7, -4, 14, 14); c.fillStyle = "#72afbb"; c.fillRect(-5, -2, 10, 4);
  for (const [offset, thrust] of [[-7, s.port_feedback], [7, s.starboard_feedback]]) {
    c.fillStyle = "#149e9b"; c.fillRect(offset - 2, 20, 4, 6);
    if (s.mode === "RUNNING" && Math.abs(thrust) > .02) {c.strokeStyle = "#3abbb3"; c.lineWidth = 3; c.beginPath(); c.moveTo(offset, 27); c.lineTo(offset, 28 + Math.abs(thrust) * 30); c.stroke();}
  }
  c.restore();
  c.fillStyle = "#6c929e"; c.font = "9px Consolas"; c.fillText(`E ${s.east_m.toFixed(1)} m / N ${s.north_m.toFixed(1)} m`, 15, 23);
  c.strokeStyle = "#6a929e"; c.lineWidth = 1; c.beginPath(); c.moveTo(w - 30, 38); c.lineTo(w - 30, 16); c.lineTo(w - 34, 23); c.moveTo(w - 30, 16); c.lineTo(w - 26, 23); c.stroke(); c.fillText("N", w - 33, 49);
  c.beginPath(); c.moveTo(w - 75, h - 22); c.lineTo(w - 25, h - 22); c.stroke(); c.fillText(`${(50 / scale).toFixed(0)} m`, w - 66, h - 30);
}
function drawTrend() {
  if (!state) return;
  const {ctx: c, w, h} = context("trend"), left = 28, right = w - 15, top = 6, bottom = h - 22;
  const mid = (top + bottom) / 2, amp = (bottom - top) / 2, end = state.time_s, start = Math.max(0, end - 60);
  c.font = "8px Consolas"; c.strokeStyle = "#e6edef"; c.fillStyle = "#91a3ac"; c.lineWidth = .6;
  for (const value of [-1, 0, 1]) {const y = mid - value * amp; c.beginPath(); c.moveTo(left, y); c.lineTo(right, y); c.stroke(); c.fillText(`${value * 100}`, 0, y + 3);}
  const duration = Math.max(10, end - start);
  for (const [field, color] of [["port_feedback", "#008d8b"], ["starboard_feedback", "#d5a050"]]) {
    c.strokeStyle = color; c.lineWidth = 1.6; c.beginPath(); let first = true;
    for (const sample of trend.filter(p => p.time_s >= start)) {const x = left + (sample.time_s - start) / duration * (right - left), y = mid - sample[field] * amp; if (first) c.moveTo(x, y); else c.lineTo(x, y); first = false;}
    c.stroke();
  }
  c.fillText(`${start.toFixed(0)} s`, left, h - 5); c.fillText(`${(start + duration).toFixed(0)} s`, right - 25, h - 5);
}
async function mutate(suffix, body) {
  try {const result = await request(endpoint(suffix), body); render(result.state || result); if (result.accepted === false) feedback("Action rejected. Check the event journal and controller permissives.", true);}
  catch (error) {feedback(error.message, true);}
}
async function pump() {
  try {
    if (!paused && session) {render(await request(endpoint("tick"), {command: command(), scans: 2})); $("connection").textContent = "● Connected";}
  } catch (error) {$("connection").textContent = "○ Connection interrupted"; feedback(error.message, true);}
  setTimeout(pump, 100);
}
for (const slider of ["surge", "turn", "target-heading"]) $(slider).addEventListener("input", labels);
$("manual-mode").addEventListener("click", () => setMode("manual")); $("heading-mode").addEventListener("click", () => setMode("heading"));
$("neutral").addEventListener("click", () => {$("surge").value = $("turn").value = 0; labels();});
for (const button of document.querySelectorAll("[data-action]")) button.addEventListener("click", async () => {
  if (button.dataset.action === "stop") {$("surge").value = $("turn").value = 0; labels();}
  if (["arm", "run", "reset"].includes(button.dataset.action)) await mutate("tick", {command: command(), scans: 1});
  await mutate("action", {action: button.dataset.action});
});
for (const box of document.querySelectorAll("[data-fault]")) box.addEventListener("change", () => mutate("fault", {fault: box.dataset.fault, enabled: box.checked}));
for (const button of document.querySelectorAll("[data-scenario]")) button.addEventListener("click", async () => {
  try {
    const result = await request(endpoint("scenario"), {name: button.dataset.scenario});
    trail = []; trend = []; lastTime = -1; syncControls(result); render(result);
    const history = await request(endpoint("history"), undefined, "GET");
    trail = history.map(p => [p.east_m, p.north_m]); trend = history.slice(-600); drawSea(); drawTrend();
    for (const other of document.querySelectorAll("[data-scenario]")) other.classList.toggle("active", other === button);
  } catch (error) {feedback(error.message, true);}
});
$("pause").addEventListener("click", () => {paused = !paused; $("pause").textContent = paused ? "▶ Resume" : "Ⅱ Pause"; $("connection").textContent = paused ? "Ⅱ Simulation paused" : "● Connected";});
$("export").addEventListener("click", () => {if (session) {const link = document.createElement("a"); link.href = endpoint("export.csv"); link.download = "waterjet-simulation.csv"; link.click();}});
window.addEventListener("resize", () => {drawSea(); drawTrend();});
window.addEventListener("keydown", e => {if (e.key === "Escape" && session) {e.preventDefault(); mutate("action", {action: "estop"});}});
async function init() {
  try {const result = await request("/api/sessions"); session = result.session_id; render(result.state); $("connection").textContent = "● Connected"; pump();}
  catch (error) {feedback(`Could not start simulation: ${error.message}. Reload to try again.`, true);}
}
labels(); init();
