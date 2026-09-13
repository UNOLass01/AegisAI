"""Replay production-like traffic against /predict, then simulate an incident.

Phase A (baseline): clean transactions -> model v1.
Phase B (incident): drifted transactions (+30% legitimate amounts, holiday
spending surge) -> model v2 at higher concurrency.

Ground truth rides along in each request (demo harness only) so Grafana can
plot the precision proxy (correct / total) per model version in real time.

Usage:
    python monitoring/simulate_incident.py
    python monitoring/simulate_incident.py --base-url http://localhost:8000 \\
        --phase-a-n 100 --phase-b-n 200 --workers-b 8
"""
import argparse
import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ml" / "training"))

from dataset import DatasetConfig, generate_dataset  # noqa: E402

TIMEOUT_S = 30


def build_payload(row, version: str) -> dict:
    """Turn one dataset row into a /predict body (ground truth attached)."""
    return {
        "transaction_amount": float(row["transaction_amount"]),
        "merchant_category": str(row["merchant_category"]),
        "hour_of_day": int(row["hour_of_day"]),
        "model_version": version,
        "ground_truth": bool(row["is_fraud"]),
    }


def send_predict(base_url: str, payload: dict) -> tuple[int, dict, float]:
    """POST one payload. Returns (status_code, body, latency_seconds)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/predict",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body, time.perf_counter() - start
    except urllib.error.HTTPError as exc:
        return exc.code, {}, time.perf_counter() - start


def run_phase(base_url: str, payloads: list[dict], max_workers: int = 1,
              sender=send_predict) -> dict:
    """Fire all payloads (optionally concurrently) and summarize the outcome."""
    latencies: list[float] = []
    ok = 0
    correct = 0
    flagged = 0
    true_positives = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_payload = {
            pool.submit(sender, base_url, p): p for p in payloads
        }
        for future in concurrent.futures.as_completed(future_to_payload):
            payload = future_to_payload[future]
            status, body, latency = future.result()
            latencies.append(latency)
            if status == 200:
                ok += 1
                predicted = body.get("is_fraud")
                if predicted == payload["ground_truth"]:
                    correct += 1
                if predicted is True:
                    flagged += 1
                    if payload["ground_truth"] is True:
                        true_positives += 1
    n = len(payloads)
    return {
        "n": n,
        "ok": ok,
        "correct": correct,
        "precision_proxy": round(correct / ok, 4) if ok else 0.0,
        "flagged": flagged,
        "true_positives": true_positives,
        "precision": round(true_positives / flagged, 4) if flagged else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies) * 1000, 2) if latencies else 0.0,
    }


def check_backend(base_url: str) -> None:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"/health returned {resp.status}")
    except Exception as exc:
        raise SystemExit(f"Backend not reachable at {base_url}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate the v2 drift incident.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--phase-a-n", type=int, default=150)
    parser.add_argument("--phase-b-n", type=int, default=300)
    parser.add_argument("--workers-a", type=int, default=1)
    parser.add_argument("--workers-b", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    check_backend(args.base_url)

    clean = generate_dataset(DatasetConfig(n_samples=args.phase_a_n, seed=args.seed))
    drifted = generate_dataset(
        DatasetConfig(n_samples=args.phase_b_n, seed=args.seed + 1, legit_amount_shift=0.30)
    )
    phase_a = [build_payload(r, "v1") for _, r in clean.iterrows()]
    phase_b = [build_payload(r, "v2") for _, r in drifted.iterrows()]

    print(f"Phase A: {len(phase_a)} clean txns -> v1 (workers={args.workers_a})")
    stats_a = run_phase(args.base_url, phase_a, max_workers=args.workers_a)
    print(f"  ok={stats_a['ok']}/{stats_a['n']} precision={stats_a['precision']} "
          f"(tp={stats_a['true_positives']}/flagged={stats_a['flagged']}) "
          f"avg_latency={stats_a['avg_latency_ms']}ms")

    print(f"Phase B (incident): {len(phase_b)} drifted txns -> v2 (workers={args.workers_b})")
    stats_b = run_phase(args.base_url, phase_b, max_workers=args.workers_b)
    print(f"  ok={stats_b['ok']}/{stats_b['n']} precision={stats_b['precision']} "
          f"(tp={stats_b['true_positives']}/flagged={stats_b['flagged']}) "
          f"avg_latency={stats_b['avg_latency_ms']}ms")

    print("Done. Watch Grafana: model mix flips v1->v2, precision proxy drops, latency moves.")


if __name__ == "__main__":
    main()
