import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from database import init_db
from routers import auth, books, progress, translate, settings, tts, voicebox, listening, search, downloads

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:4200")
BOOKS_DIR = os.getenv("BOOKS_DIR", "./books")

app = FastAPI(
    title="LNreader API",
    description="Backend API for LNreader - an EPUB/TXT reader with Japanese support",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount book covers static directory
os.makedirs(BOOKS_DIR, exist_ok=True)

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(progress.router)
app.include_router(translate.router)
app.include_router(settings.router)
app.include_router(tts.router)
app.include_router(voicebox.router)
app.include_router(listening.router)
app.include_router(search.router)
app.include_router(downloads.router)


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/")
async def root():
    return {"message": "LNreader API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
