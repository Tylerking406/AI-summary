from fastapi import APIRouter, HTTPException
from services.Groq_client import chat

router = APIRouter()

@router.get("/llm-smoke")
async def llm_smoke():
    try:
        msg = [{"role": "user", "content": "Respond with: OK"}]
        out = await chat(msg, temperature=0.0, max_completion_tokens=10)
        return {"model_response": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
