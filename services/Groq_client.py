import os
from groq import AsyncGroq

MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# The client reads GROQ_API_KEY from env automatically.
_client = AsyncGroq()

async def chat(messages, **kwargs) -> str:
    """
    messages: list like [{"role":"system","content":"..."},{"role":"user","content":"..."}]
    kwargs: temperature, max_completion_tokens, response_format, etc.
    """
    resp = await _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=False,
        **kwargs
    )
    return resp.choices[0].message.content
