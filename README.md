# SIGNOS — Adaptive Input for Windows

**Control Windows with Indian Sign Language and hand gestures — no keyboard, no mouse, no touchpad.**
The same gesture means a different action depending on what you're looking at: `SWIPE_RIGHT` moves a desktop forward, flips a browser tab forward, or advances a slide — automatically, based on context.

Built for the **Snapdragon® AI Lab Build & Present Challenge** (Qualcomm × HP, via Unstop).

---

> **Note on scope:** This README reports the system's real, current state as of the last live test in this build session. Numbers are tagged `MEASURED-LOCAL` (actually run on this machine), `PROJECTED` (blueprint target, not yet measured), or `NOT YET RUN`. Nothing below is invented — see [Working Rule #5](#working-rules) for why that matters here specifically.

---

## What It Does

**Direct gesture control** — point to move the cursor, pinch to click, pinch-and-hold to drag, two-finger motion to scroll. A fist held for ~700ms toggles a "clutch" so ordinary signing doesn't move the pointer.

**Context-aware intent** — the same physical gesture resolves to a different real Windows action depending on the foreground app: `DESKTOP` → next virtual desktop, `BROWSER` → forward, `PRESENTATION` → next slide, `MEDIA` → next track. This mode switch is deterministic (foreground process + fullscreen state), not an AI guess.

**Risk-gated execution** — every action is tiered by risk (R0–R3). R0/R1 fire immediately; destructive actions (R3, e.g. closing a window) require a second, *different* gesture within 5 seconds to confirm — the same gesture repeated does not confirm it.

**Local memory (OBSERVE + SUGGEST only)** — every action that actually executes is logged locally (SQLite, no video, no frames). If a mode repeats strongly enough at the same time-of-day/day-of-week, the dashboard surfaces a passive suggestion. **Nothing auto-switches or auto-executes based on this** — see [What's Honestly Not Built Yet](#whats-honestly-not-built-yet).

**ISL command layer** — a 3-consecutive-frame, 1.5s-cooldown confirmer for ISL sign classification exists and is unit-tested (`isl_runtime.py`). It is not yet wired to a trained model or a confirmed vocabulary — see below.

---

## Live Demo Status

| Piece | Status |
|---|---|
| Camera → hand landmarks (MediaPipe Tasks API) | `MEASURED-LOCAL` — working live, handedness verified correct against a real camera |
| Direct gestures live-fired | `MEASURED-LOCAL` — PINCH, PINCH_HOLD_MOVE (drag), PINCH_HOLD_STILL, PALM_HOLD, SCROLL_V confirmed firing correctly via the live dashboard event timeline |
| SWIPE_LEFT/RIGHT, CLUTCH_ON/OFF | Implemented and unit-tested (`tests/test_gestures.py`), **not yet confirmed live** against a real camera |
| Mode resolution (DESKTOP/BROWSER/PRESENTATION/MEDIA) | `MEASURED-LOCAL` — verified live: PowerPoint in a non-fullscreen (Protected View) window correctly resolved to `DESKTOP`, not `PRESENTATION`, matching the fullscreen-gate design |
| Scroll/volume direction | Implemented (resolved at runtime from consecutive pointer deltas), **directional sign not yet confirmed live** |
| ISL sign recognition | Confirmer logic unit-tested; **no trained model, no confirmed vocabulary yet** |
| UI Automation (tier 1 action execution) | `pywinauto` installed; **not yet exercised live** — falls through to input-injection (tier 3) until confirmed |
| TEXT mode (UI Automation focused-control detection) | **Not yet implemented** |
| Snapdragon NPU profiling (AI Hub) | **Not yet run** |
| False-positive rate (`fp_rate_test`, ≥120s) | **Not yet run** |

---

## Measured Numbers (Real Data Only)

| Metric | Value | Source |
|---|---|---|
| Perception loop FPS | **~19.5–19.9 fps** | `MEASURED-LOCAL`, live camera run |
| Camera → landmark latency | **~12–19 ms** (after cold-start warmup) | `MEASURED-LOCAL`, `run_perception.py --timing-csv` |
| Landmark → intent latency | **~0.02–0.03 ms** | `MEASURED-LOCAL`, same run — gesture state machine overhead is negligible |
| Unit test suite | **65 / 65 passing** | `pytest tests/ -v`, this machine |
| Camera-to-action end-to-end latency | *not yet measured* | blueprint target: 150–250 ms |
| ISL sign accuracy | *not yet measured — no trained model* | — |
| NPU inference time | *not yet measured — AI Hub profiling not run* | Qualcomm AI Hub reports ~294 µs for a comparable MediaPipe hand model on Snapdragon X Elite CRD in one published job; this is **not our number** and is cited only as a target reference, not a SignOS result |

No accuracy, latency, or NPU number in this README is invented. Anything not in this table has not been run.

---

## Challenge Fit — Evaluation Area Map

| Evaluation Area | SignOS Evidence |
|---|---|
| **Technical Implementation** | Camera → landmarks → temporal gesture/ISL recognition → context resolution → risk-gated action broker → native Windows action. Full unit coverage on the recognition and action-routing logic (65/65 tests). Live camera integration confirmed, not just synthetic-data tested. |
| **Application Use Case & Innovation** | Adaptive intent layer, not a sign-to-text demo — the same `SWIPE_RIGHT` intent resolves to a different real OS action per app, deterministically, with a documented, auditable mapping table (`config/mapping.yaml`) that requires no code change to retarget. |
| **Deployment & Accessibility** | Runs as a local background process; raw camera video is never persisted (perception writes structured intent events only, never frames, to `state/intent_bus.jsonl`); dashboard surfaces privacy status (camera: local, raw video: off, network AI: off) at all times. |
| **Presentation & Documentation** | Live Mission Control dashboard (embedded camera feed, mode badge, event timeline, self-documenting gesture library read live from the mapping config, local routine panel) — this README's own honesty about what's unverified is itself part of the presentation case. |

---

## Gesture Library

*(Also rendered live and kept automatically in sync with `config/mapping.yaml` at `http://localhost:8420` — the dashboard version is authoritative; this table is a snapshot.)*

| Gesture | How to perform it | Resolves to, per mode |
|---|---|---|
| `POINT` | Index finger extended, others curled | Cursor follows the index knuckle |
| `PINCH` | Touch thumb + index tip, release within ~450ms | DESKTOP/BROWSER: click · PRESENTATION: advance slide · MEDIA: play/pause |
| `PINCH_HOLD_STILL` | Pinch and hold still ~450ms without moving | Context/right-click (still tier-1 wiring pending) |
| `PINCH_HOLD_MOVE` | Pinch, then move while still pinched | Drag |
| `SCROLL_V` | Index + middle extended, others curled, move hand up/down | DESKTOP/BROWSER: scroll · MEDIA: volume, direction-resolved from motion |
| `SCROLL_H` | Same shape, move hand left/right | Horizontal scroll where mapped |
| `SWIPE_LEFT` / `SWIPE_RIGHT` | Open palm, fast short horizontal motion | DESKTOP: virtual desktop · BROWSER: back/forward · PRESENTATION: prev/next slide · MEDIA: prev/next track |
| `PALM_HOLD` | Open palm held still ~800ms | Reserved (command palette, not yet wired to an action) |
| `CLUTCH_ON` / `CLUTCH_OFF` | Fist held ~700ms, toggles | Suspends/resumes pointer control so ordinary signing doesn't move the cursor |
| `DOUBLE_PINCH` | *Not currently emitted by any live detector* | Present only as the R3 confirmation-gate demo mapping in `mapping.yaml` |

---

## Architecture

See **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the full system diagram, sequence flows, component map, and the fixed intent-bus contract.

```
CAMERA → HAND LANDMARKS → DIRECT GESTURE STATE MACHINE ─┐
                        → ISL TEMPORAL CONFIRMER ────────┼→ INTENT BUS (JSONL, local file)
                                                          │
FOREGROUND WINDOW → MODE RESOLVER ───────────────────────┤
                                                          ▼
                              MAPPING TABLE (config/mapping.yaml)
                                                          ▼
                              RISK-GATED ACTION BROKER (R0–R3)
                              tier 1: UI Automation → tier 2: app adapter → tier 3: input injection
                                                          ▼
                                                  WINDOWS ACTION
                                                          ▼
                                    LOCAL MEMORY (SQLite, OBSERVE + SUGGEST)
                                                          ▼
                                    MISSION CONTROL DASHBOARD (localhost:8420)
```

---

## Quick Start

```powershell
git clone https://github.com/ashish-doing/SignOS.git
cd SignOS
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-track-a.txt -r requirements-track-b.txt
```

Every new terminal, before running anything:
```powershell
$env:PYTHONPATH = "src"
```

Run all three processes, one per terminal:
```powershell
# terminal 1 — perception (camera + gesture recognition), streams camera to the dashboard
python -m src.perception.run_perception --camera 0 --hand right --no-window

# terminal 2 — context resolution + action execution + local memory logging
python -m context_action.main_loop

# terminal 3 — Mission Control dashboard
python -m context_action.dashboard
```

Open **http://localhost:8420**.

### Run tests
```powershell
pytest tests/ -v
# 65 passed
```

---

## Working Rules

This project follows explicit non-negotiable rules carried through the whole build, stated here because they explain why this README looks the way it does:

1. Every ISL sign must trace to an authentic ISLRTC source, logged in `docs/ATTRIBUTIONS.md` — never invented.
2. Every latency/accuracy/FPS figure is tagged `MEASURED-LOCAL` / `MEASURED-AIHUB` / `MEASURED-QDC` / `PROJECTED` — never stated as fact without a tag.
3. Raw camera video is never part of the runtime. Training clips (once ISL recording starts) are a separate, never-committed path.
4. Destructive actions require a second, distinct gesture to confirm — never the same gesture repeated.
5. **A number that wasn't actually measured this session is never claimed as measured.** This is why the tables above have explicit "not yet run" rows instead of plausible-looking placeholder numbers.

---

## What's Honestly Not Built Yet

- **ISL vocabulary is unconfirmed.** 8 candidate command words exist in `docs/isl_vocab.json`; none have been verified against ISLRTC (islrtc.nic.in) yet. No sign is recordable or trainable until it is.
- **No trained ISL model.** `train_isl.py` and the ONNX inference path exist; nothing has been trained.
- **TEXT mode does not exist yet** — needs UI Automation focused-control detection, not yet implemented.
- **Memory learning stops at SUGGEST.** There is no ASSIST or AUTO level — the system never pre-arms a mode or executes anything based on a learned pattern without you touching a gesture yourself. This is a deliberate scope decision given remaining build time, not an oversight.
- **UI Automation (tier 1 action execution) is installed but not proven live.** Until confirmed, assume actions are running through tier-3 input injection.
- **No Snapdragon NPU number exists for this project.** The AI Hub profiling step has not been run.
- **No false-positive rate has been measured.**

---

## Project Structure

```
SignOS/
├── config/
│   └── mapping.yaml              intent → mode → action lookup table
├── docs/
│   ├── ATTRIBUTIONS.md
│   ├── CURRENT_STATE.md
│   ├── LICENSES.md
│   ├── isl_vocab.json            8 candidate ISL commands, none confirmed yet
│   └── track-a-readme.md
├── models/
│   └── hand_landmarker.task      MediaPipe Tasks API model
├── src/
│   ├── perception/
│   │   ├── capture.py            webcam + FPS meter
│   │   ├── landmarks.py          MediaPipe HandLandmarker wrapper
│   │   ├── filters.py            One Euro filter (pointer smoothing)
│   │   ├── gestures.py           direct-gesture state machine
│   │   ├── features.py           ISL feature builder (train/serve parity)
│   │   ├── isl_runtime.py        ONNX inference + temporal confirmer
│   │   ├── vocab.py              confirmed-sign loader
│   │   ├── intent_bus.py         writer, fsync per line, schema-validated
│   │   └── run_perception.py     live runner + MJPEG camera stream
│   └── context_action/
│       ├── window_detector.py    foreground app/window (pywin32)
│       ├── mode_resolver.py      deterministic mode lookup
│       ├── mapping.py            YAML-backed action resolver
│       ├── action_broker.py      risk-gated tiered execution (R0–R3)
│       ├── actions.py            tier-3 input-injection fallback
│       ├── uia_actions.py        tier-1 UI Automation
│       ├── adapters/powerpoint.py tier-2 PowerPoint COM adapter
│       ├── intent_bus.py         reader, byte-offset tailer
│       ├── memory_store.py       local SQLite event log
│       ├── routine_engine.py     OBSERVE+SUGGEST pattern detection
│       ├── main_loop.py          wires everything end-to-end
│       └── dashboard.py          Mission Control web UI
├── scripts/
│   ├── aihub_profile.py
│   ├── bench_latency.py
│   ├── fp_rate_test.py
│   ├── gesture_studio_record.py
│   ├── render_results.py
│   └── train_isl.py
├── tests/                        65 tests, all passing
├── state/                        intent_bus.jsonl, local memory DB (gitignored)
├── ARCHITECTURE.md
└── README.md
```

---

## Author

**Ashish Kumar** — B.Tech ECE, IIIT Guwahati (Batch 2024–2028)

[![GitHub](https://img.shields.io/badge/GitHub-ashish--doing-181717?style=flat-square&logo=github)](https://github.com/ashish-doing)

---

## License

See [LICENSES.md](./docs/LICENSES.md) and [ATTRIBUTIONS.md](./docs/ATTRIBUTIONS.md) for third-party model and ISL sourcing terms.