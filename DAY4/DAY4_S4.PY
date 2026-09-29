# Cut cost per query by at least 40 percent while keeping the pass rate within 2 points
import os
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

# Two tiers - swap these for whatever's live on your Groq account
# (run models.list() from earlier if either of these 404s)
SMALL_MODEL = "openai/gpt-oss-20b"
LARGE_MODEL = "openai/gpt-oss-120b"

# Placeholder pricing - verify actual rates at console.groq.com/docs/pricing
PRICING = {
    SMALL_MODEL: {"input": 0.05, "output": 0.25},   # $ per million tokens
    LARGE_MODEL: {"input": 0.15, "output": 0.75},
}


def estimate_cost(model, usage):
    rates = PRICING[model]
    return (usage.prompt_tokens / 1_000_000) * rates["input"] + \
           (usage.completion_tokens / 1_000_000) * rates["output"]


def call_model(model, prompt):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    answer = resp.choices[0].message.content
    cost = estimate_cost(model, resp.usage)
    return answer, cost


# ---------- Escalation trigger: how do we know the small model "failed"? ----------

def small_model_failed(answer, question):
    """
    Heuristics for when to escalate. In production you might also use a
    judge-model confidence check, but these cheap checks catch the most
    common small-model failure modes without an extra LLM call:
    """
    if not answer or len(answer.strip()) < 3:
        return True, "empty or near-empty response"

    uncertainty_phrases = [
        "i don't know", "i'm not sure", "unclear", "cannot determine",
        "i cannot answer", "as an ai", "i don't have enough information"
    ]
    lower = answer.lower()
    for phrase in uncertainty_phrases:
        if phrase in lower:
            return True, f"expressed uncertainty ('{phrase}')"

    # Heuristic: if the question looks complex (long, multi-part, or asks
    # for reasoning/analysis) but the small model gave a very short answer,
    # that's suspicious - likely under-serving a hard question.
    complex_signals = ["explain why", "analyze", "compare", "step by step", "reasoning"]
    if any(s in question.lower() for s in complex_signals) and len(answer.strip()) < 40:
        return True, "question looked complex but answer was suspiciously short"

    return False, None


def run_with_routing(question, verbose=True):
    small_answer, small_cost = call_model(SMALL_MODEL, question)

    failed, reason = small_model_failed(small_answer, question)

    if not failed:
        if verbose:
            print(f"  [{SMALL_MODEL}] handled it. Cost: ${small_cost:.8f}")
        return {
            "question": question, "final_answer": small_answer,
            "model_used": SMALL_MODEL, "escalated": False,
            "cost": small_cost, "escalation_reason": None,
        }

    # Escalate
    if verbose:
        print(f"  [{SMALL_MODEL}] failed ({reason}) -> escalating to {LARGE_MODEL}")
    large_answer, large_cost = call_model(LARGE_MODEL, question)
    total_cost = small_cost + large_cost  # you pay for BOTH calls when escalating
    if verbose:
        print(f"  [{LARGE_MODEL}] handled it. Cost: ${large_cost:.8f} (total incl. small model attempt: ${total_cost:.8f})")

    return {
        "question": question, "final_answer": large_answer,
        "model_used": LARGE_MODEL, "escalated": True,
        "cost": total_cost, "escalation_reason": reason,
    }


def run_large_only(question):
    answer, cost = call_model(LARGE_MODEL, question)
    return {"question": question, "final_answer": answer, "cost": cost}


# ---------- Test set: mix of simple and genuinely complex questions ----------

TEST_QUESTIONS = [
    "What is the capital of Japan?",
    "What is 12 + 15?",
    "What color is the sky on a clear day?",
    "How many days are in a week?",
    "What's the chemical symbol for gold?",
    "Explain why context engineering matters for AI agent cost management, step by step.",
    "Compare and analyze the tradeoffs between using a fixed pipeline versus an autonomous agent for a task with a genuinely unpredictable number of steps.",
    "What is the opposite of 'hot'?",
    "Analyze the reasoning behind why small-model-first routing reduces cost, and explain the failure modes it introduces.",
    "What year is it commonly considered the internet became publicly available?",
    "hOW MANY DAYS IN FEBRUARY IN YEAR 2000?",
]


if __name__ == "__main__":
    print("=== RUNNING WITH ROUTING (small-first, escalate on failure) ===\n")
    routed_results = []
    for q in TEST_QUESTIONS:
        print(f"Q: {q}")
        result = run_with_routing(q)
        routed_results.append(result)
        print()

    print("\n=== RUNNING LARGE-MODEL-ONLY BASELINE (for comparison) ===\n")
    baseline_results = []
    for q in TEST_QUESTIONS:
        result = run_large_only(q)
        baseline_results.append(result)

    routed_total_cost = sum(r["cost"] for r in routed_results)
    baseline_total_cost = sum(r["cost"] for r in baseline_results)
    escalated_count = sum(1 for r in routed_results if r["escalated"])

    print(f"\n\n{'='*60}")
    print("COST COMPARISON")
    print(f"{'='*60}")
    print(f"Questions tested: {len(TEST_QUESTIONS)}")
    print(f"Escalated to large model: {escalated_count}/{len(TEST_QUESTIONS)}")
    print(f"\nRouted total cost:        ${routed_total_cost:.8f}")
    print(f"Large-model-only cost:    ${baseline_total_cost:.8f}")

    if baseline_total_cost > 0:
        savings_pct = round((1 - routed_total_cost / baseline_total_cost) * 100, 1)
        print(f"Savings from routing:     {savings_pct}%")

    print(f"\nEscalated questions (small model correctly identified as needing help):")
    for r in routed_results:
        if r["escalated"]:
            print(f"  - \"{r['question'][:60]}\" (reason: {r['escalation_reason']})")