import os
import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import get_db, UserSettings
from sqlalchemy.orm import Session
from fastapi import Depends

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:4200")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REDIRECT_URI = f"{BACKEND_URL}/auth/callback"


def create_jwt(email: str, name: str, picture: str) -> str:
    expire = datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": email,
        "name": name,
        "picture": picture,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def verify_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/local")
async def login_local(db: Session = Depends(get_db)):
    """Bypass OAuth — create a local session with no credentials required."""
    settings = db.query(UserSettings).first()
    if settings:
        settings.google_user_email = "local@localhost"
        settings.google_user_name = "Local User"
        settings.google_user_picture = ""
        db.commit()
    token = create_jwt("local@localhost", "Local User", "")
    return {"token": token}


@router.get("/google")
async def login_google():
    """Redirect user to Google OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env")

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/callback")
async def auth_callback(code: str = None, error: str = None, db: Session = Depends(get_db)):
    """Handle Google OAuth callback, issue JWT, redirect to frontend."""
    if error or not code:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error or 'no_code'}")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=token_exchange_failed")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        user_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_resp.status_code != 200:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=userinfo_failed")

        user_data = user_resp.json()

    email = user_data.get("email", "")
    name = user_data.get("name", "")
    picture = user_data.get("picture", "")

    # Persist user info in settings
    settings = db.query(UserSettings).first()
    if settings:
        settings.google_user_email = email
        settings.google_user_name = name
        settings.google_user_picture = picture
        db.commit()

    jwt_token = create_jwt(email, name, picture)
    return RedirectResponse(url=f"{FRONTEND_URL}/auth/callback?token={jwt_token}")


@router.get("/user")
async def get_user(db: Session = Depends(get_db)):
    """Return stored user info (no token required for single-user local app)."""
    settings = db.query(UserSettings).first()
    if not settings or not settings.google_user_email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "email": settings.google_user_email,
        "name": settings.google_user_name,
        "picture": settings.google_user_picture,
        "is_authenticated": True
    }


@router.post("/logout")
async def logout(db: Session = Depends(get_db)):
    """Clear stored user info."""
    settings = db.query(UserSettings).first()
    if settings:
        settings.google_user_email = ""
        settings.google_user_name = ""
        settings.google_user_picture = ""
        db.commit()
    return {"message": "Logged out"}
