import os
import re
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

# ---------- The "tools" the agent can use ----------
def calculator(expression):
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {e}"

def word_count(text):
    return str(len(text.split()))

AVAILABLE_TOOLS = {
    "calculator": calculator,
    "word_count": word_count,
}

# ---------- The ReAct system prompt ----------
# We are NOT using tools=[...] here. Instead we teach the model, via plain
# text instructions, to output a strict format we can parse ourselves.
SYSTEM_PROMPT = """You are a ReAct agent.

You MUST follow this exact format.

For every tool call, output EXACTLY:

Thought: <what you need to do>
Action: <tool_name>[<input>]

Then STOP.

The Python program will execute the Action and return an Observation.

Available tools:

- calculator[expression]
  Use this tool for ALL arithmetic calculations.
  Example: calculator[45*12]

- word_count[text]
  Use this tool for ALL word counting.
  Example: word_count[hello world]

IMPORTANT RULES:
1. NEVER perform arithmetic yourself. Always use calculator.
2. NEVER count words yourself. Always use word_count.
3. NEVER write an Observation yourself.
4. NEVER output more than ONE Action per turn.
5. After an Action, STOP immediately.
6. Wait for the Observation before continuing.
7. After all required tools have been used, output:

Thought: <final reasoning>
Final Answer: <final answer>

Your final answer must answer the user's question.

Do not skip the Action.
Do not combine Thought and Action on the same line.
"""


ACTION_PATTERN = re.compile(r"Action:\s*(\w+)\[(.*)\]", re.DOTALL)
FINAL_PATTERN = re.compile(r"Final Answer:\s*(.*)", re.DOTALL)


def run_react_loop(question, max_steps=8):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages)
        text = resp.choices[0].message.content
        print(f"\n--- STEP {step} (raw model output) ---")
        print(text)

        # Append exactly what the model said, so it sees its own prior steps
        messages.append({"role": "assistant", "content": text})

        # Check for a final answer first
        final_match = FINAL_PATTERN.search(text)
        if final_match:
            answer = final_match.group(1).strip()
            print(f"\n=== FINAL ANSWER ===\n{answer}")
            return answer

        # Otherwise, look for an Action to execute
        action_match = ACTION_PATTERN.search(text)
        if not action_match:
            print("No Action or Final Answer found - stopping (model didn't follow format).")
            return None

        tool_name = action_match.group(1).strip()
        tool_input = action_match.group(2).strip()

        if tool_name not in AVAILABLE_TOOLS:
            observation = f"Error: unknown tool '{tool_name}'"
        else:
            observation = AVAILABLE_TOOLS[tool_name](tool_input)

        print(f"OBSERVATION: {observation}")

        # Feed the observation back as a user turn, so the model continues the loop
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    print("Max steps reached without a final answer.")
    return None


if __name__ == "__main__":
    run_react_loop(
    "What is 45 times 12, and how many words are in the sentence "
    "'the quick brown fox jumps over the lazy dog'? "
    "Use the calculator and word_count tools to get both answers, "
    "then give me both answers combined into one final sentence."

    )