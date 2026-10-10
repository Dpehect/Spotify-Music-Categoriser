# MASTER PROMPT & COMPLETE ARCHITECTURE AUDIT — Spotify Lyrics & Semantic Music Discovery Engine v2.1 PRO

## ROLÜN VE AMACIN
Sen kıdemli bir Principal Full-Stack Engineer, Python/FastAPI Sistem Mimarı, API Güvenliği Uzmanı ve Kıdemli UI/UX Tasarım Denetçisisin (Lead Reviewer & Enterprise Architect).

Aşağıda sıfırdan geliştirdiğimiz ve çalışır durumda olan **"Spotify Şarkı Sözü (Lyrics) & Anlamsal Müzik Keşif Motoru (v2.1 PRO)"** projesinin tüm mimari kararları, veri modelleri, çözülen kritik sorunları, backend modülleri, HTML arayüzü ve JavaScript kodları eksiksiz, tek parça olarak yer almaktadır.

Lütfen bu sistemi mimari kalite, API rate limit & hata toleransı, telif hakları uyumluluğu, Spotify güncel kısıtları, UI/UX deneyimi ve kurumsal üretim (Enterprise Production) seviyesine geçiş açısından kapsamlı şekilde incele ve profesyonelleştirme önerilerini sun.

================================================================================
1. PROJE ÖZETİ, HİKAYESİ VE KRİTİK YASAL/TEKNİK KISITLAR
================================================================================

1. Temel İşlev:
   - Kullanıcı şarkı adı veya sanatçı bilmese dahi şarkıda geçen söz/dize, müzik kategorisi, alt tür, dönem/yıl ve anlam kalitesine göre şarkı bulur.
   - Bulunan şarkıları PKCE OAuth ile doğrudan kendi Spotify profiline yeni çalma listesi (playlist) olarak aktarır.

2. Spotify API Kısıtları & Uyumluluk:
   - Spotify Web API'de `/v1/search` endpoint'i tek seferlik çağrılarda maksimum 10 limit kabul eder (fazlası 400 hatası verir). Bu kurala tam uyumlu sayfalama (pagination) kullanılır.
   - Spotify'ın yeni uygulamalara kapattığı `recommendations`, `audio-features`, `audio-analysis` ve `related-artists` endpoint'leri KESİNLİKLE KULLANILMAZ.
   - Bunun yerine yerel metaveri analizine dayanan `similarity_engine.py` geliştirilmiştir.

3. Söz Kaynakları Fallback Zinciri & Telif Güvencesi:
   - Spotify API şarkı sözü sağlamaz. Sözler sırasıyla: LRCLIB (açık kaynak/ücretsiz) -> SyncedLyrics (Musixmatch/Deezer) -> WebGeniusFallback zincirinden çekilir.
   - Telif Yasaları Gereği: Şarkı sözlerinin tam metni sunucuda veya veritabanında ASLA saklanmaz. DB'de yalnızca `lyrics_hash` (SHA-256), sayısal analiz skorları, dil, tema ve maksimum 5-8 kelimelik alıntı (`snippet`) tutulur.

4. Çözülen P0/P1 Hatalar:
   - ISRC Kirlenmesi Çözüldü: Spotify track ID'sinin ISRC olarak atanması iptal edildi; ISRC ve Spotify ID ayrı tutuldu.
   - Cache `_is_passed` Mantık Hatası Çözüldü: Önbellekten okunan kayıtlarda `meaningful_score`, `strictness` ve `target_theme` parametreleri anlık olarak yeniden doğrulanıyor; sahte `True` varsayılanı kaldırıldı.
   - Hata İzolasyonu: ThreadPoolExecutor içinde tek bir şarkının analiz hatası vermesi durumunda tüm aramanın düşmesi engellendi; her parça için `analiz_bekliyor`, `tamamlandi`, `soz_bulunamadi`, `hata` durum rozetleri sağlandı.
   - Rate Limiter & Circuit Breaker: 429 Retry-After, geçici 5xx üstel geri çekilme, 5.0s timeout ve 5 ardışık hatada 30 saniyelik devre kesici eklendi.
   - Dürüst Tür Etiketleri: `genre_matcher.py` artık `Doğrulandı` (%95), `Olası Eşleşme` (%75) ve `Belirsiz` (%50) etiketleri üretir.
   - Faz 2 Arayüz Geliştirmeleri: 6 modlu dinamik sıralama çubuğu, açılır (accordion) 4 bileşenli analiz kartı, tek tıkla "✨ Benzer" şarkı önerme motoru, 30 sn ses önizleme oynatıcısı ve mobil uyumlu sticky butonlar entegre edildi.
   - Test Kapsamı: 13/13 birim ve regresyon testi (`test_suite.py`) eksiksiz geçmektedir.

================================================================================
2. VERİTABANI ŞEMASI (SQLite - db.py)
================================================================================

```sql
CREATE TABLE IF NOT EXISTS tracks (
    spotify_id TEXT PRIMARY KEY,
    isrc TEXT,
    name TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    release_date TEXT,
    popularity INTEGER,
    duration_ms INTEGER,
    preview_url TEXT,
    external_url TEXT,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TABLE IF NOT EXISTS user_auth (
    session_id TEXT PRIMARY KEY,
    access_token TEXT,
    refresh_token TEXT,
    expires_at REAL,
    code_verifier TEXT,
    user_id TEXT,
    display_name TEXT
);
```

================================================================================
3. ÇEKİRDEK BACKEND MODÜLLERİ (KODLAR)
================================================================================

--- [rate_limiter.py] ---
import time, requests

class SpotifyRateLimiter:
    """
    Dayanıklı Rate Limit (429) & Hata Koruyucusu (Circuit Breaker & Exponential Backoff)
    """
    def __init__(self, max_retries: int = 3, base_backoff: float = 1.0, timeout: float = 5.0):
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.timeout = timeout
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        now = time.time()
        if now < self.circuit_open_until:
            raise requests.exceptions.RequestException(f"Circuit breaker açık: {url} geçici olarak askıya alındı.")

        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        retries, backoff = 0, self.base_backoff
        while retries <= self.max_retries:
            try:
                response = requests.request(method, url, **kwargs)
            except requests.exceptions.Timeout:
                retries += 1
                if retries > self.max_retries:
                    self._record_failure()
                    raise
                time.sleep(backoff)
                backoff *= 1.5
                continue
            except requests.exceptions.RequestException as e:
                self._record_failure()
                raise e

            if response.status_code == 429:
                self._record_failure()
                retry_after = response.headers.get("Retry-After")
                wait_time = int(retry_after) + 0.5 if retry_after and retry_after.isdigit() else backoff
                time.sleep(min(wait_time, 15.0))
                retries += 1
                backoff *= 2
                continue

            if 500 <= response.status_code < 600:
                self._record_failure()
                retries += 1
                if retries <= self.max_retries:
                    time.sleep(backoff)
                    backoff *= 1.5
                    continue
                return response

            self.consecutive_failures = 0
            return response
        return response

    def _record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= 5:
            self.circuit_open_until = time.time() + 30.0

--- [deduplication.py] ---
import re

VERSION_PATTERNS = [
    (r'(?i)\b(radio\s+edit|radio\s+version)\b', 'radio_edit'),
    (r'(?i)\b(remaster(ed)?(\s+\d{4})?)\b', 'remaster'),
    (r'(?i)\b(remix|rmx)\b', 'remix'),
    (r'(?i)\b(live(\s+at|\s+version|\s+\d{4})?)\b', 'live'),
    (r'(?i)\b(instrumental|enstrümantal|beat)\b', 'instrumental'),
    (r'(?i)\b(karaoke)\b', 'karaoke'),
    (r'(?i)\b(acoustic|akustik)\b', 'acoustic'),
    (r'(?i)\b(clean(\s+version)?)\b', 'clean'),
    (r'(?i)\b(explicit(\s+version)?)\b', 'explicit'),
]

def clean_song_title(title: str) -> tuple[str, list[str]]:
    detected_versions = []
    clean = title
    for pattern, tag in VERSION_PATTERNS:
        if re.search(pattern, clean):
            detected_versions.append(tag)
            clean = re.sub(pattern, '', clean)
    clean = re.sub(r'[\(\[\{][^\)\]\}]*[\)\]\}]', '', clean)
    clean = re.sub(r'[-–—:]+', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip().lower()
    return clean, detected_versions

def deduplicate_tracks(
    tracks: list[dict],
    preferred_version: str = "original",
    allow_instrumental: bool = False
) -> list[dict]:
    seen_isrcs = set()
    cleaned_candidates = []

    for track in tracks:
        raw_name = track.get("name", "")
        norm_title, tags = clean_song_title(raw_name)
        if not allow_instrumental and any(t in tags for t in ["instrumental", "karaoke"]):
            continue
        track["_detected_tags"] = tags
        track["_norm_title"] = norm_title
        cleaned_candidates.append(track)

    grouped_tracks = {}
    for track in cleaned_candidates:
        primary_artist = track.get("artist", "").split(",")[0].strip().lower()
        norm_title = track.get("_norm_title", "")
        key = (norm_title, primary_artist)
        if key not in grouped_tracks:
            grouped_tracks[key] = []
        grouped_tracks[key].append(track)

    final_tracks = []
    for key, candidate_list in grouped_tracks.items():
        best_track = candidate_list[0]
        if len(candidate_list) > 1 and preferred_version != "any":
            for cand in candidate_list:
                tags = cand.get("_detected_tags", [])
                if preferred_version in tags:
                    best_track = cand
                    break
                elif preferred_version == "original" and len(tags) == 0:
                    best_track = cand
                    break

        track_isrc = best_track.get("isrc")
        if track_isrc and track_isrc != best_track.get("id"):
            if track_isrc.upper() in seen_isrcs:
                continue
            seen_isrcs.add(track_isrc.upper())

        final_tracks.append(best_track)

    return final_tracks

--- [meaningful_engine.py] ---
import re
from typing import Dict, Any, List
from langdetect import detect

JUNK_ADLIBS = [
    r"\bgrr+\b", r"\bskr+t\b", r"\bpaw+\b", r"\bbrr+\b", r"\byeah yeah\b",
    r"\blil\b", r"\baye aye\b", r"\buh uh\b", r"\bla la la\b", r"\bpew pew\b",
    r"\bgucci\b", r"\bprada\b", r"\bbalenciaga\b", r"\blouis vuitton\b",
    r"\brolex\b", r"\bversace\b", r"\blambo\b", r"\bferrari\b", r"\bmaybach\b"
]

THEMES = {
    "sokak": ["sokak", "mahalle", "köşe", "kaldırım", "getto", "varoş", "gecekondu", "polis", "semt"],
    "aşk": ["aşk", "sevgi", "özlem", "kalp", "ayrılık", "hasret", "gözlerin", "gülüm", "sevgilim"],
    "dert": ["dert", "hüzün", "keder", "acı", "çile", "efkar", "karanlık", "yalnızlık", "gözyaşı"],
    "toplumsal": ["düzen", "sistem", "adalet", "baskı", "özgürlük", "halk", "emek", "isyan", "yoksulluk"],
    "motivasyon": ["başarı", "zirve", "çaba", "mücadele", "asla pes", "zafer", "kazanmak", "yükseliş"],
    "nostalji": ["eski", "mazi", "geçmiş", "çocukluk", "hatıra", "zaman", "anılar", "yıllar"]
}

PROFANITY_WORDS = [
    r"\bsik\b", r"\borospu\b", r"\bpiç\b", r"\bamk\b", r"\baq\b", r"\byarrak\b",
    r"\bgöt\b", r"\bfuck\b", r"\bbitch\b", r"\bshit\b", r"\bass\b", r"\bdick\b"
]

def detect_lyrics_language(lyrics_text: str) -> str:
    try:
        sample = "\n".join([line for line in lyrics_text.splitlines() if len(line.strip()) > 15][:5])
        if sample:
            return detect(sample)
    except Exception:
        pass
    return "unknown"

def analyze_lyrics_comprehensive(
    lyrics_text: str, 
    strictness: str = "balanced", 
    profanity_mode: str = "all", 
    target_theme: str = "all"
) -> Dict[str, Any]:
    if not lyrics_text or len(lyrics_text.strip()) < 50:
        return {
            "score": 20.0, "is_passed": False, "reason": "Sözler çok kısa veya arşivde bulunamadı",
            "theme": "belirsiz", "profanity_count": 0, "detected_lang": "unknown",
            "components": {"vocab_diversity": 20.0, "repetition": 20.0, "adlib_cleanliness": 100.0, "theme_depth": 0.0}
        }

    text_lower = lyrics_text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = len(words)
    if total_words < 25:
        return {
            "score": 30.0, "is_passed": False, "reason": "Yetersiz kelime sayısı",
            "theme": "belirsiz", "profanity_count": 0, "detected_lang": "unknown",
            "components": {"vocab_diversity": 30.0, "repetition": 30.0, "adlib_cleanliness": 100.0, "theme_depth": 0.0}
        }

    detected_lang = detect_lyrics_language(lyrics_text)

    junk_count = sum(len(re.findall(pat, text_lower)) for pat in JUNK_ADLIBS)
    junk_ratio = junk_count / total_words
    adlib_score = max(0.0, min(100.0, round(100.0 - (junk_ratio * 1000.0), 1)))

    unique_words = len(set(words))
    vocab_richness = unique_words / total_words
    vocab_score = max(10.0, min(100.0, round((vocab_richness / 0.55) * 100.0, 1)))

    lines = [l.strip() for l in text_lower.splitlines() if len(l.strip()) > 5]
    total_lines = len(lines)
    unique_lines = len(set(lines))
    line_diversity = (unique_lines / total_lines) if total_lines > 0 else 1.0
    line_score = max(10.0, min(100.0, round((line_diversity / 0.85) * 100.0, 1)))

    profanity_count = sum(len(re.findall(p, text_lower)) for p in PROFANITY_WORDS)

    theme_scores = {}
    for theme_name, keywords in THEMES.items():
        cnt = sum(len(re.findall(r'\b' + re.escape(k) + r'\b', text_lower)) for k in keywords)
        theme_scores[theme_name] = cnt
    
    top_theme_cnt = max(theme_scores.values()) if theme_scores else 0
    detected_theme = max(theme_scores, key=theme_scores.get) if top_theme_cnt > 0 else "genel"
    theme_depth_score = min(100.0, round(top_theme_cnt * 20.0, 1))

    score = (vocab_score * 0.40) + (line_score * 0.30) + (adlib_score * 0.20) + (theme_depth_score * 0.10)
    score = max(5.0, min(99.0, round(score, 1)))

    thresholds = {"loose": 40.0, "balanced": 60.0, "strict": 75.0}
    required_score = thresholds.get(strictness, 60.0)

    is_passed = (score >= required_score)
    reason_parts = []
    if junk_ratio > 0.04: reason_parts.append(f"Yüksek ad-lib/marka oranı (%{int(junk_ratio*100)})")
    if vocab_richness > 0.40: reason_parts.append("Zengin kelime haznesi")
    if line_diversity > 0.75: reason_parts.append("Düşük nakarat tekrarı")
    if detected_theme != "genel": reason_parts.append(f"Tema: {detected_theme.capitalize()}")

    if profanity_mode == "clean" and profanity_count > 0:
        is_passed = False
        reason_parts.append(f"Temiz mod: {profanity_count} argo ifade elendi")
    elif profanity_mode == "moderate" and profanity_count > 3:
        is_passed = False
        reason_parts.append(f"Orta mod eşiği aşıldı ({profanity_count} küfür)")

    if target_theme != "all" and detected_theme != target_theme:
        is_passed = False
        reason_parts.append(f"Tema uyuşmazlığı ({target_theme})")

    final_reason = ", ".join(reason_parts) if reason_parts else ("Yüksek söz yapısı kalitesi" if is_passed else "Standart söz kalitesi")

    return {
        "score": score, "is_passed": bool(is_passed), "reason": final_reason,
        "theme": detected_theme, "profanity_count": profanity_count, "detected_lang": detected_lang,
        "vocab_richness": round(vocab_richness, 3), "junk_ratio": round(junk_ratio, 3),
        "components": {
            "vocab_diversity": vocab_score, "repetition": line_score,
            "adlib_cleanliness": adlib_score, "theme_depth": theme_depth_score
        }
    }

--- [genre_matcher.py] ---
import re
from typing import List, Dict, Any, Tuple
from taxonomy import CATEGORIES

CATEGORY_TAG_MAP = {
    "hiphop_rap": ["hip-hop", "rap", "trap", "drill", "underground rap", "boom bap", "türkçe rap", "turkce rap"],
    "rock_metal": ["rock", "metal", "alternative", "punk", "grunge", "anadolu rock", "hard rock", "indie rock"],
    "pop": ["pop", "synth-pop", "dance-pop", "türkçe pop", "turkce pop", "electropop"],
    "electronic_dance": ["electronic", "edm", "house", "techno", "dance", "club", "trance"],
    "rnb_soul": ["r&b", "rnb", "soul", "funk", "groove"],
    "acoustic_chill": ["acoustic", "chill", "lo-fi", "ambient", "folk", "akustik"],
    "jazz_blues": ["jazz", "blues", "bossa nova"],
    "latin_reggae": ["latin", "reggae", "reggaeton", "salsa", "afrobeat"],
    "classical_soundtrack": ["classical", "soundtrack", "ost", "orchestral", "piano"],
    "traditional_folk": ["folk", "türkü", "turku", "etnik", "anadolu"]
}

def calculate_genre_match_score(
    track_item: Dict[str, Any],
    selected_category: str = "all",
    selected_genres: List[str] = None
) -> Tuple[float, str]:
    if selected_category == "all" and (not selected_genres or "Tümü" in selected_genres):
        return 1.0, "Genel Uyumlu"

    album_name = (track_item.get("album", "") or "").lower()
    track_name = (track_item.get("name", "") or "").lower()
    artist_name = (track_item.get("artist", "") or "").lower()
    combined_text = f"{album_name} {track_name} {artist_name}"

    target_keywords = set()
    if selected_category != "all" and selected_category in CATEGORY_TAG_MAP:
        target_keywords.update(CATEGORY_TAG_MAP[selected_category])

    if selected_genres:
        for g in selected_genres:
            if g != "Tümü":
                target_keywords.add(g.replace("-", " ").lower())

    matched_keywords = []
    for kw in target_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', combined_text):
            matched_keywords.append(kw)

    if matched_keywords:
        return 0.95, f"Doğrulandı ({matched_keywords[0].title()})"

    if track_item.get("_sourced_from_genre_query"):
        return 0.75, "Olası Eşleşme"

    return 0.50, "Belirsiz"

--- [track_sorting.py] ---
import random
from typing import List, Dict, Any

def sort_tracks(tracks: List[Dict[str, Any]], sort_by: str = "relevance") -> List[Dict[str, Any]]:
    sorted_list = list(tracks)
    if sort_by == "meaningful_score":
        sorted_list.sort(key=lambda x: (x.get("analysis_status") == "tamamlandi", x.get("meaningful_score") if x.get("meaningful_score") is not None else -1), reverse=True)
    elif sort_by == "lyrics_match":
        sorted_list.sort(key=lambda x: (x.get("match_score") or 0, bool(x.get("snippet"))), reverse=True)
    elif sort_by == "genre_match":
        sorted_list.sort(key=lambda x: (x.get("genre_match_score") or 0), reverse=True)
    elif sort_by == "popularity":
        sorted_list.sort(key=lambda x: (x.get("popularity") or 0), reverse=True)
    elif sort_by == "newest":
        sorted_list.sort(key=lambda x: (x.get("release_date") or ""), reverse=True)
    elif sort_by == "random":
        random.shuffle(sorted_list)
    else: # relevance
        sorted_list.sort(key=lambda x: (x.get("analysis_status") == "tamamlandi", x.get("meaningful_score") or 0, (x.get("genre_match_score") or 0.5) * 20, (x.get("popularity") or 0) * 0.1), reverse=True)
    return sorted_list

--- [similarity_engine.py] ---
from typing import Dict, Any, List

def calculate_similarity(track_a: Dict[str, Any], track_b: Dict[str, Any]) -> Dict[str, Any]:
    theme_a = track_a.get("theme", "genel")
    theme_b = track_b.get("theme", "genel")
    if theme_a == theme_b and theme_a != "genel":
        theme_sim = 100.0
    elif theme_a == theme_b and theme_a == "genel":
        theme_sim = 60.0
    else:
        theme_sim = 20.0

    score_a = track_a.get("meaningful_score") or 50.0
    score_b = track_b.get("meaningful_score") or 50.0
    vocab_sim = max(0.0, 100.0 - (abs(score_a - score_b) * 2.5))

    lang_a = track_a.get("detected_lang", "unknown")
    lang_b = track_b.get("detected_lang", "unknown")
    if lang_a == lang_b and lang_a != "unknown":
        lang_sim = 100.0
    elif lang_a == "unknown" or lang_b == "unknown":
        lang_sim = 50.0
    else:
        lang_sim = 0.0

    artist_a = track_a.get("artist", "").lower()
    artist_b = track_b.get("artist", "").lower()
    if any(art.strip() in artist_b for art in artist_a.split(",") if len(art.strip()) > 2):
        genre_sim = 95.0
    else:
        genre_diff = abs(track_a.get("genre_match_score", 0.5) - track_b.get("genre_match_score", 0.5))
        genre_sim = max(30.0, 100.0 - (genre_diff * 100.0))

    overall_score = round(max(0.0, min(100.0, (theme_sim * 0.35) + (vocab_sim * 0.25) + (lang_sim * 0.20) + (genre_sim * 0.20))), 1)

    return {
        "overall_similarity": overall_score,
        "theme_similarity": theme_sim,
        "vocab_similarity": round(vocab_sim, 1),
        "language_similarity": lang_sim,
        "genre_similarity": round(genre_sim, 1)
    }

def find_similar_tracks(target_track: Dict[str, Any], candidate_pool: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    target_id = target_track.get("id")
    target_name = target_track.get("name", "").lower()
    scored = []
    for cand in candidate_pool:
        if cand.get("id") == target_id or cand.get("name", "").lower() == target_name:
            continue
        sim = calculate_similarity(target_track, cand)
        cand_copy = dict(cand)
        cand_copy["similarity_info"] = sim
        scored.append(cand_copy)
    scored.sort(key=lambda x: x["similarity_info"]["overall_similarity"], reverse=True)
    return scored[:limit]

--- [search_pipeline.py] ---
import os, concurrent.futures, spotipy
from typing import List, Dict, Any, Optional
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

from lyrics_providers import LyricsManager
from text_nlp import parse_boolean_query, extract_match_snippet
from meaningful_engine import analyze_lyrics_comprehensive
from deduplication import deduplicate_tracks
from genre_matcher import calculate_genre_match_score
from db import get_cached_analysis, save_analysis, save_track
from pkce_auth import SpotifyPKCEAuthManager
from rate_limiter import SpotifyRateLimiter
from track_sorting import sort_tracks
from taxonomy import CATEGORIES

load_dotenv()

class SearchPipelineEngine:
    def __init__(self):
        self.client_id = os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        self.rate_limiter = SpotifyRateLimiter()
        self.lyrics_manager = LyricsManager()
        self.pkce_auth = SpotifyPKCEAuthManager(client_id=self.client_id)
        self.sp = None
        self._init_spotify_client()

    def _init_spotify_client(self):
        if self.client_id and self.client_secret and "buraya_" not in self.client_id:
            try:
                auth = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
                self.sp = spotipy.Spotify(auth_manager=auth)
            except Exception as e:
                print("Spotify ClientCredentials init error:", e)

    def is_authenticated(self) -> bool:
        if not self.sp: return False
        try:
            self.sp.search(q="test", limit=1, type="track")
            return True
        except Exception: return False

    def search_tracks(
        self, lyrics_query="", language="all", category="all", genres=None,
        year_start=1990, year_end=2026, popularity_min=0, popularity_max=100,
        strictness="balanced", profanity_mode="all", target_theme="all",
        filter_meaningful=True, preferred_version="original", allow_instrumental=False,
        sort_by="relevance", limit=20
    ) -> Dict[str, Any]:
        genres = genres or []
        clean_lyrics = lyrics_query.strip()
        parsed_boolean = parse_boolean_query(clean_lyrics) if clean_lyrics else None
        raw_candidates, seen_ids = [], set()

        stats = {
            "total_candidates": 0, "eliminated_no_lyrics": 0, "eliminated_genre_mismatch": 0,
            "eliminated_meaningful_filter": 0, "eliminated_duplicate_version": 0, "eliminated_language_mismatch": 0
        }

        def add_candidate(item: dict, snippet: str = None, match_score: float = 1.0, is_genre_sourced: bool = False):
            if not item: return
            t_id = item.get("id")
            if t_id in seen_ids: return
            pop = item.get("popularity", 0)
            if not (popularity_min <= pop <= popularity_max): return
            seen_ids.add(t_id)

            ext_ids = item.get("external_ids", {})
            isrc = ext_ids.get("isrc") # Spotify track ID ASLA ISRC'ye atanmaz
            album_images = item.get("album", {}).get("images", [])
            image_url = album_images[0]["url"] if album_images else None

            track_data = {
                "id": t_id, "spotify_track_id": t_id, "isrc": isrc, "uri": item.get("uri"),
                "name": item.get("name"), "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
                "album": item.get("album", {}).get("name", ""), "release_date": item.get("album", {}).get("release_date", ""),
                "popularity": pop, "duration_ms": item.get("duration_ms", 0), "preview_url": item.get("preview_url"),
                "external_url": item.get("external_urls", {}).get("spotify", ""), "image_url": image_url,
                "snippet": snippet, "match_score": match_score, "analysis_status": "analiz_bekliyor",
                "meaningful_score": None, "meaningful_reason": None, "genre_match_score": 1.0, "genre_badge": "Uyumlu",
                "theme": "genel", "detected_lang": "unknown", "_sourced_from_genre_query": is_genre_sourced
            }
            save_track(track_data)
            raw_candidates.append(track_data)

        # 1. Söz Sağlayıcıları
        if clean_lyrics:
            main_phrase = (parsed_boolean["exact_phrases"] or [clean_lyrics])[0]
            for hit in self.lyrics_manager.search_by_phrase(main_phrase, lang=language, limit=limit * 2):
                q = f"{hit['artist']} {hit['title']}".strip()
                if q:
                    try:
                        res = self.sp.search(q=q, type="track", limit=2)
                        for item in res.get("tracks", {}).get("items", []):
                            snip = hit.get("snippet") or extract_match_snippet(clean_lyrics, hit.get("snippet", ""))
                            add_candidate(item, snippet=snip, match_score=0.95, is_genre_sourced=False)
                    except Exception: pass

        # 2. Spotify Aday Havuzu (En az limit*3)
        query_parts, is_genre_query = [], False
        if clean_lyrics: query_parts.append(clean_lyrics)
        if genres and "Tümü" not in genres:
            is_genre_query = True
            for g in genres[:2]: query_parts.append(g.replace("-", " ") if "-" in g and "turkish" in g else f'genre:"{g}"')
        elif category and category != "all":
            is_genre_query = True
            for cat in CATEGORIES:
                if cat["id"] == category and cat.get("genres"):
                    fg = cat["genres"][0]
                    query_parts.append(f'turkish {fg}' if language == "tr" and "turkish" not in fg else f'genre:"{fg}"')
                    break
        if year_start and year_end and not (year_start == 1990 and year_end == 2026):
            query_parts.append(f'year:{year_start}-{year_end}')

        final_q = " ".join(query_parts).strip() or ("turkish 2024" if language == "tr" else "year:2024")
        offset = 0
        while len(raw_candidates) < max(limit * 3, 30) and offset <= 40:
            try:
                items = self.sp.search(q=final_q, type="track", limit=10, offset=offset).get("tracks", {}).get("items", [])
                if not items: break
                for it in items: add_candidate(it, match_score=0.80, is_genre_sourced=is_genre_query)
                offset += 10
            except Exception: break

        stats["total_candidates"] = len(raw_candidates)

        # 3. Tekilleştirme & Tür Uyumu
        deduped = deduplicate_tracks(raw_candidates, preferred_version=preferred_version, allow_instrumental=allow_instrumental)
        stats["eliminated_duplicate_version"] = len(raw_candidates) - len(deduped)

        genre_filtered = []
        for track in deduped:
            g_score, g_badge = calculate_genre_match_score(track, selected_category=category, selected_genres=genres)
            track["genre_match_score"], track["genre_badge"] = g_score, g_badge
            if category != "all" and g_score < 0.65:
                stats["eliminated_genre_mismatch"] += 1
                continue
            genre_filtered.append(track)

        # 4. Paralel Söz Analizi
        def process_track_lyrics(track):
            artist, name = track["artist"], track["name"]
            cached = get_cached_analysis(artist, name)
            if cached:
                cached_score = cached["meaningful_score"]
                thresholds = {"loose": 40.0, "balanced": 60.0, "strict": 75.0}
                required_score = thresholds.get(strictness, 60.0)
                cached_is_passed = (cached_score is not None and cached_score >= required_score)
                cached_theme = cached.get("theme", "genel")
                if target_theme != "all" and cached_theme != target_theme:
                    cached_is_passed = False

                track.update({
                    "analysis_status": "tamamlandi", "meaningful_score": cached_score,
                    "meaningful_reason": cached["evaluation_reason"], "detected_lang": cached["detected_lang"],
                    "theme": cached_theme, "vocab_richness": cached.get("vocab_richness"),
                    "junk_ratio": cached.get("junk_ratio"), "_is_passed": cached_is_passed,
                    "snippet": track.get("snippet") or cached.get("snippet")
                })
                return track

            try:
                raw_lyrics = self.lyrics_manager.get_lyrics(artist, name)
                if not raw_lyrics or len(raw_lyrics.strip()) < 30:
                    track.update({"analysis_status": "soz_bulunamadi", "meaningful_score": None, "meaningful_reason": "Söz arşivlerinde bulunamadı", "_is_passed": False})
                    return track

                analysis = analyze_lyrics_comprehensive(raw_lyrics, strictness=strictness, profanity_mode=profanity_mode, target_theme=target_theme)
                snip = track.get("snippet") or extract_match_snippet(clean_lyrics or name, raw_lyrics)

                save_analysis(
                    artist=artist, track_name=name, lyrics_text=raw_lyrics, detected_lang=analysis["detected_lang"],
                    meaningful_score=analysis["score"], junk_ratio=analysis["junk_ratio"], vocab_richness=analysis["vocab_richness"],
                    evaluation_reason=analysis["reason"], snippet=snip, theme=analysis["theme"], algo_version="2.1"
                )

                track.update({
                    "analysis_status": "tamamlandi", "meaningful_score": analysis["score"],
                    "meaningful_reason": analysis["reason"], "detected_lang": analysis["detected_lang"],
                    "theme": analysis["theme"], "vocab_richness": analysis["vocab_richness"],
                    "junk_ratio": analysis["junk_ratio"], "components": analysis.get("components", {}),
                    "_is_passed": bool(analysis["is_passed"]), "snippet": snip
                })
                return track
            except Exception:
                track.update({"analysis_status": "hata", "meaningful_score": None, "meaningful_reason": "Analiz sırasında teknik bir hata oluştu", "_is_passed": False})
                return track

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            analyzed = list(executor.map(process_track_lyrics, genre_filtered))

        # 5. Filtreler
        final_tracks = []
        for track in analyzed:
            if language != "all" and track.get("detected_lang") not in ["unknown", language]:
                stats["eliminated_language_mismatch"] += 1; continue
            if clean_lyrics and track["analysis_status"] == "soz_bulunamadi":
                stats["eliminated_no_lyrics"] += 1; continue
            if filter_meaningful and track["analysis_status"] == "tamamlandi":
                if track.get("_is_passed") is not True:
                    stats["eliminated_meaningful_filter"] += 1; continue
            final_tracks.append(track)

        # 6. Dinamik Sıralama
        final_tracks = sort_tracks(final_tracks, sort_by=sort_by)

        return {"tracks": final_tracks[:limit], "stats": {"requested_limit": limit, "found_count": len(final_tracks[:limit]), **stats}}

    def create_playlist_pkce(self, name: str, track_uris: List[str], description: str = "") -> Dict[str, Any]:
        token = self.pkce_auth.get_valid_access_token()
        if not token: raise Exception("Kullanıcı oturumu bulunamadı.")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        me_resp = self.rate_limiter.request("GET", "https://api.spotify.com/v1/me", headers=headers)
        if me_resp.status_code != 200: raise Exception(f"Profil alınamadı: {me_resp.text}")
        user_id = me_resp.json()["id"]

        pl_resp = self.rate_limiter.request("POST", f"https://api.spotify.com/v1/users/{user_id}/playlists", json={"name": name, "public": True, "description": description}, headers=headers)
        if pl_resp.status_code not in [200, 201]: raise Exception(f"Çalma listesi oluşturulamadı: {pl_resp.text}")
        pl_data = pl_resp.json()
        playlist_id, playlist_url = pl_data["id"], pl_data.get("external_urls", {}).get("spotify", "")

        unique_uris = list(dict.fromkeys(track_uris))
        for i in range(0, len(unique_uris), 100):
            chunk = unique_uris[i:i + 100]
            self.rate_limiter.request("POST", f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", json={"uris": chunk}, headers=headers)

        return {"id": playlist_id, "name": name, "url": playlist_url, "track_count": len(unique_uris)}

--- [web_app.py] ---
import os, secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
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

class SearchRequest(BaseModel):
    lyrics_query: Optional[str] = ""
    language: Optional[str] = "all"
    category: Optional[str] = "all"
    genres: Optional[List[str]] = []
    year_start: Optional[int] = 1990
    year_end: Optional[int] = 2026
    popularity_min: Optional[int] = 0
    popularity_max: Optional[int] = 100
    strictness: Optional[str] = "balanced"
    profanity_mode: Optional[str] = "all"
    target_theme: Optional[str] = "all"
    filter_meaningful: Optional[bool] = True
    preferred_version: Optional[str] = "original"
    allow_instrumental: Optional[bool] = False
    sort_by: Optional[str] = "relevance"
    limit: Optional[int] = 20

class SimilarRequest(BaseModel):
    target_track: dict
    candidate_pool: List[dict]
    limit: Optional[int] = 5

class SortRequest(BaseModel):
    tracks: List[dict]
    sort_by: str = "relevance"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login():
    state = secrets.token_urlsafe(16)
    auth_url, _ = engine.pkce_auth.get_authorize_url(state=state)
    return RedirectResponse(auth_url)

@app.get("/callback")
async def callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    if code and state and engine.pkce_auth.exchange_code_for_token(code=code, state=state):
        return RedirectResponse("/?auth=success")
    return RedirectResponse("/?error=auth_failed")

@app.get("/api/status")
async def get_status():
    return {
        "has_credentials": engine.is_authenticated(),
        "is_user_authenticated": engine.pkce_auth.get_current_user_profile() is not None,
        "user_profile": engine.pkce_auth.get_current_user_profile()
    }

@app.get("/api/taxonomy")
async def get_taxonomy():
    return {"languages": LANGUAGES, "categories": CATEGORIES, "genres": ALL_GENRES}

@app.post("/api/search")
async def search_endpoint(req: SearchRequest):
    return engine.search_tracks(
        lyrics_query=req.lyrics_query or "", language=req.language or "all", category=req.category or "all",
        genres=req.genres or [], year_start=req.year_start or 1990, year_end=req.year_end or 2026,
        strictness=req.strictness or "balanced", profanity_mode=req.profanity_mode or "all",
        target_theme=req.target_theme or "all", filter_meaningful=bool(req.filter_meaningful),
        preferred_version=req.preferred_version or "original", allow_instrumental=bool(req.allow_instrumental),
        sort_by=req.sort_by or "relevance", limit=req.limit or 20
    )

@app.post("/api/sort-tracks")
async def sort_tracks_endpoint(req: SortRequest):
    return {"tracks": sort_tracks(req.tracks, sort_by=req.sort_by)}

@app.post("/api/find-similar")
async def find_similar_endpoint(req: SimilarRequest):
    return {"similar_tracks": find_similar_tracks(req.target_track, req.candidate_pool, limit=req.limit or 5)}

@app.post("/api/create-playlist")
async def create_playlist_endpoint(req: dict):
    res = engine.create_playlist_pkce(name=req["name"], track_uris=req["track_uris"], description=req.get("description", ""))
    return {"success": True, **res}

if __name__ == "__main__":
    uvicorn.run("web_app:app", host="0.0.0.0", port=3001, reload=True)

================================================================================
4. ARAYÜZ (HTML & JAVASCRIPT) KODLARI
================================================================================

--- [templates/index.html] ---
<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Spotify Şarkı Sözü & Anlamsal Müzik Keşif Motoru 2.1 PRO</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            spotify: { green: '#1DB954', hoverGreen: '#1ed760', dark: '#121212', card: '#181818', textGray: '#b3b3b3' }
          }
        }
      }
    }
  </script>
</head>
<body class="bg-[#121212] text-white min-h-screen flex flex-col font-sans antialiased selection:bg-spotify-green selection:text-black">
  <header class="border-b border-[#282828] bg-[#181818]/90 backdrop-blur sticky top-0 z-40 px-6 py-3.5 flex items-center justify-between">
    <div class="flex items-center space-x-3.5">
      <div class="w-10 h-10 rounded-full bg-spotify-green flex items-center justify-center text-black shadow-lg shadow-green-500/20">
        <i class="fa-brands fa-spotify text-2xl"></i>
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h1 class="text-lg font-bold tracking-tight">Spotify Şarkı Sözü & Keşif Motoru</h1>
          <span class="text-[10px] bg-spotify-green/20 text-spotify-green border border-spotify-green/40 px-2 py-0.5 rounded-full font-bold">v2.1 PRO</span>
        </div>
        <p class="text-xs text-spotify-textGray">LRCLIB/Genius Söz Motoru • PKCE OAuth • Anti-Mumble Analizörü</p>
      </div>
    </div>
    <div class="flex items-center space-x-3">
      <div id="userProfileBadge" class="flex items-center space-x-2 bg-[#242424] px-3.5 py-1.5 rounded-full text-sm border border-[#333]">
        <span class="w-2.5 h-2.5 rounded-full bg-gray-500" id="userStatusDot"></span>
        <span id="userStatusText" class="text-xs text-gray-300">Durum Kontrol Ediliyor...</span>
      </div>
      <button onclick="openApiModal()" class="text-xs bg-[#242424] hover:bg-[#333] text-gray-200 px-3 py-2 rounded-xl transition border border-[#383838] flex items-center space-x-1.5">
        <i class="fa-solid fa-key"></i>
        <span>API Ayarları</span>
      </button>
    </div>
  </header>

  <div class="bg-[#161616] border-b border-[#242424] px-6 py-3">
    <div class="max-w-7xl mx-auto flex flex-col sm:flex-row items-center gap-2.5">
      <div class="flex items-center gap-2 text-xs text-spotify-green font-bold shrink-0">
        <i class="fa-solid fa-wand-magic-sparkles"></i>
        <span>Doğal Dil Arama:</span>
      </div>
      <div class="relative flex-1 w-full">
        <input type="text" id="nlInput" placeholder="Örn: 90'lar Türkçe rap, sokak hikâyesi anlatan, küfürsüz..." 
               class="w-full bg-[#202020] border border-[#333] rounded-xl pl-9 pr-24 py-1.5 text-xs text-white focus:outline-none focus:border-spotify-green">
        <button onclick="applyNaturalLanguageSearch()" class="absolute right-1 top-1 bg-spotify-green hover:bg-spotify-hoverGreen text-black font-bold text-[11px] px-3 py-1 rounded-lg transition">
          Filtrele & Bul
        </button>
      </div>
    </div>
  </div>

  <div class="flex-1 flex flex-col lg:flex-row max-w-7xl w-full mx-auto p-4 md:p-6 gap-6">
    <aside class="w-full lg:w-96 bg-spotify-card border border-[#282828] rounded-2xl p-5 flex flex-col gap-4 shadow-xl shrink-0 overflow-y-auto max-h-[calc(100vh-140px)]">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-bold text-gray-200 flex items-center gap-2">
          <i class="fa-solid fa-sliders text-spotify-green"></i> Filtreler & Arama
        </h2>
        <button onclick="resetFilters()" class="text-[11px] text-gray-400 hover:text-white underline">Sıfırla</button>
      </div>

      <div>
        <label class="text-xs font-semibold text-spotify-textGray">Şarkıda Geçen Söz / Dize</label>
        <input type="text" id="lyricsInput" placeholder="Örn: paramparça kalpler, -hadise..." 
               class="w-full bg-[#242424] border border-[#333] rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-spotify-green">
      </div>

      <div class="bg-[#1c1c1c] border border-[#333] p-3 rounded-xl space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-white">Anlamlı Söz Filtresi</span>
          <input type="checkbox" id="meaningfulCheckbox" class="w-4 h-4 accent-spotify-green rounded cursor-pointer" checked>
        </div>
        <div class="flex justify-between text-[11px] text-gray-400">
          <span>Şiddet:</span>
          <span id="strictnessLabel" class="text-spotify-green font-bold">Dengeli (>=60)</span>
        </div>
        <div class="grid grid-cols-3 gap-1.5">
          <button type="button" onclick="setStrictness('loose')" id="btn-loose" class="text-[10px] py-1 bg-[#262626] rounded-lg border border-[#333]">Gevşek</button>
          <button type="button" onclick="setStrictness('balanced')" id="btn-balanced" class="text-[10px] py-1 bg-spotify-green text-black font-bold rounded-lg border border-spotify-green">Dengeli</button>
          <button type="button" onclick="setStrictness('strict')" id="btn-strict" class="text-[10px] py-1 bg-[#262626] rounded-lg border border-[#333]">Sıkı</button>
        </div>
      </div>

      <div>
        <label class="block text-xs font-semibold text-spotify-textGray mb-1">Şarkının Dili</label>
        <select id="langSelect" class="w-full bg-[#242424] border border-[#333] rounded-xl px-3 py-2 text-sm text-white focus:outline-none"></select>
      </div>

      <div>
        <label class="block text-xs font-semibold text-spotify-textGray mb-1">Müzik Kategorisi</label>
        <select id="categorySelect" class="w-full bg-[#242424] border border-[#333] rounded-xl px-3 py-2 text-sm text-white focus:outline-none"></select>
        <div id="genreChipsContainer" class="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto p-1 bg-[#202020] rounded-xl border border-[#2c2c2c] mt-2"></div>
      </div>

      <div>
        <div class="flex justify-between text-xs font-semibold text-spotify-textGray mb-1">
          <span>Yıl Aralığı</span>
          <span id="yearRangeDisplay" class="text-spotify-green font-bold">1990 - 2026</span>
        </div>
        <div class="flex items-center gap-2">
          <input type="number" id="yearStartInput" min="1950" max="2026" value="1990" class="w-20 bg-[#242424] border border-[#333] text-center rounded-lg text-xs py-1 text-white">
          <span class="text-gray-500 text-xs">-</span>
          <input type="number" id="yearEndInput" min="1950" max="2026" value="2026" class="w-20 bg-[#242424] border border-[#333] text-center rounded-lg text-xs py-1 text-white">
        </div>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="block text-[11px] font-semibold text-spotify-textGray mb-1">Tema Odak</label>
          <select id="themeSelect" class="w-full bg-[#242424] border border-[#333] rounded-xl px-2 py-1.5 text-xs text-white focus:outline-none">
            <option value="all">Tüm Temalar</option>
            <option value="sokak">Sokak & Gerçeklik</option>
            <option value="aşk">Aşk & Ayrılık</option>
            <option value="dert">Dert & Efkar</option>
            <option value="toplumsal">Toplumsal Eleştiri</option>
            <option value="motivasyon">Motivasyon & Zirve</option>
            <option value="nostalji">Nostalji & Mazi</option>
          </select>
        </div>
        <div>
          <label class="block text-[11px] font-semibold text-spotify-textGray mb-1">Müstehcenlik</label>
          <select id="profanitySelect" class="w-full bg-[#242424] border border-[#333] rounded-xl px-2 py-1.5 text-xs text-white focus:outline-none">
            <option value="all">Serbest (Tümü)</option>
            <option value="moderate">Hafif / Orta</option>
            <option value="clean">Temiz (Küfürsüz)</option>
          </select>
        </div>
      </div>

      <div>
        <div class="flex justify-between items-center mb-1">
          <label class="text-xs font-semibold text-spotify-textGray">Sonuç Adedi</label>
          <span id="limitDisplay" class="text-xs text-spotify-green font-bold">20</span>
        </div>
        <input type="range" id="limitRange" min="5" max="50" step="5" value="20" class="w-full accent-spotify-green bg-[#333] h-1.5 rounded-lg appearance-none cursor-pointer">
      </div>

      <div class="sticky bottom-0 bg-[#181818]/95 backdrop-blur pt-3 pb-1 border-t border-[#282828] -mx-5 px-5 flex flex-col gap-2 mt-auto z-10">
        <button id="searchBtn" onclick="executeSearch()" class="w-full bg-spotify-green hover:bg-spotify-hoverGreen text-black font-bold py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 transition shadow-lg shadow-green-500/20">
          <i class="fa-solid fa-magnifying-glass"></i>
          <span>Şarkıları Bul</span>
        </button>
        <button id="exportBtn" onclick="openExportModal()" disabled class="w-full bg-[#282828] text-gray-500 font-semibold py-2 px-3 rounded-xl text-xs flex items-center justify-center gap-2 transition cursor-not-allowed border border-[#333]">
          <i class="fa-brands fa-spotify text-sm"></i>
          <span>Önizle & Playlist Yap (<span id="selectedCount">0</span>)</span>
        </button>
      </div>
    </aside>

    <main class="flex-1 bg-spotify-card border border-[#282828] rounded-2xl flex flex-col overflow-hidden shadow-xl">
      <div class="px-6 py-4 border-b border-[#282828] flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <h2 id="resultsHeading" class="text-lg font-bold text-white">Keşif Sonuçları</h2>
          <span id="resultsCountBadge" class="hidden text-xs bg-[#242424] text-spotify-textGray px-2.5 py-1 rounded-full border border-[#333]">0 parça</span>
        </div>
        <div class="flex items-center gap-3">
          <div id="sortContainer" class="hidden flex items-center gap-2">
            <span class="text-xs text-gray-400 font-medium">Sırala:</span>
            <select id="sortBySelect" onchange="changeSorting(this.value)" class="bg-[#242424] text-white border border-[#333] text-xs rounded-xl px-2.5 py-1.5 focus:outline-none focus:border-spotify-green cursor-pointer">
              <option value="relevance">Önerilen (Relevance)</option>
              <option value="meaningful_score">En Yüksek Söz Skoru</option>
              <option value="genre_match">En İyi Tür Uyumu</option>
              <option value="popularity">En Popüler</option>
              <option value="newest">En Yeni Çıkanlar</option>
              <option value="random">Rastgele Karışık</option>
            </select>
          </div>
          <div id="selectionActions" class="hidden flex items-center gap-3">
            <button onclick="toggleSelectAll()" id="selectAllBtn" class="text-xs text-gray-300 hover:text-white underline">Hepsini Seç</button>
          </div>
        </div>
      </div>

      <div id="statsSummaryBanner" class="hidden mx-4 mt-3 p-3 bg-[#1e231f] border border-[#2e4033] rounded-xl flex items-center justify-between gap-2 text-xs">
        <div class="flex items-center gap-2 text-gray-300">
          <i class="fa-solid fa-circle-info text-spotify-green"></i>
          <span id="statsSummaryText">Arama özeti</span>
        </div>
        <button onclick="relaxFiltersAndSearch()" class="text-[11px] bg-[#28382c] hover:bg-spotify-green hover:text-black text-green-300 font-bold px-3 py-1 rounded-lg transition border border-green-800">
          Filtreleri Gevşet
        </button>
      </div>

      <div id="tracksContainer" class="flex-1 overflow-y-auto p-4 space-y-3">
        <div id="welcomePlaceholder" class="h-full flex flex-col items-center justify-center text-center p-8 text-spotify-textGray">
          <i class="fa-solid fa-music text-3xl mb-4 text-spotify-green"></i>
          <h3 class="text-lg font-bold text-white mb-2">Müzik Aramaya Hazır</h3>
          <p class="max-w-md text-xs text-gray-400">Söz girin veya kategori seçip "Şarkıları Bul" butonuna basın.</p>
        </div>
      </div>
    </main>
  </div>

  <audio id="audioPreviewPlayer" class="hidden"></audio>
  <script src="/static/js/main.js"></script>
</body>
</html>

--- [static/js/main.js] ---
let currentTracks = [];
let selectedTrackUris = new Set();
let isUserLoggedIn = false;
let taxonomyData = null;
let selectedGenres = new Set();
let currentStrictness = "balanced";
let currentlyPlayingUrl = null;

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  loadTaxonomy();
  checkAuthStatus();
});

function setupEventListeners() {
  const limitRange = document.getElementById("limitRange");
  limitRange.addEventListener("input", (e) => {
    document.getElementById("limitDisplay").innerText = e.target.value;
  });
  document.getElementById("lyricsInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") executeSearch();
  });
  document.getElementById("nlInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") applyNaturalLanguageSearch();
  });
  document.getElementById("categorySelect").addEventListener("change", (e) => {
    renderGenreChips(e.target.value);
  });
  const yStart = document.getElementById("yearStartInput");
  const yEnd = document.getElementById("yearEndInput");
  const updateYearLabel = () => {
    document.getElementById("yearRangeDisplay").textContent = `${yStart.value} - ${yEnd.value}`;
  };
  yStart.addEventListener("input", updateYearLabel);
  yEnd.addEventListener("input", updateYearLabel);
}

async function loadTaxonomy() {
  try {
    const res = await fetch("/api/taxonomy");
    taxonomyData = await res.json();
    const langSelect = document.getElementById("langSelect");
    langSelect.innerHTML = "";
    const savedLang = localStorage.getItem("spoti_finder_lang") || "all";
    taxonomyData.languages.forEach(l => {
      const opt = document.createElement("option");
      opt.value = l.code;
      opt.textContent = l.name;
      if (l.code === savedLang) opt.selected = true;
      langSelect.appendChild(opt);
    });
    langSelect.addEventListener("change", (e) => {
      localStorage.setItem("spoti_finder_lang", e.target.value);
    });
    const catSelect = document.getElementById("categorySelect");
    catSelect.innerHTML = "";
    taxonomyData.categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      catSelect.appendChild(opt);
    });
    renderGenreChips("all");
  } catch (err) { console.error("Taksonomi yükleme hatası:", err); }
}

function renderGenreChips(catId) {
  const container = document.getElementById("genreChipsContainer");
  container.innerHTML = "";
  selectedGenres.clear();
  if (!taxonomyData) return;
  let genres = taxonomyData.genres.filter(g => g !== "Tümü");
  if (catId !== "all") {
    const cat = taxonomyData.categories.find(c => c.id === catId);
    if (cat && cat.genres) genres = cat.genres;
  }
  genres.forEach(g => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "text-[10px] bg-[#2a2a2a] hover:bg-[#383838] text-gray-300 px-2 py-0.5 rounded-lg border border-[#383838]";
    chip.textContent = g.toUpperCase();
    chip.onclick = () => {
      if (selectedGenres.has(g)) {
        selectedGenres.delete(g);
        chip.classList.remove("bg-spotify-green", "text-black", "font-bold");
      } else {
        selectedGenres.add(g);
        chip.classList.add("bg-spotify-green", "text-black", "font-bold");
      }
    };
    container.appendChild(chip);
  });
}

async function checkAuthStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    const dot = document.getElementById("userStatusDot");
    const text = document.getElementById("userStatusText");
    if (data.is_user_authenticated && data.user_profile) {
      isUserLoggedIn = true;
      dot.className = "w-2.5 h-2.5 rounded-full bg-spotify-green animate-pulse";
      text.innerHTML = `<span class="text-white font-bold text-xs">${data.user_profile.display_name}</span>`;
    } else {
      isUserLoggedIn = false;
      dot.className = "w-2.5 h-2.5 rounded-full bg-yellow-500";
      text.innerHTML = `<a href="/login" class="text-yellow-400 font-semibold text-xs">Spotify Bağla</a>`;
    }
  } catch (err) { console.error(err); }
}

async function executeSearch() {
  const lyrics = document.getElementById("lyricsInput").value.trim();
  const lang = document.getElementById("langSelect").value;
  const category = document.getElementById("categorySelect").value;
  const yearStart = parseInt(document.getElementById("yearStartInput").value) || 1990;
  const yearEnd = parseInt(document.getElementById("yearEndInput").value) || 2026;
  const theme = document.getElementById("themeSelect").value;
  const profanity = document.getElementById("profanitySelect").value;
  const limit = parseInt(document.getElementById("limitRange").value) || 20;
  const filterMeaningful = document.getElementById("meaningfulCheckbox").checked;
  const sortBy = document.getElementById("sortBySelect").value;

  const searchBtn = document.getElementById("searchBtn");
  searchBtn.disabled = true;
  searchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Taranıyor...</span>';

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lyrics_query: lyrics, language: lang, category: category, genres: Array.from(selectedGenres),
        year_start: yearStart, year_end: yearEnd, strictness: currentStrictness, profanity_mode: profanity,
        target_theme: theme, filter_meaningful: filterMeaningful, sort_by: sortBy, limit: limit
      })
    });
    const data = await res.json();
    currentTracks = data.tracks || [];
    selectedTrackUris.clear();
    currentTracks.forEach(t => selectedTrackUris.add(t.uri));
    updateSelectionUI();
    renderTracks(currentTracks);
  } catch (err) {
    console.error(err);
  } finally {
    searchBtn.disabled = false;
    searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i><span>Şarkıları Bul</span>';
  }
}

async function changeSorting(sortBy) {
  if (!currentTracks || currentTracks.length === 0) return;
  try {
    const res = await fetch("/api/sort-tracks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks: currentTracks, sort_by: sortBy })
    });
    const data = await res.json();
    if (data.tracks) {
      currentTracks = data.tracks;
      renderTracks(currentTracks);
    }
  } catch (err) { console.error(err); }
}

async function findSimilarToTrack(trackId) {
  const target = currentTracks.find(t => t.id === trackId);
  if (!target) return;
  try {
    const res = await fetch("/api/find-similar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_track: target, candidate_pool: currentTracks, limit: 5 })
    });
    const data = await res.json();
    if (data.similar_tracks && data.similar_tracks.length > 0) {
      const similarIds = new Set(data.similar_tracks.map(s => s.id));
      const remaining = currentTracks.filter(t => !similarIds.has(t.id));
      currentTracks = [...data.similar_tracks, ...remaining];
      renderTracks(currentTracks);
    }
  } catch (err) { console.error(err); }
}

function renderTracks(tracks) {
  const container = document.getElementById("tracksContainer");
  const countBadge = document.getElementById("resultsCountBadge");
  const actions = document.getElementById("selectionActions");
  const sortContainer = document.getElementById("sortContainer");

  container.innerHTML = "";
  if (!tracks || tracks.length === 0) {
    countBadge.classList.add("hidden");
    actions.classList.add("hidden");
    sortContainer.classList.add("hidden");
    container.innerHTML = `<div class="p-8 text-center text-gray-400 text-xs">Kriterlere uygun şarkı bulunamadı.</div>`;
    return;
  }

  countBadge.classList.remove("hidden");
  countBadge.textContent = `${tracks.length} parça`;
  actions.classList.remove("hidden");
  sortContainer.classList.remove("hidden");

  tracks.forEach((track, index) => {
    const isSelected = selectedTrackUris.has(track.uri);
    const card = document.createElement("div");
    card.className = `flex flex-col p-3.5 rounded-xl border gap-2.5 ${isSelected ? "bg-[#1f1f1f] border-spotify-green/50" : "bg-[#181818] border-transparent hover:bg-[#222]"}`;
    const comp = track.components || {};

    card.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div class="flex items-start space-x-3.5 flex-1 min-w-0">
          <input type="checkbox" ${isSelected ? "checked" : ""} onchange="toggleTrackSelection('${track.uri}', this)" class="mt-1 w-4 h-4 rounded text-spotify-green accent-spotify-green">
          <span class="mt-1 text-xs font-bold text-gray-500 w-5 text-right shrink-0">${index + 1}</span>
          <img src="${track.image_url || 'https://placehold.co/48x48/282828/fff?text=🎵'}" class="w-12 h-12 rounded-lg object-cover">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-bold text-white hover:underline cursor-pointer truncate" onclick="window.open('${track.external_url}', '_blank')">${track.name}</span>
              <span class="text-[10px] px-2 py-0.5 rounded-full font-bold border ${track.meaningful_score >= 70 ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800' : 'text-amber-400 bg-amber-950/60 border-amber-800'}">🎯 ${track.meaningful_score || 'N/A'} Puan</span>
              <span class="text-[10px] bg-[#2a2a2a] text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-900/60">🏷️ ${track.genre_badge}</span>
              ${track.similarity_info ? `<span class="text-[10px] bg-purple-950/60 text-purple-300 px-2 py-0.5 rounded-full border border-purple-800 font-bold">✨ %${track.similarity_info.overall_similarity} Benzer</span>` : ''}
            </div>
            <p class="text-xs text-spotify-textGray truncate mt-0.5">${track.artist} • ${track.album}</p>
            ${track.snippet ? `<div class="mt-1 text-[11px] text-emerald-300 bg-[#131c15] p-2 rounded-lg border border-emerald-900/50">💬 "...${track.snippet}..."</div>` : ''}
          </div>
        </div>
        <div class="flex items-center space-x-2 shrink-0 self-end sm:self-center">
          <button onclick="findSimilarToTrack('${track.id}')" class="text-[11px] bg-[#252525] hover:bg-purple-900/40 text-purple-300 px-2.5 py-1.5 rounded-lg border border-purple-800/40">✨ Benzer</button>
          <button onclick="toggleDetails('${track.id}')" class="text-[11px] bg-[#282828] hover:bg-[#333] text-gray-300 px-2.5 py-1.5 rounded-lg border border-gray-700">Metrikler</button>
          <a href="${track.external_url}" target="_blank" class="text-xs bg-[#282828] hover:bg-spotify-green hover:text-black text-gray-200 px-2.5 py-1.5 rounded-lg border border-gray-700">Spotify ↗</a>
        </div>
      </div>
      <div id="details-${track.id}" class="hidden border-t border-[#2a2a2a] pt-2.5 mt-1 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-gray-300 bg-[#161616] p-2.5 rounded-lg">
        <div><span class="text-gray-500 block">Kelime Zenginliği:</span><b class="text-white">${comp.vocab_diversity !== undefined ? comp.vocab_diversity + '/100' : 'N/A'}</b></div>
        <div><span class="text-gray-500 block">Satır Çeşitliliği:</span><b class="text-white">${comp.repetition !== undefined ? comp.repetition + '/100' : 'N/A'}</b></div>
        <div><span class="text-gray-500 block">Ad-Lib Temizliği:</span><b class="text-white">${comp.adlib_cleanliness !== undefined ? comp.adlib_cleanliness + '/100' : 'N/A'}</b></div>
        <div><span class="text-gray-500 block">Tema Yoğunluğu:</span><b class="text-white">${comp.theme_depth !== undefined ? comp.theme_depth + '/100' : 'N/A'}</b></div>
      </div>
    `;
    container.appendChild(card);
  });
}

function toggleDetails(trackId) {
  const el = document.getElementById(`details-${trackId}`);
  if (el) el.classList.toggle("hidden");
}

function toggleTrackSelection(uri, checkbox) {
  if (checkbox.checked) selectedTrackUris.add(uri);
  else selectedTrackUris.delete(uri);
  updateSelectionUI();
}

function updateSelectionUI() {
  const count = selectedTrackUris.size;
  document.getElementById("selectedCount").textContent = `${count}`;
  const exportBtn = document.getElementById("exportBtn");
  if (count > 0) {
    exportBtn.disabled = false;
    exportBtn.className = "w-full bg-spotify-green hover:bg-spotify-hoverGreen text-black font-bold py-2 px-3 rounded-xl text-xs flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-green-500/20";
  } else {
    exportBtn.disabled = true;
    exportBtn.className = "w-full bg-[#282828] text-gray-500 font-semibold py-2 px-3 rounded-xl text-xs flex items-center justify-center gap-2 cursor-not-allowed border border-[#333]";
  }
}

================================================================================
5. PROFESYONELLEŞTİRME SORULARI (CLAUDE İÇİN)
================================================================================
Lütfen yukarıdaki sistemi bir Principal Architect gözüyle değerlendirerek şu konularda somut mimari öneriler sun:
1. Mimari Katmanlama (Clean Architecture): Domain, Service, Repository, Router katmanları ve Pydantic v2 modelleri nasıl kurgulanmalı?
2. Asenkronluk (Async/Await): `ThreadPoolExecutor(max_workers=5)` yapısını `httpx.AsyncClient` ve `asyncio.Semaphore` ile asenkron hale getirirken rate limit ve circuit breaker'ı nasıl tasarlamalıyız?
3. UI/UX: Tailwind CSS arayüzüne Skeleton Loader, Toast bildirimleri ve modern bir Web Audio Player barı nasıl eklenmeli?
4. Gözlemlenebilirlik (Observability): API çağrı sürelerini, cache hit/miss oranlarını ve 429 hatalarını takip etmek için structured logging (`structlog`) nasıl kurgulanmalı?
5. Gelecek Nesil Vektör Arama: Telif yasalarını ihlal etmeden yerel açık kaynak embedding (ör. `all-MiniLM-L6-v2` veya Qdrant/ChromaDB) ile anlamsal lirik vektör araması bu boru hattına nasıl entegre edilebilir?
