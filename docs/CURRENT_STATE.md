# SignOS Track A — Current State (authoritative, overrides the original batch-1-from-scratch plan)

## 1. Project and contract
SignOS: replaces mouse, keyboard and touchpad on Windows with ISL signs plus direct hand gestures (point, pinch, swipe, scroll). Direct gestures are a separate control layer from ISL.
Track A (perception): camera → MediaPipe hand landmarks → direct-gesture state machine → ISL temporal classifier → JSON lines to the intent bus.
Track B (separate chat): app detection, UI Automation, action execution, SQLite memory. Track A never touches these.
Only interface: the intent bus, schema signos.intent.v1, unchanged. One JSON object per line, flushed and fsynced after every write.
Evidence rules: every number is tagged MEASURED-LOCAL, MEASURED-AIHUB, MEASURED-QDC or PROJECTED. ISL signs need an authentic ISLRTC source and are never invented. Raw video is never part of runtime.

## 2. How we got here
The Nemotron hosted API returned "Service temporarily overloaded" on every BATCH 1 attempt, so all of Track A was built directly in a Claude chat instead. Batches 1 to 6 were delivered in full there. Two environment problems were fixed: the venv was pointed at C:\dev\signos\.venv, and imports were rewritten from an assumed nested signos\src\... layout to the real layout (src\perception next to Track B's src\context_action).

## 3. Environment (verified from actual output on this machine — treat as ground truth)
- Venv: C:\dev\signos\.venv, Python 3.11.15.
- Layout: C:\dev\signos\src\perception (Track A), src\context_action (Track B), tests\, scripts\, docs\, state\. **This is the repo root — do not nest a second `signos` folder inside it.**
- Run modules from the repo root: `python -m src.perception.X` and `python -m scripts.X`. pytest.ini has `pythonpath = . src`.
- Installed: mediapipe 1.0.1 (Tasks API — **not** the old `mp.solutions` API), opencv-contrib 5.0.0, numpy 2.4.6, torch 2.14.0, onnx 1.23.0, onnxruntime 1.30.0, scikit-learn 1.9.1.
- Bus path: Track A writes `C:\dev\signos\state\intent_bus.jsonl`. Track B's STATE_DIR resolves to the same folder — verified matching. **Do not use a different relative bus path.**

## 4. Done: code delivered and on disk
- Batch 1: intent_bus.py (writer with strict validation, fsync per line), capture.py (webcam + FPS meter), run_capture.py (idle NONE stream at 5 Hz).
- Batches 2–3: filters.py (One Euro), landmarks.py (MediaPipe wrapper), gestures.py (state machine), run_perception.py (runner with debug overlay). Direct gestures implemented: POINT, PINCH, PINCH_HOLD_STILL, PINCH_HOLD_MOVE, SCROLL_V, SCROLL_H, SWIPE_LEFT, SWIPE_RIGHT, PALM_HOLD, CLUTCH_ON/OFF, NONE, TRANSITION. Tooling: gesture_studio_record.py (landmark sequences only, video opt-in via --save-video), fp_rate_test.py.
- Batch 4 (ISL): features.py, isl_runtime.py (ONNX inference + confirmer: 3 consecutive predictions ≥0.85, 1.5s cooldown), vocab.py + docs\isl_vocab.json (8 candidates present, none confirmed yet), scripts\train_isl.py (GRU, honest eval, ONNX export).
- Batches 5–6: aihub_profile.py, bench_latency.py, render_results.py, docs (ATTRIBUTIONS.md, LICENSES.md, track-a-readme.md).
- Tests: 45 pass, 1 fails (a bug in the confirmer test — needs a real fix, don't invent one from memory, ask to see the actual failing test and the confirmer code before patching).
- **Not yet verified anywhere: everything that touches the camera or MediaPipe.** Only unit-tested with synthetic landmarks so far.

## 5. Pending — this is the actual work queue, in order

1. Fix `landmarks.py` for the mediapipe 1.0.1 Tasks API (no `mp.solutions` on this version) — download `models\hand_landmarker.task`. Untested, [VERIFY].
2. Fix the 1 failing confirmer test (need to see the actual current test + confirmer code first).
3. Verify OpenCV 5.0.0 works with the capture code (DirectShow backend) — untested.
4. Run `pytest -s tests/test_capture.py` — first real `MEASURED-LOCAL` webcam FPS number.
5. Run `run_capture --seconds 10`, validate bus lines.
6. Test each gesture live in the overlay window; tune `GestureConfig` thresholds (all currently untuned starting values).
7. Run `fp_rate_test --seconds 120` (valid only if hands visible ≥50% of the time).
8. **ISL — blocked on Ashish:** confirm each of the 8 candidates (COPY, PASTE, UNDO, SELECT, SAVE, CANCEL, NEXT, BACK) against ISLRTC, fill `source`/`confirmed` in `docs\isl_vocab.json`, log in `ATTRIBUTIONS.md`. Never improvise a hand shape for an unconfirmed word. Then record ≥30 samples/sign + NONE/TRANSITION, two sessions, train with `--holdout-session`, report the real confusion matrix and P/R/F1.
9. Run `bench_latency` and `render_results`. AI Hub profiling needs the API token, x64 Python, and the hand-landmark export module name [VERIFY]. QDC is optional — if skipped, say "not run," don't imply otherwise.
10. Commit the 4 drafted commits (not confirmed made yet).
11. End-to-end check: run Track A live, confirm Track B's tailer actually sees the real intents (it's currently running on synthetic intents only).

## 6. Measured numbers so far
None yet. No FPS, latency, accuracy, or false-positive numbers exist yet — anything claimed before this point in any doc/deck is wrong.

## 7. Contract notes for Track B (already resolved, don't re-litigate)
- Pointer coords: camera-normalized 0–1, mirrored view, source is index knuckle not fingertip. Track B applies its own ~0.15 edge margin.
- POINT, SCROLL_V/H, PINCH_HOLD_MOVE stream at ~30Hz with a pointer. **Track B derives scroll direction/delta from successive pointer positions — this is not a schema gap, it's the intended design.**
- PINCH = one click, emitted on release. PINCH_HOLD_STILL = one-shot after 450ms held still.
- Drag ends at the first intent that isn't PINCH_HOLD_MOVE.
- CLUTCH_ON suspends gestures and ISL until CLUTCH_OFF.
- NONE/TRANSITION carry placeholder hand/confidence values, rate-limited ~5Hz — Track B should ignore both for action purposes.
- Confidence on direct gestures is the tracker's hand score, not a calibrated gesture probability.
- Hand dropout <200ms ignored; longer resets state and emits NONE.
- ISL events: `kind:"isl"`, `intent:"ISL_<NAME>"`, `hand:"two"` when both hands visible. Suppressed while a pinch/point/scroll is active or while clutched.
- DOUBLE_PINCH is never emitted by Track A — Track B synthesizes it from two PINCH intents if needed.

## 8. Known risks
- mediapipe 1.0.1 / OpenCV 5.0.0 / numpy 2.4.6 are newer than the APIs the original code assumed — expect fixes on first real camera contact.
- ISL accuracy will look optimistic with ~30 single-person samples per sign until a second-session holdout is run — report it honestly regardless.
- The GRU may not compile on the Snapdragon QNN path — if so, record the failure as-is in `results/`, don't hide it.