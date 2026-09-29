# observibility file
import os
from dotenv import load_dotenv
from typing import TypedDict, Literal

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

load_dotenv()


if not os.environ.get("LANGCHAIN_TRACING_V2"):
    print("WARNING: LANGCHAIN_TRACING_V2 not set - this run will NOT be traced. "
          "Add the LangSmith env vars to your .env file (see comments above).")

MODEL = "openai/gpt-oss-120b"
llm = ChatGroq(model=MODEL, api_key=os.environ["GROQ_API_KEY"])


class AgentState(TypedDict):
    task: str
    research_notes: str
    final_output: str
    next_agent: str


def mock_web_search(query: str) -> str:
    return (
        f"[MOCK DATA - placeholder, not real search results] "
        f"Simulated findings on '{query}': point A, point B, point C."
    )


def researcher_node(state: AgentState):
    query = state["task"]
    raw_results = mock_web_search(query)
    prompt = f"Summarize into 3-4 bullet points for '{query}'.\n\nRaw findings:\n{raw_results}"
    resp = llm.invoke([HumanMessage(content=prompt)])
    return {"research_notes": resp.content, "next_agent": "supervisor"}


def writer_node(state: AgentState):
    # --- INTENTIONAL BUG for the debugging exercise ---
    # This references a key that doesn't exist in state ("resarch_notes",
    # misspelled) instead of "research_notes". This will raise a KeyError,
    # producing a real failed run for you to trace and debug.
    prompt = (
        f"Write a 3-sentence summary for task '{state['task']}' using "
        f"these notes:\n{state['research_notes']}"  # <-- BUG: typo, will KeyError
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    return {"final_output": resp.content, "next_agent": "supervisor"}


def supervisor_node(state: AgentState):
    if not state.get("research_notes"):
        decision = "researcher"
    elif not state.get("final_output"):
        decision = "writer"
    else:
        decision = "done"
    return {"next_agent": decision}


def route_from_supervisor(state: AgentState) -> Literal["researcher", "writer", "__end__"]:
    decision = state["next_agent"]
    if decision == "researcher":
        return "researcher"
    elif decision == "writer":
        return "writer"
    return END


graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor_node)
graph.add_node("researcher", researcher_node)
graph.add_node("writer", writer_node)
graph.set_entry_point("supervisor")
graph.add_conditional_edges(
    "supervisor", route_from_supervisor,
    {"researcher": "researcher", "writer": "writer", END: END}
)
graph.add_edge("researcher", "supervisor")
graph.add_edge("writer", "supervisor")

app = graph.compile()


if __name__ == "__main__":
    task = "the current state of agentic AI adoption in enterprises"

    print("Running agent (this run is INTENTIONALLY going to fail in the writer step)...")
    print("If tracing is enabled, check smith.langchain.com after this crashes -")
    print("you should see the full trace: supervisor -> researcher (succeeded) -> ")
    print("supervisor -> writer (FAILED with KeyError), with inputs/outputs for each span.\n")

    try:
        result = app.invoke({
            "task": task,
            "research_notes": "",
            "final_output": "",
            "next_agent": ""
        })
        print("Unexpected: run succeeded. Final output:", result["final_output"])
    except KeyError as e:
        print(f"\n  EXPECTED FAILURE CAUGHT: KeyError: {e}")
        print("This is your 'one real failed run' - now go to LangSmith and:")
        print("  1. Find this run in your project (agentic-ai-week2-day3)")
        print("  2. Open the trace tree - find the 'writer' span, marked as failed/red")
        print("  3. Inspect its INPUT (the state dict passed in) - notice 'research_notes'")
        print("     exists in state, but the code looked up 'resarch_notes' (typo)")
        print("  4. That's the root cause, visible directly from the trace without")
        print("     needing to reproduce the bug by re-running or adding print statements")