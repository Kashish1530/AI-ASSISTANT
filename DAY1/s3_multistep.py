import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq
from s2_tools import read_file


load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

# ---------- Tools (reusing S2's set + get_time) ----------

def get_time():
    return datetime.now().isoformat()

def web_search(query):
    return f"[MOCK DATA — not real search results] Placeholder results for '{query}': [result 1, result 2, result 3]"

def read_file(path):
    try:
        with open(path, "r") as f:
            return f.read()[:2000]
    except FileNotFoundError:
        return f"Error: file '{path}' not found. Check the path and try again."
    except Exception as e:
        return f"Error reading file: {e}"

def query_sqlite(query):
    try:
        conn = sqlite3.connect("test.db")
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        conn.close()
        return str(rows) if rows else "No rows returned."
    except Exception as e:
        return f"Error running query: {e}"

tools = [
    {"type": "function", "function": {
        "name": "get_time",
        "description": "Get the current date and time.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for current information. NOTE: in this dev environment this returns MOCK/placeholder data, not real results.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read the text contents of a local file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    }},
    {"type": "function", "function": {
        "name": "query_sqlite",
        "description": "Run a SQL query against the local 'test.db' SQLite database.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    }}
]

tool_functions = {
    "get_time": get_time,
    "web_search": web_search,
    "read_file": read_file,
    "query_sqlite": query_sqlite
}

# ---------- Multi-step agent loop with full T/A/O logging ----------

def run_agent(user_input, max_iterations=10):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to tools. "
                "If a tool returns placeholder, mock, or simulated data "
                "(look for '[MOCK DATA]'), say so explicitly instead of "
                "inventing realistic details on top of it."
            )
        },
        {"role": "user", "content": user_input}
    ]

    step_log = []

    for step in range(max_iterations):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        msg = resp.choices[0].message
        thought = msg.reasoning if hasattr(msg, "reasoning") else None

        print(f"\n{'='*50}")
        print(f"STEP {step + 1}")
        print(f"{'='*50}")
        print(f"THOUGHT: {thought}")

        if not msg.tool_calls:
            print(f"\nFINAL ANSWER:\n{msg.content}")
            step_log.append({"step": step + 1, "thought": thought, "action": None, "observation": None, "final": msg.content})
            print(f"\nTotal conversation messages: {len(messages)}")
            return msg.content, step_log

        messages.append(msg)

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)

            print(f"ACTION: {name}({args})")

            try:
                result = tool_functions[name](**args)
            except Exception as e:
                result = f"Tool error: {e}"

            print(f"OBSERVATION: {result}")

            step_log.append({"step": step + 1, "thought": thought, "action": f"{name}({args})", "observation": result, "final": None})

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result)
            })

    print("Max iterations reached without a final answer.")
    return None, step_log


if __name__ == "__main__":
    question = (
        "First, get the current time. Then search the web for 'agentic AI trends'. "
        "Then read the file 'notes.txt' and tell me if it exists. "
        "Then query the database with 'SELECT * FROM nonexistent_table' and report "
        "what happens. Summarize all four results at the end."
    )

    final_answer, log = run_agent(question)

    print(f"\n\n{'='*50}")
    print("FULL STEP LOG (for submission)")
    print(f"{'='*50}")
    for entry in log:
        print(json.dumps(entry, indent=2, default=str))
        