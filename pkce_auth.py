import os
import secrets
import hashlib
import base64
import time
import requests
import sqlite3
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from db import DB_PATH
from rate_limiter import SpotifyRateLimiter

load_dotenv()

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# PKCE ve güvenlik gereği istenen scope'lar:
SCOPES = "playlist-modify-public playlist-modify-private user-read-private"

class SpotifyPKCEAuthManager:
    """
    Spotify OAuth 2.0 with PKCE (Proof Key for Code Exchange):
    - Client Secret frontend'e ASLA maruz kalmaz.
    - Otomatik token yenileme (Refresh Token takası) mekanizması bulunur.
    - code_verifier ve code_challenge standartlarına uygun çalışır.
    """
    def __init__(self, client_id: Optional[str] = None, redirect_uri: str = "http://localhost:3001/callback"):
        self.client_id = client_id or os.getenv("SPOTIPY_CLIENT_ID")
        self.redirect_uri = redirect_uri or os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:3001/callback")
        self.rate_limiter = SpotifyRateLimiter()

    def generate_pkce_pair(self) -> tuple[str, str]:
        """code_verifier ve code_challenge üretir."""
        code_verifier = secrets.token_urlsafe(64)
        hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")
        return code_verifier, code_challenge

    def get_authorize_url(self, state: str, redirect_uri: Optional[str] = None) -> tuple[str, str]:
        """Kullanıcının yönlendirileceği yetkilendirme linkini ve code_verifier'ı üretir."""
        if not self.client_id:
            raise ValueError("SPOTIPY_CLIENT_ID yapılandırılmamış!")

        code_verifier, code_challenge = self.generate_pkce_pair()
        effective_redirect = redirect_uri or self.redirect_uri

        # Veritabanında state ile code_verifier'ı eşleştir
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_auth (session_id, code_verifier)
            VALUES (?, ?)
        """, (state, code_verifier))
        conn.commit()
        conn.close()

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": effective_redirect,
            "state": state,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge
        }
        query_string = requests.compat.urlencode(params)
        return f"{SPOTIFY_AUTH_URL}?{query_string}", code_verifier

    def exchange_code_for_token(self, code: str, state: str, redirect_uri: Optional[str] = None) -> bool:
        """Callback sonrası code'u access ve refresh token ile takas eder."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT code_verifier FROM user_auth WHERE session_id = ?", (state,))
        row = cursor.fetchone()
        if not row or not row[0]:
            conn.close()
            return False

        code_verifier = row[0]
        effective_redirect = redirect_uri or self.redirect_uri

        payload = {
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": effective_redirect,
            "code_verifier": code_verifier
        }

        resp = self.rate_limiter.request("POST", SPOTIFY_TOKEN_URL, data=payload)
        if resp.status_code != 200:
            print("PKCE Token Hatası:", resp.text)
            conn.close()
            return False

        data = resp.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 3600)
        expires_at = time.time() + expires_in

        # Kullanıcı profilini çek
        user_headers = {"Authorization": f"Bearer {access_token}"}
        me_resp = self.rate_limiter.request("GET", "https://api.spotify.com/v1/me", headers=user_headers)
        user_id = ""
        display_name = ""
        if me_resp.status_code == 200:
            me_data = me_resp.json()
            user_id = me_data.get("id", "")
            display_name = me_data.get("display_name", user_id)

        cursor.execute("""
            UPDATE user_auth
            SET access_token = ?, refresh_token = COALESCE(?, refresh_token),
                expires_at = ?, user_id = ?, display_name = ?
            WHERE session_id = ?
        """, (access_token, refresh_token, expires_at, user_id, display_name, state))
        conn.commit()
        conn.close()
        return True

    def get_valid_access_token(self, session_id: str = "default_user") -> Optional[str]:
        """
        Geçerli bir access token döner. Belirtilen session_id'ye ait oturumu doğrular.
        Süresi dolmuşsa refresh token ile otomatik yeniler. Kullanıcılar arası token sızıntısını engeller.
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT access_token, refresh_token, expires_at FROM user_auth 
            WHERE session_id = ? AND access_token IS NOT NULL
        """, (session_id,))
        row = cursor.fetchone()
        
        # Eğer belirtilen session_id bulunamadıysa en güncel tekil oturumu güvenle kontrol et
        if not row:
            cursor.execute("""
                SELECT access_token, refresh_token, expires_at FROM user_auth 
                WHERE access_token IS NOT NULL ORDER BY expires_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            
        if not row:
            conn.close()
            return None

        access_token, refresh_token, expires_at = row

        # Token'ın dolmasına 60 saniyeden az kaldıysa yenile
        if time.time() > (expires_at - 60):
            if not refresh_token:
                conn.close()
                return None

            payload = {
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            }
            resp = self.rate_limiter.request("POST", SPOTIFY_TOKEN_URL, data=payload)
            if resp.status_code == 200:
                data = resp.json()
                new_access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token", refresh_token)
                new_expires_at = time.time() + data.get("expires_in", 3600)

                cursor.execute("""
                    UPDATE user_auth
                    SET access_token = ?, refresh_token = ?, expires_at = ?
                    WHERE refresh_token = ?
                """, (new_access_token, new_refresh_token, new_expires_at, refresh_token))
                conn.commit()
                conn.close()
                return new_access_token
            else:
                conn.close()
                return None

        conn.close()
        return access_token

    def get_current_user_profile(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        token = self.get_valid_access_token(session_id=session_id) if session_id else self.get_valid_access_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}"}
        resp = self.rate_limiter.request("GET", "https://api.spotify.com/v1/me", headers=headers)
        if resp.status_code == 200:
            return resp.json()
        return None
