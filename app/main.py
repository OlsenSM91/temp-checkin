from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.api.routes import router
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Get session secret from environment variables
session_secret = os.getenv("SESSION_SECRET", "supersecret")
app.add_middleware(SessionMiddleware, secret_key=session_secret)

app.include_router(router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
