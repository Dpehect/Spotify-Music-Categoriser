import os
import re
import concurrent.futures
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from dotenv import load_dotenv

from lyrics_service import search_songs_by_lyrics_web, get_song_lyrics
from lyrics_filter import evaluate_lyric_quality
from taxonomy import LANGUAGES, CATEGORIES, ALL_GENRES

load_dotenv()

SCOPE = "playlist-modify-public playlist-modify-private user-library-modify user-read-playback-state user-modify-playback-state"

class SpotifyClient:
    def __init__(self, client_id=None, client_secret=None, redirect_uri="http://localhost:3001/callback"):
        self.client_id = client_id or os.getenv("SPOTIPY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIPY_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:3001/callback")
        
        self.sp = None
        self.oauth_manager = None
        self.user_sp = None
        self._init_spotify()

    def _init_spotify(self):
        if self.client_id and self.client_secret and "buraya_" not in self.client_id:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
            except Exception as e:
                print(f"Spotify client credentials error: {e}")
                self.sp = None

            try:
                self.oauth_manager = SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri=self.redirect_uri,
                    scope=SCOPE,
                    cache_path=".spotify_user_cache",
                    open_browser=False
                )
                token_info = self.oauth_manager.get_cached_token()
                if token_info:
                    self.user_sp = spotipy.Spotify(auth=token_info["access_token"])
            except Exception as e:
                print(f"OAuth manager init error: {e}")

    def update_credentials(self, client_id, client_secret, redirect_uri=None):
        self.client_id = client_id
        self.client_secret = client_secret
        if redirect_uri:
            self.redirect_uri = redirect_uri
        self._init_spotify()
        return self.is_authenticated()

    def is_authenticated(self):
        if not self.sp:
            return False
        try:
            self.sp.search(q="test", limit=1, type="track")
            return True
        except Exception:
            return False

    def is_user_authenticated(self):
        if not self.oauth_manager:
            return False
        token = self.oauth_manager.get_cached_token()
        if token:
            try:
                if not self.user_sp:
                    self.user_sp = spotipy.Spotify(auth=token["access_token"])
                self.user_sp.current_user()
                return True
            except Exception:
                return False
        return False

    def get_auth_url(self):
        if not self.oauth_manager:
            self._init_spotify()
        if self.oauth_manager:
            return self.oauth_manager.get_authorize_url()
        return None

    def handle_auth_code(self, code):
        if not self.oauth_manager:
            return False
        try:
            token_info = self.oauth_manager.get_access_token(code, as_dict=True)
            if token_info:
                self.user_sp = spotipy.Spotify(auth=token_info["access_token"])
                return True
        except Exception as e:
            print(f"Token alma hatası: {e}")
        return False

    def get_current_user_profile(self):
        if self.user_sp:
            try:
                return self.user_sp.current_user()
            except Exception:
                pass
        return None

    def get_taxonomy_data(self):
        return {
            "languages": LANGUAGES,
            "categories": CATEGORIES,
            "genres": ALL_GENRES
        }

    def _extract_track_data(self, item, snippet=None):
        album_images = item.get("album", {}).get("images", [])
        image_url = album_images[0]["url"] if album_images else None
        return {
            "id": item["id"],
            "uri": item["uri"],
            "name": item["name"],
            "artist": ", ".join([a["name"] for a in item.get("artists", [])]),
            "album": item.get("album", {}).get("name", ""),
            "release_date": item.get("album", {}).get("release_date", ""),
            "popularity": item.get("popularity", 0),
            "duration_ms": item.get("duration_ms", 0),
            "preview_url": item.get("preview_url"),
            "external_url": item.get("external_urls", {}).get("spotify", ""),
            "image_url": image_url,
            "snippet": snippet
        }

    def search_tracks(
        self, 
        lyrics_query: str = "", 
        language: str = "all", 
        category: str = "all", 
        genre: str = "Tümü", 
        year: str = "Tümü", 
        filter_meaningful: bool = False,
        limit: int = 20
    ):
        """
        - lyrics_query: İsteğe bağlı (Boş bırakılırsa seçilen kategori/tür/dil trendlerinden bulur).
        - filter_meaningful: True ise 'grr, skrt, marka' vb. anlamsız/mumble şarkıları eler.
        """
        if not self.sp:
            return []

        clean_lyrics = lyrics_query.strip() if lyrics_query else ""
        market = None
        for lang in LANGUAGES:
            if lang["code"] == language and lang.get("market"):
                market = lang["market"]
                break

        collected_tracks = []
        seen_ids = set()

        def add_items(items, snippet=None):
            for it in items:
                if it and it["id"] not in seen_ids:
                    seen_ids.add(it["id"])
                    collected_tracks.append(self._extract_track_data(it, snippet=snippet))

        # 1. Şarkı Sözü (Lyrics) girilmişse önce lirik arşivlerinden tara
        if clean_lyrics:
            lyrics_hits = search_songs_by_lyrics_web(clean_lyrics, lang_code=language, limit=limit)
            for hit in lyrics_hits:
                if len(collected_tracks) >= limit:
                    break
                sp_query = f"{hit['artist']} {hit['title']}".strip()
                if sp_query:
                    try:
                        kwargs = {"q": sp_query, "type": "track", "limit": 2}
                        if market:
                            kwargs["market"] = market
                        res = self.sp.search(**kwargs)
                        trks = res.get("tracks", {}).get("items", [])
                        if trks:
                            add_items(trks[:1], snippet=hit.get("snippet"))
                    except Exception as e:
                        print(f"Hit arama hatası: {e}")

        # 2. Spotify Arama Sorgusu Oluştur (Söz girilmemişse veya ek şarkı gerekiyorsa)
        if len(collected_tracks) < limit:
            spotify_parts = []
            if clean_lyrics:
                spotify_parts.append(clean_lyrics)

            # Tür & Kategori
            if genre and genre != "Tümü":
                # Spotify API'de tireli bazı alt türler (turkish-rap vb.) serbest metin olarak daha iyi sonuç verir
                if "-" in genre and "turkish" in genre:
                    spotify_parts.append(genre.replace("-", " "))
                else:
                    spotify_parts.append(f'genre:"{genre}"')
            elif category and category != "all":
                for cat in CATEGORIES:
                    if cat["id"] == category and cat.get("genres"):
                        first_genre = cat["genres"][0]
                        if language == "tr" and "turkish" not in first_genre:
                            spotify_parts.append(f'turkish {first_genre}')
                        else:
                            spotify_parts.append(f'genre:"{first_genre}"')
                        break

            if year and year != "Tümü":
                spotify_parts.append(f'year:{year}')

            q_str = " ".join(spotify_parts).strip()
            if not q_str:
                q_str = "turkish 2024" if language == "tr" else "year:2024"

            try:
                # İhtiyaca göre çekim
                needed = limit - len(collected_tracks)
                fetch_limit = min(10, max(needed, 5))
                kwargs = {"q": q_str, "type": "track", "limit": fetch_limit}
                if market:
                    kwargs["market"] = market
                res = self.sp.search(**kwargs)
                items = res.get("tracks", {}).get("items", [])
                add_items(items)

                # Ek sayfalama
                if len(collected_tracks) < limit and len(items) >= 5:
                    res2 = self.sp.search(q=q_str, type="track", limit=fetch_limit, offset=fetch_limit, **({"market": market} if market else {}))
                    items2 = res2.get("tracks", {}).get("items", [])
                    add_items(items2)
            except Exception as e:
                print(f"Spotify arama hatası: {e}")

        # 3. Anlamlı Söz Filtresi (Anti-Junk / Anti-Mumble)
        if filter_meaningful and collected_tracks:
            def check_track(tr):
                try:
                    lyrics_text = get_song_lyrics(tr["name"], tr["artist"])
                    if lyrics_text:
                        evaluation = evaluate_lyric_quality(lyrics_text)
                        return tr if evaluation["is_meaningful"] else None
                except Exception:
                    pass
                return tr

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(check_track, collected_tracks))

            filtered = [r for r in results if r is not None]
            if filtered:
                collected_tracks = filtered

        return collected_tracks[:limit]

    def create_playlist_and_add_tracks(self, playlist_name, track_uris, description="Spotify Müzik Keşif aracı ile oluşturuldu."):
        if not self.user_sp:
            raise Exception("Kullanıcı Spotify hesabı bağlı değil! Lütfen önce Spotify ile giriş yapın.")

        user = self.user_sp.current_user()
        user_id = user["id"]

        new_playlist = self.user_sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=True,
            description=description
        )
        playlist_id = new_playlist["id"]
        playlist_url = new_playlist["external_urls"]["spotify"]

        if track_uris:
            chunk_size = 100
            for i in range(0, len(track_uris), chunk_size):
                self.user_sp.playlist_add_items(playlist_id, track_uris[i:i + chunk_size])

        return {
            "id": playlist_id,
            "name": playlist_name,
            "url": playlist_url,
            "track_count": len(track_uris)
        }
