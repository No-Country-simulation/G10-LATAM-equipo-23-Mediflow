from fastapi import FastAPI

from app.api.triagem import router as triagem_router

app = FastAPI(title="MediFlow", version="0.1.0")
app.include_router(triagem_router)


@app.get("/health")
def health():
    return {"status": "ok"}