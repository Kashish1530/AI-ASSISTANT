import os
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "openai/gpt-oss-120b"

TASK = "the current state of agentic AI adoption in enterprises"

# Groq pricing for openai/gpt-oss-120b 
PRICE_PER_M_INPUT = 0.15   # $ per million input tokens 
PRICE_PER_M_OUTPUT = 0.75  # $ per million output tokens 


def mock_web_search(query: str) -> str:
    return (
        f"[MOCK DATA - placeholder, not real search results] "
        f"Simulated findings on '{query}': point A, point B, point C."
    )


def estimate_cost(usage):
    input_cost = (usage.prompt_tokens / 1_000_000) * PRICE_PER_M_INPUT
    output_cost = (usage.completion_tokens / 1_000_000) * PRICE_PER_M_OUTPUT
    return input_cost + output_cost


# ==================== APPROACH 1: FIXED PIPELINE ====================

def run_fixed_pipeline(task: str):
    start = time.time()
    total_cost = 0.0
    total_calls = 0

    # Step 1: always research
    raw_results = mock_web_search(task)
    resp1 = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": (
            f"Summarize into 3-4 bullet points for '{task}'. If findings are "
            f"mock/placeholder, say so.\n\nRaw findings:\n{raw_results}"
        )}]
    )
    notes = resp1.choices[0].message.content
    total_cost += estimate_cost(resp1.usage)
    total_calls += 1

    # Step 2: always write
    resp2 = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": (
            f"Write a polished 3-sentence summary for task '{task}' using "
            f"these notes:\n{notes}"
        )}]
    )
    final = resp2.choices[0].message.content
    total_cost += estimate_cost(resp2.usage)
    total_calls += 1

    elapsed = time.time() - start
    return {
        "approach": "fixed_pipeline",
        "final_output": final,
        "llm_calls": total_calls,
        "latency_seconds": round(elapsed, 2),
        "estimated_cost_usd": round(total_cost, 6),
    }


# ==================== APPROACH 2: AGENT (SUPERVISOR-ROUTED) ====================
                                                                                                                                                             
def run_agent_version(task: str):
    start = time.time()
    total_cost = 0.0
    total_calls = 0

    state = {"research_notes": "", "final_output": ""}

    while True:
        supervisor_prompt = (
            f"Research notes exist: {bool(state['research_notes'])}. "
            f"Final output exists: {bool(state['final_output'])}. "
            f"Reply with exactly one word: 'researcher', 'writer', or 'done'."
        )
        sresp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": supervisor_prompt}]
        )
        decision = sresp.choices[0].message.content.strip().lower()
        total_cost += estimate_cost(sresp.usage)
        total_calls += 1

        if "done" in decision:
            break
        elif "researcher" in decision:
            raw_results = mock_web_search(task)
            rresp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": (
                    f"Summarize into 3-4 bullet points for '{task}'. If "
                    f"findings are mock/placeholder, say so.\n\nRaw findings:\n{raw_results}"
                )}]
            )
            state["research_notes"] = rresp.choices[0].message.content
            total_cost += estimate_cost(rresp.usage)
            total_calls += 1
        elif "writer" in decision:
            wresp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": (
                    f"Write a polished 3-sentence summary for task '{task}' "
                    f"using these notes:\n{state['research_notes']}"
                )}]
            )
            state["final_output"] = wresp.choices[0].message.content
            total_cost += estimate_cost(wresp.usage)
            total_calls += 1
        else:
            break  

    elapsed = time.time() - start
    return {
        "approach": "agent_supervised",
        "final_output": state["final_output"],
        "llm_calls": total_calls,
        "latency_seconds": round(elapsed, 2),
        "estimated_cost_usd": round(total_cost, 6),
    }


if __name__ == "__main__":
    print("=== RUNNING FIXED PIPELINE ===")
    pipeline_result = run_fixed_pipeline(TASK)
    print(f"\nOutput: {pipeline_result['final_output']}")

    print("\n\n=== RUNNING AGENT VERSION ===")
    agent_result = run_agent_version(TASK)
    print(f"\nOutput: {agent_result['final_output']}")

    print("\n\n=== COMPARISON ===")
    print(f"{'Metric':<20} {'Fixed Pipeline':<20} {'Agent':<20}")
    print(f"{'LLM calls':<20} {pipeline_result['llm_calls']:<20} {agent_result['llm_calls']:<20}")
    print(f"{'Latency (s)':<20} {pipeline_result['latency_seconds']:<20} {agent_result['latency_seconds']:<20}")
    print(f"{'Est. cost (USD)':<20} {pipeline_result['estimated_cost_usd']:<20} {agent_result['estimated_cost_usd']:<20}")

    extra_calls = agent_result['llm_calls'] - pipeline_result['llm_calls']
    extra_cost = agent_result['estimated_cost_usd'] - pipeline_result['estimated_cost_usd']
    print(f"\nAgent overhead: +{extra_calls} LLM call(s), +${extra_cost:.6f}, "
          f"for a task whose steps never actually needed a routing decision.")
    print("Conclusion: the fixed pipeline is strictly better here - this task "
          "has a known, unchanging path (always research, then always write). "
          "An agent only earns its overhead when the NEXT step genuinely "
          "depends on what the PREVIOUS step returned.")
