# AI ASSISTANT - Full Walkthrough

A day-by-day record of everything built for the Week 2 internship roadmap:
what was built, why, what broke, and what was learned from each failure.

**Stack:** Groq (`openai/gpt-oss-120b`, free tier) · LangGraph · LangSmith ·
FastAPI · Streamlit · Docker · GitHub Actions

---

## Setup

- Compared Grok (no free API), Gemini (free tier but rate-limited, Pro removed
  from free tier), and Groq (generous free tier, fast inference) — chose Groq.
- Python venv in VS Code, `.env` for secrets (never committed), `python-dotenv`
  to load them, `.gitignore` covering `.env`.

---

## Day 1 — Tool Calling & MCP

- **S1:** Built the core request→execute→return loop by hand: model requests
  a tool call, code runs the real Python function, result is sent back as a
  `role: "tool"` message. Logged every step.
- **S2:** Built 5 tools — `calculator`, `get_time`, `web_search` (mock),
  `read_file`, `send_email` (mock) — each with a clear name, a description
  written for the model (not just for a human reader), typed JSON-schema
  arguments, and **errors returned as observations** (a string like
  `"Error: file not found"`) instead of raising exceptions and crashing.
- **S3:** Chained 4 tools in one request, logging every Thought → Action →
  Observation. **Finding:** the model sometimes skipped the calculator for
  simple arithmetic, computing it mentally instead of calling the tool — a
  small preview of the trust/hallucination problem explored later.
- **S4:** Connected to the official MCP filesystem server (`npx
  @modelcontextprotocol/server-filesystem`) as a standardized way to expose
  tools, instead of writing bespoke integration code per tool source.

---

## Day 2 — Agents, Frameworks & Memory

- **S1:** Built a bare ReAct loop with **no SDK tool-calling** — taught the
  model a plain-text `Thought: / Action: tool[input]` format via the system
  prompt, then parsed it with regex. This is what tool-calling looked like
  before SDKs added structured support.
- **S2:** Rebuilt the same agent in **LangGraph** — nodes, a shared state
  object, and a conditional edge cycling `agent → tools → agent` until done.
  Rendered the graph as a Mermaid diagram.
- **S3:** Added **long-term memory** — a per-user JSON file on disk. Only
  short, *derived* preference facts are stored (e.g. "prefers concise
  answers"), never raw conversation text, and never sensitive data (an
  extraction prompt explicitly screens out passwords/financial info).
  Verified persistence by loading memory in a completely separate function
  call with zero shared conversation history — the actual proof it survives
  a restart, not just survives within one Python process.
- **S4:** Added three reliability guardrails: a max iteration cap, a
  per-tool timeout (noted as Unix-only via `signal.alarm`; Windows needs a
  `ThreadPoolExecutor`-based version instead), and a human-approval gate
  before any dangerous tool (`send_email`) can execute.

---

## Day 3 — Multi-Agent Systems & Observability

- **S1:** Built a Researcher + Writer system with a Supervisor node routing
  between them based on what's present in shared state.
- **S2:** Solved the *same* task two ways — a fixed 2-call pipeline vs. an
  agent with an LLM-based supervisor deciding routing — and measured calls,
  latency, and cost for both. **Finding (the intended one):** the fixed
  pipeline won, because the task's steps never actually needed a dynamic
  decision. The agent added a real extra LLM call for zero benefit. Lesson:
  agents earn their overhead only when the next step genuinely depends on
  what the previous step returned.
- **S3:** Context engineering — summarized older conversation turns into 2–3
  sentences via one extra LLM call, kept the most recent turn verbatim,
  measured real `prompt_tokens` before/after. Reduction target was 30%+.
- **S4:** Instrumented the Day 3 S1 graph with LangSmith tracing (env vars
  only, no code changes to the graph). **Deliberately planted a bug** — a
  typo, `state['resarch_notes']` instead of `state['research_notes']` — to
  produce a real failed run. Found the root cause purely by reading the
  trace's captured input state (which had the data all along), without
  adding a single print statement. Fixed the typo afterward.

---

## Day 4 — Guardrails, Security & Evaluation

- **S1:** Planted 5 different prompt-injection styles inside mock "retrieved
  documents" (direct override, fake system message, fake prior tool call,
  authority impersonation, base64-encoded payload) and tested an unguarded
  agent against them.
- **S2:** Built real guardrails: `<untrusted_context>` tagging so the model
  is explicitly told never to obey instructions found inside retrieved
  content, plus a regex-based output-side safety net. Verified **zero false
  positives** across 20 legitimate queries, including one deliberately tricky
  benign question containing the word "ignore."
- **S3:** Built a 30-case eval suite across correctness, tool selection,
  refusal handling, and robustness, graded by a second LLM acting as judge
  (not exact-string matching, since answers are free text).
- **S4:** Implemented model routing — try a small model first
  (`openai/gpt-oss-20b`), escalate to the larger model
  (`openai/gpt-oss-120b`) only on empty/uncertain answers or when a complex
  question got a suspiciously short one. Measured real cost savings vs.
  always using the large model, correctly counting the cost of *both* calls
  on escalated questions.

---

## Day 5 — Capstone

- **S1:** Wired tools + memory + guardrails + approval gate into one agent
  and ran a 6-case self-test against it. **Finding:** one case failed
  because the test asked an **LLM judge** to confirm a memory *file existed
  on disk* — something a text-only judge has no way to observe. Fixed by
  checking the filesystem directly in Python for that specific case instead
  of trusting the judge to guess. General lesson: side effects (files
  written, rows inserted, emails sent) need programmatic verification, not
  an LLM judge.
- **S2:** Built a Streamlit chat UI (shows which tools ran + cited sources
  per answer) and a FastAPI `/chat` endpoint with session handling. Verified
  session continuity by storing a preference in one call and confirming a
  later call with the same `session_id` produced a noticeably shorter
  answer. **Finding:** a guardrail disclaimer stating "this is mock data" is
  necessary but not sufficient — the model still generated detailed,
  plausible-sounding fabricated bullet points *before* the disclaimer,
  which could mislead a reader who doesn't read to the end.
- **Source citation follow-up:** originally only `web_search` got a
  citation-style note. Fixed by adding a structured `sources` list returned
  from every agent call — `read_file` cites the real file path, `calculator`
  cites the expression, `web_search` explicitly flags mock vs. live data —
  surfaced in both the Streamlit UI and the FastAPI response.
- **Real email attempt:** tried wiring `send_email` to Gmail SMTP. Required
  a Gmail **App Password** (a separate 16-character credential for scripts,
  since 2FA blocks a script from using the real password directly) —
  required enabling 2-Step Verification first. Wired `smtplib` in behind the
  existing approval gate. **Debugging note:** the first "why didn't I get
  the email" turned out to be that the model asked a clarifying question in
  plain text instead of calling the tool at all (`tool_calls: []` in the
  response), not an SMTP problem — a reminder to check whether the tool was
  actually invoked before debugging the tool's internals.
- **FastAPI approval gate gap:** discovered that a blocking `input()` call
  inside a FastAPI request handler pauses the *server process* and waits
  for terminal input, which is invisible from the browser/Swagger UI. Fixed
  properly during the production hardening pass (see below) by having the
  agent detect there's no interactive terminal attached and deny by default
  rather than hang forever.
- **S3 — Results & Documentation:** wrote a README with an architecture
  diagram, setup instructions, a results table (pass rate, cost, latency,
  token reduction), known failure modes, and honest limitations
  (in-memory session store, mock search data, Windows timeout gap).

---

## Production hardening pass (latest additions)

Everything below was added after the initial capstone, in response to a
request to make the system demo-and-report-ready with proper metrics,
safety defaults, and deployment:

- **Cost per query, latency p50/p90, pass rate by query type** — added a
  `metrics.py` module recording latency, tokens, and estimated cost per
  request to `logs/metrics.jsonl`, plus a percentile helper. The eval suite
  now reports pass rate broken down by all 6 query types (correctness,
  tool_selection, refusal, robustness, memory, guardrails), not just an
  overall number.
- **Audit logging** — every request, tool call, approval decision, memory
  write, and guardrail block is now written to `logs/audit.jsonl`. Sensitive
  values (email bodies) are never logged, only their length; long tool
  arguments are truncated.
- **Fixed the FastAPI approval-gate hang** — the approval function now
  checks whether a real terminal is attached (`sys.stdin.isatty()`). If not
  (Docker, CI, a `uvicorn` server with no one watching its console), the
  action is **denied by default** and logged, rather than hanging forever
  waiting for input nobody can provide. A request can still explicitly opt
  in via `auto_approve_dangerous: true`.
- **Eval suite expanded to 30 cases, 6 types**, including a case that
  reads a file containing a live-fire prompt-injection payload
  (`injected.txt`, containing "IGNORE ALL PREVIOUS INSTRUCTIONS...") to
  confirm the guardrail holds against the exact attack style from Day 4 S1,
  and a case sending fake card/password details to confirm they never reach
  the memory file. The runner writes `logs/eval_report.md` and `.json` and
  **exits with a non-zero code if the pass rate drops below 80%** — the
  actual CI gate.
- **`read_file` sandboxing** — when `READ_ROOT` is set (as it is in Docker
  and CI), file reads are confined to that one folder; a `../../etc/passwd`
  style path is rejected rather than potentially escaping the sandbox.
- **`send_email` dry-run switch** — `DRY_RUN_EMAIL=true` (the default in
  Docker/CI) makes the tool report success without ever calling `smtplib`,
  so evals and CI runs can never send a real email.
- **Untrusted-content wrapping in production, not just guardrail tests** —
  every `read_file` and `web_search` result is now wrapped in
  `<untrusted_context>` tags before being sent back to the model in the
  *actual* agent loop (previously this tagging only existed in the separate
  Day 4 S2 guardrail demo script).
- **Containerized deployment** — a `Dockerfile` (non-root user, health
  check hitting `/health`) and a `docker-compose.yml` running the API and a
  monitoring dashboard as two services sharing a log volume. Secrets are
  passed in via `.env` at runtime, never baked into the image
  (`.dockerignore` excludes it).
- **Monitoring dashboard** (`dashboard.py`, Streamlit) — reads the JSON
  Lines logs directly (no separate database) and shows request count, error
  rate, latency p50/p90, cost per request, tool-usage breakdown, an audit
  event table, and the most recent eval report — filterable by time window.
- **CI wired to the eval suite** — a GitHub Actions workflow
  (`.github/workflows/eval.yml`) runs the eval suite on every push and pull
  request (a smaller 12-case subset on PRs to stay fast, the full 30 on
  `main`), posts the report to the job summary, uploads it as an artifact,
  and fails the build if the pass rate drops below threshold. A second job
  confirms the Docker image still builds.
- **Testing before shipping:** rather than asking you to discover bugs live,
  every new piece (metrics math, the agent loop's new audit/cost tracking,
  the sandbox, the approval-gate default-deny behavior, the eval runner
  end-to-end) was exercised offline first against a scripted fake LLM client
  standing in for Groq, so the logic was verified without spending real API
  calls or waiting on rate limits.

---

## Recurring lessons across the whole project

1. **Mock data + a confident model = fabrication.** Seen twice: once with
   full invented sources/statistics, once again later as a subtler
   disclaimer-after-fabrication pattern. A guardrail instruction helps but
   doesn't fully close the gap.
2. **LLM judges can only grade what's in the text.** Anything that's a real
   side effect — a file, a database row, a sent email — needs a
   programmatic check, not a judge's guess.
3. **Silent blocking is worse than an explicit denial.** A blocking
   `input()` call inside a server process looks like a hang, not a security
   feature, until you know to look for it. Explicit default-deny-when-no-terminal
   is both safer and more debuggable.
4. **An agent isn't automatically better than a pipeline.** When the steps
   are fixed and known in advance, a plain pipeline is cheaper, faster, and
   just as correct — the honest result of Day 3 S2, not a failure of the
   agent.
5. **Real infrastructure (SMTP, Docker, CI) surfaces problems mock/local
   setups hide** — path escaping, non-interactive approval, and secrets
   management all became real concerns only once things left "just run it
   in my terminal."
