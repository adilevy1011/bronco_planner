"""FastAPI API for the CPP course planner.

Supabase is intentionally server-side only. Set SUPABASE_URL,
SUPABASE_ANON_KEY, and SUPABASE_SERVICE_ROLE_KEY in the backend environment.
"""

from pathlib import Path
import json
import os

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from supabase import Client, create_client


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
COOKIE_NAME = "planner_session"

app = FastAPI(title="CPP Course Planner API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


class AuthPayload(BaseModel):
    email: str
    password: str


class PlanPayload(BaseModel):
    terms: list[dict] = Field(default_factory=list)


def read_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Data file not found: {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}") from error


def supabase_config() -> tuple[str, str, str]:
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not anon_key or not service_key:
        raise HTTPException(status_code=503, detail="Supabase server configuration is missing")
    return url, anon_key, service_key


def auth_client() -> Client:
    url, anon_key, _ = supabase_config()
    return create_client(url, anon_key)


def data_client() -> Client:
    url, _, service_key = supabase_config()
    return create_client(url, service_key)


def current_user(request: Request):
    access_token = request.cookies.get(COOKIE_NAME)
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        return auth_client().auth.get_user(access_token).user
    except Exception as error:
        raise HTTPException(status_code=401, detail="Session expired") from error


def set_session(response: JSONResponse, session) -> JSONResponse:
    secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    response.set_cookie(COOKIE_NAME, session.access_token, httponly=True, secure=secure, samesite="lax", max_age=session.expires_in or 3600)
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "supabase_configured": all(os.getenv(key) for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"))}


@app.get("/api/manifest")
def manifest() -> dict:
    return read_json(MANIFEST_PATH)


@app.get("/api/general-education")
def general_education() -> dict:
    return read_json(DATA_DIR / "general-education.json")


@app.get("/api/programs/{program_id}")
def program(program_id: str) -> dict:
    return read_json(DATA_DIR / "programs" / f"{program_id}.json")


@app.get("/api/departments/{department_id}")
def department(department_id: str) -> dict:
    return read_json(DATA_DIR / "departments" / f"{department_id}.json")


@app.post("/api/auth/register")
def register(payload: AuthPayload):
    try:
        result = auth_client().auth.sign_up({"email": payload.email.strip().lower(), "password": payload.password})
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not result.session:
        return {"message": "Check your email to confirm your account."}
    return set_session(JSONResponse({"user": {"id": result.user.id, "email": result.user.email}}), result.session)


@app.post("/api/auth/login")
def login(payload: AuthPayload):
    try:
        result = auth_client().auth.sign_in_with_password({"email": payload.email.strip().lower(), "password": payload.password})
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid email or password") from error
    return set_session(JSONResponse({"user": {"id": result.user.id, "email": result.user.email}}), result.session)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request) -> dict:
    user = current_user(request)
    return {"id": user.id, "email": user.email}


@app.get("/api/me/plan")
def get_plan(request: Request) -> dict:
    user = current_user(request)
    result = data_client().table("planner_plans").select("terms,updated_at").eq("user_id", user.id).limit(1).execute()
    rows = result.data if result else []
    return rows[0] if rows else {"terms": [], "updated_at": None}


@app.put("/api/me/plan")
def save_plan(payload: PlanPayload, request: Request) -> dict:
    user = current_user(request)
    result = data_client().table("planner_plans").upsert({"user_id": user.id, "terms": payload.terms}, on_conflict="user_id").execute()
    rows = result.data if result else []
    return rows[0] if rows else {"terms": payload.terms}
