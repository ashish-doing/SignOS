"""Compile + profile the ISL ONNX on a hosted Snapdragon device via Qualcomm AI Hub.
Saves job URLs and the RAW profile; if compile fails, that failure is recorded as-is."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", default=str(ROOT / "models" / "isl_gru_static.onnx"))
    ap.add_argument("--device", default="Snapdragon X Elite CRD")
    ap.add_argument("--options", default="")  # [VERIFY] e.g. "--target_runtime onnx" vs qnn_context_binary
    a = ap.parse_args()
    onnx = Path(a.onnx)
    out = {"tag": "MEASURED-AIHUB", "model": onnx.name, "device_requested": a.device, "options": a.options,
           "when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "started"}
    try:
        import qai_hub as hub
        dev = hub.get_devices(name=a.device)[0]
        out["device_resolved"] = dev.name
        model = hub.upload_model(str(onnx))
        cj = hub.submit_compile_job(model=model, device=dev, options=a.options)
        out["compile_job_url"] = cj.url
        cj.wait()
        pj = hub.submit_profile_job(model=cj.get_target_model(), device=dev)
        out["profile_job_url"] = pj.url
        pj.wait()
        out["profile"] = pj.download_profile()
        out["status"] = "ok"
    except Exception as e:  # record honestly
        out["status"], out["error"] = "failed", repr(e)
    (ROOT / "results").mkdir(exist_ok=True)
    p = ROOT / "results" / f"aihub_{onnx.stem}.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(out["status"], out.get("compile_job_url"), out.get("profile_job_url"), out.get("error", ""))
    print("saved", p)


if __name__ == "__main__":
    main()