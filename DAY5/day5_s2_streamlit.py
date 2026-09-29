import streamlit as st
import sys
import os

# Import the capstone agent from Day 5 S1 - keep this file in the same folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from day5_s1_capstone import run_capstone_agent, load_memory

st.set_page_config(page_title="Agentic AI Capstone", page_icon="🤖")
st.title("🤖 Agentic AI Capstone Demo")
st.caption("Week 2 capstone: tools + memory + guardrails, wired end to end (Groq / openai/gpt-oss-120b)")

# --- Session handling: a stable user_id per browser session ---
if "user_id" not in st.session_state:
    st.session_state.user_id = "streamlit_user_" + str(id(st.session_state))
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role", "content", "tool_calls", "sources"}

with st.sidebar:
    st.subheader("Session Info")
    st.text(f"User ID: {st.session_state.user_id}")

    memory = load_memory(st.session_state.user_id)
    st.subheader("Remembered Preferences")
    if memory["preferences"]:
        for p in memory["preferences"]:
            st.text(f"- {p['text']}")
    else:
        st.text("(none yet)")

    auto_approve = st.checkbox(
        "Auto-approve dangerous actions (demo only - disable for real use)",
        value=False
    )


def render_sources(tool_calls, sources):
    if not tool_calls:
        return
    with st.expander(f"🔧 Tools used: {', '.join(tool_calls)}"):
        if not sources:
            st.write("No citable sources for this response.")
            return
        for s in sources:
            icon = {"file": "📄", "web_search": "🌐", "system": "🕐", "computation": "🧮", "action": "✉️"}.get(s["type"], "🔧")
            line = f"{icon} **{s['type']}**: `{s['label']}`"
            st.markdown(line)
            if s["note"]:
                if "MOCK" in s["note"]:
                    st.warning(f"⚠️ {s['note']}")
                else:
                    st.caption(s["note"])


# --- Render chat history ---
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant":
            render_sources(msg.get("tool_calls", []), msg.get("sources", []))

# --- Chat input ---
user_input = st.chat_input("Ask something...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input, "tool_calls": [], "sources": []})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, tool_calls, sources = run_capstone_agent(
                st.session_state.user_id, user_input, auto_approve_dangerous=auto_approve
            )
        st.write(answer or "(no response - check terminal for errors)")
        render_sources(tool_calls, sources)

    st.session_state.chat_history.append({
        "role": "assistant", "content": answer, "tool_calls": tool_calls, "sources": sources
    })