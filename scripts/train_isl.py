"""Train GRU on recorded landmark sequences, evaluate honestly, export ONNX."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from src.perception.features import HZ, T_DEFAULT, build_features
from src.perception.vocab import confirmed_signs

ROOT = Path(__file__).resolve().parents[1]
DATA, MODELS, RESULTS = ROOT / "training" / "datasets", ROOT / "models", ROOT / "results"


class GRUNet(nn.Module):
    def __init__(self, f, c, h=64):
        super().__init__()
        self.gru = nn.GRU(f, h, num_layers=2, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(h, c)

    def forward(self, x):
        o, _ = self.gru(x)
        return self.fc(o[:, -1])


def crop(f, T, train, rng):
    if len(f) < T:
        f = np.pad(f, ((T - len(f), 0), (0, 0)), mode="edge")
    off = int(rng.integers(0, len(f) - T + 1)) if train else (len(f) - T) // 2
    return f[off:off + T]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--holdout-session", default=None, help="test on an entire session (more honest)")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    torch.manual_seed(a.seed)

    want = ["NONE", "TRANSITION"] + confirmed_signs()
    classes, X, y, sess, aspects = [], [], [], [], []
    for name in want:
        files = sorted((DATA / name).glob("*.npz")) if (DATA / name).exists() else []
        if not files:
            continue
        ci = len(classes)
        classes.append(name)
        for p in files:
            z = np.load(p, allow_pickle=False)
            X.append(build_features(z["lm"], z["present"], z["ts"], HZ, None, float(z["aspect"])))
            y.append(ci)
            sess.append(str(z["session"]))
            aspects.append(float(z["aspect"]))
    y = np.array(y)
    counts = {c: int((y == i).sum()) for i, c in enumerate(classes)}
    print("samples per class:", counts)
    if "NONE" not in classes or len(classes) < 3:
        raise SystemExit("need NONE + at least one confirmed sign with recordings")
    low = [c for c, n in counts.items() if n < 10]
    if low:
        raise SystemExit(f"fewer than 10 samples for {low}; record more (spec asks >=30/sign)")
    warns = [f"{c} has {n} samples (<30)" for c, n in counts.items() if n < 30]
    if len(set(sess)) < 2:
        warns.append("single recording session: accuracy will be optimistic; record a 2nd session and use --holdout-session")

    idx = np.arange(len(y))
    if a.holdout_session:
        te = idx[[s == a.holdout_session for s in sess]]
        tr = idx[[s != a.holdout_session for s in sess]]
        split = f"holdout session {a.holdout_session}"
    else:
        tr, te = train_test_split(idx, test_size=0.25, stratify=y, random_state=a.seed)
        split = "stratified random 75/25 by sample (same session(s) in train and test)"
    allf = np.concatenate([X[i] for i in tr])
    mean, std = allf.mean(0).astype(np.float32), np.maximum(allf.std(0), 0.1).astype(np.float32)
    Xn = [((f - mean) / std).astype(np.float32) for f in X]
    T, F, C = T_DEFAULT, Xn[0].shape[1], len(classes)

    model = GRUNet(F, C)
    w = torch.tensor(len(tr) / (C * np.maximum(np.bincount(y[tr], minlength=C), 1)), dtype=torch.float32)
    lossf, opt = nn.CrossEntropyLoss(weight=w), torch.optim.Adam(model.parameters(), lr=2e-3)
    for ep in range(a.epochs):  # fixed epochs, NO checkpoint selection on the test set
        model.train()
        perm, tot = rng.permutation(tr), 0.0
        for b in range(0, len(perm), 32):
            ids = perm[b:b + 32]
            xb = np.stack([crop(Xn[i], T, True, rng) for i in ids])
            xb = xb + rng.normal(0, 0.05, xb.shape).astype(np.float32)
            loss = lossf(model(torch.from_numpy(xb)), torch.from_numpy(y[ids]))
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss) * len(ids)
        if ep % 10 == 0 or ep == a.epochs - 1:
            print(f"epoch {ep:3d}  train loss {tot / len(tr):.4f}")

    model.eval()

    def predict(ids):
        xb = torch.from_numpy(np.stack([crop(Xn[i], T, False, rng) for i in ids]))
        with torch.no_grad():
            return model(xb).argmax(1).numpy()

    ptr, pte = predict(tr), predict(te)
    rep = classification_report(y[te], pte, labels=list(range(C)), target_names=classes, output_dict=True, zero_division=0)
    cm = confusion_matrix(y[te], pte, labels=list(range(C)))
    print("\nconfusion matrix (rows=true, cols=pred):", classes)
    print(cm)
    print(classification_report(y[te], pte, labels=list(range(C)), target_names=classes, zero_division=0))
    print(f"train acc {np.mean(ptr == y[tr]):.3f} | test acc {np.mean(pte == y[te]):.3f}  (MEASURED-LOCAL)")

    MODELS.mkdir(exist_ok=True); RESULTS.mkdir(exist_ok=True)
    meta = {"classes": classes, "T": T, "F": F, "hz": HZ, "aspect": float(np.mean(aspects)),
            "mean": mean.tolist(), "std": std.tolist()}
    (MODELS / "isl_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    dummy = torch.zeros(1, T, F)
    for path, dyn in ((MODELS / "isl_gru.onnx", True), (MODELS / "isl_gru_static.onnx", False)):
        kw = dict(input_names=["feats"], output_names=["logits"], opset_version=17)
        if dyn:
            kw["dynamic_axes"] = {"feats": {0: "batch"}, "logits": {0: "batch"}}
        try:
            torch.onnx.export(model, dummy, str(path), dynamo=False, **kw)
        except TypeError:
            torch.onnx.export(model, dummy, str(path), **kw)
    import onnxruntime as ort
    sess_ort = ort.InferenceSession(str(MODELS / "isl_gru.onnx"), providers=["CPUExecutionProvider"])
    xb = torch.from_numpy(np.stack([crop(Xn[i], T, False, rng) for i in te[:8]]))
    with torch.no_grad():
        ref = model(xb).numpy()
    diff = float(np.abs(sess_ort.run(None, {"feats": xb.numpy()})[0] - ref).max())
    print(f"ONNX vs torch max abs diff: {diff:.2e}")

    out = {"tag": "MEASURED-LOCAL", "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "classes": classes, "n_per_class": counts, "n_train": int(len(tr)), "n_test": int(len(te)),
           "split": split, "seed": a.seed, "epochs": a.epochs, "train_acc": float(np.mean(ptr == y[tr])),
           "test_acc": float(np.mean(pte == y[te])), "report": rep, "confusion_matrix": cm.tolist(),
           "onnx_max_abs_diff": diff, "caveats": warns}
    (RESULTS / "isl_eval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("saved models/isl_gru.onnx, models/isl_gru_static.onnx, models/isl_meta.json, results/isl_eval.json")


if __name__ == "__main__":
    main()