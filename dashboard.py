import json
import os

import pandas as pd
import streamlit as st

from metrics import AUDIT_PATH, LOG_DIR, METRICS_PATH, load_jsonl, summarize

st.set_page_config(page_title="Agent monitoring", page_icon="📈", layout="wide")
st.title("📈 Agent monitoring")

with st.sidebar:
    window = st.selectbox("Time window", ["Last hour", "Last 24 hours", "Last 7 days", "All time"], index=1)
    include_eval = st.checkbox("Include eval traffic", value=False)
    st.button("Refresh")
    st.caption(f"Reading logs from `{LOG_DIR}/`")

hours = {"Last hour": 1, "Last 24 hours": 24, "Last 7 days": 168}.get(window)


def load(path):
    df = pd.DataFrame(load_jsonl(path))
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    if hours:
        df = df[df["ts"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)]
    if not include_eval and "user_id" in df:
        df = df[~df["user_id"].fillna("").astype(str).str.startswith("eval_")]
    return df


m, a = load(METRICS_PATH), load(AUDIT_PATH)

if m.empty:
    st.info("No requests in this window yet. Send a message through the API or the chat UI.")
else:
    s = summarize(m.to_dict("records"))
    k = st.columns(6)
    k[0].metric("Requests", s["requests"])
    k[1].metric("Error rate", f"{s['error_rate']:.1%}")
    k[2].metric("Latency p50", f"{s['latency_p50_s']} s")
    k[3].metric("Latency p90", f"{s['latency_p90_s']} s")
    k[4].metric("Cost / request", f"${s['cost_per_request_usd']:.5f}")
    k[5].metric("Total cost", f"${s['cost_total_usd']:.4f}")

    left, right = st.columns(2)
    with left:
        st.subheader("Latency per request (s)")
        st.line_chart(m.set_index("ts")["latency_s"])
        st.subheader("Cost per request ($)")
        st.bar_chart(m.set_index("ts")["cost_usd"])
    with right:
        st.subheader("Tool usage")
        if s["tool_usage"]:
            st.bar_chart(pd.Series(s["tool_usage"]))
        else:
            st.caption("No tools called in this window.")
        st.subheader("Request outcomes")
        st.bar_chart(pd.Series(s["status_counts"]))

st.subheader("Audit log")
if a.empty:
    st.caption("No audit events in this window.")
else:
    denied = int(a["decision"].isin(["denied_non_interactive", "human_denied"]).sum()) if "decision" in a else 0
    blocks = int((a["event"] == "guardrail_blocked").sum())
    tool_errors = int(((a["event"] == "tool_call") & (a["outcome"] == "error")).sum()) if "outcome" in a else 0
    c = st.columns(3)
    c[0].metric("Approvals denied", denied)
    c[1].metric("Guardrail blocks", blocks)
    c[2].metric("Tool errors", tool_errors)

    events = sorted(a["event"].unique())
    default = [e for e in events if e in ("approval_decision", "guardrail_blocked", "tool_call")] or events
    pick = st.multiselect("Event types", events, default=default)
    st.dataframe(a[a["event"].isin(pick)].sort_values("ts", ascending=False).head(200), hide_index=True)

st.subheader("Latest eval run")
report_path = os.path.join(LOG_DIR, "eval_report.json")
if os.path.exists(report_path):
    with open(report_path) as f:
        rep = json.load(f)
    st.caption(f"{rep['generated_at']} · {rep['model']} · {rep['passed']}/{rep['total']} passed")
    st.bar_chart(pd.Series({k: v["pass_rate"] for k, v in rep["by_type"].items()}))
    st.write(f"p50 {rep['latency_p50_s']} s · p90 {rep['latency_p90_s']} s · ${rep['cost_per_query_usd']} per query")
else:
    st.caption("No eval report yet. Run `python eval_suite.py`.")
