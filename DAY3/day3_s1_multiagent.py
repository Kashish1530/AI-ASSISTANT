import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Literal
import operator

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

load_dotenv()
MODEL = "openai/gpt-oss-120b"
llm = ChatGroq(model=MODEL, api_key=os.environ["GROQ_API_KEY"])

# ---------- Shared state ----------
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


# ---------- Worker: Researcher ----------
def researcher_node(state: AgentState):
    print("\n--- RESEARCHER AGENT running ---")
    query = state["task"]
    raw_results = mock_web_search(query)

    prompt = (
        f"You are a research agent. Summarize these raw findings into 3-4 "
        f"clear bullet points for the topic '{query}'. If the findings say "
        f"they are mock/placeholder data, say so explicitly in your notes "
        f"instead of inventing real facts.\n\nRaw findings:\n{raw_results}"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    print(f"RESEARCH NOTES:\n{resp.content}")
    return {"research_notes": resp.content, "next_agent": "supervisor"}


# ---------- Worker: Writer ----------
def writer_node(state: AgentState):
    print("\n--- WRITER AGENT running ---")
    prompt = (
        f"You are a writing agent. Using these research notes, write a short, "
        f"polished 3-sentence summary answering the original task.\n\n"
        f"Original task: {state['task']}\n\n"
        f"Research notes:\n{state['research_notes']}"
    )
    resp = llm.invoke([HumanMessage(content=prompt)])
    print(f"FINAL WRITTEN OUTPUT:\n{resp.content}")
    return {"final_output": resp.content, "next_agent": "supervisor"}


# ---------- Supervisor ----------
def supervisor_node(state: AgentState):
    print("\n--- SUPERVISOR routing ---")

    if not state.get("research_notes"):
        decision = "researcher"
    elif not state.get("final_output"):
        decision = "writer"
    else:
        decision = "done"

    print(f"SUPERVISOR DECISION: route to '{decision}'")
    return {"next_agent": decision}


def route_from_supervisor(state: AgentState) -> Literal["researcher", "writer", "__end__"]:
    decision = state["next_agent"]
    if decision == "researcher":
        return "researcher"
    elif decision == "writer":
        return "writer"
    return END


# ---------- Build the graph ----------
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

    result = app.invoke({
        "task": task,
        "research_notes": "",
        "final_output": "",
        "next_agent": ""
    })

    print("\n=== FINAL RESULT ===")
    print(result["final_output"])

    print("\n=== COST/LATENCY NOTE ===")
    print(
        "This task took 3 LLM calls total (supervisor decisions are free/"
        "logic-only here, but researcher + writer are real calls, plus the "
        "supervisor could itself be an LLM call in a fancier version). "
        "Compare this to a single well-tooled agent doing research+writing "
        "in one call - that's the 'honest cost' tradeoff S2 asks you to measure."
    )

