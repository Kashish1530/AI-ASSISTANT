import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated
import operator

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

load_dotenv()

MODEL = "openai/gpt-oss-120b"

# ---------- Tools (LangChain-native this time, using @tool decorator) ----------

@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression, e.g. '12*7'."""
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {e}"

@tool
def word_count(text: str) -> str:
    """Count the number of words in a piece of text."""
    return str(len(text.split()))

tools = [calculator, word_count]
tool_node = ToolNode(tools)

llm = ChatGroq(model=MODEL, api_key=os.environ["GROQ_API_KEY"])
llm_with_tools = llm.bind_tools(tools)

# ---------- State ----------
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]

# ---------- Nodes ----------

def call_model(state: AgentState):
    """The 'Thought' node - the model decides what to do next."""
    response = llm_with_tools.invoke(state["messages"])
    print(f"\n--- MODEL STEP ---")
    print(f"Content: {response.content}")
    print(f"Tool calls: {response.tool_calls}")
    return {"messages": [response]}

def should_continue(state: AgentState):
    """Conditional edge: does the last message request a tool, or are we done?"""
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

# ---------- Build the graph ----------
graph = StateGraph(AgentState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)

graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")  # after tool runs, go back to the model (the cycle)

app = graph.compile()

# ---------- Render the graph diagram ----------
def save_graph_diagram():
    try:
        png_bytes = app.get_graph().draw_mermaid_png()
        with open("day2_s2_graph.png", "wb") as f:
            f.write(png_bytes)
        print("Graph diagram saved to day2_s2_graph.png")
    except Exception as e:
        # Mermaid rendering needs internet access to a rendering service;
        # if it fails, print the mermaid source instead so you can render it
        # manually at https://mermaid.live
        print(f"Could not render PNG ({e}). Mermaid source below - paste into https://mermaid.live :\n")
        print(app.get_graph().draw_mermaid())


if __name__ == "__main__":
    save_graph_diagram()

    question = (
        "What is 45 times 12, and how many words are in the sentence "
        "'the quick brown fox jumps over the lazy dog'? "
        "Give me both answers combined into one final sentence."
    )

    result = app.invoke({
        "messages": [
            SystemMessage(content="You are a helpful assistant with access to tools. Use them when needed."),
            HumanMessage(content=question)
        ]
    })

    print("\n=== FINAL ANSWER ===")
    print(result["messages"][-1].content)

