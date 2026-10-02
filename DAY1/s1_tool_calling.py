import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])

MODEL = "openai/gpt-oss-120b"


def get_time():
    return datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%Y-%m-%d %I:%M:%S %p IST")

def calculator(expression):
    return str(eval(expression))


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression, e.g. '12*7'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]


messages = [
    {
        "role": "user",
        "content": (
            "Use BOTH tools. "
            "Call calculator to compute 45 * 12. "
            "Call get_time to get the current time. "
            "Do not calculate the answer yourself."
        )
    }
]


while True:

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    msg = resp.choices[0].message

    print("\nMODEL RESPONSE:")
    print(msg)

    if not msg.tool_calls:
        print("\nFINAL ANSWER:")
        print(msg.content)
        break

    messages.append(msg)

    for call in msg.tool_calls:

        name = call.function.name
        args = json.loads(call.function.arguments)

        print(f"\nEXECUTING: {name}({args})")

        if name == "get_time":
            result = get_time()

        elif name == "calculator":
            result = calculator(**args)

        else:
            result = f"Unknown tool: {name}"

        print(f"RESULT: {result}")

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": str(result)
        })
