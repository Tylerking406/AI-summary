from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Contract Summarizer API", version="0.1.0")
## to run thois app use: uvicorn app:app --reload --port 8000
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "summarizer", "version": "0.1.0"})
