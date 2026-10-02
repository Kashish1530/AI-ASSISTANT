import json
import os
import threading
from collections import Counter
from datetime import datetime, timezone

LOG_DIR = os.environ.get("LOG_DIR", "logs")
AUDIT_PATH = os.path.join(LOG_DIR, "audit.jsonl")
METRICS_PATH = os.path.join(LOG_DIR, "metrics.jsonl")
_lock = threading.Lock()


PRICE_INPUT_PER_M = float(os.environ.get("PRICE_INPUT_PER_M", "0.15"))
PRICE_OUTPUT_PER_M = float(os.environ.get("PRICE_OUTPUT_PER_M", "0.75"))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _append(path, record):
    with _lock:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def sanitize_args(tool, args):
    """Keep the audit trail useful without storing sensitive payloads."""
    clean = {}
    for k, v in (args or {}).items():
        if tool == "send_email" and k == "body":
            clean["body_chars"] = len(str(v))
        elif isinstance(v, str) and len(v) > 200:
            clean[k] = v[:200] + "...[truncated]"
        else:
            clean[k] = v
    return clean


def audit(event, **fields):
    _append(AUDIT_PATH, {"ts": _now(), "event": event, **fields})


def estimate_cost(prompt_tokens, completion_tokens):
    return (prompt_tokens / 1e6) * PRICE_INPUT_PER_M + (completion_tokens / 1e6) * PRICE_OUTPUT_PER_M


def record_request(**fields):
    rec = {"ts": _now(), **fields}
    rec["cost_usd"] = round(estimate_cost(fields.get("prompt_tokens", 0), fields.get("completion_tokens", 0)), 8)
    _append(METRICS_PATH, rec)
    return rec


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass 
    return out


def percentile(values, p):
    """Linear-interpolated percentile (same method as numpy's default)."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize(records):
    n = len(records)
    if n == 0:
        return {"requests": 0}
    lat = [r["latency_s"] for r in records if "latency_s" in r]
    costs = [r.get("cost_usd", 0) for r in records]
    tools = Counter(t for r in records for t in r.get("tools", []))
    status = Counter(r.get("status", "unknown") for r in records)
    return {
        "requests": n,
        "error_rate": round(status.get("error", 0) / n, 4),
        "status_counts": dict(status),
        "latency_p50_s": round(percentile(lat, 50), 3),
        "latency_p90_s": round(percentile(lat, 90), 3),
        "latency_mean_s": round(sum(lat) / len(lat), 3),
        "total_tokens": sum(r.get("prompt_tokens", 0) + r.get("completion_tokens", 0) for r in records),
        "cost_total_usd": round(sum(costs), 6),
        "cost_per_request_usd": round(sum(costs) / n, 6),
        "tool_usage": dict(tools),
    }
