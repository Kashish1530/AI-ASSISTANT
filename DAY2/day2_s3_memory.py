import os
import json
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

MEMORY_DIR = "memory_store"
os.makedirs(MEMORY_DIR, exist_ok=True)


def memory_path(user_id: str) -> str:
    return os.path.join(MEMORY_DIR, f"{user_id}.json")


def load_memory(user_id: str) -> dict:
    path = memory_path(user_id)
    if not os.path.exists(path):
        return {"preferences": [], "facts": []}
    with open(path, "r") as f:
        return json.load(f)


def save_memory(user_id: str, memory: dict):
    with open(memory_path(user_id), "w") as f:
        json.dump(memory, f, indent=2)


def extract_and_store_memory(user_id: str, user_message: str, memory: dict):
    """
    Ask the model whether this message contains a durable preference or fact
    worth remembering long-term. Deliberately narrow: we store short, factual
    statements only - never raw conversation text, never sensitive PII like
    passwords, card numbers, addresses, etc.
    """
    extraction_prompt = f"""Does this message contain a lasting user preference or fact worth
remembering for future sessions (e.g. "I prefer short answers", "I'm a Python developer")?

Message: "{user_message}"

If yes, reply with ONLY a short factual statement to remember (under 15 words).
If no, reply with exactly: NONE
Never extract passwords, financial details, or other sensitive personal data - reply NONE for those."""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": extraction_prompt}]
    )
    extracted = resp.choices[0].message.content.strip()

    if extracted and extracted != "NONE":
        memory["preferences"].append({
            "text": extracted,
            "stored_at": datetime.now().isoformat()
        })
        save_memory(user_id, memory)
        print(f"[MEMORY STORED]: {extracted}")


def build_system_prompt(memory: dict) -> str:
    if not memory["preferences"]:
        return "You are a helpful assistant."

    prefs_text = "\n".join(f"- {p['text']}" for p in memory["preferences"])
    return (
        "You are a helpful assistant. Here is what you remember about this "
        f"user from previous sessions:\n{prefs_text}\n"
        "Use this context naturally, don't explicitly list it back unless asked."
    )


def chat_turn(user_id: str, user_message: str):
    memory = load_memory(user_id)

    extract_and_store_memory(user_id, user_message, memory)

    memory = load_memory(user_id)
    system_prompt = build_system_prompt(memory)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )
    reply = resp.choices[0].message.content
    print(f"\nUSER: {user_message}")
    print(f"ASSISTANT: {reply}")
    return reply


if __name__ == "__main__":
    USER_ID = "kashish"

    print("=== SESSION 1 ===")
    chat_turn(USER_ID, "Hi, I prefer short, concise answers - no long explanations.")
    chat_turn(USER_ID, "What's the capital of France?")

    print("\n\n=== SIMULATING RESTART (new process, memory loaded fresh from disk) ===")
    print(f"Memory file on disk: {memory_path(USER_ID)}")
    print(json.dumps(load_memory(USER_ID), indent=2))

    print("\n=== SESSION 2 (after 'restart') ===")
    chat_turn(USER_ID, "What's the capital of Japan?")
