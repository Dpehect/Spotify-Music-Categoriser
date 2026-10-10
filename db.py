import sqlite3
import os
import hashlib
from typing import Optional, Dict, Any

if os.getenv("DATABASE_PATH"):
    DB_PATH = os.environ["DATABASE_PATH"]
elif os.getenv("VERCEL"):
    # Vercel's deployed source directory is read-only. /tmp is writable but
    # ephemeral, so configure DATABASE_PATH to a durable database in production.
    DB_PATH = os.path.join("/tmp", "music_finder.db")
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "music_finder.db")

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    cursor = conn.cursor()
    
    # 1. Şarkılar tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tracks (
        spotify_id TEXT PRIMARY KEY,
        isrc TEXT,
        name TEXT NOT NULL,
        artist TEXT NOT NULL,
        album TEXT,
        release_date TEXT,
        popularity INTEGER DEFAULT 0,
        duration_ms INTEGER DEFAULT 0,
        preview_url TEXT,
        external_url TEXT,
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist_name ON tracks(artist, name)")

    # 2. Şarkı Sözü Analiz & Telifsiz Skor Tablosu
    # Telif kuralı: Şarkı sözünün tamamı ASLA saklanmaz. Sadece sha256_hash, skorlar, dil, tema ve 5-8 kelimelik alıntı saklanır.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lyrics_analysis (
        cache_key TEXT PRIMARY KEY,
        lyrics_hash TEXT NOT NULL,
        detected_lang TEXT,
        meaningful_score REAL,
        junk_ratio REAL,
        vocab_richness REAL,
        evaluation_reason TEXT,
        snippet TEXT,
        theme TEXT DEFAULT 'genel',
        algo_version TEXT DEFAULT '2.1',
        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lyrics_hash ON lyrics_analysis(lyrics_hash)")

    # Geriye dönük kolon migrasyonları (varsa eski DB yapısını korur)
    try:
        cursor.execute("ALTER TABLE lyrics_analysis ADD COLUMN theme TEXT DEFAULT 'genel'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE lyrics_analysis ADD COLUMN algo_version TEXT DEFAULT '2.1'")
    except sqlite3.OperationalError:
        pass

    # 3. Kullanıcı Oturum ve PKCE State Tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_auth (
        session_id TEXT PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT,
        expires_at REAL,
        code_verifier TEXT,
        user_id TEXT,
        display_name TEXT
    )
    """)

    # 4. Dinamik Kullanıcı Geri Bildirimi ve Sıralama Optimizasyon Tablosu (Feedback Loop)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_relevance_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_theme TEXT NOT NULL,
        query_genre TEXT NOT NULL,
        track_id TEXT NOT NULL,
        action_type TEXT NOT NULL, -- 'play_preview' (1.0), 'select' (2.0), 'export' (4.0)
        weight REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_theme_track ON user_relevance_feedback(query_theme, track_id)")

    conn.commit()
    conn.close()

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def record_feedback(query_theme: str, query_genre: str, track_id: str, action_type: str = "select"):
    weights = {"play_preview": 1.0, "select": 2.0, "export": 4.0}
    w = weights.get(action_type, 1.0)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_relevance_feedback (query_theme, query_genre, track_id, action_type, weight)
        VALUES (?, ?, ?, ?, ?)
    """, (query_theme or "all", query_genre or "all", track_id, action_type, w))
    conn.commit()
    conn.close()

def get_feedback_boost(query_theme: str, track_id: str) -> float:
    """Geçmiş kullanıcı seçimlerine göre parçaya küçük bir güven takviyesi (0.0 - 0.15) hesaplar."""
    if not query_theme or query_theme == "all":
        return 0.0
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(weight) FROM user_relevance_feedback 
        WHERE (query_theme = ? OR query_theme = 'all') AND track_id = ?
    """, (query_theme, track_id))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        total_w = float(row[0])
        import math
        return min(0.15, round(math.log1p(total_w) * 0.04, 3))
    return 0.0

def get_cached_analysis(artist: str, track_name: str) -> Optional[Dict[str, Any]]:
    cache_key = f"{artist.lower().strip()} - {track_name.lower().strip()}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT lyrics_hash, detected_lang, meaningful_score, junk_ratio, vocab_richness, evaluation_reason, snippet, theme, algo_version
        FROM lyrics_analysis WHERE cache_key = ?
    """, (cache_key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "lyrics_hash": row[0],
            "detected_lang": row[1],
            "meaningful_score": row[2],
            "junk_ratio": row[3],
            "vocab_richness": row[4],
            "evaluation_reason": row[5],
            "snippet": row[6],
            "theme": row[7] if row[7] else "genel",
            "algo_version": row[8] if len(row) > 8 else "2.1"
        }
    return None

def save_analysis(artist: str, track_name: str, lyrics_text: str, detected_lang: str,
                  meaningful_score: float, junk_ratio: float, vocab_richness: float,
                  evaluation_reason: str, snippet: str, theme: str = "genel", algo_version: str = "2.1"):
    cache_key = f"{artist.lower().strip()} - {track_name.lower().strip()}"
    l_hash = hash_text(lyrics_text)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO lyrics_analysis 
        (cache_key, lyrics_hash, detected_lang, meaningful_score, junk_ratio, vocab_richness, evaluation_reason, snippet, theme, algo_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cache_key, l_hash, detected_lang, meaningful_score, junk_ratio, vocab_richness, evaluation_reason, snippet, theme, algo_version))
    conn.commit()
    conn.close()

def save_track(track_dict: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO tracks 
        (spotify_id, isrc, name, artist, album, release_date, popularity, duration_ms, preview_url, external_url, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        track_dict.get("id"),
        track_dict.get("isrc"),
        track_dict.get("name"),
        track_dict.get("artist"),
        track_dict.get("album"),
        track_dict.get("release_date"),
        track_dict.get("popularity", 0),
        track_dict.get("duration_ms", 0),
        track_dict.get("preview_url"),
        track_dict.get("external_url"),
        track_dict.get("image_url")
    ))
    conn.commit()
    conn.close()

init_db()
