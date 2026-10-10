# Spotify Şarkı Sözü & Anlamsal Müzik Keşif Motoru (v2.0 PRO) 🎧

Spotify Web API, LRCLIB, Genius ve Musixmatch entegrasyonuyla; söz/dize, dil, kategori, alt tür, dönem/yıl aralığı ve "Anti-Mumble" anlamlılık filtresiyle müzik keşfedip doğrudan kendi Spotify hesabınızda çalma listesi (Playlist) oluşturan full-stack platform.

---

## How to Use / Nasıl Kullanılır

### English
1. Set `SPOTIPY_CLIENT_ID` and `SPOTIPY_REDIRECT_URI` in your `.env` file. Add the same redirect URI to your Spotify app settings.
2. Start the app using the setup commands below, then open **http://localhost:3001**.
3. Search with a song lyric, mood, or genre, or choose the filters and categories you want.
4. Connect your Spotify account, choose the songs you like, and create a playlist.

### Türkçe
1. `.env` dosyasında `SPOTIPY_CLIENT_ID` ve `SPOTIPY_REDIRECT_URI` değerlerini ayarlayın. Aynı yönlendirme adresini Spotify uygulama ayarlarına da ekleyin.
2. Aşağıdaki kurulum komutlarıyla uygulamayı başlatın ve **http://localhost:3001** adresini açın.
3. Şarkı sözü, ruh hâli veya tür yazarak arayın ya da istediğiniz filtre ve kategorileri seçin.
4. Spotify hesabınızı bağlayın, beğendiğiniz şarkıları seçin ve çalma listenizi oluşturun.

## 🛠️ Teknik Mimari & Yasal Uyumluluk (Compliance)

### 1. Spotify Web API Endpoint Kullanımı
> [!IMPORTANT]
> Spotify'ın Kasım 2024 itibarıyla yeni/geliştirici uygulamalarına kapattığı `recommendations`, `audio-features`, `audio-analysis` ve `related-artists` endpoint'leri **kesinlikle kullanılmamaktadır**.
> 
> **Kullanılan Resmi Açık Endpoint'ler:**
> - `GET /v1/search` (`track`, `genre:`, `year:`, `market=`)
> - `GET /v1/me` (Kullanıcı kimliği ve profil bilgileri)
> - `POST /v1/users/{user_id}/playlists` (Çalma listesi oluşturma)
> - `POST /v1/playlists/{playlist_id}/tracks` (100'lük gruplar halinde toplu ekleme)
> - `POST /api/token` (OAuth 2.0 PKCE Code Exchange ve Refresh Token yenileme)

### 2. Telif Hakları & Şarkı Sözü Saklama İlkeleri
- Şarkı sözlerinin tamamı sunucuda veya veritabanında **ASLA kalıcı saklanmaz** ve kullanıcıya toplu yayımlanmaz.
- Veritabanında (`music_finder.db`) telif hakları gereği yalnızca `sha256_hash`, hesaplanan `meaningful_score`, `detected_lang`, `theme` ve aramayla eşleşen en fazla 5-8 kelimelik `snippet` alıntısı tutulur.

### 3. Çoklu Söz Sağlayıcı (LyricsProvider) Fallback Zinciri
- **LRCLIB Provider:** Açık kaynaklı, ücretsiz ve rate-limit dostu birincil sağlayıcı.
- **SyncedLyrics Provider:** Musixmatch / Deezer çoklu arşivi.
- **WebGeniusFallback Provider:** Genius ve açık web lirik arşivleri.

### 4. Güvenlik & Rate Limiting
- **OAuth 2.0 PKCE:** `code_verifier` ve `code_challenge` (S256) ile güvenli giriş. Client Secret frontend'e asla sızmaz.
- **Rate Limit (429):** Spotify API `Retry-After` başlığına tam uyumlu üstel geri çekilme (`Exponential Backoff`).

---

## 🚀 Kurulum ve Başlatma

### 1. Sanal Ortamı Aktif Edin
```bash
source venv/bin/activate
```

### 2. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

### 3. Sunucuyu Başlatın
```bash
python3 web_app.py
```
> Uygulama **http://localhost:3001** adresinde çalışır.

---

## 🧪 Test Sürecini Çalıştırma
```bash
source venv/bin/activate
python3 test_suite.py
```
Test suite; Sağlayıcı zinciri, Türkçe normalizasyonu, Boolean sorgu ayrıştırıcısı, RapidFuzz bulanık eşleme, 0-100 Anlamlılık ve Anti-Mumble filtresi ile Doğal Dil (NL) ayrıştırıcısını test eder.

---

## 📄 Lisans ve Söz Sağlayıcı Şartları
- Spotify markası, Spotify AB'nin tescilli ticari markasıdır.
- Şarkı sözleri yalnızca telif hakları çerçevesinde metin analizi ve alıntı amacıyla işlenmektedir.
