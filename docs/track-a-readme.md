# Track A - perception and control loop
Camera -> MediaPipe landmarks -> direct-gesture state machine -> (optional) ISL GRU -> signos/state/intent_bus.jsonl

Run:        python -m signos.src.perception.run_perception [--isl models\isl_gru.onnx]
Record:     python -m scripts.gesture_studio_record --label <NAME> --n 30 --session S1
Train:      python -m scripts.train_isl [--holdout-session S2]
FP rate:    python -m scripts.fp_rate_test --seconds 120
Latency:    python -m scripts.bench_latency --seconds 30
AI Hub:     python -m scripts.aihub_profile
Report:     python -m scripts.render_results   (writes docs/results.md; every number comes from results/*.json)

Rules: signs need a confirmed source (docs/isl_vocab.json + docs/ATTRIBUTIONS.md). Raw video is never part of
runtime; training uses landmark sequences only (--save-video is opt-in, local, gitignored).
Tags: MEASURED-LOCAL | MEASURED-AIHUB | MEASURED-QDC | PROJECTED. Direct-gesture confidence is the tracker hand score,
not a calibrated probability. Tune thresholds in GestureConfig using the overlay's pinch/ratios readout.