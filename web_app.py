import os
import secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
import uvicorn
from dotenv import load_dotenv

from search_pipeline import SearchPipelineEngine
from nl_parser import parse_natural_language_prompt
from taxonomy import LANGUAGES, CATEGORIES, ALL_GENRES
from lyrics_service import get_song_lyrics
from track_sorting import sort_tracks
from similarity_engine import find_similar_tracks

load_dotenv()

app = FastAPI(title="Spotify Şarkı Sözü & Keşif Motoru 2.1 PRO")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

engine = SearchPipelineEngine()


def get_spotify_redirect_uri(request: Request) -> str:
    """Return the one redirect URI used for both authorize and token exchange.

    Spotify requires an exact match with the URI allowlisted in its dashboard.
    In production, set SPOTIPY_REDIRECT_URI to the public HTTPS callback URL.
    For local development, the configured value defaults to the loopback URL.
    """
    configured = os.getenv("SPOTIPY_REDIRECT_URI")
    if configured:
        return configured.strip()
    return f"{str(request.base_url).rstrip('/')}/callback"

class SearchRequest(BaseModel):
    lyrics_query: Optional[str] = Field(default="", max_length=200)
    language: Optional[str] = Field(default="all", max_length=10)
    category: Optional[str] = Field(default="all", max_length=50)
    genres: Optional[List[str]] = Field(default_factory=list, max_length=15)
    year_start: Optional[int] = Field(default=1990, ge=1950, le=2026)
    year_end: Optional[int] = Field(default=2026, ge=1950, le=2026)
    popularity_min: Optional[int] = Field(default=0, ge=0, le=100)
    popularity_max: Optional[int] = Field(default=100, ge=0, le=100)
    strictness: Optional[str] = Field(default="balanced")
    profanity_mode: Optional[str] = Field(default="all")
    target_theme: Optional[str] = Field(default="all", max_length=30)
    avoid_themes: Optional[List[str]] = Field(default_factory=list, max_length=10)
    filter_meaningful: Optional[bool] = Field(default=True)
    preferred_version: Optional[str] = Field(default="original", max_length=20)
    allow_instrumental: Optional[bool] = Field(default=False)
    sort_by: Optional[str] = Field(default="relevance", max_length=25)
    limit: Optional[int] = Field(default=20, ge=5, le=100)

    model_config = {"extra": "forbid"}

class SimilarRequest(BaseModel):
    target_track: dict
    candidate_pool: List[dict]
    limit: Optional[int] = 5

class SortRequest(BaseModel):
    tracks: List[dict]
    sort_by: str = "relevance"

class NLSearchRequest(BaseModel):
    prompt: str

class LyricsRequest(BaseModel):
    track_name: str
    artist_name: str

class CreatePlaylistRequest(BaseModel):
    name: str
    track_uris: List[str]
    description: Optional[str] = "Spotify Müzik Keşif Motoru ile oluşturuldu."

class CredentialsRequest(BaseModel):
    client_id: str
    client_secret: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login(request: Request):
    """PKCE ile güvenli OAuth linki üretir. Kullanıcıya özel session_id cookie atar."""
    session_id = request.cookies.get("spoti_session_id") or secrets.token_urlsafe(16)
    
    redirect_uri = get_spotify_redirect_uri(request)
    auth_url, _ = engine.pkce_auth.get_authorize_url(state=session_id, redirect_uri=redirect_uri)
    response = RedirectResponse(auth_url)
    response.set_cookie(
        key="spoti_session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600
    )
    return response

@app.get("/callback")
async def callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """PKCE kod takası."""
    if error:
        return RedirectResponse(f"/?error={error}")
    if code and state:
        if request.cookies.get("spoti_session_id") != state:
            return RedirectResponse("/?error=auth_failed")
        redirect_uri = get_spotify_redirect_uri(request)
        success = engine.pkce_auth.exchange_code_for_token(code=code, state=state, redirect_uri=redirect_uri)
        if success:
            resp = RedirectResponse("/?auth=success")
            resp.set_cookie(
                key="spoti_session_id",
                value=state,
                httponly=True,
                samesite="lax",
                max_age=30 * 24 * 3600
            )
            return resp
    return RedirectResponse("/?error=auth_failed")

@app.get("/api/status")
async def get_status(request: Request):
    has_credentials = engine.is_authenticated()
    session_id = request.cookies.get("spoti_session_id")
    user_profile = engine.pkce_auth.get_current_user_profile(session_id=session_id)
    
    return {
        "has_credentials": has_credentials,
        "is_user_authenticated": user_profile is not None,
        "user_profile": user_profile
    }

@app.get("/api/taxonomy")
async def get_taxonomy():
    return {
        "languages": LANGUAGES,
        "categories": CATEGORIES,
        "genres": ALL_GENRES
    }

@app.get("/logout")
async def logout(request: Request):
    """Kullanıcı oturumunu sonlandırır."""
    import sqlite3
    from db import DB_PATH
    session_id = request.cookies.get("spoti_session_id")
    if session_id:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("DELETE FROM user_auth WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
    resp = RedirectResponse("/?logout=success")
    resp.delete_cookie("spoti_session_id")
    return resp

class FeedbackRequest(BaseModel):
    track_id: str = Field(min_length=1, max_length=128)
    action_type: str = Field(default="play_preview", pattern="^(play_preview|select|export|favorite|dismiss)$")
    user_theme: Optional[str] = Field(default=None, max_length=30)

@app.post("/api/search")
async def search_endpoint(req: SearchRequest):
    result = engine.search_tracks(
        lyrics_query=req.lyrics_query or "",
        language=req.language or "all",
        category=req.category or "all",
        genres=req.genres or [],
        year_start=req.year_start or 1990,
        year_end=req.year_end or 2026,
        popularity_min=req.popularity_min or 0,
        popularity_max=req.popularity_max or 100,
        strictness=req.strictness or "balanced",
        profanity_mode=req.profanity_mode or "all",
        target_theme=req.target_theme or "all",
        avoid_themes=req.avoid_themes or [],
        filter_meaningful=bool(req.filter_meaningful),
        preferred_version=req.preferred_version or "original",
        allow_instrumental=bool(req.allow_instrumental),
        sort_by=req.sort_by or "relevance",
        limit=req.limit or 20
    )
    return result

@app.post("/api/feedback")
async def feedback_endpoint(req: FeedbackRequest):
    """Kullanıcı etkileşim geri bildirimini kaydeder ve sonraki sıralamaları iyileştirir."""
    try:
        from db import record_feedback
        record_feedback(
            query_theme=req.user_theme or "all",
            query_genre="all",
            track_id=req.track_id,
            action_type=req.action_type,
        )
        return {"status": "ok", "track_id": req.track_id, "action": req.action_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Geri bildirim kaydedilemedi.") from e

@app.post("/api/sort-tracks")
async def sort_tracks_endpoint(req: SortRequest):
    """Mevcut sonuçları yeniden indirmeden anlık olarak sıralar."""
    sorted_tracks = sort_tracks(req.tracks, sort_by=req.sort_by)
    return {"tracks": sorted_tracks}

@app.post("/api/find-similar")
async def find_similar_endpoint(req: SimilarRequest):
    """Anlamsal müzik keşfi: Hedef parçaya en yakın parçaları sıralar."""
    similar = find_similar_tracks(req.target_track, req.candidate_pool, limit=req.limit or 5)
    return {"similar_tracks": similar}

@app.post("/api/nl-parse")
async def nl_parse_endpoint(req: NLSearchRequest):
    """Doğal dil ifadesini filtrelere dönüştürür."""
    parsed = parse_natural_language_prompt(req.prompt)
    return {"filters": parsed}

@app.post("/api/get-lyrics")
async def get_lyrics_endpoint(req: LyricsRequest):
    # Telif güvencesi: Kullanıcıya sadece analiz / teyit için geçici gösterim
    lyrics = get_song_lyrics(req.track_name, req.artist_name)
    return {"lyrics": lyrics}

@app.post("/api/create-playlist")
async def create_playlist_endpoint(req: CreatePlaylistRequest, request: Request):
    try:
        session_id = request.cookies.get("spoti_session_id")
        res = engine.create_playlist_pkce(
            name=req.name,
            track_uris=req.track_uris,
            description=req.description or "Spotify Keşif Motoru",
            session_id=session_id
        )
        return {"success": True, **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-credentials")
async def save_credentials(req: CredentialsRequest):
    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"SPOTIPY_CLIENT_ID={req.client_id}\n")
        f.write(f"SPOTIPY_CLIENT_SECRET={req.client_secret}\n")
        f.write(f"SPOTIPY_REDIRECT_URI={os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:3001/callback')}\n")

    engine.client_id = req.client_id
    engine.client_secret = req.client_secret
    engine._init_spotify_client()
    engine.pkce_auth.client_id = req.client_id

    return {"success": engine.is_authenticated()}

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="0.0.0.0", port=3001, reload=True)
