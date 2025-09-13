from fastapi import APIRouter, HTTPException
from services.Groq_client import chat

router = APIRouter()

@router.get("/llm-smoke")
async def llm_smoke():
    try:
        messages = [
            {"role": "system", "content": "You are a maths friendly tutor who is eager to help."},
            {"role": "user", "content": "What is 1 + 1?"}
        ]
        out = await chat(messages, temperature=0.0, max_completion_tokens=20)
        return {"model_response": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
