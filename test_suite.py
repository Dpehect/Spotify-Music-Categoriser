from lyrics_providers import LyricsManager
from text_nlp import normalize_turkish, parse_boolean_query, fuzzy_lyric_match_score, extract_match_snippet
from meaningful_engine import analyze_lyrics_comprehensive
from nl_parser import parse_natural_language_prompt
from rate_limiter import SpotifyRateLimiter
from deduplication import deduplicate_tracks, clean_song_title
from genre_matcher import calculate_genre_match_score
from track_sorting import sort_tracks
from similarity_engine import calculate_similarity, find_similar_tracks
from fastapi.testclient import TestClient
from pydantic import ValidationError
import web_app
import sqlite3
from urllib.parse import parse_qs, urlparse
from unittest.mock import mock_open, patch
from db import DB_PATH

# 1. Söz Sağlayıcıları Testi
def test_lyrics_providers():
    lm = LyricsManager()
    assert len(lm.providers) == 3
    names = [p.name for p in lm.providers]
    assert "LRCLIB" in names
    assert "SyncedLyrics(Musixmatch/Deezer)" in names

# 2. Türkçe Normalizasyon Testi
def test_turkish_nlp_normalization():
    assert normalize_turkish("ŞARKILAR VE GÖZLER") == "sarkilar ve gozler"
    assert normalize_turkish("sıfırdan") == "sifirdan"

# 3. Boolean Sorgu Parser Testi
def test_boolean_query_parser():
    parsed = parse_boolean_query('"sıfırdan zirveye" -hadise')
    assert "sifirdan zirveye" in parsed["exact_phrases"]
    assert "hadise" in parsed["excluded_words"]

# 4. Bulanık Eşleşme Testi
def test_fuzzy_match():
    score = fuzzy_lyric_match_score("paramparca kalpler", "Paramparça kalpler ne sandınız")
    assert score >= 0.9

# 5. Alıntı (Snippet) Çıkarma ve Karakter Sınırı Testi
def test_snippet_extraction():
    snip = extract_match_snippet("paramparca", "Gözlerim baygın\nParamparça kalpler ne sandınız tek başıma savaştım")
    assert "Paramparça" in snip
    assert len(snip.split()) <= 10

# 6. NLP Junk / Ad-lib Filtresi Testi
def test_meaningful_engine_junk_filter():
    junk_lyric = "grr skrt skrt paw paw yeah yeah gucci prada rolex brr brr lambo bas gaza"
    res = analyze_lyrics_comprehensive(junk_lyric, strictness="balanced")
    assert res["is_passed"] is False
    assert res["score"] < 40
    assert "adlib_cleanliness" in res["components"]

# 7. NLP Yüksek Kaliteli Söz Testi
def test_meaningful_engine_high_quality():
    deep_lyric = """
    Karanlık sokaklarda adalet aradık yıllarca sabahı beklerken
    Emek verdik bu topraklara hiç durmadan ter dökerek
    Yüreğimizde umut, ceplerimiz boş olsa da sokak sokak yürüdük
    Zirveye değil hakikate varmaktı niyetimiz, mücadelemiz bitmez
    Adaletin sesini duyurmak için direndik her gece
    """
    res = analyze_lyrics_comprehensive(deep_lyric, strictness="balanced")
    assert res["is_passed"] is True
    assert res["score"] >= 60
    assert res["components"]["vocab_diversity"] > 40

# 8. Doğal Dil Arama Prompt Parser Testi
def test_nl_prompt_parser():
    parsed = parse_natural_language_prompt("90'lar Türkçe rap sokak küfürsüz")
    assert parsed["language"] == "tr"
    assert parsed["year_start"] == 1990
    assert parsed["year_end"] == 1999
    assert parsed["profanity_mode"] == "clean"

# 9. ISRC ve Tekilleştirme Testi (P0 Regresyon Önleme)
def test_isrc_and_deduplication():
    tracks = [
        {"id": "sp_1", "isrc": "TR001", "name": "Cambaz (Radio Edit)", "artist": "Mor ve Ötesi"},
        {"id": "sp_2", "isrc": "TR001", "name": "Cambaz - Remastered", "artist": "Mor ve Ötesi"},
        {"id": "sp_3", "isrc": None, "name": "Cambaz (Live 2008)", "artist": "Mor ve Ötesi"},
        {"id": "sp_4", "isrc": None, "name": "Cambaz (Instrumental)", "artist": "Mor ve Ötesi"}
    ]
    # Instrumental elenmeli, aynı ISRC tekilleşmeli
    deduped = deduplicate_tracks(tracks, preferred_version="original", allow_instrumental=False)
    # Cambaz Instrumental elendiği için gruptan yalnızca 1 orijinal veya radio_edit kalmalı
    assert len(deduped) == 1
    assert "Instrumental" not in deduped[0]["name"]

# 10. Farklı Sanatçı Aynı Şarkı Başlığı Testi
def test_same_title_different_artist():
    tracks = [
        {"id": "sp_a", "isrc": "TRAAA", "name": "Yalan", "artist": "Duman"},
        {"id": "sp_b", "isrc": "TRBBB", "name": "Yalan", "artist": "Candan Erçetin"}
    ]
    deduped = deduplicate_tracks(tracks)
    assert len(deduped) == 2

# 11. Dinamik Sıralama Testi (Track Sorting)
def test_track_sorting():
    tracks = [
        {"id": "1", "name": "A", "meaningful_score": 50.0, "popularity": 30, "analysis_status": "tamamlandi"},
        {"id": "2", "name": "B", "meaningful_score": 85.0, "popularity": 90, "analysis_status": "tamamlandi"},
        {"id": "3", "name": "C", "meaningful_score": 70.0, "popularity": 10, "analysis_status": "tamamlandi"}
    ]
    by_score = sort_tracks(tracks, sort_by="meaningful_score")
    assert by_score[0]["name"] == "B"
    assert by_score[1]["name"] == "C"

    by_pop = sort_tracks(tracks, sort_by="popularity")
    assert by_pop[0]["name"] == "B"
    assert by_pop[1]["name"] == "A"

# 12. Anlamsal Benzerlik Hesaplama Testi (Similarity Engine)
def test_similarity_engine():
    track_a = {"id": "1", "name": "Sokak Çocuğu", "artist": "Ceza", "theme": "sokak", "meaningful_score": 80.0, "detected_lang": "tr"}
    track_b = {"id": "2", "name": "Gettolar", "artist": "Sagopa", "theme": "sokak", "meaningful_score": 78.0, "detected_lang": "tr"}
    track_c = {"id": "3", "name": "Aşk Masalı", "artist": "Tarkan", "theme": "aşk", "meaningful_score": 55.0, "detected_lang": "tr"}

    sim_ab = calculate_similarity(track_a, track_b)
    sim_ac = calculate_similarity(track_a, track_c)

    # Aynı tema ve yakın skordaki şarkıların benzerliği daha yüksek olmalı
    assert sim_ab["overall_similarity"] > sim_ac["overall_similarity"]
    assert sim_ab["overall_similarity"] >= 80.0

# 13. Dürüst Tür Eşleşmesi ve Rozet Testi
def test_genre_matching_honesty():
    track = {"name": "Rock Dinle", "album": "Alternatif Rock", "artist": "Kurban", "_sourced_from_genre_query": False}
    score, badge = calculate_genre_match_score(track, selected_category="rock_metal")
    assert score == 0.95
    assert "Doğrulandı" in badge

    unverified_track = {"name": "Deneme", "album": "Bilinmeyen", "artist": "Ali", "_sourced_from_genre_query": False}
    score_unver, badge_unver = calculate_genre_match_score(unverified_track, selected_category="rock_metal")
    assert score_unver == 0.50
    assert badge_unver == "Belirsiz"

# 14. Hibrit Tema ve Anti-Keyword Ceza Puanı Testi
def test_hybrid_theme_anti_keyword_penalty():
    # İçinde 'özlem' geçmesine rağmen yoğun sokak, çete ve mermi içeren söz
    gangsta_with_single_love_word = """
    Karanlık sokaklarda çete gezer, pusu kurduk köşe başında gece yarısı
    Mermiler konuşur getto mahallemizde torbacı ve polis kavgası
    Yıllar geçer ve de özlem artar bra ama semt kan ağlar
    Silahlar patlar kurşunlar adres sormaz burası soğuk beton
    """
    res = analyze_lyrics_comprehensive(gangsta_with_single_love_word, strictness="balanced", target_theme="aşk")
    # Aşk teması için anti-keyword cezası almalı ve elenmeli
    assert res["is_passed"] is False
    assert res["theme"] == "sokak"

    # Saf aşk şarkısı
    pure_love = """
    Aşkım sevgilim seni ne çok seviyorum bir bilsen
    Ayrılık acısı kalbimi kırdı terk ettin beni sebepsizce
    Sensizlik ne zor sevgilim, aşığım sana deli gibi her gece
    Kavuşmak hayal oldu vuslat beklerken gözyaşlarım sel oldu
    """
    res_love = analyze_lyrics_comprehensive(pure_love, strictness="balanced", target_theme="aşk")
    assert res_love["is_passed"] is True
    assert res_love["theme"] == "aşk"
    assert res_love["components"]["target_dominance_ratio"] >= 1.5

# 15. API Routes Smoke & Validation Tests
def test_api_routes_and_validation():
    with TestClient(web_app.app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Parametre Kılavuzu" in home.text

        status = client.get("/api/status")
        assert status.status_code == 200
        assert "is_user_authenticated" in status.json()

        login = client.get("/login", follow_redirects=False)
        assert login.status_code in (302, 307)
        auth_params = parse_qs(urlparse(login.headers["location"]).query)
        oauth_state = auth_params["state"][0]
        assert auth_params["redirect_uri"] == [web_app.get_spotify_redirect_uri(login.request)]
        assert client.cookies.get("spoti_session_id") == oauth_state

        exchanged = {}
        original_exchange = web_app.engine.pkce_auth.exchange_code_for_token
        web_app.engine.pkce_auth.exchange_code_for_token = lambda **kwargs: exchanged.update(kwargs) or True
        try:
            callback = client.get(f"/callback?code=smoke-code&state={oauth_state}", follow_redirects=False)
            assert callback.status_code in (302, 307)
            assert exchanged["redirect_uri"] == auth_params["redirect_uri"][0]
            with TestClient(web_app.app) as attacker_client:
                rejected_callback = attacker_client.get(
                    f"/callback?code=smoke-code&state={oauth_state}",
                    follow_redirects=False
                )
                assert "auth_failed" in rejected_callback.headers["location"]
            assert exchanged["code"] == "smoke-code"
        finally:
            web_app.engine.pkce_auth.exchange_code_for_token = original_exchange
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM user_auth WHERE session_id = ?", (oauth_state,))
            conn.commit()
            conn.close()

        taxonomy = client.get("/api/taxonomy")
        assert taxonomy.status_code == 200
        assert len(taxonomy.json()["categories"]) > 0
        assert len(taxonomy.json()["genres"]) > 0

        parsed = client.post("/api/nl-parse", json={"prompt": "90'lar Türkçe rap sokak küfürsüz"})
        assert parsed.status_code == 200
        assert parsed.json()["filters"]["genres"]

        sorted_response = client.post("/api/sort-tracks", json={
            "tracks": [
                {"id": "low", "name": "Düşük", "popularity": 10},
                {"id": "high", "name": "Yüksek", "popularity": 90}
            ],
            "sort_by": "popularity"
        })
        assert sorted_response.status_code == 200
        assert sorted_response.json()["tracks"][0]["id"] == "high"

        similar = client.post("/api/find-similar", json={
            "target_track": {"id": "a", "name": "Sokak", "artist": "A", "theme": "sokak"},
            "candidate_pool": [{"id": "b", "name": "Mahalle", "artist": "B", "theme": "sokak"}],
            "limit": 1
        })
        assert similar.status_code == 200
        assert len(similar.json()["similar_tracks"]) == 1

        with patch.object(web_app, "get_song_lyrics", return_value="kısa test sözleri"):
            lyrics = client.post("/api/get-lyrics", json={"track_name": "Test", "artist_name": "Testçi"})
        assert lyrics.status_code == 200
        assert lyrics.json()["lyrics"] == "kısa test sözleri"

        original_playlist = web_app.engine.create_playlist_pkce
        web_app.engine.create_playlist_pkce = lambda **kwargs: {
            "id": "playlist-smoke", "name": kwargs["name"], "url": "https://open.spotify.com/playlist/test", "track_count": len(kwargs["track_uris"])
        }
        try:
            playlist = client.post("/api/create-playlist", json={
                "name": "API Smoke", "track_uris": ["spotify:track:one"]
            })
            assert playlist.status_code == 200
            assert playlist.json()["success"] is True
        finally:
            web_app.engine.create_playlist_pkce = original_playlist

        # Credential saving is isolated from the real .env and Spotify network.
        old_engine_creds = (web_app.engine.client_id, web_app.engine.client_secret, web_app.engine.pkce_auth.client_id)
        original_init = web_app.engine._init_spotify_client
        original_auth_check = web_app.engine.is_authenticated
        credential_file = mock_open()
        try:
            web_app.engine._init_spotify_client = lambda: None
            web_app.engine.is_authenticated = lambda: True
            with patch("builtins.open", credential_file):
                credentials = client.post("/api/save-credentials", json={
                    "client_id": "audit-client", "client_secret": "audit-secret"
                })
            assert credentials.status_code == 200
            assert credentials.json()["success"] is True
            saved_env = "".join(call.args[0] for call in credential_file().write.call_args_list)
            assert "SPOTIPY_REDIRECT_URI=" + web_app.get_spotify_redirect_uri(login.request) in saved_env
        finally:
            web_app.engine.client_id, web_app.engine.client_secret, web_app.engine.pkce_auth.client_id = old_engine_creds
            web_app.engine._init_spotify_client = original_init
            web_app.engine.is_authenticated = original_auth_check

        feedback = client.post("/api/feedback", json={
            "track_id": "api-smoke-track",
            "action_type": "play_preview",
            "user_theme": "sokak"
        })
        assert feedback.status_code == 200
        assert feedback.json()["status"] == "ok"
        conn = sqlite3.connect(DB_PATH)
        try:
            feedback_row = conn.execute(
                "SELECT query_theme, query_genre, track_id, action_type FROM user_relevance_feedback WHERE track_id = ?",
                ("api-smoke-track",)
            ).fetchone()
            assert feedback_row == ("sokak", "all", "api-smoke-track", "play_preview")
            conn.execute("DELETE FROM user_relevance_feedback WHERE track_id = ?", ("api-smoke-track",))
            conn.commit()
        finally:
            conn.close()

        no_theme_feedback = client.post("/api/feedback", json={
            "track_id": "api-smoke-no-theme",
            "action_type": "play_preview"
        })
        assert no_theme_feedback.status_code == 200
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT query_theme, query_genre, track_id FROM user_relevance_feedback WHERE track_id = ?",
                ("api-smoke-no-theme",)
            ).fetchone()
            assert row == ("all", "all", "api-smoke-no-theme")
            conn.execute("DELETE FROM user_relevance_feedback WHERE track_id = ?", ("api-smoke-no-theme",))
            conn.commit()
        finally:
            conn.close()

        invalid_feedback = client.post("/api/feedback", json={"track_id": "", "action_type": "bad-action"})
        assert invalid_feedback.status_code == 422

        invalid_search = client.post("/api/search", json={"limit": 1000})
        assert invalid_search.status_code == 422

        # Logging out without a session cookie must not invalidate other sessions.
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO user_auth (session_id) VALUES (?)", ("retained-session",))
        conn.commit()
        conn.close()
        with TestClient(web_app.app) as anonymous_client:
            assert anonymous_client.get("/logout", follow_redirects=False).status_code in (302, 307)
        conn = sqlite3.connect(DB_PATH)
        try:
            assert conn.execute("SELECT 1 FROM user_auth WHERE session_id = ?", ("retained-session",)).fetchone()
            conn.execute("DELETE FROM user_auth WHERE session_id = ?", ("retained-session",))
            conn.commit()
        finally:
            conn.close()

        # Search itself is isolated from live Spotify and lyric provider network calls.
        original_search = web_app.engine.search_tracks
        web_app.engine.search_tracks = lambda **kwargs: {"tracks": [], "received": kwargs}
        try:
            search = client.post("/api/search", json={"lyrics_query": "test", "limit": 5})
            assert search.status_code == 200
            assert search.json()["received"]["limit"] == 5
        finally:
            web_app.engine.search_tracks = original_search

if __name__ == "__main__":
    test_lyrics_providers()
    test_turkish_nlp_normalization()
    test_boolean_query_parser()
    test_fuzzy_match()
    test_snippet_extraction()
    test_meaningful_engine_junk_filter()
    test_meaningful_engine_high_quality()
    test_nl_prompt_parser()
    test_isrc_and_deduplication()
    test_same_title_different_artist()
    test_track_sorting()
    test_similarity_engine()
    test_genre_matching_honesty()
    test_hybrid_theme_anti_keyword_penalty()
    test_api_routes_and_validation()
    print("✅ TÜM BİRİM, REGRESYON VE API TESTLERİ (15/15) BAŞARIYLA GEÇTİ!")
