import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

# ---------- Build a long, realistic conversation to test on ----------

LONG_CONVERSATION = [
    {"role": "system", "content": "You are a helpful research assistant."},
    {"role": "user", "content": "What is agentic AI?"},
    {"role": "assistant", "content": "Agentic AI refers to AI systems that can autonomously plan, decide, and take multi-step actions toward a goal, rather than just responding to a single prompt. Unlike traditional chatbots, agentic systems use tools, maintain state, and adapt their approach based on intermediate results."},
    {"role": "user", "content": "How is that different from a regular chatbot?"},
    {"role": "assistant", "content": "A regular chatbot typically responds to one message at a time with no independent action - it can't browse the web, run code, or call APIs on its own. An agentic system can decide 'I need to search for X, then read a file, then compute Y' and execute that whole chain without a human directing each individual step."},
    {"role": "user", "content": "What frameworks are commonly used to build these?"},
    {"role": "assistant", "content": "Popular frameworks include LangGraph (state-graph based agent orchestration), LangChain (general LLM app framework with agent support), AutoGen (multi-agent conversation framework from Microsoft), and CrewAI (role-based multi-agent framework). Each has different tradeoffs in flexibility versus structure."},
    {"role": "user", "content": "What's the difference between LangGraph and LangChain?"},
    {"role": "assistant", "content": "LangChain is the broader library with utilities for prompts, chains, and basic agents. LangGraph is a more specialized library built on top of LangChain concepts, specifically for building agents as explicit state graphs with nodes, edges, and cycles - giving you more control over branching logic and making the agent's flow easier to visualize and debug."},
    {"role": "user", "content": "Is LangGraph good for beginners?"},
    {"role": "assistant", "content": "It has a steeper learning curve than a simple LangChain agent because you need to think in terms of state, nodes, and conditional edges rather than a simple loop. That said, once you understand the mental model, it makes complex agent behavior (like multi-agent supervisors or cyclical ReAct loops) much easier to reason about and debug than a tangle of nested if-statements."},
    {"role": "user", "content": "What about memory in agents - how does that work?"},
    {"role": "assistant", "content": "Agent memory splits into short-term (the conversation buffer within one session) and long-term (persisted across sessions, usually to a database or file). Long-term memory typically stores derived facts or preferences rather than raw conversation history, and should be scoped per-user to avoid mixing different users' data together."},
]

QUESTION = "Given everything we discussed, should I start with LangChain or LangGraph for my first agent project?"


def count_tokens_approx(messages):
    """Rough approximation: ~4 characters per token (standard rule of thumb).
    For exact counts, you'd use a tokenizer library like tiktoken, but Groq's
    open models don't have an official tiktoken encoding, so this estimate
    is what we'll use consistently for a fair before/after comparison."""
    total_chars = sum(len(m["content"]) for m in messages)
    return total_chars // 4


def ask_with_full_history():
    messages = LONG_CONVERSATION + [{"role": "user", "content": QUESTION}]
    tokens_sent = count_tokens_approx(messages)

    resp = client.chat.completions.create(model=MODEL, messages=messages)
    answer = resp.choices[0].message.content

    return {
        "method": "full_history",
        "estimated_input_tokens": tokens_sent,
        "actual_prompt_tokens": resp.usage.prompt_tokens,
        "answer": answer,
    }


def summarize_old_turns(messages_to_summarize):
    """Compress older turns into a short summary via one extra LLM call."""
    convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages_to_summarize)
    prompt = (
        "Summarize this conversation into 2-3 sentences capturing only the "
        "key facts/decisions, so it can replace the full history:\n\n" + convo_text
    )
    resp = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content


def ask_with_summarized_history():
    system_msg = LONG_CONVERSATION[0]
    older_turns = LONG_CONVERSATION[1:-2]   
    recent_turns = LONG_CONVERSATION[-2:]  

    summary = summarize_old_turns(older_turns)
    print(f"SUMMARY OF OLDER TURNS:\n{summary}\n")

    trimmed_messages = [
        system_msg,
        {"role": "system", "content": f"Earlier conversation summary: {summary}"},
        *recent_turns,
        {"role": "user", "content": QUESTION},
    ]
    tokens_sent = count_tokens_approx(trimmed_messages)

    resp = client.chat.completions.create(model=MODEL, messages=trimmed_messages)
    answer = resp.choices[0].message.content

    return {
        "method": "summarized_history",
        "estimated_input_tokens": tokens_sent,
        "actual_prompt_tokens": resp.usage.prompt_tokens,
        "answer": answer,
    }


if __name__ == "__main__":
    print("=== METHOD 1: FULL HISTORY (baseline) ===")
    full = ask_with_full_history()
    print(f"Answer: {full['answer']}")
    print(f"Prompt tokens (actual, from API): {full['actual_prompt_tokens']}")

    print("\n\n=== METHOD 2: SUMMARIZED HISTORY ===")
    summarized = ask_with_summarized_history()
    print(f"Answer: {summarized['answer']}")
    print(f"Prompt tokens (actual, from API): {summarized['actual_prompt_tokens']}")

    print("\n\n=== COMPARISON ===")
    baseline = full["actual_prompt_tokens"]
    reduced = summarized["actual_prompt_tokens"]
    pct_reduction = round((1 - reduced / baseline) * 100, 1)

    print(f"Full history prompt tokens:        {baseline}")
    print(f"Summarized history prompt tokens:  {reduced}")
    print(f"Reduction: {pct_reduction}%")
    print(f"\nNote: the summarization call itself costs extra tokens (not counted "
          f"above) - factor that into real cost comparisons, though it's a "
          f"one-time cost amortized across all future turns, not paid every turn.")
    print(f"\nTarget was 30%+ reduction with no accuracy loss - compare both "
          f"answers above manually: does the summarized version still correctly "
          f"recommend LangGraph vs LangChain with sound reasoning?")
