# AI-ASSISTANT 

A single agent combining tool use, persistent memory, prompt-injection guardrails,
and self-evaluation, served via both a Streamlit chat UI and a FastAPI endpoint.
Built on Groq (`openai/gpt-oss-120b`).

---

## Architecture

```
                         ┌─────────────────────┐
                         │   User (chat msg)    │
                         └──────────┬───────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                      │
        ┌────────▼────────┐                    ┌─────────▼─────────┐
        │  Streamlit UI    │                   │   FastAPI /chat    │
        │ (day5_s2_        │                   │  (day5_s2_         │
        │  streamlit_app)  │                   │   fastapi_server)  │
        └────────┬─────────┘                   └─────────┬──────────┘
                  │                                       │
                  └───────────────────┬───────────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │   run_capstone_agent()     │
                          │   (day5_s1_capstone.py)    │
                          └────────────┬───────────────┘
                                       │
        ┌──────────────┬──────────────┼──────────────┬───────────────┐
        │              │              │               │               │
  ┌─────▼─────┐   ┌─────▼──────┐  ┌────▼─────┐   ┌──────▼──────┐   ┌──────▼──────┐
  │  Memory    │  │ Guardrails  │ │  Tools   │  │  Approval    │ │   Groq LLM   │
  │ (per-user  │  │ (input/     │ │ calc,    │  │  gate        │ │ openai/gpt-  │
  │  JSON on   │  │  output     │ │ time,    │  │ (send_email  │ │ oss-120b     │
  │  disk)     │  │  filtering) │ │ search*, │  │  requires    │ │              │
  │            │  │             │ │ read_file│  │  human OK)   │ │              │
  └────────────┘  └─────────────┘ └──────────┘  └──────────────┘ └──────────────┘

* web_search currently returns MOCK data — no live search API connected.
  Guardrails explicitly instruct the model to flag this rather than
  fabricate details on top of it.
```

**Flow for one request:**
1. Message arrives via Streamlit or FastAPI → both call the same `run_capstone_agent()`
2. Any durable preference in the message is extracted and saved to `memory_store/<user_id>.json`
3. System prompt is built dynamically, including remembered preferences + guardrail rules
4. Agent loop calls the LLM with tools available; loops on tool calls until a final answer
5. Dangerous tools (`send_email`) pause for human approval before executing
6. Final output passes an output-side guardrail check (regex) before being returned

---

## Setup

```powershell
# 1. Clone/copy this project, then create a virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install groq python-dotenv langgraph langchain-groq fastapi uvicorn streamlit mcp

# 3. Create a .env file in the project root:
#    GROQ_API_KEY=your_groq_key_here
#    LANGCHAIN_API_KEY=your_langsmith_key_here      (optional, for tracing)
#    LANGCHAIN_TRACING_V2=true                       (optional)
#    LANGCHAIN_PROJECT=agentic-ai-week2               (optional)

# 4. Run the capstone self-test
python day5_s1_capstone.py

# 5. Run the chat UI
streamlit run day5_s2_streamlit_app.py

# 6. Run the API server (separate terminal)
uvicorn day5_s2_fastapi_server:app --reload --port 8000
# Interactive docs at http://127.0.0.1:8000/docs
```

---

## Results

### Capstone self-test (6 cases spanning correctness, tool selection, refusal,
robustness, memory, guardrails)

| Metric | Result |
|---|---|
| Pass rate | 5/6 → 6/6 after fixing the memory test (see Known Failure Modes) |
| Model | `openai/gpt-oss-120b` (Groq) |

### Full 30-case eval suite 
Run `python eval_suite.py` and record here:
- Overall pass rate: `25/30 (83%)`
- By category: correctness `6/6`, tool_selection `6/7`, refusal `3/5`, robustness `5/5`

### Model routing comparison (Day 4 S4)
Run `python day4_s4_model_routing.py` and record here:
- Cost with routing: `$0.00172305`
- Cost large-model-only: `$0.00676890`
- Savings: `74.5%`

### Context engineering (Day 3 S3)
- Full history prompt tokens: `598`
- Summarized history prompt tokens: `285`
- Reduction: `52.3%`


## Known Failure Modes

1. **LLM judges can't verify filesystem side effects.** The memory test case
   initially failed because the eval asked an LLM judge to confirm a memory
   file existed on disk — something it has no way to observe from
   conversation text alone. Fixed by checking the file directly in Python
   instead of relying on the judge for that specific case. General lesson:
   any criteria involving a side effect (file written, DB row inserted,
   email sent) needs a programmatic check, not an LLM judge.

2. **Guardrail disclaimers don't fully prevent fabrication.** Even with a
   system prompt instructing the model to flag mock/placeholder data, the
   model still generated detailed, specific-sounding bullet points (e.g.
   fabricated claims about "Glacial Lake Outburst Floods" and government
   policy) before adding an accurate disclaimer at the end. A visible
   disclaimer is necessary but not sufficient — content generated *before*
   the disclaimer can still look convincingly real to a reader who doesn't
   read to the end.

3. **`web_search` currently returns mock data**, not real results — no live
   search API is connected. This was a deliberate scope decision to avoid
   adding an external dependency (e.g. Tavily) mid-build; the tool and
   guardrails are structured so a real search API could be swapped in with
   a single function change (see `web_search()` in `day5_s1_capstone.py`).

4. **FastAPI session store is in-memory (`SESSIONS = {}`).** Sessions are
   lost on server restart and won't work across multiple server instances.
   Fine for this demo; a production version would need Redis or a database.

5. **Tool timeout enforcement is Unix-only** (`signal.alarm`). On Windows,
   the timeout guardrail from Day 2 S4 silently doesn't enforce a hard
   limit — tools can still hang indefinitely. A cross-platform fix would
   use `concurrent.futures.ThreadPoolExecutor` instead (noted in code
   comments in `day2_s4_reliability.py`).

---

## Honest Limitations

- Eval suite (30 cases) is a reasonable smoke test but not exhaustive —
  a production agent would need a much larger, continuously-updated suite.
- Cost/latency numbers are specific to Groq's `openai/gpt-oss-120b` free
  tier at the time of testing (Sept 2026) — pricing and rate limits on
  Groq's platform have changed multiple times during this project and may
  change again.

---

## Operations

**Run everything in Docker** (API on :8000, monitoring dashboard on :8501):
```powershell
docker compose up --build
```
- Secrets come from `.env` at runtime (never baked into the image).
- `DRY_RUN_EMAIL` defaults to `true` in Docker. Set `DRY_RUN_EMAIL=false` in `.env` to send real email.
- `read_file` is confined to `./data` (`READ_ROOT`) in the container.
- No terminal is attached in Docker, so dangerous tools are **denied by default**; a request must
  explicitly set `auto_approve_dangerous: true` to allow them.

**Audit log** (`logs/audit.jsonl`, append-only JSON Lines): one event per request received, tool call
(executed / error / blocked), approval decision (auto_approved / human_approved / human_denied /
denied_non_interactive), memory write, guardrail block, and request completion. Email bodies are never
logged (only their length); long arguments are truncated.

**Metrics** (`logs/metrics.jsonl`): per request latency, tokens, LLM calls, estimated cost, tools, status.
Dashboard: `streamlit run dashboard.py` (or http://localhost:8501 in Docker). API summary: `GET /metrics`.

**Eval + CI:** `python eval_suite.py` runs 30 cases across 6 query types (correctness, tool_selection,
refusal, robustness, memory, guardrails) against the real agent and writes `logs/eval_report.md/.json`
with pass rate by type, cost per query, and p50/p90 latency. It exits non-zero below `EVAL_MIN_PASS_RATE`
(default 80%). `.github/workflows/eval.yml` runs it on every push/PR (add a `GROQ_API_KEY` repo secret)
and checks that the Docker image builds. Set `PRICE_INPUT_PER_M` / `PRICE_OUTPUT_PER_M` to your model's
real rates, otherwise cost figures use placeholders.

---

## File Guide

| File | Purpose |
|---|---|
| `day5_s1_capstone.py` | Core agent: tools, memory, guardrails, self-test |
| `day5_s2_streamlit_app.py` | Chat UI |
| `day5_s2_fastapi_server.py` | REST API with session handling |
| `day4_s3_eval_suite.py` | 30-case evaluation suite |
| `day4_s4_model_routing.py` | Small-model-first cost routing experiment |
| `day3_s3_context_engineering.py` | Token reduction via summarization |
| `day3_s4_observability.py` | LangSmith tracing example |
| `metrics.py` | Audit log, per-request metrics, cost and percentile helpers |
| `eval_cases.py` / `eval_suite.py` | 30-case eval, report by query type, CI gate |
| `dashboard.py` | Monitoring dashboard (Streamlit) |
| `Dockerfile` / `docker-compose.yml` | Containerized API + dashboard |
| `.github/workflows/eval.yml` | CI: eval on push/PR + Docker build check |
| `data/` | Fixtures for evals (`notes.txt`, `injected.txt`) and the `read_file` sandbox |
