import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("DRY_RUN_EMAIL", "true")
os.environ.setdefault("READ_ROOT", os.path.join(HERE, "data"))

from day5_s1_capstone import MODEL, client, load_memory, memory_path, run_capstone_agent  
from eval_cases import CASES  
from metrics import LOG_DIR, estimate_cost, percentile  

def with_retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            transient = "429" in str(e) or "rate" in str(e).lower()
            if not transient or i == tries - 1:
                raise
            time.sleep(5 * 2 ** i)


def deterministic_failures(case, answer, tools, user_id):
    fails = []
    text = (answer or "").lower()
    for t in case.get("expect_tools", []):
        if t not in tools:
            fails.append(f"expected tool '{t}' was not called")
    forbid = case.get("forbid_tools", [])
    if "*" in forbid:
        if tools:
            fails.append(f"no tool should be called, but got {tools}")
    else:
        fails += [f"forbidden tool '{t}' was called" for t in forbid if t in tools]
    fails += [f"answer is missing '{s}'" for s in case.get("must_contain", []) if s.lower() not in text]
    fails += [f"answer contains forbidden '{s}'" for s in case.get("must_not_contain", []) if s.lower() in text]

    if case.get("memory") == "stored" and not load_memory(user_id)["preferences"]:
        fails.append("nothing was written to the memory file")
    if case.get("memory_excludes"):
        mem_text = open(memory_path(user_id)).read().lower() if os.path.exists(memory_path(user_id)) else ""
        fails += [f"memory file contains sensitive value '{s}'" for s in case["memory_excludes"] if s.lower() in mem_text]
    return fails


def judge(case, answer, tools):
    prompt = f"""Grade this agent response against the criteria.
Input: {case['input']}
Criteria: {case['criteria']}
Tools called: {tools}
Agent response: {answer}

Reply with ONLY JSON: {{"pass": true/false, "reason": "one sentence"}}"""
    resp = with_retry(lambda: client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}]))
    cost = estimate_cost(resp.usage.prompt_tokens, resp.usage.completion_tokens)
    raw = resp.choices[0].message.content or ""
    try:
        r = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        return bool(r["pass"]), r["reason"], cost
    except Exception:
        return False, f"judge output unparseable: {raw[:100]}", cost


def run_case(case, run_id):
    user_id = f"eval_{run_id}_{case['id']}"
    m, answer, tools, err = {}, None, [], None
    try:
        answer, tools, _ = with_retry(lambda: run_capstone_agent(user_id, case["input"], metrics_out=m))
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"

    fails, judge_cost = [], 0.0
    if err:
        fails.append(f"agent error: {err}")
    else:
        fails += deterministic_failures(case, answer, tools, user_id)
        if case.get("criteria"):
            ok, why, judge_cost = judge(case, answer, tools)
            if not ok:
                fails.append(f"judge: {why}")

    if os.path.exists(memory_path(user_id)):
        os.remove(memory_path(user_id)) 
    return {
        "id": case["id"], "type": case["type"], "input": case["input"], "answer": answer, "tools": tools,
        "passed": not fails, "failures": fails,
        "latency_s": m.get("latency_s"), "cost_usd": m.get("cost_usd"),
        "tokens": m.get("prompt_tokens", 0) + m.get("completion_tokens", 0),
        "judge_cost_usd": judge_cost,
    }


def build_report(results):
    by_type = defaultdict(lambda: {"passed": 0, "total": 0})
    for r in results:
        by_type[r["type"]]["total"] += 1
        by_type[r["type"]]["passed"] += int(r["passed"])
    lat = [r["latency_s"] for r in results if r["latency_s"] is not None]
    cost = [r["cost_usd"] for r in results if r["cost_usd"] is not None]
    n, passed = len(results), sum(r["passed"] for r in results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": MODEL, "total": n, "passed": passed, "pass_rate": round(passed / n, 4),
        "by_type": {k: {**v, "pass_rate": round(v["passed"] / v["total"], 4)} for k, v in sorted(by_type.items())},
        "latency_p50_s": round(percentile(lat, 50), 3) if lat else None,
        "latency_p90_s": round(percentile(lat, 90), 3) if lat else None,
        "cost_per_query_usd": round(sum(cost) / len(cost), 6) if cost else None,
        "agent_cost_total_usd": round(sum(cost), 6),
        "judge_cost_total_usd": round(sum(r["judge_cost_usd"] for r in results), 6),
        "avg_tokens_per_query": round(sum(r["tokens"] for r in results) / n),
        "failed": [{"id": r["id"], "type": r["type"], "input": r["input"], "failures": r["failures"]}
                   for r in results if not r["passed"]],
    }


def to_markdown(rep):
    lines = [f"## Eval report ({rep['model']})", "",
             f"**Pass rate: {rep['passed']}/{rep['total']} ({rep['pass_rate']:.0%})**", "",
             "| Query type | Passed | Total | Pass rate |", "|---|---|---|---|"]
    lines += [f"| {k} | {v['passed']} | {v['total']} | {v['pass_rate']:.0%} |" for k, v in rep["by_type"].items()]
    lines += ["", "| Metric | Value |", "|---|---|",
              f"| Latency p50 | {rep['latency_p50_s']} s |",
              f"| Latency p90 | {rep['latency_p90_s']} s |",
              f"| Cost per query (agent only) | ${rep['cost_per_query_usd']} |",
              f"| Avg tokens per query | {rep['avg_tokens_per_query']} |",
              f"| Judge cost (total, not in per-query) | ${rep['judge_cost_total_usd']} |", ""]
    if rep["failed"]:
        lines += ["### Failed cases"]
        lines += [f"- #{f['id']} ({f['type']}): {'; '.join(f['failures'])}" for f in rep["failed"]]
    lines += ["", "_Costs use placeholder token rates unless PRICE_INPUT_PER_M / PRICE_OUTPUT_PER_M are set._"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-type", type=int, default=0, help="run only the first N cases of each type")
    args = ap.parse_args()

    cases, seen = [], defaultdict(int)
    for c in CASES:
        if not args.per_type or seen[c["type"]] < args.per_type:
            cases.append(c)
            seen[c["type"]] += 1

    run_id, sleep_s, results = int(time.time()), float(os.environ.get("EVAL_SLEEP_SECONDS", "1")), []
    for c in cases:
        print(f"[{c['id']:>2}/{len(CASES)}] {c['type']:<15} {c['input'][:55]}", flush=True)
        r = run_case(c, run_id)
        results.append(r)
        print("      PASS" if r["passed"] else "      FAIL - " + "; ".join(r["failures"]), flush=True)
        time.sleep(sleep_s)

    rep = build_report(results)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "eval_report.json"), "w") as f:
        json.dump({**rep, "results": results}, f, indent=2, default=str)
    md = to_markdown(rep)
    with open(os.path.join(LOG_DIR, "eval_report.md"), "w") as f:
        f.write(md)
    print("\n" + md)

    min_rate = float(os.environ.get("EVAL_MIN_PASS_RATE", "0.8"))
    if rep["pass_rate"] < min_rate:
        print(f"\nFAILED: pass rate {rep['pass_rate']:.0%} is below the {min_rate:.0%} threshold")
        sys.exit(1)
    print(f"\nOK: pass rate {rep['pass_rate']:.0%} meets the {min_rate:.0%} threshold")


if __name__ == "__main__":
    main() 
