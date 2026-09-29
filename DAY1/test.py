from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
resp = client.chat.completions.create(
    model = "openai/gpt-oss-120b",
    messages = [{"role": "user", "content": "say hi in 5 words"}]
)
print(resp.choices[0].message.content)
