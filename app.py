import os
import sys
import webbrowser
import threading
import urllib.request
from io import BytesIO
from PIL import Image

import customtkinter as ctk
from spotify_service import SpotifyClient, DEFAULT_GENRES

# Tema ve renk ayarları
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

class SpotifyMusicFinderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Spotify Müzik Keşif & Arama Aracı")
        self.geometry("1100x750")
        self.minsize(900, 600)

        # Spotify Servisi Başlat
        self.spotify_service = SpotifyClient()

        # Ana layout: 2 sütunlu grid (Sol Menü / Filtreler, Sağ Sonuçlar)
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.categories_data = []
        self.genres_data = ["Tümü"] + self.spotify_service.get_available_genres()
        self.cached_images = {}

        self.create_sidebar()
        self.create_main_content()

        # Başlangıçta API kontrolü
        self.check_initial_auth()

    def check_initial_auth(self):
        if not self.spotify_service.is_authenticated():
            self.show_api_settings_modal()
        else:
            self.load_categories_async()

    def create_sidebar(self):
        sidebar = ctk.CTkFrame(self, corner_radius=0, width=320)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        sidebar.grid_propagate(False)

        # Başlık & Logo
        title_label = ctk.CTkLabel(
            sidebar, 
            text="🎧 Müzik Keşif", 
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(padx=20, pady=(20, 15), anchor="w")

        # 1. Metin Arama Kutusu
        search_label = ctk.CTkLabel(sidebar, text="Şarkı / Sanatçı / İpucu:", font=ctk.CTkFont(size=13, weight="bold"))
        search_label.pack(padx=20, pady=(5, 2), anchor="w")

        self.search_entry = ctk.CTkEntry(
            sidebar, 
            placeholder_text="Örn: Daft Punk, Gece, Chill...",
            height=36
        )
        self.search_entry.pack(padx=20, pady=(0, 15), fill="x")
        self.search_entry.bind("<Return>", lambda e: self.perform_search())

        # 2. Müzik Türü (Genre)
        genre_label = ctk.CTkLabel(sidebar, text="Müzik Türü (Genre):", font=ctk.CTkFont(size=13, weight="bold"))
        genre_label.pack(padx=20, pady=(5, 2), anchor="w")

        self.genre_combo = ctk.CTkComboBox(
            sidebar,
            values=self.genres_data[:40],
            height=36
        )
        self.genre_combo.set("Tümü")
        self.genre_combo.pack(padx=20, pady=(0, 15), fill="x")

        # 3. Kategori Seçimi (Category)
        cat_label = ctk.CTkLabel(sidebar, text="Kategori / Mood:", font=ctk.CTkFont(size=13, weight="bold"))
        cat_label.pack(padx=20, pady=(5, 2), anchor="w")

        self.category_combo = ctk.CTkComboBox(
            sidebar,
            values=["Tümü"],
            height=36
        )
        self.category_combo.set("Tümü")
        self.category_combo.pack(padx=20, pady=(0, 15), fill="x")

        # 4. Yıl Aralığı / Filtresi
        year_label = ctk.CTkLabel(sidebar, text="Dönem / Yıl Filtresi:", font=ctk.CTkFont(size=13, weight="bold"))
        year_label.pack(padx=20, pady=(5, 2), anchor="w")

        self.year_combo = ctk.CTkComboBox(
            sidebar,
            values=["Tümü", "2024", "2023", "2020-2024", "2010-2019", "2000-2009", "1990-1999", "1980-1989"],
            height=36
        )
        self.year_combo.set("Tümü")
        self.year_combo.pack(padx=20, pady=(0, 15), fill="x")

        # 5. Şarkı Adedi
        limit_label = ctk.CTkLabel(sidebar, text="Sonuç Adedi:", font=ctk.CTkFont(size=13, weight="bold"))
        limit_label.pack(padx=20, pady=(5, 2), anchor="w")

        self.limit_slider = ctk.CTkSlider(sidebar, from_=5, to=50, number_of_steps=9)
        self.limit_slider.set(20)
        self.limit_slider.pack(padx=20, pady=(0, 5), fill="x")

        self.limit_val_label = ctk.CTkLabel(sidebar, text="20 şarkı", font=ctk.CTkFont(size=11), text_color="gray")
        self.limit_val_label.pack(padx=20, pady=(0, 20), anchor="w")
        self.limit_slider.configure(command=lambda val: self.limit_val_label.configure(text=f"{int(val)} şarkı"))

        # Arama Yap Butonu
        self.search_btn = ctk.CTkButton(
            sidebar,
            text="🔍 Müzik Bul",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            fg_color="#1DB954",
            hover_color="#1aa34a",
            command=self.perform_search
        )
        self.search_btn.pack(padx=20, pady=(5, 10), fill="x")

        # Alt kısım: Ayarlar / API Anahtarı butonu
        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        settings_btn = ctk.CTkButton(
            sidebar,
            text="⚙️ Spotify API Ayarları",
            fg_color="transparent",
            border_width=1,
            border_color="#444",
            text_color="#aaa",
            hover_color="#333",
            height=32,
            command=self.show_api_settings_modal
        )
        settings_btn.pack(padx=20, pady=15, fill="x")

    def create_main_content(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#121212")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Üst Bilgi Başlığı
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=60)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=25, pady=(20, 10))

        self.results_title = ctk.CTkLabel(
            self.header_frame,
            text="Keşfetmeye Hazır",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.results_title.pack(side="left")

        self.status_label = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#888"
        )
        self.status_label.pack(side="right")

        # Şarkı Kartlarının Kaydırılabilir Listesi
        self.scrollable_results = ctk.CTkScrollableFrame(
            self.main_frame, 
            fg_color="transparent",
            label_text=""
        )
        self.scrollable_results.grid(row=1, column=0, sticky="nsew", padx=25, pady=(0, 20))
        self.scrollable_results.grid_columnconfigure(0, weight=1)

        # Boş başlangıç durumu mesajı
        self.show_welcome_state()

    def show_welcome_state(self):
        for widget in self.scrollable_results.winfo_children():
            widget.destroy()

        welcome_box = ctk.CTkFrame(self.scrollable_results, fg_color="#181818", corner_radius=12)
        welcome_box.pack(fill="x", pady=40, padx=20)

        welcome_title = ctk.CTkLabel(
            welcome_box,
            text="🎵 İstediğiniz Tarz Müzikleri Keşfedin",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        welcome_title.pack(pady=(25, 10))

        welcome_text = ctk.CTkLabel(
            welcome_box,
            text=(
                "Sol taraftaki menüyü kullanarak:\n\n"
                "• Belirli bir müzik türü (Rock, Electronic, Jazz, Turkish, Hip-Hop vb.) seçebilir\n"
                "• Bir tema / kategori belirleyebilir\n"
                "• Çıkış yılı ve arama terimi ekleyerek tam aradığınız havaya uygun parçaları listeleyebilirsiniz.\n\n"
                "Bir parçayı beğendiğinizde 'Spotify'da Aç' butonuyla anında dinleyebilirsiniz!"
            ),
            font=ctk.CTkFont(size=13),
            justify="center",
            text_color="#bbb"
        )
        welcome_text.pack(pady=(0, 25), padx=20)

    def load_categories_async(self):
        def _fetch():
            categories = self.spotify_service.get_categories(country="TR", limit=40)
            self.categories_data = categories
            names = ["Tümü"] + [c["name"] for c in categories]
            self.after(0, lambda: self.category_combo.configure(values=names))
            
            # Güncel genre'leri de ekle
            all_genres = ["Tümü"] + self.spotify_service.get_available_genres()
            self.after(0, lambda: self.genre_combo.configure(values=all_genres))

        threading.Thread(target=_fetch, daemon=True).start()

    def perform_search(self):
        if not self.spotify_service.is_authenticated():
            self.show_api_settings_modal()
            return

        query = self.search_entry.get().strip()
        genre = self.genre_combo.get()
        category_name = self.category_combo.get()
        year = self.year_combo.get()
        if year == "Tümü":
            year = None
        limit = int(self.limit_slider.get())

        self.status_label.configure(text="Aranıyor...")
        self.search_btn.configure(state="disabled")

        for widget in self.scrollable_results.winfo_children():
            widget.destroy()

        def _worker():
            tracks = []
            # Kategori seçilmişse ve tür seçilmemişse, kategoriden çalma listesi şarkıları çekilebilir
            selected_cat_id = None
            if category_name != "Tümü":
                for cat in self.categories_data:
                    if cat["name"] == category_name:
                        selected_cat_id = cat["id"]
                        break

            if selected_cat_id and not query and (not genre or genre == "Tümü"):
                playlists = self.spotify_service.get_category_playlists(selected_cat_id, limit=3)
                if playlists:
                    for pl in playlists[:2]:
                        tracks.extend(self.spotify_service.get_playlist_tracks(pl["id"], limit=limit // 2))
            else:
                tracks = self.spotify_service.search_tracks(
                    query=query if query else None,
                    genre=genre if genre != "Tümü" else None,
                    year=year,
                    limit=limit
                )

            self.after(0, lambda: self.display_results(tracks, query, genre, category_name))

        threading.Thread(target=_worker, daemon=True).start()

    def display_results(self, tracks, query, genre, category_name):
        self.search_btn.configure(state="normal")
        desc = []
        if query: desc.append(f'"{query}"')
        if genre and genre != "Tümü": desc.append(f'Tür: {genre}')
        if category_name and category_name != "Tümü": desc.append(f'Kategori: {category_name}')
        
        filter_summary = " + ".join(desc) if desc else "Genel Trendler"
        self.results_title.configure(text=f"Sonuçlar ({filter_summary})")
        self.status_label.configure(text=f"{len(tracks)} parça bulundu")

        if not tracks:
            empty_lbl = ctk.CTkLabel(
                self.scrollable_results,
                text="Aradığınız kriterlere uygun parça bulunamadı.\nFiltreleri veya arama terimini değiştirmeyi deneyin.",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            empty_lbl.pack(pady=40)
            return

        for idx, track in enumerate(tracks):
            card = ctk.CTkFrame(self.scrollable_results, fg_color="#181818", corner_radius=8, height=72)
            card.pack(fill="x", pady=4, padx=5)
            card.pack_propagate(False)

            # Sıra No
            idx_lbl = ctk.CTkLabel(
                card, 
                text=str(idx + 1), 
                width=30, 
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#888"
            )
            idx_lbl.pack(side="left", padx=(10, 5))

            # Şarkı Bilgileri (İsim, Sanatçı, Albüm)
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            track_name = ctk.CTkLabel(
                info_frame, 
                text=track["name"], 
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            track_name.pack(fill="x", anchor="w")

            meta_text = f"{track['artist']} • {track['album']}"
            if track.get("release_date"):
                meta_text += f" ({track['release_date'][:4]})"

            track_meta = ctk.CTkLabel(
                info_frame, 
                text=meta_text, 
                font=ctk.CTkFont(size=12),
                text_color="#999",
                anchor="w"
            )
            track_meta.pack(fill="x", anchor="w")

            # Popülarite / Beğeni rozeti
            pop = track.get("popularity", 0)
            pop_label = ctk.CTkLabel(
                card,
                text=f"🔥 {pop}%",
                font=ctk.CTkFont(size=11),
                text_color="#777"
            )
            pop_label.pack(side="left", padx=10)

            # Spotify'da Aç Butonu
            ext_url = track.get("external_url")
            if ext_url:
                open_btn = ctk.CTkButton(
                    card,
                    text="Spotify'da Aç ↗",
                    width=110,
                    height=30,
                    fg_color="#282828",
                    hover_color="#1DB954",
                    font=ctk.CTkFont(size=12),
                    command=lambda u=ext_url: webbrowser.open(u)
                )
                open_btn.pack(side="right", padx=15)

    def show_api_settings_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Spotify API Yapılandırması")
        modal.geometry("540x420")
        modal.transient(self)
        modal.grab_set()

        title = ctk.CTkLabel(modal, text="Spotify API Bağlantısı", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(20, 10))

        info_text = ctk.CTkLabel(
            modal,
            text=(
                "Spotify'dan müzik çekebilmek için ücretsiz Spotify Developer hesabı gereklidir:\n"
                "1. developer.spotify.com/dashboard adresine gidip oturum açın.\n"
                "2. 'Create App' ile bir uygulama oluşturun.\n"
                "3. Uygulamanın 'Client ID' ve 'Client Secret' bilgilerini aşağıya yapıştırın."
            ),
            font=ctk.CTkFont(size=12),
            text_color="#aaa",
            justify="left",
            wraplength=480
        )
        info_text.pack(pady=(0, 15), padx=25)

        # Client ID Input
        id_lbl = ctk.CTkLabel(modal, text="Client ID:", anchor="w", font=ctk.CTkFont(weight="bold"))
        id_lbl.pack(fill="x", padx=30, pady=(5, 2))
        id_entry = ctk.CTkEntry(modal, placeholder_text="Spotify Client ID")
        id_entry.pack(fill="x", padx=30, pady=(0, 10))
        if self.spotify_service.client_id and "buraya_" not in self.spotify_service.client_id:
            id_entry.insert(0, self.spotify_service.client_id)

        # Client Secret Input
        secret_lbl = ctk.CTkLabel(modal, text="Client Secret:", anchor="w", font=ctk.CTkFont(weight="bold"))
        secret_lbl.pack(fill="x", padx=30, pady=(5, 2))
        secret_entry = ctk.CTkEntry(modal, placeholder_text="Spotify Client Secret", show="*")
        secret_entry.pack(fill="x", padx=30, pady=(0, 15))
        if self.spotify_service.client_secret and "buraya_" not in self.spotify_service.client_secret:
            secret_entry.insert(0, self.spotify_service.client_secret)

        status_msg = ctk.CTkLabel(modal, text="", font=ctk.CTkFont(size=12))
        status_msg.pack(pady=(0, 10))

        def _save_and_test():
            cid = id_entry.get().strip()
            csecret = secret_entry.get().strip()
            if not cid or not csecret:
                status_msg.configure(text="Lütfen her iki alanı da doldurun!", text_color="#ff5555")
                return

            status_msg.configure(text="Test ediliyor...", text_color="#e0e0e0")
            success = self.spotify_service.update_credentials(cid, csecret)
            if success:
                # .env dosyasına yaz
                with open(".env", "w", encoding="utf-8") as f:
                    f.write(f"SPOTIPY_CLIENT_ID={cid}\nSPOTIPY_CLIENT_SECRET={csecret}\n")
                status_msg.configure(text="✅ Bağlantı başarılı!", text_color="#1DB954")
                self.load_categories_async()
                modal.after(1000, modal.destroy)
            else:
                status_msg.configure(
                    text="❌ Bağlantı başarısız! ID ve Secret bilgilerini kontrol edin.", 
                    text_color="#ff5555"
                )

        btn_row = ctk.CTkFrame(modal, fg_color="transparent")
        btn_row.pack(fill="x", padx=30, pady=(0, 15))

        dev_btn = ctk.CTkButton(
            btn_row, 
            text="Dashboard'a Git ↗", 
            fg_color="#333", 
            hover_color="#444",
            width=140,
            command=lambda: webbrowser.open("https://developer.spotify.com/dashboard")
        )
        dev_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            btn_row, 
            text="Kaydet & Bağlan", 
            fg_color="#1DB954", 
            hover_color="#1aa34a",
            width=160,
            command=_save_and_test
        )
        save_btn.pack(side="right")


if __name__ == "__main__":
    app = SpotifyMusicFinderApp()
    app.mainloop()
