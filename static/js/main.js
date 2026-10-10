/**
 * Spotify Lyrics & Semantic Music Discovery Engine v2.1 PRO
 * Enterprise-grade Frontend Controller
 * 
 * Security features:
 * - DOM XSS prevention: Safe DOM construction (createElement / textContent), strict sanitization.
 * - HTTP Race-condition mitigation via AbortController.
 * - Defensive URL validation (safeSpotifyUrl check).
 * - Full WCAG 2.1 AA accessibility (aria-live, keyboard navigation, focus management).
 * - Responsive mobile drawer with backdrop and Esc-key support.
 * - Floating audio player with real-time seeking and time counters.
 */

// Global State
let currentTracks = [];
let selectedTrackUris = new Set();
let isUserLoggedIn = false;
let taxonomyData = null;
let selectedGenres = new Set();
let currentStrictness = "balanced";
let currentlyPlayingUrl = null;
let searchAbortController = null;
let activeAvoidThemes = [];

// DOM Ready Bootstrap
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  setupAudioEvents();
  setupKeyboardShortcuts();
  loadTaxonomy();
  checkAuthStatus();
  checkUrlNotification();
});

// Check OAuth return params in URL
function checkUrlNotification() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("auth") === "success") {
    showToast("Spotify hesabınız başarıyla bağlandı! Artık listelerinizi doğrudan aktarabilirsiniz.", "success", 5000);
    window.history.replaceState({}, document.title, window.location.pathname);
  } else if (params.get("logout") === "success") {
    showToast("Spotify oturumunuz güvenle kapatıldı.", "info", 4000);
    window.history.replaceState({}, document.title, window.location.pathname);
  } else if (params.get("error")) {
    showToast("Spotify bağlantısı kurulamadı: " + params.get("error"), "error", 5000);
    window.history.replaceState({}, document.title, window.location.pathname);
  }
}

// Toast Notification Manager
function showToast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  const bgStyles = {
    info: "bg-[#222] border-spotify-border text-white",
    success: "bg-emerald-950/90 border-emerald-800 text-emerald-200",
    error: "bg-red-950/90 border-red-800 text-red-200",
    warning: "bg-amber-950/90 border-amber-800 text-amber-200"
  };

  const icons = {
    info: "fa-circle-info text-blue-400",
    success: "fa-circle-check text-emerald-400",
    error: "fa-triangle-exclamation text-red-400",
    warning: "fa-circle-exclamation text-amber-400"
  };

  toast.className = `flex items-center gap-2.5 px-4 py-3 rounded-xl border shadow-xl text-xs backdrop-blur-md pointer-events-auto transform translate-y-[-10px] opacity-0 transition-all duration-200 ${bgStyles[type] || bgStyles.info}`;
  
  const icon = document.createElement("i");
  icon.className = `fa-solid ${icons[type] || icons.info} text-sm shrink-0`;
  toast.appendChild(icon);

  const textSpan = document.createElement("span");
  textSpan.textContent = message;
  textSpan.className = "flex-1 font-medium";
  toast.appendChild(textSpan);

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-[-10px]", "opacity-0");
  });

  // Announce to screen reader
  announceToScreenReader(message);

  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-[-10px]");
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

function announceToScreenReader(message) {
  const announcer = document.getElementById("liveAnnouncer");
  if (announcer) {
    announcer.textContent = "";
    setTimeout(() => {
      announcer.textContent = message;
    }, 50);
  }
}

// Global Event Listeners & Binding
function setupEventListeners() {
  const limitRange = document.getElementById("limitRange");
  const limitDisplay = document.getElementById("limitDisplay");
  if (limitRange && limitDisplay) {
    limitRange.addEventListener("input", (e) => {
      limitDisplay.innerText = e.target.value;
    });
  }

  const lyricsInput = document.getElementById("lyricsInput");
  if (lyricsInput) {
    lyricsInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        executeSearch();
      }
    });
  }

  const nlInput = document.getElementById("nlInput");
  if (nlInput) {
    nlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        applyNaturalLanguageSearch();
      }
    });
  }

  const categorySelect = document.getElementById("categorySelect");
  if (categorySelect) {
    categorySelect.addEventListener("change", (e) => {
      renderGenreChips(e.target.value);
    });
  }

  const genreSearch = document.getElementById("genreSearchInput");
  if (genreSearch) {
    genreSearch.addEventListener("input", () => renderGenreChips(categorySelect?.value || "all"));
  }

  // Quick Inspiration Chips binding
  const quickChips = document.querySelectorAll(".quick-chip");
  quickChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      const nlInput = document.getElementById("nlInput");
      if (nlInput && prompt) {
        nlInput.value = prompt;
        applyNaturalLanguageSearch();
      }
    });
  });

  const yStart = document.getElementById("yearStartInput");
  const yEnd = document.getElementById("yearEndInput");
  const updateYearLabel = () => {
    const valStart = parseInt(yStart.value) || 1990;
    const valEnd = parseInt(yEnd.value) || 2026;
    document.getElementById("yearRangeDisplay").textContent = `${valStart} - ${valEnd}`;
  };
  if (yStart && yEnd) {
    yStart.addEventListener("input", updateYearLabel);
    yEnd.addEventListener("input", updateYearLabel);
  }
}

// Collapsible Sidebar Accordions
function toggleAccordion(sectionId) {
  const section = document.getElementById(sectionId);
  const icon = document.getElementById(`icon-${sectionId}`);
  if (!section) return;

  const isHidden = section.classList.contains("hidden");
  const button = document.querySelector(`[aria-controls="${sectionId}"]`);
  if (isHidden) {
    section.classList.remove("hidden");
    if (icon) icon.style.transform = "rotate(0deg)";
    if (button) button.setAttribute("aria-expanded", "true");
  } else {
    section.classList.add("hidden");
    if (icon) icon.style.transform = "rotate(-90deg)";
    if (button) button.setAttribute("aria-expanded", "false");
  }
}

// Tech Info Modal Handlers
function openTechInfoModal() {
  const modal = document.getElementById("techInfoModal");
  if (modal) modal.classList.remove("hidden");
}

function closeTechInfoModal() {
  const modal = document.getElementById("techInfoModal");
  if (modal) modal.classList.add("hidden");
}

// Keyboard shortcuts (Esc closes modals and drawers)
function setupKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeExportModal();
      closeLyricsModal();
      closeApiModal();
      toggleMobileDrawer(false);
      closeFloatingPlayer();
    }
  });
}

// Mobile Filter Drawer Toggle
function toggleMobileDrawer(open) {
  const sidebar = document.getElementById("filterSidebar");
  const backdrop = document.getElementById("drawerBackdrop");
  const toggleBtn = document.getElementById("mobileFilterToggleBtn");

  if (!sidebar || !backdrop) return;

  if (open) {
    sidebar.classList.remove("-translate-x-full");
    backdrop.classList.remove("hidden");
    requestAnimationFrame(() => {
      backdrop.classList.remove("opacity-0");
    });
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
    document.body.classList.add("overflow-hidden", "lg:overflow-auto");
  } else {
    sidebar.classList.add("-translate-x-full");
    backdrop.classList.add("opacity-0");
    setTimeout(() => {
      backdrop.classList.add("hidden");
    }, 300);
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
    document.body.classList.remove("overflow-hidden", "lg:overflow-auto");
  }
}

// 1. Taksonomi ve Dinamik Alt Tür Chip'leri
async function loadTaxonomy() {
  try {
    const res = await fetch("/api/taxonomy");
    if (!res.ok) throw new Error("Taksonomi API yanıt vermedi");
    taxonomyData = await res.json();

    // Diller (localStorage ile kalıcı)
    const langSelect = document.getElementById("langSelect");
    if (langSelect && taxonomyData.languages) {
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
    }

    // Kategoriler
    const catSelect = document.getElementById("categorySelect");
    if (catSelect && taxonomyData.categories) {
      catSelect.innerHTML = "";
      taxonomyData.categories.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = `${c.name}${c.genres ? ` · ${c.genres.length} tür` : ""}`;
        catSelect.appendChild(opt);
      });
    }

    renderGenreChips("all");
  } catch (err) {
    console.error("Taksonomi yükleme hatası:", err);
    showToast("Kategoriler yüklenirken bir problem oluştu.", "warning");
  }
}

function renderGenreChips(catId) {
  const container = document.getElementById("genreChipsContainer");
  const countBadge = document.getElementById("genreCountBadge");
  const resultsLabel = document.getElementById("genreResultsLabel");
  const categoryDescription = document.getElementById("categoryDescription");
  const query = (document.getElementById("genreSearchInput")?.value || "").trim().toLocaleLowerCase("tr");
  if (!container) return;

  container.innerHTML = "";

  if (!taxonomyData) return;

  let genres = (taxonomyData.genres || []).filter(g => g !== "Tümü");
  let description = "Tüm türler arasından seçim yapın; birden fazla alt tür seçebilirsiniz.";
  if (catId !== "all") {
    const cat = taxonomyData.categories.find(c => c.id === catId);
    if (cat && cat.genres) {
      genres = cat.genres;
      description = `${cat.name.replace(/^\S+\s*/, "")} kategorisindeki alt türler.`;
    }
  }
  if (categoryDescription) categoryDescription.textContent = description;
  const visibleGenres = genres.filter(g => g.toLocaleLowerCase("tr").includes(query));

  visibleGenres.forEach(g => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "genre-chip text-[10px] bg-[#222] hover:bg-[#303030] text-gray-300 px-2.5 py-1.5 rounded-lg border border-[#333] transition select-none cursor-pointer focus:outline-none";
    chip.textContent = g.replace(/-/g, " ").toLocaleUpperCase("tr");
    const isSelected = selectedGenres.has(g);
    if (isSelected) chip.classList.add("chip-active");
    chip.setAttribute("aria-pressed", String(isSelected));

    chip.onclick = () => {
      if (selectedGenres.has(g)) {
        selectedGenres.delete(g);
      } else {
        selectedGenres.add(g);
      }
      renderGenreChips(catId);
    };
    container.appendChild(chip);
  });
  if (countBadge) countBadge.textContent = `${selectedGenres.size} seçili`;
  if (resultsLabel) resultsLabel.textContent = query
    ? `${visibleGenres.length} / ${genres.length} tür gösteriliyor`
    : `${genres.length} tür`;
}

function clearSelectedGenres() {
  selectedGenres.clear();
  renderGenreChips(document.getElementById("categorySelect")?.value || "all");
}

function setDecade(start, end) {
  const yStart = document.getElementById("yearStartInput");
  const yEnd = document.getElementById("yearEndInput");
  const display = document.getElementById("yearRangeDisplay");

  if (yStart && yEnd) {
    yStart.value = start;
    yEnd.value = end;
  }
  if (display) {
    display.textContent = `${start} - ${end}`;
  }
}

function setStrictness(level) {
  currentStrictness = level;
  ["loose", "balanced", "strict"].forEach(l => {
    const b = document.getElementById(`btn-${l}`);
    if (!b) return;
    if (l === level) {
      b.className = "text-[10px] py-1.5 bg-spotify-green text-black font-bold rounded-lg border border-spotify-green transition active:scale-95";
      b.setAttribute("aria-pressed", "true");
    } else {
      b.className = "text-[10px] py-1.5 bg-[#262626] hover:bg-spotify-hover rounded-lg border border-spotify-border text-gray-300 font-medium transition active:scale-95";
      b.setAttribute("aria-pressed", "false");
    }
  });

  const labels = {
    loose: "Gevşek (>=40 Skor)",
    balanced: "Dengeli (>=60 Skor)",
    strict: "Sıkı (>=75 Skor)"
  };
  const labelEl = document.getElementById("strictnessLabel");
  if (labelEl) {
    labelEl.textContent = labels[level] || "Dengeli";
  }
}

function resetFilters() {
  const lyricsInput = document.getElementById("lyricsInput");
  const nlInput = document.getElementById("nlInput");
  const langSelect = document.getElementById("langSelect");
  const catSelect = document.getElementById("categorySelect");
  const genreSearch = document.getElementById("genreSearchInput");
  const themeSelect = document.getElementById("themeSelect");
  const profSelect = document.getElementById("profanitySelect");
  const meanCb = document.getElementById("meaningfulCheckbox");

  if (lyricsInput) lyricsInput.value = "";
  if (nlInput) nlInput.value = "";
  if (langSelect) langSelect.value = "all";
  if (catSelect) catSelect.value = "all";
  if (genreSearch) genreSearch.value = "";
  if (themeSelect) themeSelect.value = "all";
  if (profSelect) profSelect.value = "all";
  if (meanCb) meanCb.checked = true;

  setDecade(1990, 2026);
  setStrictness("balanced");
  renderGenreChips("all");
  showToast("Filtreler sıfırlandı.", "info");
}

// 2. Doğal Dil Arama (NL Prompt)
async function applyNaturalLanguageSearch() {
  const nlInput = document.getElementById("nlInput");
  const nlBtn = document.getElementById("nlSearchBtn");
  const prompt = (nlInput ? nlInput.value : "").trim();
  if (!prompt) return;

  if (nlBtn) {
    nlBtn.disabled = true;
    nlBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Ayrıştırılıyor...</span>';
  }

  try {
    const res = await fetch("/api/nl-parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    });
    const data = await res.json();
    const f = data.filters || {};

    if (f.language && document.getElementById("langSelect")) {
      document.getElementById("langSelect").value = f.language;
    }
    if (f.category && document.getElementById("categorySelect")) {
      document.getElementById("categorySelect").value = f.category;
      renderGenreChips(f.category);
    }
    if (f.genres && Array.isArray(f.genres) && f.genres.length > 0) {
      selectedGenres.clear();
      f.genres.forEach(g => selectedGenres.add(g));
      renderGenreChips(f.category || document.getElementById("categorySelect")?.value || "all");
    }
    if (f.target_theme && document.getElementById("themeSelect")) {
      document.getElementById("themeSelect").value = f.target_theme;
    }
    if (f.profanity_mode && document.getElementById("profanitySelect")) {
      document.getElementById("profanitySelect").value = f.profanity_mode;
    }
    if (f.strictness) {
      setStrictness(f.strictness);
    }
    if (f.year_start && f.year_end) {
      setDecade(f.year_start, f.year_end);
    }
    if (f.avoid_themes && Array.isArray(f.avoid_themes)) {
      activeAvoidThemes = f.avoid_themes;
    } else {
      activeAvoidThemes = [];
    }
    if (f.lyrics_query && document.getElementById("lyricsInput")) {
      document.getElementById("lyricsInput").value = f.lyrics_query;
    }

    // Render extracted pills in UI
    renderExtractedPills(f);

    showToast("Doğal dil parametreleri tespit edildi & arama başlatıldı!", "success");
    // Otomatik aramayı tetikle
    executeSearch();
  } catch (err) {
    console.error("NL parse error:", err);
    showToast("Doğal dil ayrıştırmasında hata: " + err.message, "error");
  } finally {
    if (nlBtn) {
      nlBtn.disabled = false;
      nlBtn.innerHTML = '<span>Ayrıştır & Ara</span><i class="fa-solid fa-arrow-right text-xs"></i>';
    }
  }
}

// Render dynamic AI extracted pills
function renderExtractedPills(filters) {
  const container = document.getElementById("aiExtractedPillsContainer");
  const pillsList = document.getElementById("aiPillsList");
  if (!container || !pillsList) return;

  pillsList.innerHTML = "";
  const pills = [];

  if (filters.category && filters.category !== "all") {
    pills.push({ label: `Kategori: ${filters.category}`, icon: "fa-folder" });
  }
  if (filters.genres && filters.genres.length > 0) {
    pills.push({ label: `Tür: ${filters.genres.join(', ')}`, icon: "fa-tag" });
  }
  if (filters.language && filters.language !== "all") {
    pills.push({ label: `Dil: ${filters.language.toUpperCase()}`, icon: "fa-globe" });
  }
  if (filters.target_theme && filters.target_theme !== "all") {
    pills.push({ label: `Tema: #${filters.target_theme}`, icon: "fa-heart" });
  }
  if (filters.year_start && filters.year_end) {
    pills.push({ label: `Dönem: ${filters.year_start}-${filters.year_end}`, icon: "fa-calendar" });
  }
  if (filters.avoid_themes && filters.avoid_themes.length > 0) {
    pills.push({ label: `Hariç: ${filters.avoid_themes.join(', ')}`, icon: "fa-ban", color: "text-red-400 border-red-800/40 bg-red-950/20" });
  }
  if (filters.lyrics_query) {
    pills.push({ label: `Dize: "${filters.lyrics_query}"`, icon: "fa-quote-left" });
  }

  if (pills.length === 0) {
    container.classList.add("hidden");
    return;
  }

  pills.forEach(p => {
    const pill = document.createElement("span");
    pill.className = `px-2.5 py-1 rounded-lg border font-mono text-[10px] flex items-center gap-1.5 ${p.color || "text-emerald-300 border-emerald-800/40 bg-emerald-950/30"}`;
    pill.innerHTML = `<i class="fa-solid ${p.icon}"></i> ${escapeHtml(p.label)}`;
    pillsList.appendChild(pill);
  });

  container.classList.remove("hidden");
}

// 3. Auth Kontrolü (PKCE OAuth & Session)
async function checkAuthStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    const dot = document.getElementById("userStatusDot");
    const text = document.getElementById("userStatusText");

    if (data.is_user_authenticated && data.user_profile) {
      isUserLoggedIn = true;
      if (dot) dot.className = "w-2.5 h-2.5 rounded-full bg-spotify-green animate-pulse shrink-0";
      const u = data.user_profile;
      const avatarUrl = (u.images && u.images.length > 0) ? u.images[0].url : null;
      
      if (text) {
        text.innerHTML = "";
        const wrapper = document.createElement("div");
        wrapper.className = "flex items-center gap-1.5";

        if (avatarUrl) {
          const img = document.createElement("img");
          img.src = avatarUrl;
          img.alt = u.display_name || "Spotify";
          img.className = "w-4 h-4 rounded-full border border-spotify-green object-cover";
          wrapper.appendChild(img);
        }

        const nameSpan = document.createElement("span");
        nameSpan.className = "text-white font-bold text-xs truncate max-w-[120px]";
        nameSpan.textContent = u.display_name || u.id;
        wrapper.appendChild(nameSpan);

        const logoutLink = document.createElement("a");
        logoutLink.href = "/logout";
        logoutLink.title = "Çıkış Yap";
        logoutLink.className = "text-gray-400 hover:text-red-400 text-xs ml-1 pl-1 border-l border-gray-600";
        logoutLink.innerHTML = '<i class="fa-solid fa-arrow-right-from-bracket"></i>';
        wrapper.appendChild(logoutLink);

        text.appendChild(wrapper);
      }
    } else {
      isUserLoggedIn = false;
      if (dot) dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500/50 shrink-0";
      if (text) {
        text.innerHTML = `<a href="/login" class="text-white hover:text-spotify-green font-bold text-xs flex items-center gap-1.5 transition"><i class="fa-brands fa-spotify text-spotify-green text-sm"></i><span>Spotify ile Bağlan</span></a>`;
      }
    }
  } catch (err) {
    console.error("Auth status error:", err);
  }
}

// Skeleton Yükleyici (Layout Shift Engelleyici)
function renderSkeletonLoaders() {
  const container = document.getElementById("tracksContainer");
  if (!container) return;

  const skeletonCard = () => `
    <div class="flex flex-col p-3.5 rounded-xl border border-spotify-border bg-[#181818] gap-3">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center space-x-3.5 flex-1">
          <div class="w-4 h-4 rounded skeleton-box shrink-0"></div>
          <div class="w-5 h-3 rounded skeleton-box shrink-0"></div>
          <div class="w-12 h-12 rounded-lg skeleton-box shrink-0"></div>
          <div class="flex-1 space-y-2">
            <div class="w-2/5 h-4 rounded skeleton-box"></div>
            <div class="w-1/3 h-3 rounded skeleton-box"></div>
          </div>
        </div>
        <div class="flex gap-2">
          <div class="w-16 h-7 rounded-lg skeleton-box"></div>
          <div class="w-16 h-7 rounded-lg skeleton-box"></div>
        </div>
      </div>
      <div class="w-full h-8 rounded-lg skeleton-box"></div>
    </div>
  `;

  container.innerHTML = Array(4).fill(0).map(skeletonCard).join('');
}

// 4. Ana Arama Yürütücüsü (AbortController ile Yarış Koşulu Korumalı)
async function executeSearch() {
  if (searchAbortController) {
    searchAbortController.abort();
  }
  searchAbortController = new AbortController();

  const lyrics = (document.getElementById("lyricsInput")?.value || "").trim();
  const lang = document.getElementById("langSelect")?.value || "all";
  const category = document.getElementById("categorySelect")?.value || "all";
  const yearStart = parseInt(document.getElementById("yearStartInput")?.value) || 1990;
  const yearEnd = parseInt(document.getElementById("yearEndInput")?.value) || 2026;
  const theme = document.getElementById("themeSelect")?.value || "all";
  const profanity = document.getElementById("profanitySelect")?.value || "all";
  const limit = parseInt(document.getElementById("limitRange")?.value) || 20;
  const filterMeaningful = document.getElementById("meaningfulCheckbox")?.checked ?? true;

  const searchBtn = document.getElementById("searchBtn");
  if (searchBtn) {
    searchBtn.disabled = true;
    searchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Taranıyor...</span>';
  }

  // En fazla 25 saniye sonra zaman aşımı vererek sonsuz 'Taranıyor...' kilitlenmesini engelle
  const timeoutId = setTimeout(() => {
    if (searchAbortController) {
      searchAbortController.abort();
      showToast("Arama zaman aşımına uğradı. Lütfen filtreleri gevşetip tekrar deneyin.", "warning");
    }
  }, 25000);

  // Mobilde çekmeceyi kapat ki sonuçlar anında görünsün
  toggleMobileDrawer(false);

  // Skeleton UI aktif et
  renderSkeletonLoaders();
  announceToScreenReader("Arama başlatıldı, müzik kütüphanesi taranıyor...");

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: searchAbortController.signal,
      body: JSON.stringify({
        lyrics_query: lyrics,
        language: lang,
        category: category,
        genres: Array.from(selectedGenres),
        year_start: yearStart,
        year_end: yearEnd,
        strictness: currentStrictness,
        profanity_mode: profanity,
        target_theme: theme,
        avoid_themes: activeAvoidThemes,
        filter_meaningful: filterMeaningful,
        limit: limit
      })
    });

    if (!res.ok) {
      const errorJson = await res.json().catch(() => ({}));
      throw new Error(errorJson.detail || "Sunucu aramayı işleyemedi.");
    }

    const data = await res.json();
    currentTracks = data.tracks || [];
    selectedTrackUris.clear();
    updateSelectionUI();

    // Eleme İstatistikleri Bannerı
    const statsBanner = document.getElementById("statsSummaryBanner");
    const statsText = document.getElementById("statsSummaryText");
    const stats = data.stats;

    if (statsBanner && statsText && stats) {
      if (stats.found_count < stats.requested_limit) {
        statsBanner.classList.remove("hidden");
        const details = [];
        if (stats.eliminated_no_lyrics > 0) details.push(`${stats.eliminated_no_lyrics} sözsüz`);
        if (stats.eliminated_genre_mismatch > 0) details.push(`${stats.eliminated_genre_mismatch} tür uyuşmazlığı`);
        if (stats.eliminated_meaningful_filter > 0) details.push(`${stats.eliminated_meaningful_filter} anlamsız/mumble`);
        if (stats.eliminated_language_mismatch > 0) details.push(`${stats.eliminated_language_mismatch} farklı dil`);

        statsText.innerHTML = `<b>${stats.requested_limit}</b> hedefinden <b>${stats.found_count}</b> parça listelendi: ${details.join(', ')} nedeniyle elendi.`;
      } else {
        statsBanner.classList.add("hidden");
      }
    }

    renderTracks(currentTracks);
    announceToScreenReader(`${currentTracks.length} parça başarıyla bulundu.`);
  } catch (err) {
    if (err.name === 'AbortEvent' || err.name === 'AbortError') {
      console.log("Önceki arama isteği iptal edildi.");
      return;
    }
    const container = document.getElementById("tracksContainer");
    if (container) {
      container.innerHTML = `
        <div class="h-64 flex flex-col items-center justify-center text-center p-6 text-red-400">
          <i class="fa-solid fa-triangle-exclamation text-3xl mb-3"></i>
          <p class="text-sm font-semibold text-white">Arama sırasında hata oluştu</p>
          <p class="text-xs text-gray-400 mt-1 max-w-sm">${escapeHtml(err.message)}</p>
          <button onclick="executeSearch()" class="mt-4 px-4 py-2 bg-spotify-surface hover:bg-spotify-hover text-white text-xs rounded-xl border border-spotify-border transition">
            Tekrar Dene
          </button>
        </div>
      `;
    }
    showToast("Arama başarısız: " + err.message, "error");
  } finally {
    clearTimeout(timeoutId);
    if (searchBtn) {
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i><span>Şarkıları Bul</span>';
    }
  }
}

function relaxFiltersAndSearch() {
  setStrictness("loose");
  const meanCb = document.getElementById("meaningfulCheckbox");
  if (meanCb) meanCb.checked = false;
  const catSel = document.getElementById("categorySelect");
  if (catSel) catSel.value = "all";
  setDecade(1980, 2026);
  executeSearch();
  showToast("Filtreler gevşetildi ve arama yenilendi.", "info");
}

// 4.1. Anlık Sıralama Değiştirici
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
      showToast("Sıralama güncellendi.", "info");
    }
  } catch (err) {
    console.error("Sıralama hatası:", err);
    showToast("Sıralama değiştirilemedi.", "error");
  }
}

// 4.2. Benzer Şarkı Bulucu
async function findSimilarToTrack(trackId) {
  const target = currentTracks.find(t => t.id === trackId);
  if (!target) return;

  const btn = document.getElementById(`btn-sim-${trackId}`);
  if (btn) btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-[10px]"></i>';

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
      showToast(`"${target.name}" ile benzer 5 parça öne alındı.`, "success");
    } else {
      showToast("Mevcut havuzda yeterince benzer parça bulunamadı.", "warning");
    }
  } catch (err) {
    console.error("Benzer bulma hatası:", err);
    showToast("Benzer şarkılar aranırken hata oluştu.", "error");
  } finally {
    if (btn) btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles text-[10px]"></i> Benzer';
  }
}

// Güvenli URL ve XSS Yardımcısı
function sanitizeExternalUrl(url) {
  if (!url || typeof url !== 'string') return "#";
  try {
    const parsed = new URL(url, window.location.origin);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return parsed.href;
    }
  } catch {
    // Geçersiz URL
  }
  return "#";
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// 5. Kartların Render Edilmesi (XSS-Safe DOM İnşası & WCAG Uyumlu)
function renderTracks(tracks) {
  const container = document.getElementById("tracksContainer");
  const countBadge = document.getElementById("resultsCountBadge");
  const actions = document.getElementById("selectionActions");
  const sortContainer = document.getElementById("sortContainer");

  if (!container) return;
  container.innerHTML = "";

  if (!tracks || tracks.length === 0) {
    if (countBadge) countBadge.classList.add("hidden");
    if (actions) actions.classList.add("hidden");
    if (sortContainer) sortContainer.classList.add("hidden");
    
    container.innerHTML = `
      <div class="h-64 flex flex-col items-center justify-center text-center p-6 text-spotify-textMuted">
        <div class="w-12 h-12 rounded-full bg-spotify-surface flex items-center justify-center text-2xl mb-3 text-spotify-textSubtle">
          <i class="fa-solid fa-microphone-slash"></i>
        </div>
        <p class="text-sm font-semibold text-white">Kriterlere Uygun Şarkı Bulunamadı</p>
        <p class="text-xs text-spotify-textMuted mt-1 max-w-sm">Filtre katılık seviyesini 'Gevşek' yapmayı veya yıl aralığını genişletmeyi deneyin.</p>
        <button onclick="relaxFiltersAndSearch()" class="mt-4 text-xs bg-spotify-green text-black font-bold px-4 py-2 rounded-xl hover:bg-spotify-hoverGreen transition shadow-md">
          Filtreleri Gevşet ve Tekrar Dene
        </button>
      </div>
    `;
    return;
  }

  if (countBadge) {
    countBadge.classList.remove("hidden");
    countBadge.textContent = `${tracks.length} parça`;
  }
  if (actions) actions.classList.remove("hidden");
  if (sortContainer) sortContainer.classList.remove("hidden");

  // İlk aramada tüm parçaları varsayılan seç
  if (selectedTrackUris.size === 0) {
    tracks.forEach(t => selectedTrackUris.add(t.uri));
  }
  updateSelectionUI();

  tracks.forEach((track, index) => {
    const isSelected = selectedTrackUris.has(track.uri);
    
    // Güvenli DOM Kök Kartı
    const card = document.createElement("article");
    card.className = `flex flex-col p-3 sm:p-3.5 rounded-xl transition duration-150 border gap-2.5 ${
      isSelected ? "bg-[#1b1b1b] border-spotify-green/60 shadow-lg" : "bg-spotify-card border-spotify-border hover:bg-spotify-hover"
    }`;
    card.id = `track-${track.id}`;
    card.setAttribute("aria-label", `${track.name} - ${track.artist}`);

    // Üst Bilgi Satırı
    const topRow = document.createElement("div");
    topRow.className = "flex flex-col sm:flex-row sm:items-center justify-between gap-3";

    // Sol Taraf (Checkbox, Sıra, Albüm Kapağı, Başlık/Sanatçı)
    const leftInfo = document.createElement("div");
    leftInfo.className = "flex items-start space-x-3 flex-1 min-w-0";

    // Seçim Kutusu
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = isSelected;
    checkbox.className = "mt-1.5 w-4 h-4 rounded text-spotify-green accent-spotify-green cursor-pointer shrink-0";
    checkbox.setAttribute("aria-label", `${track.name} parçasını seç`);
    checkbox.onchange = (e) => toggleTrackSelection(track.uri, e.target);
    leftInfo.appendChild(checkbox);

    // İndeks
    const indexSpan = document.createElement("span");
    indexSpan.className = "mt-1.5 text-xs font-mono font-bold text-spotify-textSubtle w-5 text-right shrink-0";
    indexSpan.textContent = (index + 1).toString();
    leftInfo.appendChild(indexSpan);

    // Albüm Kapağı & 30sn Önizleme Overlay
    const imgWrapper = document.createElement("div");
    imgWrapper.className = "relative shrink-0 group";

    const albumImg = document.createElement("img");
    albumImg.src = track.image_url || "https://placehold.co/48x48/282828/fff?text=🎵";
    albumImg.alt = `${track.name} albüm kapağı`;
    albumImg.loading = "lazy";
    albumImg.className = "w-12 h-12 rounded-lg object-cover shadow border border-spotify-border";
    imgWrapper.appendChild(albumImg);

    if (track.preview_url) {
      const playOverlay = document.createElement("button");
      playOverlay.type = "button";
      playOverlay.className = "absolute inset-0 flex items-center justify-center bg-black/60 rounded-lg opacity-0 group-hover:opacity-100 focus:opacity-100 transition text-spotify-green hover:text-white";
      playOverlay.setAttribute("aria-label", `${track.name} önizlemesini dinle`);
      playOverlay.innerHTML = '<i class="fa-solid fa-play text-xs"></i>';
      playOverlay.onclick = () => playPreviewAudio(track.preview_url, track.name, track.artist, track.id);
      imgWrapper.appendChild(playOverlay);
    }
    leftInfo.appendChild(imgWrapper);

    // Şarkı Detay Bilgileri
    const metaContainer = document.createElement("div");
    metaContainer.className = "min-w-0 flex-1";

    // Başlık & Rozetler
    const titleRow = document.createElement("div");
    titleRow.className = "flex items-center gap-2 flex-wrap";

    const titleLink = document.createElement("a");
    titleLink.href = sanitizeExternalUrl(track.external_url);
    titleLink.target = "_blank";
    titleLink.rel = "noopener noreferrer";
    titleLink.className = "text-sm font-bold text-white hover:text-spotify-green hover:underline truncate max-w-full sm:max-w-md";
    titleLink.textContent = track.name;
    titleRow.appendChild(titleLink);

    // Puan Rozeti
    if (track.analysis_status === 'tamamlandi' && track.meaningful_score !== null) {
      const scoreBadge = document.createElement("span");
      const isHigh = track.meaningful_score >= 70;
      scoreBadge.className = `text-[10px] px-2 py-0.5 rounded-full font-bold border font-mono ${
        isHigh ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800' : 'text-amber-400 bg-amber-950/60 border-amber-800'
      }`;
      scoreBadge.textContent = `🎯 ${track.meaningful_score} Puan`;
      titleRow.appendChild(scoreBadge);
    } else if (track.analysis_status === 'soz_bulunamadi') {
      const noLyricsBadge = document.createElement("span");
      noLyricsBadge.className = "text-[10px] px-2 py-0.5 rounded-full font-medium border text-gray-400 bg-gray-800/60 border-gray-700";
      noLyricsBadge.textContent = "🔍 Söz Bulunamadı";
      titleRow.appendChild(noLyricsBadge);
    }

    // Tür Rozeti
    if (track.genre_badge) {
      const genreBadge = document.createElement("span");
      genreBadge.className = "text-[10px] bg-[#222] text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-900/60 font-medium";
      genreBadge.textContent = `🏷️ ${track.genre_badge}`;
      titleRow.appendChild(genreBadge);
    }

    // Benzerlik Rozeti
    if (track.similarity_info) {
      const simBadge = document.createElement("span");
      simBadge.className = "text-[10px] bg-purple-950/60 text-purple-300 px-2 py-0.5 rounded-full border border-purple-800 font-bold font-mono";
      simBadge.textContent = `✨ %${track.similarity_info.overall_similarity} Benzer`;
      titleRow.appendChild(simBadge);
    }

    // Tema Etiketi
    if (track.theme && track.theme !== 'genel') {
      const themeBadge = document.createElement("span");
      themeBadge.className = "text-[10px] bg-[#222] text-gray-300 px-2 py-0.5 rounded-full border border-gray-700 font-medium";
      themeBadge.textContent = `#${track.theme}`;
      titleRow.appendChild(themeBadge);
    }

    metaContainer.appendChild(titleRow);

    // Sanatçı & Albüm Satırı
    const artistAlbum = document.createElement("p");
    artistAlbum.className = "text-xs text-spotify-textMuted truncate mt-0.5";
    artistAlbum.textContent = `${track.artist} • ${track.album}`;
    metaContainer.appendChild(artistAlbum);

    // Anlam Gerekçesi (Varsa)
    if (track.meaningful_reason) {
      const reasonP = document.createElement("p");
      reasonP.className = "text-[10px] text-gray-400 mt-1";
      reasonP.innerHTML = `<span class="text-spotify-textSubtle">Gerekçe:</span> ${escapeHtml(track.meaningful_reason)}`;
      metaContainer.appendChild(reasonP);
    }

    // Söz Kesiti (Snippet)
    if (track.snippet) {
      const snippetBox = document.createElement("div");
      snippetBox.className = "mt-1.5 text-[11px] text-emerald-300 bg-[#131c15] p-2 rounded-lg border border-emerald-900/50 italic";
      snippetBox.textContent = `💬 "...${track.snippet}..."`;
      metaContainer.appendChild(snippetBox);
    }

    leftInfo.appendChild(metaContainer);
    topRow.appendChild(leftInfo);

    // Sağ Aksiyon Butonları
    const actionsRow = document.createElement("div");
    actionsRow.className = "flex items-center space-x-1.5 shrink-0 self-end sm:self-center";

    // Benzerini Bul Butonu
    const similarBtn = document.createElement("button");
    similarBtn.type = "button";
    similarBtn.id = `btn-sim-${track.id}`;
    similarBtn.className = "text-[11px] bg-[#252525] hover:bg-purple-900/40 text-purple-300 px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1.5 border border-purple-800/40 active:scale-95";
    similarBtn.title = "Bu parçaya anlamsal olarak en yakın şarkıları getir";
    similarBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles text-[10px]"></i><span>Benzer</span>';
    similarBtn.onclick = () => findSimilarToTrack(track.id);
    actionsRow.appendChild(similarBtn);

    // Metrikler Butonu
    const metricsBtn = document.createElement("button");
    metricsBtn.type = "button";
    metricsBtn.className = "text-[11px] bg-[#252525] hover:bg-spotify-hover text-gray-300 px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1.5 border border-spotify-border active:scale-95";
    metricsBtn.title = "NLP ve Anlam Analiz Metriklerini Görüntüle";
    metricsBtn.innerHTML = '<i class="fa-solid fa-chart-simple text-[10px]"></i><span>Metrikler</span>';
    metricsBtn.onclick = () => toggleDetails(track.id);
    actionsRow.appendChild(metricsBtn);

    // Söz Butonu
    const lyricsBtn = document.createElement("button");
    lyricsBtn.type = "button";
    lyricsBtn.className = "text-[11px] bg-[#252525] hover:bg-spotify-hover text-gray-300 px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1.5 border border-spotify-border active:scale-95";
    lyricsBtn.title = "Şarkı Sözlerini Aç";
    lyricsBtn.innerHTML = '<i class="fa-solid fa-align-left text-[10px]"></i><span>Söz</span>';
    lyricsBtn.onclick = () => viewLyrics(track.name, track.artist);
    actionsRow.appendChild(lyricsBtn);

    // Spotify Harici Bağlantı Butonu
    const spotifyExtBtn = document.createElement("a");
    spotifyExtBtn.href = sanitizeExternalUrl(track.external_url);
    spotifyExtBtn.target = "_blank";
    spotifyExtBtn.rel = "noopener noreferrer";
    spotifyExtBtn.className = "text-xs bg-[#252525] hover:bg-spotify-green hover:text-black text-gray-200 px-2.5 py-1.5 rounded-lg transition font-medium flex items-center gap-1 border border-spotify-border";
    spotifyExtBtn.innerHTML = '<span>Spotify ↗</span>';
    actionsRow.appendChild(spotifyExtBtn);

    topRow.appendChild(actionsRow);
    card.appendChild(topRow);

    // Genişletilebilir Analiz Metrik Paneli
    const comp = track.components || {};
    const detailsPanel = document.createElement("div");
    detailsPanel.id = `details-${track.id}`;
    detailsPanel.className = "hidden border-t border-spotify-border/80 pt-2.5 mt-1 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-gray-300 bg-[#141414] p-2.5 rounded-lg font-mono";
    
    detailsPanel.innerHTML = `
      <div>
        <span class="text-spotify-textSubtle block font-sans">Kelime Zenginliği:</span>
        <b class="text-white">${comp.vocab_diversity !== undefined ? comp.vocab_diversity + '/100' : (track.vocab_richness || 'N/A')}</b>
      </div>
      <div>
        <span class="text-spotify-textSubtle block font-sans">Satır Çeşitliliği:</span>
        <b class="text-white">${comp.repetition !== undefined ? comp.repetition + '/100' : 'N/A'}</b>
      </div>
      <div>
        <span class="text-spotify-textSubtle block font-sans">Ad-Lib Temizliği:</span>
        <b class="text-white">${comp.adlib_cleanliness !== undefined ? comp.adlib_cleanliness + '/100' : 'N/A'}</b>
      </div>
      <div>
        <span class="text-spotify-textSubtle block font-sans">Tema Derinliği:</span>
        <b class="text-white">${comp.theme_depth !== undefined ? comp.theme_depth + '/100' : 'N/A'}</b>
      </div>
    `;

    card.appendChild(detailsPanel);
    container.appendChild(card);
  });
}

function toggleDetails(trackId) {
  const el = document.getElementById(`details-${trackId}`);
  if (el) el.classList.toggle("hidden");
}

// 6. Gelişmiş Önizleme ve Floating Player
function setupAudioEvents() {
  const audio = document.getElementById("audioPreviewPlayer");
  const progressFill = document.getElementById("floatingProgressFill");
  const timeDisplay = document.getElementById("floatingTimeDisplay");
  const playIcon = document.getElementById("floatingPlayIcon");

  if (!audio) return;

  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;
    const current = audio.currentTime;
    const dur = audio.duration;
    const pct = (current / dur) * 100;
    if (progressFill) progressFill.style.width = `${pct}%`;

    const formatTime = (secs) => {
      const m = Math.floor(secs / 60);
      const s = Math.floor(secs % 60);
      return `${m}:${s < 10 ? '0' : ''}${s}`;
    };

    if (timeDisplay) {
      timeDisplay.textContent = `${formatTime(current)} / ${formatTime(dur)}`;
    }
  });

  audio.addEventListener("ended", () => {
    if (playIcon) playIcon.className = "fa-solid fa-play text-xs";
    currentlyPlayingUrl = null;
  });

  audio.addEventListener("pause", () => {
    if (playIcon) playIcon.className = "fa-solid fa-play text-xs";
  });

  audio.addEventListener("play", () => {
    if (playIcon) playIcon.className = "fa-solid fa-pause text-xs";
  });
}

function sendUserFeedback(trackId, actionType) {
  if (!trackId) return;
  const currentTheme = document.getElementById("themeSelect")?.value || "all";
  fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      track_id: trackId,
      action_type: actionType,
      user_theme: currentTheme !== "all" ? currentTheme : null
    })
  }).catch(e => console.debug("Feedback log error:", e));
}

function playPreviewAudio(url, title, artist, trackId = null) {
  const audio = document.getElementById("audioPreviewPlayer");
  const floatingBar = document.getElementById("floatingPlayerBar");
  const trackNameEl = document.getElementById("floatingTrackName");
  const playIcon = document.getElementById("floatingPlayIcon");

  if (!audio || !floatingBar) return;

  if (currentlyPlayingUrl === url && !audio.paused) {
    audio.pause();
    currentlyPlayingUrl = null;
    return;
  }

  if (trackId) {
    sendUserFeedback(trackId, "play_preview");
  }

  audio.src = url;
  audio.play().then(() => {
    currentlyPlayingUrl = url;
    if (trackNameEl) trackNameEl.textContent = `${title} - ${artist}`;
    if (playIcon) playIcon.className = "fa-solid fa-pause text-xs";
    floatingBar.classList.remove("hidden");
  }).catch(err => {
    console.error("Audio playback error:", err);
    showToast("30 sn önizleme çalınamadı.", "warning");
  });
}

function toggleFloatingPlayPause() {
  const audio = document.getElementById("audioPreviewPlayer");
  if (!audio) return;

  if (audio.paused) {
    audio.play();
  } else {
    audio.pause();
  }
}

function seekFloatingAudio(event) {
  const audio = document.getElementById("audioPreviewPlayer");
  const bar = document.getElementById("floatingProgressBar");
  if (!audio || !bar || !audio.duration) return;

  const rect = bar.getBoundingClientRect();
  const clickX = event.clientX - rect.left;
  const width = rect.width;
  const seekRatio = Math.max(0, Math.min(1, clickX / width));
  audio.currentTime = seekRatio * audio.duration;
}

function closeFloatingPlayer() {
  const audio = document.getElementById("audioPreviewPlayer");
  const floatingBar = document.getElementById("floatingPlayerBar");
  if (audio) audio.pause();
  if (floatingBar) floatingBar.classList.add("hidden");
  currentlyPlayingUrl = null;
}

// 7. Seçim Yönetimi
function toggleTrackSelection(uri, checkbox) {
  if (checkbox.checked) {
    selectedTrackUris.add(uri);
  } else {
    selectedTrackUris.delete(uri);
  }
  updateSelectionUI();
}

function toggleSelectAll() {
  const allSelected = selectedTrackUris.size === currentTracks.length;
  if (allSelected) {
    selectedTrackUris.clear();
  } else {
    currentTracks.forEach(t => selectedTrackUris.add(t.uri));
  }
  renderTracks(currentTracks);
}

function updateSelectionUI() {
  const count = selectedTrackUris.size;
  const countLabel = document.getElementById("selectedCount");
  if (countLabel) countLabel.textContent = `${count} Seçili`;

  const exportBtn = document.getElementById("exportBtn");
  const selectAllBtn = document.getElementById("selectAllBtn");

  if (selectAllBtn) {
    selectAllBtn.textContent = (count === currentTracks.length && count > 0) ? "Seçimi Kaldır" : "Hepsini Seç";
  }

  if (exportBtn) {
    if (count > 0) {
      exportBtn.disabled = false;
      exportBtn.className = "w-full bg-spotify-green hover:bg-spotify-hoverGreen text-black font-bold py-2.5 px-3 rounded-xl text-xs flex items-center justify-center gap-2 transition cursor-pointer shadow-lg shadow-green-500/20 active:scale-[0.98]";
    } else {
      exportBtn.disabled = true;
      exportBtn.className = "w-full bg-[#282828] text-gray-500 font-semibold py-2.5 px-3 rounded-xl text-xs flex items-center justify-center gap-2 transition cursor-not-allowed border border-spotify-border";
    }
  }
}

// 8. Şarkı Sözleri (Lyrics) İnceleme Modalı
async function viewLyrics(title, artist) {
  const modal = document.getElementById("lyricsModal");
  if (!modal) return;

  document.getElementById("lyricsModalTitle").textContent = title;
  document.getElementById("lyricsModalArtist").textContent = artist;
  const content = document.getElementById("lyricsModalContent");

  content.innerHTML = `
    <div class="h-40 flex flex-col items-center justify-center text-spotify-textMuted">
      <i class="fa-solid fa-spinner fa-spin text-2xl text-spotify-green mb-2"></i>
      <span class="text-xs">LRCLIB & Genius arşivinden çekiliyor...</span>
    </div>
  `;
  modal.classList.remove("hidden");

  try {
    const res = await fetch("/api/get-lyrics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_name: title, artist_name: artist })
    });
    const data = await res.json();

    if (data.lyrics && data.lyrics.trim().length > 0) {
      const pre = document.createElement("pre");
      pre.className = "font-sans text-xs text-gray-200 whitespace-pre-wrap leading-relaxed select-text p-2";
      pre.textContent = data.lyrics;
      content.innerHTML = "";
      content.appendChild(pre);
    } else {
      content.innerHTML = `
        <div class="h-32 flex flex-col items-center justify-center text-spotify-textMuted text-center p-4">
          <i class="fa-solid fa-microphone-slash text-2xl mb-2 text-spotify-textSubtle"></i>
          <span class="text-xs">Bu parça için sözler henüz arşivde bulunamadı.</span>
        </div>
      `;
    }
  } catch (err) {
    content.innerHTML = `<div class="text-red-400 text-xs p-3">Hata: ${escapeHtml(err.message)}</div>`;
  }
}

function closeLyricsModal() {
  const modal = document.getElementById("lyricsModal");
  if (modal) modal.classList.add("hidden");
}

// 9. Playlist Aktarımı (ISRC Tekilleştirme Destekli)
function openExportModal() {
  if (!isUserLoggedIn) {
    showToast("Spotify hesabınıza aktarım yapmak için giriş yapmalısınız.", "warning");
    setTimeout(() => {
      window.location.href = "/login";
    }, 1200);
    return;
  }
  const badge = document.getElementById("exportCountBadge");
  if (badge) badge.textContent = selectedTrackUris.size;
  const statusDiv = document.getElementById("exportStatus");
  if (statusDiv) statusDiv.innerHTML = "";
  
  const modal = document.getElementById("exportModal");
  if (modal) modal.classList.remove("hidden");
}

function closeExportModal() {
  const modal = document.getElementById("exportModal");
  if (modal) modal.classList.add("hidden");
}

async function exportToSpotify() {
  const nameInput = document.getElementById("playlistNameInput");
  const descInput = document.getElementById("playlistDescInput");
  const name = (nameInput ? nameInput.value : "").trim() || "Keşif Listem";
  const desc = (descInput ? descInput.value : "").trim();
  const uris = Array.from(selectedTrackUris);
  const statusDiv = document.getElementById("exportStatus");
  const confirmBtn = document.getElementById("confirmExportBtn");

  if (!confirmBtn) return;
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>Aktarılıyor...</span>';

  try {
    const res = await fetch("/api/create-playlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, track_uris: uris, description: desc })
    });
    const data = await res.json();

    if (data.success) {
      if (statusDiv) {
        statusDiv.innerHTML = `
          <div class="p-3 bg-green-950/70 border border-green-700/60 rounded-xl text-green-300 text-xs">
            ✅ <b>${data.track_count}</b> şarkı ISRC tekilleştirmesiyle Spotify hesabınıza aktarıldı!<br>
            <a href="${sanitizeExternalUrl(data.url)}" target="_blank" rel="noopener noreferrer" class="underline font-bold text-white hover:text-spotify-green mt-1.5 inline-block">
              Spotify'da Çalma Listesini Aç ↗
            </a>
          </div>
        `;
      }
      confirmBtn.innerHTML = '<span>Tamamlandı!</span>';
      showToast("Çalma listesi Spotify hesabınızda başarıyla oluşturuldu!", "success");

      // Başarılı aktarım geri bildirimlerini dinamik ranker'a kaydet
      currentTracks.filter(t => selectedTrackUris.has(t.uri)).forEach(t => {
        sendUserFeedback(t.id, "export");
      });
    } else {
      if (statusDiv) {
        statusDiv.innerHTML = `<span class="text-red-400">Hata: ${escapeHtml(data.detail || "Aktarım başarısız oldu")}</span>`;
      }
      confirmBtn.disabled = false;
      confirmBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i><span>Tekrar Dene</span>';
      showToast("Aktarım başarısız.", "error");
    }
  } catch (err) {
    if (statusDiv) {
      statusDiv.innerHTML = `<span class="text-red-400">Hata: ${escapeHtml(err.message)}</span>`;
    }
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i><span>Tekrar Dene</span>';
    showToast("Hata oluştu: " + err.message, "error");
  }
}

// 10. API Ayarları
function openApiModal() {
  const modal = document.getElementById("apiModal");
  if (modal) modal.classList.remove("hidden");
}

function closeApiModal() {
  const modal = document.getElementById("apiModal");
  if (modal) modal.classList.add("hidden");
}

async function saveApiKeys() {
  const clientId = document.getElementById("modalClientId")?.value.trim();
  const clientSecret = document.getElementById("modalClientSecret")?.value.trim();
  const status = document.getElementById("modalStatus");

  if (!clientId || !clientSecret) {
    if (status) status.innerHTML = '<span class="text-red-400">Lütfen Client ID ve Secret alanlarını eksiksiz doldurun.</span>';
    return;
  }

  if (status) status.innerHTML = '<span class="text-spotify-textMuted">Doğrulanıyor...</span>';

  try {
    const res = await fetch("/api/save-credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret })
    });
    const data = await res.json();

    if (data.success) {
      if (status) status.innerHTML = '<span class="text-emerald-400">✅ Başarıyla bağlandı! Sayfa yenileniyor...</span>';
      showToast("API anahtarları kaydedildi.", "success");
      setTimeout(() => {
        closeApiModal();
        window.location.reload();
      }, 1000);
    } else {
      if (status) status.innerHTML = '<span class="text-red-400">❌ Bilgiler geçersiz veya Spotify reddetti.</span>';
    }
  } catch (err) {
    if (status) status.innerHTML = `<span class="text-red-400">Hata: ${escapeHtml(err.message)}</span>`;
  }
}
