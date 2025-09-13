from fastapi import FastAPI
import dotenv; dotenv.load_dotenv()
from fastapi.responses import JSONResponse
from App.routes import router 

app = FastAPI(title="Contract Summarizer API", version="0.1.0")
app.include_router(router) 
## to run thois app use: uvicorn app:app --reload --port 8000
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "summarizer", "version": "0.1.0"})

@app.get("/")
def read_root():
    return {"message": "Welcome to the Contract Summarizer API"}
