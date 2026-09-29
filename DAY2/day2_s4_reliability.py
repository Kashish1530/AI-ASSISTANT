import os
import json
import signal
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

# ---------- Tools ----------

def calculator(expression):
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {e}"

def send_email(to, subject, body):
    print(f"[MOCK EMAIL SENT] To: {to} | Subject: {subject} | Body: {body}")
    return f"Email sent to {to}."

# Tools that require explicit human approval before running
DANGEROUS_TOOLS = {"send_email"}

tool_functions = {
    "calculator": calculator,
    "send_email": send_email,
}

tools = [
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Evaluate a math expression.",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"]
        }
    }},
    {"type": "function", "function": {
        "name": "send_email",
        "description": "Send an email. DANGEROUS - irreversible action.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"}
            },
            "required": ["to", "subject", "body"]
        }
    }}
]

# ---------- Timeout mechanism ----------
# Uses SIGALRM (Unix-style). Windows doesn't support SIGALRM natively -
# see the Windows-safe fallback note below the class.

class ToolTimeoutError(Exception):
    pass

def _timeout_handler(signum, frame):
    raise ToolTimeoutError("Tool call exceeded timeout")

def run_tool_with_timeout(func, kwargs, timeout_seconds=5):
    """
    Cross-platform-safe timeout: tries SIGALRM (Mac/Linux), falls back to a
    plain call with no enforced timeout on Windows (signal.alarm doesn't
    exist there). On Windows, swap this for the `concurrent.futures`
    ThreadPoolExecutor pattern shown in the comment below if you need a
    real enforced timeout.
    """
    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_seconds)
        try:
            return func(**kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows fallback - no enforced timeout via signal.
        # For a real Windows-safe timeout, use:
        #
        # from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
        # with ThreadPoolExecutor(max_workers=1) as ex:
        #     future = ex.submit(func, **kwargs)
        #     try:
        #         return future.result(timeout=timeout_seconds)
        #     except FutureTimeout:
        #         raise ToolTimeoutError("Tool call exceeded timeout")
        return func(**kwargs)


# ---------- Human approval gate ----------

def request_human_approval(tool_name, args):
    print(f"\n⚠️  APPROVAL REQUIRED ⚠️")
    print(f"The agent wants to call a DANGEROUS tool: {tool_name}")
    print(f"Arguments: {json.dumps(args, indent=2)}")
    answer = input("Approve this action? (yes/no): ").strip().lower()
    return answer in ("yes", "y")


# ---------- Agent loop with all three guardrails ----------

def run_agent(user_input, max_iterations=5, tool_timeout_seconds=5):
    messages = [{"role": "user", "content": user_input}]

    for step in range(1, max_iterations + 1):
        print(f"\n--- STEP {step}/{max_iterations} ---")

        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            print(f"FINAL ANSWER: {msg.content}")
            return msg.content

        messages.append(msg)

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)

            # --- GUARDRAIL: human approval for dangerous tools ---
            if name in DANGEROUS_TOOLS:
                approved = request_human_approval(name, args)
                if not approved:
                    result = f"Action blocked by user: {name} was not approved."
                    print(f"BLOCKED: {result}")
                    messages.append({
                        "role": "tool", "tool_call_id": call.id, "content": result
                    })
                    continue

            # --- GUARDRAIL: per-call timeout ---
            print(f"ACTION: {name}({args}) [timeout={tool_timeout_seconds}s]")
            try:
                result = run_tool_with_timeout(
                    tool_functions[name], args, timeout_seconds=tool_timeout_seconds
                )
            except ToolTimeoutError:
                result = f"Error: {name} timed out after {tool_timeout_seconds}s"
            except Exception as e:
                result = f"Error: {e}"

            print(f"OBSERVATION: {result}")
            messages.append({
                "role": "tool", "tool_call_id": call.id, "content": str(result)
            })

    # --- GUARDRAIL: max iteration cap hit ---
    print(f"\n🛑 Max iterations ({max_iterations}) reached - stopping to avoid a runaway loop.")
    return None


if __name__ == "__main__":
    print("=== TEST 1: safe tool, no approval needed ===")
    run_agent("What is 128 * 7?")

    print("\n\n=== TEST 2: dangerous tool, approval gate triggers ===")
    run_agent("Send an email to boss@example.com with subject 'Update' and body 'Project is on track.'")