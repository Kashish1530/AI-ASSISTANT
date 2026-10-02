import os
import json
import sqlite3

from dotenv import load_dotenv
from groq import Groq
from pathlib import Path
import fitz  # PyMuPDF
from pypdf import PdfReader
from docx import Document
from striprtf.striprtf import rtf_to_text


load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

# ---------- 1. web_search ----------
def web_search(query):
    return f"[MOCK DATA —  real search results] Placeholder results for '{query}': [result 1, result 2, result 3]"

# ---------- 2. read_file ----------


def read_file(path):
    try:
        if not os.path.exists(path):
            return f"Error: file '{path}' does not exist."

        ext = os.path.splitext(path)[1].lower()

        # ---------------- PDF ----------------
        if ext == ".pdf":
            reader = PdfReader(path)

            pages = []

            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                    pages.append(f"\n--- PAGE {i + 1} ---\n{text}")
                except Exception as e:
                    pages.append(
                        f"\n--- PAGE {i + 1} ---\n"
                        f"[Could not extract this page: {e}]"
                    )

            return "\n".join(pages)[:20000]

        # ---------------- DOCX ----------------
        elif ext == ".docx":
            doc = Document(path)

            paragraphs = []

            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    paragraphs.append(paragraph.text)

            # Also extract table contents
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    paragraphs.append(row_text)

            return "\n".join(paragraphs)[:20000]

        # ---------------- RTF ----------------
        elif ext == ".rtf":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                rtf_content = f.read()

            return rtf_to_text(rtf_content)[:20000]

        # ---------------- TXT / MD / CSV etc. ----------------
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:20000]

    except Exception as e:
        return f"Error reading '{path}': {type(e).__name__}: {e}"


# ---------- 3. query_sqlite ----------
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

# ---------- 4. call_external_api ----------
import urllib.request
def call_external_api(endpoint, params=None):
    try:
        url = endpoint
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query_string}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.read().decode()[:1000]
    except Exception as e:
        return f"Error calling API: {e}"

# ---------- 5. send_email (mock — never actually sends) ----------
def send_email(to, subject, body):
    print(f"[MOCK EMAIL] To: {to} | Subject: {subject} | Body: {body}")
    return f"Email queued to {to} (mock — not actually sent)."

# ---------- Tool schemas ----------
tools = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for current information. Use when the user asks about something you can't answer from memory alone, like recent events or live data. NOTE: in this dev environment this tool returns MOCK/placeholder data, not real results.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query"}},
            "required": ["query"]
        }
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a local document from a file path and extract its text. "
                       "Supports PDF, DOCX, RTF, TXT, Markdown, CSV, and LOG files. "
                        "Use this tool whenever the user asks you to read, summarize, "
                        "analyze, or inspect a specific local document.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file"}},
            "required": ["path"]
        }
    }},
    {"type": "function", "function": {
        "name": "query_sqlite",
        "description": "Run a SQL query against the local 'test.db' SQLite database and return matching rows.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A valid SQL query"}},
            "required": ["query"]
        }
    }},
    {"type": "function", "function": {
        "name": "call_external_api",
        "description": "Call an external HTTP API endpoint and return its raw response. Use for real-time data like weather.",
        "parameters": {
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "Full URL to call"},
                "params": {"type": "object", "description": "Optional query parameters as key-value pairs"}
            },
            "required": ["endpoint"]
        }
    }},
    {"type": "function", "function": {
        "name": "send_email",
        "description": "Send an email. This is a DANGEROUS/irreversible action — only call this when the user has explicitly and clearly asked to send an email.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text"}
            },
            "required": ["to", "subject", "body"]
        }
    }}
]

tool_functions = {
    "web_search": web_search,
    "read_file": read_file,
    "query_sqlite": query_sqlite,
    "call_external_api": call_external_api,
    "send_email": send_email
}

# ---------- Standalone individual tool tests ----------
def run_individual_tool_tests():
    print("=== INDIVIDUAL TOOL TESTS ===")
    print(web_search("test query"))
    print(read_file("nonexistent.txt"))
    print(query_sqlite("SELECT * FROM nonexistent_table"))  # triggers the error path
    print(call_external_api("https://api.github.com"))
    print(send_email("test@example.com", "Hi", "Hello world"))
    print()

# ---------- Multi-step agent loop ----------
def run_agent(user_input, max_iterations=10):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant with access to tools. "
                "If a tool returns placeholder, mock, or simulated data "
                "(look for markers like '[MOCK DATA]'), you must say so "
                "explicitly in your final answer instead of inventing "
                "realistic-sounding details, sources, or statistics on top of it."
            )
        },
        {"role": "user", "content": user_input}
    ]

    for step in range(max_iterations):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        msg = resp.choices[0].message
        print(f"\n--- STEP {step + 1} ---")
        print("MODEL RESPONSE:", msg)

        if not msg.tool_calls:
            print("\nFINAL ANSWER:")
            print(msg.content)
            return msg.content

        messages.append(msg)

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)

            print(f"\nEXECUTING: {name}")
            print(f"ARGS: {args}")

            try:
                result = tool_functions[name](**args)
            except Exception as e:
                result = f"Tool error: {e}"

            print(f"RESULT: {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result)
            })

    print("Max iterations reached without a final answer.")
    return None


if __name__ == "__main__":
    path = r"C:\Users\kashish\Downloads\ganesh chaturthi.pdf"

    text = read_file(path)

    print("=" * 60)
    print("EXTRACTED TEXT")
    print("=" * 60)
    print(text)
