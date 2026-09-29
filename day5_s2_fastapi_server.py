import os
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from day5_s1_capstone import run_capstone_agent
from metrics import METRICS_PATH, load_jsonl, summarize

load_dotenv()

app = FastAPI(title="Agentic AI Capstone API", version="1.0")


SESSIONS = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None 
    auto_approve_dangerous: bool = False  


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_calls: list[str]
    sources: list[dict]


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Create or reuse a session
    if req.session_id and req.session_id in SESSIONS:
        session_id = req.session_id
        user_id = SESSIONS[session_id]
    else:
        session_id = str(uuid.uuid4())
        user_id = f"api_user_{session_id[:8]}"
        SESSIONS[session_id] = user_id

    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    answer, tool_calls, sources = run_capstone_agent(
        user_id, req.message, auto_approve_dangerous=req.auto_approve_dangerous
    )

    if answer is None:
        raise HTTPException(status_code=500, detail="Agent did not produce a final answer (max iterations reached)")

    return ChatResponse(session_id=session_id, answer=answer, tool_calls=tool_calls, sources=sources)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    """Aggregate stats only (counts, latency p50/p90, cost). Excludes eval traffic.
    Unauthenticated - put it behind auth or a private network before exposing it."""
    records = [r for r in load_jsonl(METRICS_PATH) if not str(r.get("user_id", "")).startswith("eval_")]
    return summarize(records)


@app.get("/")
def root():
    return {
        "message": "Agentic AI Capstone API",
        "endpoints": {
            "POST /chat": "send a message, get {session_id, answer, tool_calls}",
            "GET /health": "health check",
        }
    }


