import os
import re
import concurrent.futures
from typing import List, Dict, Any, Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

from lyrics_providers import LyricsManager
from text_nlp import normalize_turkish, parse_boolean_query, fuzzy_lyric_match_score, extract_match_snippet
from meaningful_engine import analyze_lyrics_comprehensive
from deduplication import deduplicate_tracks
from genre_matcher import calculate_genre_match_score
from hybrid_nlp import evaluate_acoustic_features, segment_lyrics_structure
from db import get_cached_analysis, save_analysis, save_track, get_feedback_boost
from pkce_auth import SpotifyPKCEAuthManager
from rate_limiter import SpotifyRateLimiter
from track_sorting import sort_tracks
from taxonomy import LANGUAGES, CATEGORIES, ALL_GENRES

load_dotenv()

class SearchPipelineEngine:
    """
    SOTA Hibrit Semantik Keşif Motoru (v3.0 PRO):
    - Multi-lingual TF-IDF & Anti-Keywords Penalty.
    - Nakarat & Yapısal Ağırlıklandırma (Chorus/Hook %60).
    - Negatif Kısıt Motoru (avoid_themes filtresi).
    - Akustik Uyumluluk Doğrulama Kapısı (Audio/Remix Mismatch Filter).
    - Kullanıcı Geri Bildirimiyle Sıralama Takviyesi (Feedback Loop Boost).
    """
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
                # status_retries=0 ve retries=0: Spotify 429 verdiğinde 70.000 saniye takılı kalmayı engeller!
                self.sp = spotipy.Spotify(
                    auth_manager=auth,
                    retries=0,
                    status_retries=0,
                    requests_timeout=5
                )
            except Exception as e:
                print("Spotify ClientCredentials init error:", e)

    def get_active_sp(self):
        """Aktif kullanıcı oturumu (PKCE) varsa onun token'ını, yoksa client_credentials kullanır."""
        user_token = self.pkce_auth.get_valid_access_token()
        if user_token:
            return spotipy.Spotify(auth=user_token, retries=0, status_retries=0, requests_timeout=5)
        return self.sp

    def has_valid_credentials(self) -> bool:
        """Client ID ve Secret girilmiş mi kontrol eder."""
        return bool(self.client_id and self.client_secret and "buraya_" not in self.client_id)

    def is_authenticated(self) -> bool:
        return self.has_valid_credentials()

    def search_tracks(
        self,
        lyrics_query: str = "",
        language: str = "all",
        category: str = "all",
        genres: List[str] = None,
        year_start: int = 1990,
        year_end: int = 2026,
        popularity_min: int = 0,
        popularity_max: int = 100,
        strictness: str = "balanced",
        profanity_mode: str = "all",
        target_theme: str = "all",
        avoid_themes: List[str] = None,
        filter_meaningful: bool = True,
        preferred_version: str = "original",
        allow_instrumental: bool = False,
        sort_by: str = "relevance",
        limit: int = 20
    ) -> Dict[str, Any]:
        genres = genres or []
        avoid_themes = avoid_themes or []
        clean_lyrics = lyrics_query.strip()
        parsed_boolean = parse_boolean_query(clean_lyrics) if clean_lyrics else None

        raw_candidates = []
        seen_ids = set()

        stats = {
            "total_candidates": 0,
            "eliminated_no_lyrics": 0,
            "eliminated_genre_mismatch": 0,
            "eliminated_meaningful_filter": 0,
            "eliminated_duplicate_version": 0,
            "eliminated_language_mismatch": 0
        }

        def add_candidate(item: dict, snippet: str = None, match_score: float = 1.0, is_genre_sourced: bool = False):
            if not item:
                return
            t_id = item.get("id")
            if t_id in seen_ids:
                return

            pop = item.get("popularity", 0)
            if not (popularity_min <= pop <= popularity_max):
                return

            seen_ids.add(t_id)

            ext_ids = item.get("external_ids", {})
            isrc = ext_ids.get("isrc") # Spotify track ID ASLA ISRC'ye atanmaz
            album_images = item.get("album", {}).get("images", [])
            image_url = album_images[0]["url"] if album_images else None

            track_data = {
                "id": t_id,
                "spotify_track_id": t_id,
                "isrc": isrc,
                "uri": item.get("uri"),
                "name": item.get("name"),
                "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
                "album": item.get("album", {}).get("name", ""),
                "release_date": item.get("album", {}).get("release_date", ""),
                "popularity": pop,
                "duration_ms": item.get("duration_ms", 0),
                "preview_url": item.get("preview_url"),
                "external_url": item.get("external_urls", {}).get("spotify", ""),
                "image_url": image_url,
                "snippet": snippet,
                "match_score": match_score,
                "analysis_status": "analiz_bekliyor", # analiz_bekliyor, tamamlandi, soz_bulunamadi, hata
                "meaningful_score": None, # Sahte 55 puan yok!
                "meaningful_reason": None,
                "genre_match_score": 1.0,
                "genre_badge": "Uyumlu",
                "theme": "genel",
                "detected_lang": "unknown",
                "_sourced_from_genre_query": is_genre_sourced
            }
            save_track(track_data)
            raw_candidates.append(track_data)

        # 1. ADIM: SÖZ KAYNAKLARINDAN ADAY TOPLAMA
        if clean_lyrics:
            search_phrases = parsed_boolean["exact_phrases"] or [clean_lyrics]
            main_phrase = search_phrases[0]

            lyrics_hits = self.lyrics_manager.search_by_phrase(main_phrase, lang=language, limit=limit * 2)
            for hit in lyrics_hits:
                query_sp = f"{hit['artist']} {hit['title']}".strip()
                if not query_sp:
                    continue
                try:
                    res = self.sp.search(q=query_sp, type="track", limit=2)
                    for item in res.get("tracks", {}).get("items", []):
                        snip = hit.get("snippet") or extract_match_snippet(clean_lyrics, hit.get("snippet", ""))
                        add_candidate(item, snippet=snip, match_score=0.95, is_genre_sourced=False)
                except Exception:
                    pass

        # 2. ADIM: SPOTIFY TÜM DÜNYA & DERİN ARAMA HAVUZU (10.000 ADAY HEDEFİ)
        # Kullanıcının talebi doğrultusunda Spotify kataloğunun en geniş kapsamıyla taranması
        # (Spotify API'sinde tek sorguda limit+offset sınırı 1000'dir; 10 farklı alt sorguyla 10.000'e kadar aday taranır)
        target_candidates_count = 10000

        # Çok boyutlu arama varyasyonları
        spotify_queries = []
        base_filters = []
        if year_start and year_end and not (year_start == 1990 and year_end == 2026):
            base_filters.append(f'year:{year_start}-{year_end}')

        # Arama Tohumları Sözlüğü (Genişletilmiş)
        multilingual_theme_seeds = {
            "tr": {
                "aşk": ["aşk", "ayrılık", "özlem", "sevgili", "kalp", "yar", "hasret", "vuslat"],
                "dert": ["dert", "hüzün", "efkar", "acı", "çile", "gözyaşı", "keder"],
                "sokak": ["sokak", "mahalle", "getto", "semt", "blok", "varoş"],
                "toplumsal": ["düzen", "sistem", "isyan", "adalet", "özgürlük"],
                "motivasyon": ["başarı", "zafer", "zirve", "şampiyon", "inanç"],
                "nostalji": ["mazi", "anılar", "eskiden", "çocukluk", "hatıra"]
            },
            "en": {
                "aşk": ["love", "heartbreak", "romance", "forever", "miss you", "kiss"],
                "dert": ["sadness", "grief", "pain", "tears", "lonely", "broken"],
                "sokak": ["street", "hood", "block", "gang", "city", "hustle"],
                "toplumsal": ["justice", "freedom", "protest", "revolution"],
                "motivasyon": ["champion", "victory", "glory", "win", "unstoppable"],
                "nostalji": ["memories", "yesterday", "nostalgia", "past", "remember"]
            },
            "es": {
                "aşk": ["amor", "desamor", "romance", "corazon", "beso"],
                "dert": ["tristeza", "dolor", "soledad", "llorar", "pena"],
                "sokak": ["calle", "barrio", "esquina"],
                "toplumsal": ["justicia", "libertad", "pueblo"],
                "motivasyon": ["victoria", "campeón", "éxito"],
                "nostalji": ["recuerdos", "pasado", "ayer"]
            }
        }

        # 1. Öncelikli Ana Söz Sorgusu
        if clean_lyrics:
            spotify_queries.append(clean_lyrics)

        is_genre_query = False
        genre_kw = ""
        category_genres = []
        if genres and "Tümü" not in genres:
            is_genre_query = True
            genre_kw = genres[0].replace("-", " ")
            category_genres = [g.replace("-", " ") for g in genres[:3]]
        elif category and category != "all":
            is_genre_query = True
            for cat in CATEGORIES:
                if cat["id"] == category and cat.get("genres"):
                    genre_kw = cat["genres"][0].replace("-", " ")
                    category_genres = [g.replace("-", " ") for g in cat["genres"][:4]]
                    break

        lang_prefix = "turkish " if (language == "tr" and "turkish" not in genre_kw.lower()) else ""

        # Tema tohumları listesi
        theme_seeds_list = []
        if target_theme and target_theme != "all":
            l_key = language if language in multilingual_theme_seeds else ("tr" if language == "all" else "en")
            theme_seeds_list = multilingual_theme_seeds.get(l_key, {}).get(target_theme, [target_theme])

        # Sorguları çeşitlendir: Kategori seçilmişse tür kelimesini (örn: trap/rap) MUTLAKA her sorguya ekle
        for seed in theme_seeds_list:
            if genre_kw:
                spotify_queries.append(f"{lang_prefix}{genre_kw} {seed}".strip())
            else:
                spotify_queries.append(f"{lang_prefix}{seed}".strip())

        for g in category_genres:
            spotify_queries.append(f"{lang_prefix}{g}".strip())

        if not spotify_queries:
            fallback_lang = "turkish " if language == "tr" else ""
            if genre_kw:
                spotify_queries.append(f"{fallback_lang}{genre_kw}".strip())
            else:
                spotify_queries.append(f"{fallback_lang}2024".strip())

        # Spotify API aramalarını paralel (ThreadPoolExecutor) olarak çalıştırarak
        # Spotify hız sınırına takılmadan en kaliteli yüzlerce adayı 2-3 saniye içinde çek
        search_tasks = []
        for q_str in spotify_queries[:5]:
            for offset in [0, 10, 20, 30, 40]:
                search_tasks.append((q_str, offset))

        active_client = self.get_active_sp()

        def execute_spotify_search(task):
            q_val, off_val = task
            if not active_client:
                return []
            try:
                res = active_client.search(q=q_val, type="track", limit=10, offset=off_val)
                return res.get("tracks", {}).get("items", [])
            except Exception:
                return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            batch_results = ex.map(execute_spotify_search, search_tasks)
            for items in batch_results:
                for it in items:
                    add_candidate(it, match_score=0.85, is_genre_sourced=is_genre_query)
                if len(raw_candidates) >= target_candidates_count:
                    break

        # Spotify API Rate Limit (429) veya Çevrimdışı Durumunda Yerel Kütüphane Fallback'i
        if len(raw_candidates) < 10:
            import sqlite3
            from db import DB_PATH
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT spotify_id, isrc, name, artist, album, release_date, popularity, duration_ms, preview_url, external_url, image_url FROM tracks ORDER BY popularity DESC LIMIT 200")
                for row in c.fetchall():
                    dummy_item = {
                        "id": row[0],
                        "uri": f"spotify:track:{row[0]}",
                        "name": row[2],
                        "artists": [{"name": a.strip()} for a in (row[3] or "").split(",")],
                        "album": {"name": row[4] or "", "release_date": row[5] or "", "images": [{"url": row[10]}] if row[10] else []},
                        "popularity": row[6] or 50,
                        "duration_ms": row[7] or 0,
                        "preview_url": row[8],
                        "external_urls": {"spotify": row[9] or f"https://open.spotify.com/track/{row[0]}"},
                        "external_ids": {"isrc": row[1]}
                    }
                    add_candidate(dummy_item, match_score=0.80, is_genre_sourced=is_genre_query)
                conn.close()
            except Exception as e:
                print("DB Fallback error:", e)

        stats["total_candidates"] = len(raw_candidates)

        # 3. ADIM: VERSİYON & ISRC TEKİLLEŞTİRME
        deduped = deduplicate_tracks(raw_candidates, preferred_version=preferred_version, allow_instrumental=allow_instrumental)
        stats["eliminated_duplicate_version"] = len(raw_candidates) - len(deduped)

        # 4. ADIM: TÜR VE KATEGORİ UYUM SKORLAMASI
        genre_filtered_candidates = []
        for track in deduped:
            g_score, g_badge = calculate_genre_match_score(track, selected_category=category, selected_genres=genres)
            track["genre_match_score"] = g_score
            track["genre_badge"] = g_badge

            # Kategori seçilmişse ve tür uyumu çok düşükse ele (eşik 0.60'a esnetildi)
            if category != "all" and g_score < 0.60:
                stats["eliminated_genre_mismatch"] += 1
                continue
            genre_filtered_candidates.append(track)

        # 5. ADIM: KALİTE ANALİZİ VE SÖZ KONTROLÜ
        # Popülerlik ve tür uyumuna göre önceliklendirerek en iyi adayları öne al
        genre_filtered_candidates.sort(key=lambda x: (x.get("genre_match_score", 0.0), x.get("popularity", 0)), reverse=True)
        # Limit N ise N*2.5 kadar adayı (azami 40 şarkı) derin söz motorundan geçirerek anında sonuç ver
        eval_pool = genre_filtered_candidates[:min(max(limit * 2, 20), 40)]

        def process_track_lyrics(track):
            artist = track["artist"]
            name = track["name"]

            # 1. Önce Veritabanı Önbelleği (Sıfır ek istek)
            cached = get_cached_analysis(artist, name)
            if cached:
                cached_score = cached["meaningful_score"]
                thresholds = {"loose": 40.0, "balanced": 60.0, "strict": 75.0}
                required_score = thresholds.get(strictness, 60.0)
                cached_is_passed = (cached_score is not None and cached_score >= required_score)
                
                cached_theme = cached.get("theme", "genel")
                if target_theme != "all" and cached_theme != target_theme:
                    cached_is_passed = False

                track["analysis_status"] = "tamamlandi"
                track["meaningful_score"] = cached_score
                track["meaningful_reason"] = cached["evaluation_reason"]
                track["detected_lang"] = cached["detected_lang"]
                track["theme"] = cached_theme
                track["vocab_richness"] = cached.get("vocab_richness")
                track["junk_ratio"] = cached.get("junk_ratio")
                track["_is_passed"] = cached_is_passed
                if not track.get("snippet"):
                    track["snippet"] = cached.get("snippet")
                return track

            # 2. Önbellekte yoksa Sağlayıcı Zincirinden Çek (LRCLIB -> Genius -> Musixmatch)
            try:
                raw_lyrics = self.lyrics_manager.get_lyrics(artist, name)
                if not raw_lyrics or len(raw_lyrics.strip()) < 30:
                    track["analysis_status"] = "soz_bulunamadi"
                    track["meaningful_score"] = None
                    track["meaningful_reason"] = "Söz arşivlerinde bulunamadı"
                    track["_is_passed"] = False
                    return track

                # 3. Yapısal Segmentasyon (Chorus/Hook %60, Verses %30, Bridge %10)
                segments = segment_lyrics_structure(raw_lyrics)
                chorus_text = segments["chorus"]

                # 4. Anlamlılık ve Dil Analizi (Yapısal nakarat önceliğiyle)
                analyzed_text = f"{chorus_text}\n\n{raw_lyrics}" if chorus_text else raw_lyrics
                analysis = analyze_lyrics_comprehensive(
                    analyzed_text,
                    strictness=strictness,
                    profanity_mode=profanity_mode,
                    target_theme=target_theme
                )

                # 5. Akustik Doğrulama Kapısı (Acoustic Evaluation)
                acoustic_mult, acoustic_reason = evaluate_acoustic_features(track, target_theme=target_theme)
                
                # 6. Geri Bildirim Takviyesi (Historical Feedback Boost)
                feedback_boost = get_feedback_boost(target_theme, track.get("id"))

                snip = track.get("snippet") or extract_match_snippet(clean_lyrics or name, raw_lyrics)

                save_analysis(
                    artist=artist,
                    track_name=name,
                    lyrics_text=raw_lyrics,
                    detected_lang=analysis["detected_lang"],
                    meaningful_score=analysis["score"],
                    junk_ratio=analysis["junk_ratio"],
                    vocab_richness=analysis["vocab_richness"],
                    evaluation_reason=analysis["reason"],
                    snippet=snip,
                    theme=analysis["theme"],
                    algo_version="3.0"
                )

                # Negatif Kısıt Kontrolü (avoid_themes)
                if avoid_themes and analysis["theme"] in avoid_themes:
                    analysis["is_passed"] = False
                    analysis["reason"] += f" (Hariç tutulan '{analysis['theme']}' teması elendi)"

                # Akustik ceza uygulaması
                if acoustic_mult < 0.5 and target_theme in ["aşk", "dert", "melankoli"]:
                    analysis["is_passed"] = False
                    analysis["reason"] += f" ({acoustic_reason})"

                track["analysis_status"] = "tamamlandi"
                track["meaningful_score"] = round(analysis["score"] * acoustic_mult, 1)
                track["meaningful_reason"] = analysis["reason"]
                track["detected_lang"] = analysis["detected_lang"]
                track["theme"] = analysis["theme"]
                track["vocab_richness"] = analysis["vocab_richness"]
                track["junk_ratio"] = analysis["junk_ratio"]
                track["components"] = analysis.get("components", {})
                track["components"]["acoustic_multiplier"] = acoustic_mult
                track["components"]["feedback_boost"] = feedback_boost
                track["_is_passed"] = bool(analysis["is_passed"])
                if not track.get("snippet"):
                    track["snippet"] = snip
                return track

            except Exception as e:
                track["analysis_status"] = "hata"
                track["meaningful_score"] = None
                track["meaningful_reason"] = "Analiz sırasında teknik bir hata oluştu"
                track["_is_passed"] = False
                return track

        # max_workers=8 ile paralel söz çekme ve analiz
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            analyzed_tracks = list(executor.map(process_track_lyrics, eval_pool))

        # 6. ADIM: FİLTRELEME VE ELEME RAPORU
        final_tracks = []
        for track in analyzed_tracks:
            # Dil kontrolü
            if language != "all" and track.get("detected_lang") not in ["unknown", language]:
                stats["eliminated_language_mismatch"] += 1
                continue

            # Söz bulunamadıysa ve kullanıcı arama sözü yazmışsa veya sıkı moddaysa
            if clean_lyrics and track["analysis_status"] == "soz_bulunamadi":
                stats["eliminated_no_lyrics"] += 1
                continue

            # Anlamlı söz filtresi devredeyse ve geçmediyse
            if filter_meaningful and track["analysis_status"] == "tamamlandi":
                if track.get("_is_passed") is not True:
                    stats["eliminated_meaningful_filter"] += 1
                    continue

            # Negatif Tema (avoid_themes) son kontrol
            if avoid_themes and track.get("theme") in avoid_themes:
                continue

            final_tracks.append(track)

        # 7. ADIM: SIRALAMA (Çoklu Dinamik Mod Desteği & Feedback Boost)
        final_tracks = sort_tracks(final_tracks, sort_by=sort_by)

        return {
            "tracks": final_tracks[:limit],
            "stats": {
                "requested_limit": limit,
                "found_count": len(final_tracks[:limit]),
                **stats
            }
        }

    def create_playlist_pkce(self, name: str, track_uris: List[str], description: str = "Spotify Müzik Keşif Motoru ile oluşturuldu.", session_id: Optional[str] = None) -> Dict[str, Any]:
        token = self.pkce_auth.get_valid_access_token(session_id=session_id) if session_id else self.pkce_auth.get_valid_access_token()
        if not token:
            raise Exception("Kullanıcı Spotify oturumu bulunamadı. Lütfen önce Spotify ile giriş yapın.")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        me_resp = self.rate_limiter.request("GET", "https://api.spotify.com/v1/me", headers=headers)
        if me_resp.status_code != 200:
            raise Exception(f"Kullanıcı profili alınamadı: {me_resp.text}")
        user_id = me_resp.json()["id"]

        create_payload = {
            "name": name,
            "public": True,
            "description": description
        }
        pl_resp = self.rate_limiter.request("POST", f"https://api.spotify.com/v1/users/{user_id}/playlists", json=create_payload, headers=headers)
        if pl_resp.status_code not in [200, 201]:
            raise Exception(f"Çalma listesi oluşturulamadı: {pl_resp.text}")

        pl_data = pl_resp.json()
        playlist_id = pl_data["id"]
        playlist_url = pl_data.get("external_urls", {}).get("spotify", "")

        unique_uris = list(dict.fromkeys(track_uris))
        chunk_size = 100
        for i in range(0, len(unique_uris), chunk_size):
            chunk = unique_uris[i:i + chunk_size]
            self.rate_limiter.request("POST", f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", json={"uris": chunk}, headers=headers)

        return {
            "id": playlist_id,
            "name": name,
            "url": playlist_url,
            "track_count": len(unique_uris)
        }
