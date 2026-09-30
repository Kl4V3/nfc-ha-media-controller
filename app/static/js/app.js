/**
 * NFC Media Controller - Frontend Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
    // Translation helper
    function t(key, fallback = "") {
        if (window.I18N && window.I18N[key]) {
            return window.I18N[key];
        }
        return fallback || key;
    }

    // Display filter for NFC tag IDs (e.g. 04bcd968b82a81 -> 04-BC-D9-68-B8-2A-81)
    function formatTagId(id) {
        if (!id || typeof id !== 'string') return id || '';
        const clean = id.replace(/[^0-9a-fA-F]/g, '');
        if (clean.length >= 4 && clean.length % 2 === 0 && clean.length === id.length) {
            return clean.toUpperCase().match(/.{1,2}/g).join('-');
        }
        return id;
    }

    // State
    let tagsList = [];
    let readersList = [];
    let historyList = [];
    let absContentList = [];
    let absCurrentTab = "series"; // "series", "items", or "podcasts"
    let modalAbsCurrentTab = "series";
    let ws = null;
    let currentEditingTagId = null;

    // DOM Elements - Theme Toggle
    const btnThemeToggle = document.getElementById("btn-theme-toggle");
    const themeSunIcon = document.getElementById("theme-sun-icon");
    const themeMoonIcon = document.getElementById("theme-moon-icon");

    // DOM Elements - Status
    const elStatusMqtt = document.getElementById("status-mqtt");
    const elStatusAbs = document.getElementById("status-abs");
    const elStatusWs = document.getElementById("status-ws");
    const elMobileDotMqtt = document.getElementById("mobile-dot-mqtt");
    const elMobileDotAbs = document.getElementById("mobile-dot-abs");
    const elMobileDotWs = document.getElementById("mobile-dot-ws");

    // DOM Elements - Tabs
    const tabButtons = document.querySelectorAll(".tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");

    // DOM Elements - Tags Table & Mobile Cards
    const elTagsTableBody = document.getElementById("tags-table-body");
    const elTagsMobileList = document.getElementById("tags-mobile-list");
    const elTagsEmptyState = document.getElementById("tags-empty-state");
    const elTagsCount = document.getElementById("tags-count");
    const elSearchInput = document.getElementById("tags-search-input");
    const elFilterStatus = document.getElementById("tags-filter-status");
    const elFilterType = document.getElementById("tags-filter-type");
    const btnAddTag = document.getElementById("btn-add-tag");
    const btnDeleteUnconfigured = document.getElementById("btn-delete-unconfigured");

    // DOM Elements - Readers Table & Mobile Cards
    const elReadersTableBody = document.getElementById("readers-table-body");
    const elReadersMobileList = document.getElementById("readers-mobile-list");
    const elReadersEmptyState = document.getElementById("readers-empty-state");
    const elReadersCount = document.getElementById("readers-count");
    const btnAddReader = document.getElementById("btn-add-reader");

    // DOM Elements - Mobile FAB
    const btnMobileFab = document.getElementById("mobile-fab");

    // DOM Elements - History
    const elHistoryTableBody = document.getElementById("history-table-body");
    const btnRefreshHistory = document.getElementById("btn-refresh-history");

    // DOM Elements - Live Toast Banner
    const elLiveBanner = document.getElementById("live-scan-banner");
    const elLiveEventType = document.getElementById("live-event-type");
    const elLiveTagName = document.getElementById("live-tag-name");
    const elLiveEventDetails = document.getElementById("live-event-details");
    const btnLiveEdit = document.getElementById("live-banner-edit-btn");
    const btnCloseLiveToast = document.getElementById("btn-close-live-toast");

    // DOM Elements - Modals
    const elTagModal = document.getElementById("tag-modal");
    const elTagForm = document.getElementById("tag-form");
    const elTagModalTitle = document.getElementById("tag-modal-title");
    const inputTagId = document.getElementById("tag-id-input");
    const inputTagAlias = document.getElementById("tag-alias-input");
    const selectTagActionType = document.getElementById("tag-action-type");
    const groupLibraryId = document.getElementById("group-library-id");
    const inputTagLibraryId = document.getElementById("tag-library-id");
    const inputTagVolume = document.getElementById("tag-volume");
    const inputTagTargetId = document.getElementById("tag-target-id");
    const groupStartFromBeginning = document.getElementById("group-start-from-beginning");
    const checkTagStartFromBeginning = document.getElementById("tag-start-from-beginning");
    const groupRandom = document.getElementById("group-random");
    const checkTagRandom = document.getElementById("tag-random");
    const inputTagExtraParams = document.getElementById("tag-extra-params");
    const btnToggleModalAbsPicker = document.getElementById("btn-toggle-modal-abs-picker");
    const elTargetIdHelper = document.getElementById("target-id-helper");

    // In-Modal ABS Picker Elements
    const elModalAbsPickerBox = document.getElementById("modal-abs-picker-box");
    const btnModalAbsTabSeries = document.getElementById("btn-modal-abs-tab-series");
    const btnModalAbsTabItems = document.getElementById("btn-modal-abs-tab-items");
    const btnModalAbsTabPodcasts = document.getElementById("btn-modal-abs-tab-podcasts");
    const btnCloseModalAbsPicker = document.getElementById("btn-close-modal-abs-picker");
    const inputModalAbsSearch = document.getElementById("modal-abs-search-input");
    const elModalAbsResultsList = document.getElementById("modal-abs-results-list");

    const elReaderModal = document.getElementById("reader-modal");
    const elReaderForm = document.getElementById("reader-form");
    const elReaderModalTitle = document.getElementById("reader-modal-title");
    const inputReaderId = document.getElementById("reader-id-input");
    const inputReaderTargetPlayer = document.getElementById("reader-target-player");
    const inputReaderAbsToken = document.getElementById("reader-abs-token");
    const inputReaderAbsPrefix = document.getElementById("reader-abs-prefix");
    const inputReaderNotes = document.getElementById("reader-notes");

    const elPayloadModal = document.getElementById("payload-modal");
    const elPayloadModalContent = document.getElementById("payload-modal-content");
    const btnCopyPayloadModal = document.getElementById("btn-copy-payload-modal");

    const elLogsModal = document.getElementById("logs-modal");
    const btnOpenLogs = document.getElementById("btn-open-logs");
    const elSystemLogsContent = document.getElementById("system-logs-content");
    const btnRefreshLogs = document.getElementById("btn-refresh-logs");
    const btnCopyLogs = document.getElementById("btn-copy-logs");

    // DOM Elements - Simulator & ABS Tab
    const inputSimReaderId = document.getElementById("sim-reader-id");
    const inputSimTagId = document.getElementById("sim-tag-id");
    const btnSimScan = document.getElementById("btn-sim-scan");
    const btnSimRemove = document.getElementById("btn-sim-remove");
    const elSimResultContainer = document.getElementById("sim-result-container");
    const elSimResultOutput = document.getElementById("sim-result-output");
    
    const btnAbsTabSeries = document.getElementById("btn-abs-tab-series");
    const btnAbsTabItems = document.getElementById("btn-abs-tab-items");
    const btnAbsTabPodcasts = document.getElementById("btn-abs-tab-podcasts");
    const inputAbsSearch = document.getElementById("abs-search-input");
    const elAbsContentList = document.getElementById("abs-content-list");

    // DOM Elements - Firmware & YAML Generator
    let firmwareTemplates = [];
    const flasherHwSelect = document.getElementById("flasher-hw-select");
    const flasherReaderSelect = document.getElementById("flasher-reader-select");
    const flasherReaderIdInput = document.getElementById("flasher-reader-id-input");
    const flasherWifiSsid = document.getElementById("flasher-wifi-ssid");
    const flasherWifiPass = document.getElementById("flasher-wifi-pass");
    const flasherMqttBroker = document.getElementById("flasher-mqtt-broker");
    const flasherMqttPort = document.getElementById("flasher-mqtt-port");
    const btnDownloadYaml = document.getElementById("btn-download-yaml");
    const btnDownloadZip = document.getElementById("btn-download-zip");
    const btnDownloadBin = document.getElementById("btn-download-bin");
    const btnCopyYaml = document.getElementById("btn-copy-yaml");
    const flasherStep2Title = document.getElementById("flasher-step2-title");
    const flasherStep2Desc = document.getElementById("flasher-step2-desc");
    const flasherPreviewTitle = document.getElementById("flasher-preview-title");
    const flasherInstructionsEsphome = document.getElementById("flasher-instructions-esphome");
    const flasherInstructionsPlatformio = document.getElementById("flasher-instructions-platformio");
    const flasherYamlPreview = document.getElementById("flasher-yaml-preview");
    const yamlFilenameBadge = document.getElementById("yaml-filename-badge");
    const flasherHwName = document.getElementById("flasher-hw-name");
    const flasherHwDesc = document.getElementById("flasher-hw-desc");
    const flasherPinoutTable = document.getElementById("flasher-pinout-table");
    const flasherLedGuideSection = document.getElementById("flasher-led-guide-section");
    const flasherLedGuideList = document.getElementById("flasher-led-guide-list");

    // =========================================================================
    // THEME TOGGLE & PERSISTENCE
    // =========================================================================

    function updateThemeIcons(theme) {
        if (!themeSunIcon || !themeMoonIcon) return;
        if (theme === "light") {
            themeSunIcon.classList.remove("hidden");
            themeMoonIcon.classList.add("hidden");
        } else {
            themeSunIcon.classList.add("hidden");
            themeMoonIcon.classList.remove("hidden");
        }
    }

    function initTheme() {
        const savedTheme = localStorage.getItem("nfc_theme") || "dark";
        if (savedTheme === "light") {
            document.documentElement.classList.remove("dark");
            document.documentElement.classList.add("light");
        } else {
            document.documentElement.classList.add("dark");
            document.documentElement.classList.remove("light");
        }
        updateThemeIcons(savedTheme);
    }

    if (btnThemeToggle) {
        btnThemeToggle.addEventListener("click", () => {
            const isDark = document.documentElement.classList.contains("dark");
            const newTheme = isDark ? "light" : "dark";
            if (newTheme === "light") {
                document.documentElement.classList.remove("dark");
                document.documentElement.classList.add("light");
            } else {
                document.documentElement.classList.add("dark");
                document.documentElement.classList.remove("light");
            }
            try {
                localStorage.setItem("nfc_theme", newTheme);
            } catch (e) {}
            updateThemeIcons(newTheme);
        });
    }
    initTheme();

    // =========================================================================
    // INITIALIZATION & TAB NAVIGATION
    // =========================================================================

    let currentActiveTab = "tags-tab";
    function updateFabVisibility(tabId) {
        if (!btnMobileFab) return;
        currentActiveTab = tabId;
        if (tabId === "tags-tab" || tabId === "readers-tab") {
            btnMobileFab.classList.remove("hidden");
        } else {
            btnMobileFab.classList.add("hidden");
        }
    }

    if (btnMobileFab) {
        btnMobileFab.addEventListener("click", () => {
            if (currentActiveTab === "tags-tab" && btnAddTag) {
                btnAddTag.click();
            } else if (currentActiveTab === "readers-tab" && btnAddReader) {
                btnAddReader.click();
            }
        });
    }

    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            const targetTab = document.getElementById(btn.dataset.tab);
            if (targetTab) {
                targetTab.classList.add("active");
            }

            updateFabVisibility(btn.dataset.tab);

            if (btn.dataset.tab === "history-tab") {
                loadHistory();
            } else if (btn.dataset.tab === "tools-tab") {
                loadAbsContent();
            } else if (btn.dataset.tab === "flasher-tab") {
                loadFirmwareTemplates();
                updateFlasherReadersList();
                generateYamlPreview();
            }
        });
    });

    // Close Modals via Close-Buttons & Backdrop
    document.querySelectorAll("[data-close-modal]").forEach(el => {
        el.addEventListener("click", () => {
            if (elTagModal) elTagModal.classList.add("hidden");
            if (elReaderModal) elReaderModal.classList.add("hidden");
            if (elPayloadModal) elPayloadModal.classList.add("hidden");
            if (elLogsModal) elLogsModal.classList.add("hidden");
        });
    });

    document.querySelectorAll(".modal-backdrop").forEach(bd => {
        bd.addEventListener("click", () => {
            if (elTagModal) elTagModal.classList.add("hidden");
            if (elReaderModal) elReaderModal.classList.add("hidden");
            if (elPayloadModal) elPayloadModal.classList.add("hidden");
            if (elLogsModal) elLogsModal.classList.add("hidden");
        });
    });

    // Dynamic Helper Text & Options on Action Type Change
    selectTagActionType.addEventListener("change", () => {
        const val = selectTagActionType.value;
        if (val === "Serie") {
            if (groupLibraryId) groupLibraryId.classList.remove("hidden");
            if (inputTagLibraryId) inputTagLibraryId.required = true;
            if (groupStartFromBeginning) groupStartFromBeginning.classList.remove("hidden");
            if (groupRandom) groupRandom.classList.add("hidden");
            if (checkTagRandom) checkTagRandom.checked = false;
            elTargetIdHelper.textContent = t("type_series") + " (z. B. 01048bbc-...).";
            inputTagTargetId.placeholder = "01048bbc-3909-4db4-af85-ed81d2f087b3";
            btnToggleModalAbsPicker.classList.remove("hidden");
            btnToggleModalAbsPicker.textContent = t("abs_tab_series");
        } else if (val === "Hoerbuch") {
            if (groupLibraryId) groupLibraryId.classList.remove("hidden");
            if (inputTagLibraryId) inputTagLibraryId.required = true;
            if (groupStartFromBeginning) groupStartFromBeginning.classList.remove("hidden");
            if (groupRandom) groupRandom.classList.add("hidden");
            if (checkTagRandom) checkTagRandom.checked = false;
            elTargetIdHelper.textContent = t("type_audiobook") + " (z. B. 5dcb6e5d-...).";
            inputTagTargetId.placeholder = "5dcb6e5d-962d-434f-b26d-60a6a8cc30f8";
            btnToggleModalAbsPicker.classList.remove("hidden");
            btnToggleModalAbsPicker.textContent = t("abs_tab_items");
        } else if (val === "Podcast") {
            if (groupLibraryId) groupLibraryId.classList.remove("hidden");
            if (inputTagLibraryId) inputTagLibraryId.required = false;
            if (groupStartFromBeginning) groupStartFromBeginning.classList.add("hidden");
            if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
            if (groupRandom) groupRandom.classList.add("hidden");
            if (checkTagRandom) checkTagRandom.checked = false;
            elTargetIdHelper.textContent = t("type_podcast") + " (z. B. audiobookshelf--xPQT49LN://podcast/af09... oder library://podcast/10)";
            inputTagTargetId.placeholder = "audiobookshelf--xPQT49LN://podcast/af09... oder library://podcast/10";
            btnToggleModalAbsPicker.classList.remove("hidden");
            btnToggleModalAbsPicker.textContent = t("abs_tab_podcasts");
        } else if (val === "Album") {
            if (groupLibraryId) groupLibraryId.classList.add("hidden");
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ""; }
            if (groupStartFromBeginning) groupStartFromBeginning.classList.add("hidden");
            if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
            if (groupRandom) groupRandom.classList.remove("hidden");
            elTargetIdHelper.textContent = "Music Assistant Album (z. B. mass://album/xyz oder library://album/123)";
            inputTagTargetId.placeholder = "mass://album/mein_album";
            btnToggleModalAbsPicker.classList.add("hidden");
            elModalAbsPickerBox.classList.add("hidden");
        } else if (val === "Playlist") {
            if (groupLibraryId) groupLibraryId.classList.add("hidden");
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ""; }
            if (groupStartFromBeginning) groupStartFromBeginning.classList.add("hidden");
            if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
            if (groupRandom) groupRandom.classList.remove("hidden");
            elTargetIdHelper.textContent = "Music Assistant Playlist (z. B. mass://playlist/schlafenszeit)";
            inputTagTargetId.placeholder = "mass://playlist/schlafenszeit";
            btnToggleModalAbsPicker.classList.add("hidden");
            elModalAbsPickerBox.classList.add("hidden");
        } else if (val === "Licht" || val === "Szene") {
            if (groupLibraryId) groupLibraryId.classList.add("hidden");
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ""; }
            if (groupStartFromBeginning) groupStartFromBeginning.classList.add("hidden");
            if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
            if (groupRandom) groupRandom.classList.add("hidden");
            if (checkTagRandom) checkTagRandom.checked = false;
            elTargetIdHelper.textContent = "Home Assistant Entity ID (z. B. light.kinderzimmer oder scene.schlafenszeit)";
            inputTagTargetId.placeholder = val === "Licht" ? "light.kinderzimmer" : "scene.schlafenszeit";
            btnToggleModalAbsPicker.classList.add("hidden");
            elModalAbsPickerBox.classList.add("hidden");
        } else {
            if (groupLibraryId) groupLibraryId.classList.add("hidden");
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ""; }
            if (groupStartFromBeginning) groupStartFromBeginning.classList.add("hidden");
            if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
            if (groupRandom) groupRandom.classList.remove("hidden");
            elTargetIdHelper.textContent = "Target ID";
            inputTagTargetId.placeholder = "Target ID";
            btnToggleModalAbsPicker.classList.add("hidden");
            elModalAbsPickerBox.classList.add("hidden");
        }
    });

    // =========================================================================
    // IN-MODAL ABS PICKER LOGIC
    // =========================================================================

    btnToggleModalAbsPicker.addEventListener("click", () => {
        const isHidden = elModalAbsPickerBox.classList.contains("hidden");
        if (isHidden) {
            elModalAbsPickerBox.classList.remove("hidden");
            const val = selectTagActionType.value;
            if (val === "Hoerbuch") {
                setModalAbsTab("items");
            } else if (val === "Podcast") {
                setModalAbsTab("podcasts");
            } else {
                setModalAbsTab("series");
            }
            loadModalAbsContent();
            inputModalAbsSearch.focus();
        } else {
            elModalAbsPickerBox.classList.add("hidden");
        }
    });

    btnCloseModalAbsPicker.addEventListener("click", () => {
        elModalAbsPickerBox.classList.add("hidden");
    });

    btnModalAbsTabSeries.addEventListener("click", () => setModalAbsTab("series"));
    btnModalAbsTabItems.addEventListener("click", () => setModalAbsTab("items"));
    if (btnModalAbsTabPodcasts) {
        btnModalAbsTabPodcasts.addEventListener("click", () => setModalAbsTab("podcasts"));
    }

    function setModalAbsTab(tab) {
        modalAbsCurrentTab = tab;
        btnModalAbsTabSeries.className = tab === "series" ? "btn btn-xs btn-primary" : "btn btn-xs btn-secondary";
        btnModalAbsTabItems.className = tab === "items" ? "btn btn-xs btn-primary" : "btn btn-xs btn-secondary";
        if (btnModalAbsTabPodcasts) {
            btnModalAbsTabPodcasts.className = tab === "podcasts" ? "btn btn-xs btn-primary" : "btn btn-xs btn-secondary";
        }
        loadModalAbsContent();
    }

    let modalSearchTimeout = null;
    inputModalAbsSearch.addEventListener("input", () => {
        clearTimeout(modalSearchTimeout);
        modalSearchTimeout = setTimeout(() => {
            loadModalAbsContent();
        }, 250);
    });

    async function loadModalAbsContent() {
        const query = inputModalAbsSearch.value.trim();
        elModalAbsResultsList.innerHTML = `<p class="text-muted text-center py-2 text-xs">${t("abs_loading")}</p>`;
        
        let endpoint = "";
        if (modalAbsCurrentTab === "series") {
            endpoint = `/api/abs/series${query ? "?q=" + encodeURIComponent(query) : ""}`;
        } else if (modalAbsCurrentTab === "podcasts") {
            endpoint = `/api/abs/podcasts${query ? "?q=" + encodeURIComponent(query) : ""}`;
        } else {
            endpoint = `/api/abs/items?limit=200${query ? "&q=" + encodeURIComponent(query) : ""}`;
        }

        try {
            const res = await fetch(endpoint);
            if (res.ok) {
                absContentList = await res.json();
                renderModalAbsResults();
            } else {
                elModalAbsResultsList.innerHTML = `<p class="text-danger text-center py-2 text-xs">HTTP ${res.status}</p>`;
            }
        } catch (e) {
            elModalAbsResultsList.innerHTML = `<p class="text-danger text-center py-2 text-xs">${t("abs_not_reachable")} ${e}</p>`;
        }
    }

    function renderModalAbsResults() {
        const query = (inputModalAbsSearch.value || "").toLowerCase().trim();
        const filtered = (absContentList || []).filter(item => {
            if (!query) return true;
            const title = (item.name || item.title || "").toLowerCase();
            const id = (item.id || "").toLowerCase();
            const author = (item.author || "").toLowerCase();
            return title.includes(query) || id.includes(query) || author.includes(query);
        });

        if (filtered.length === 0) {
            let msg = t("abs_empty_items");
            if (modalAbsCurrentTab === "series") msg = t("abs_empty_series");
            if (modalAbsCurrentTab === "podcasts") msg = t("abs_empty_podcasts");
            elModalAbsResultsList.innerHTML = `<p class="text-muted text-center py-2 text-xs">${msg}</p>`;
            return;
        }

        elModalAbsResultsList.innerHTML = filtered.map(item => {
            const isSeries = modalAbsCurrentTab === "series";
            const isPodcast = modalAbsCurrentTab === "podcasts";
            const title = item.name || item.title || t("unnamed");
            
            let meta = "";
            let itemTypeParam = "Hoerbuch";
            if (isSeries) {
                meta = `Serie (${item.num_books} Bücher) • ID: ${item.id}`;
                itemTypeParam = "Serie";
            } else if (isPodcast) {
                meta = `Podcast (${item.num_episodes || 0} Folgen) • ID: ${item.id}`;
                itemTypeParam = "Podcast";
            } else {
                meta = `${item.author ? item.author + " • " : ""}ID: ${item.id}`;
                itemTypeParam = "Hoerbuch";
            }

            return `
                <div class="abs-series-item py-1">
                    <div style="max-width: 70%;">
                        <div class="abs-series-title text-xs"><strong>${escapeHtml(title)}</strong></div>
                        <div class="abs-series-meta font-mono" style="font-size: 10px;">${escapeHtml(meta)}</div>
                    </div>
                    <button type="button" class="btn btn-xs btn-primary" onclick="window.applyModalAbsItem('${escapeHtml(item.id)}')">
                        ${t("abs_btn_apply")}
                    </button>
                </div>
            `;
        }).join("");
    }

    window.applyModalAbsItem = function(id, libraryId, title, itemType) {
        if (!libraryId && !title && !itemType) {
            const item = (absContentList || []).find(x => x.id === id);
            if (item) {
                const isSeries = modalAbsCurrentTab === "series";
                const isPodcast = modalAbsCurrentTab === "podcasts";
                libraryId = item.library_id || "";
                title = item.name || item.title || "";
                itemType = isSeries ? "Serie" : (isPodcast ? "Podcast" : "Hoerbuch");
            }
        }
        inputTagTargetId.value = id;
        if (inputTagLibraryId) {
            inputTagLibraryId.value = libraryId || "";
        }
        if (!inputTagAlias.value.trim() && title) {
            inputTagAlias.value = title;
        }
        if (itemType) {
            selectTagActionType.value = (itemType === true || itemType === "Serie") ? "Serie" : (itemType === "Podcast" ? "Podcast" : "Hoerbuch");
            selectTagActionType.dispatchEvent(new Event("change"));
        }
        elModalAbsPickerBox.classList.add("hidden");
        
        // Highlight Effect
        inputTagTargetId.style.borderColor = "#10b981";
        if (inputTagLibraryId) inputTagLibraryId.style.borderColor = "#10b981";
        setTimeout(() => { 
            inputTagTargetId.style.borderColor = ""; 
            if (inputTagLibraryId) inputTagLibraryId.style.borderColor = "";
        }, 1200);
    };

    // =========================================================================
    // API CALLS & DATA LOADING
    // =========================================================================

    async function loadTags() {
        try {
            const res = await fetch("/api/tags");
            if (res.ok) {
                tagsList = await res.json();
                renderTagsTable();
            }
        } catch (e) {
            console.error("Fehler beim Laden der Tags:", e);
        }
    }

    async function loadReaders() {
        try {
            const res = await fetch("/api/readers");
            if (res.ok) {
                readersList = await res.json();
                renderReadersTable();
                updateFlasherReadersList();
            }
        } catch (e) {
            console.error("Fehler beim Laden der Reader:", e);
        }
    }

    async function loadHistory() {
        try {
            const res = await fetch("/api/history?limit=50");
            if (res.ok) {
                historyList = await res.json();
                renderHistoryTable(historyList);
            }
        } catch (e) {
            console.error("Fehler beim Laden der Historie:", e);
        }
    }

    async function checkSystemStatus() {
        try {
            const res = await fetch("/api/system/status");
            if (res.ok) {
                const data = await res.json();
                
                // MQTT
                if (data.mqtt.connected) {
                    elStatusMqtt.className = "status-indicator status-connected";
                    elStatusMqtt.querySelector(".label").textContent = `${t("status_mqtt_connected")}${data.mqtt.broker}`;
                    if (elMobileDotMqtt) elMobileDotMqtt.className = "dot-sm dot-connected";
                } else {
                    elStatusMqtt.className = "status-indicator status-disconnected";
                    elStatusMqtt.querySelector(".label").textContent = t("status_mqtt_disconnected");
                    if (elMobileDotMqtt) elMobileDotMqtt.className = "dot-sm dot-disconnected";
                }

                // Populate Flasher MQTT Fields
                if (flasherMqttBroker && flasherMqttPort) {
                    flasherMqttBroker.value = data.mqtt.broker || "localhost";
                    flasherMqttPort.value = data.mqtt.port || 1883;
                }

                // ABS
                if (data.audiobookshelf.reachable) {
                    elStatusAbs.className = "status-indicator status-connected";
                    const userLabel = data.audiobookshelf.username ? data.audiobookshelf.username : "Connected";
                    elStatusAbs.querySelector(".label").textContent = `ABS: ${userLabel}`;
                    if (elMobileDotAbs) elMobileDotAbs.className = "dot-sm dot-connected";
                } else {
                    elStatusAbs.className = "status-indicator status-unknown";
                    elStatusAbs.querySelector(".label").textContent = t("status_abs_unreachable");
                    if (elMobileDotAbs) elMobileDotAbs.className = "dot-sm dot-unknown";
                }
            }
        } catch (e) {
            console.error("Status-Check Fehler:", e);
        }
    }

    // =========================================================================
    // TABLE & MOBILE CARD RENDERING
    // =========================================================================

    function getActionTypeBadge(type) {
        if (!type || type.trim() === "") return `<span class="text-muted">—</span>`;
        const safeType = escapeHtml(type.trim());
        const cssType = safeType.toLowerCase();
        return `<span class="badge-action-type type-${cssType}">${safeType}</span>`;
    }

    function getPlaybackBadge(tag) {
        if (!tag.action_type) return `<span class="text-muted">—</span>`;
        if (tag.action_type === "Serie" || tag.action_type === "Hoerbuch") {
            if (tag.start_from_beginning) {
                return `<span class="badge-playback badge-playback-start" title="${t("modal_start_from_beginning")}"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> ${t("opt_from_start")}</span>`;
            }
            return `<span class="badge-playback badge-playback-resume" title="${t("opt_resume")}"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> ${t("opt_resume")}</span>`;
        }
        if (["Album", "Playlist", "Custom"].includes(tag.action_type)) {
            if (tag.random) {
                return `<span class="badge-playback badge-playback-shuffle" title="${t("opt_shuffle")}"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg> ${t("opt_shuffle")}</span>`;
            }
            return `<span class="text-muted">—</span>`;
        }
        return `<span class="text-muted">—</span>`;
    }

    function renderTagsTable() {
        const query = elSearchInput.value.toLowerCase().trim();
        const statusFilter = elFilterStatus.value;
        const typeFilter = elFilterType.value;

        const filtered = tagsList.filter(tag => {
            const matchesQuery = (tag.tag_id && (tag.tag_id.toLowerCase().includes(query) || formatTagId(tag.tag_id).toLowerCase().includes(query))) ||
                                 (tag.alias && tag.alias.toLowerCase().includes(query)) ||
                                 (tag.target_id && tag.target_id.toLowerCase().includes(query));

            const isUnconfigured = !tag.action_type || tag.action_type.trim() === "";
            let matchesStatus = true;
            if (statusFilter === "unconfigured") matchesStatus = isUnconfigured;
            if (statusFilter === "configured") matchesStatus = !isUnconfigured;

            let matchesType = true;
            if (typeFilter !== "all") matchesType = (tag.action_type === typeFilter);

            return matchesQuery && matchesStatus && matchesType;
        });

        elTagsCount.textContent = tagsList.length;

        if (filtered.length === 0) {
            elTagsTableBody.innerHTML = "";
            if (elTagsMobileList) elTagsMobileList.innerHTML = "";
            elTagsEmptyState.classList.remove("hidden");
            return;
        }

        elTagsEmptyState.classList.add("hidden");

        // Desktop Table Rows
        elTagsTableBody.innerHTML = filtered.map(tag => {
            const isUnconfigured = !tag.action_type || tag.action_type.trim() === "";
            const statusBadge = isUnconfigured
                ? `<span class="badge badge-warning">${t("badge_unconfigured")}</span>`
                : `<span class="badge badge-configured">${t("badge_ready")}</span>`;

            const actionTypeBadge = getActionTypeBadge(tag.action_type);

            const targetDisplay = (!isUnconfigured && tag.target_id)
                ? `<span title="${escapeHtml(tag.target_id)}">${escapeHtml(truncate(tag.target_id, 28))}</span>`
                : `<span class="text-muted">—</span>`;

            const volumeDisplay = isUnconfigured
                ? `<span class="text-muted">—</span>`
                : (tag.volume !== null ? `${tag.volume}%` : `<span class="text-muted">${t("default")}</span>`);

            const playbackDisplay = getPlaybackBadge(tag);

            const lastScannedDisplay = tag.last_scanned ? formatDate(tag.last_scanned) : `<span class="text-muted">${t("never")}</span>`;

            return `
                <tr>
                    <td>${statusBadge}</td>
                    <td class="font-mono"><strong>${escapeHtml(formatTagId(tag.tag_id))}</strong></td>
                    <td>${escapeHtml(tag.alias || t("unnamed"))}</td>
                    <td>${actionTypeBadge}</td>
                    <td class="font-mono text-muted">${targetDisplay}</td>
                    <td>${volumeDisplay}</td>
                    <td>${playbackDisplay}</td>
                    <td>${lastScannedDisplay}</td>
                    <td class="actions-cell">
                        <button class="ghost-action-btn" onclick="window.editTag('${escapeHtml(tag.tag_id)}')" title="${t('btn_edit')}" aria-label="Edit">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                        </button>
                        <button class="ghost-action-btn btn-danger-ghost" onclick="window.deleteTagConfirm('${escapeHtml(tag.tag_id)}')" title="Delete" aria-label="Delete">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </td>
                </tr>
            `;
        }).join("");

        // Mobile Card Feed
        if (elTagsMobileList) {
            elTagsMobileList.innerHTML = filtered.map(tag => {
                const isUnconfigured = !tag.action_type || tag.action_type.trim() === "";
                const statusBadge = isUnconfigured
                    ? `<span class="badge badge-warning">${t("badge_unconfigured")}</span>`
                    : `<span class="badge badge-configured">${t("badge_ready")}</span>`;
                const actionBadge = getActionTypeBadge(tag.action_type);
                const playbackBadge = getPlaybackBadge(tag);
                const lastScanned = tag.last_scanned ? formatDate(tag.last_scanned) : t("never");

                // Target display: ONLY if configured and target_id exists!
                const targetHtml = (!isUnconfigured && tag.target_id)
                    ? `<div class="card-item-target" title="${escapeHtml(tag.target_id)}">
                         <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
                         <span>${escapeHtml(truncate(tag.target_id, 36))}</span>
                       </div>`
                    : (isUnconfigured 
                        ? `<div class="card-unconfigured-hint" onclick="window.editTag('${escapeHtml(tag.tag_id)}')">
                             <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                             <span>${t("badge_unconfigured")} &bull; Tap to configure</span>
                           </div>`
                        : ``);

                // Badges row: Action Type, Playback, and Volume (if applicable)
                const hasPlayback = playbackBadge && !playbackBadge.includes("text-muted");
                const hasAction = actionBadge && !actionBadge.includes("text-muted");
                const volumeHtml = (!isUnconfigured && tag.volume !== null)
                    ? `<span class="badge-volume"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg> ${tag.volume}%</span>`
                    : "";

                const badgesRowHtml = (hasAction || hasPlayback || volumeHtml)
                    ? `<div class="card-badges-row">
                         ${hasAction ? actionBadge : ""}
                         ${hasPlayback ? playbackBadge : ""}
                         ${volumeHtml}
                       </div>`
                    : "";

                return `
                    <div class="card-item">
                        <div class="card-item-header">
                            <div class="card-tag-identity">
                                ${statusBadge}
                                <span class="card-tag-id font-mono">${escapeHtml(formatTagId(tag.tag_id))}</span>
                            </div>
                            <div class="card-item-actions">
                                <button class="touch-action-btn" onclick="window.editTag('${escapeHtml(tag.tag_id)}')" title="${t('btn_edit')}" aria-label="Edit">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                                </button>
                                <button class="touch-action-btn btn-danger" onclick="window.deleteTagConfirm('${escapeHtml(tag.tag_id)}')" title="${t('btn_delete')}" aria-label="Delete">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="card-item-body">
                            <div class="card-item-title">${escapeHtml(tag.alias || t("unnamed"))}</div>
                            ${targetHtml}
                            ${badgesRowHtml}
                        </div>
                        <div class="card-item-footer">
                            <span class="card-footer-time">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                                ${lastScanned}
                            </span>
                        </div>
                    </div>
                `;
            }).join("");
        }
    }

    function renderReadersTable() {
        elReadersCount.textContent = readersList.length;

        if (readersList.length === 0) {
            elReadersTableBody.innerHTML = "";
            if (elReadersMobileList) elReadersMobileList.innerHTML = "";
            elReadersEmptyState.classList.remove("hidden");
            return;
        }

        elReadersEmptyState.classList.add("hidden");

        // Desktop Table Rows
        elReadersTableBody.innerHTML = readersList.map(reader => {
            const tokenBadge = reader.abs_user_token
                ? `<span class="badge badge-configured" title="User-Token gesetzt">User-Token</span>`
                : `<span class="badge badge-type text-muted">${t("default")}</span>`;

            const prefixInfo = reader.abs_provider_prefix
                ? `<div class="text-xs font-mono text-muted" style="font-size: 10px;" title="ABS Prefix">${escapeHtml(reader.abs_provider_prefix)}</div>`
                : "";

            return `
                <tr>
                    <td class="font-mono"><strong>${escapeHtml(reader.reader_id)}</strong></td>
                    <td class="font-mono">${escapeHtml(reader.target_player)}</td>
                    <td>${tokenBadge}${prefixInfo}</td>
                    <td>${escapeHtml(reader.notes || "—")}</td>
                    <td class="actions-cell">
                        <button class="ghost-action-btn" onclick="window.editReader('${escapeHtml(reader.reader_id)}')" title="${t('btn_edit')}" aria-label="Edit">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                        </button>
                        <button class="ghost-action-btn btn-danger-ghost" onclick="window.deleteReaderConfirm('${escapeHtml(reader.reader_id)}')" title="Delete" aria-label="Delete">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                        </button>
                    </td>
                </tr>
            `;
        }).join("");

        // Mobile Card Feed
        if (elReadersMobileList) {
            elReadersMobileList.innerHTML = readersList.map(reader => {
                const tokenBadge = reader.abs_user_token
                    ? `<span class="badge badge-configured">User-Token</span>`
                    : `<span class="badge badge-type text-muted">${t("default")}</span>`;
                return `
                    <div class="card-item">
                        <div class="card-item-header">
                            <span class="card-tag-id font-mono">${escapeHtml(reader.reader_id)}</span>
                            <div class="card-item-actions">
                                <button class="touch-action-btn" onclick="window.editReader('${escapeHtml(reader.reader_id)}')" title="${t('btn_edit')}" aria-label="Edit">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                                </button>
                                <button class="touch-action-btn btn-danger" onclick="window.deleteReaderConfirm('${escapeHtml(reader.reader_id)}')" title="${t('btn_delete')}" aria-label="Delete">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="card-item-body">
                            ${reader.notes ? `<div class="card-item-title">${escapeHtml(reader.notes)}</div>` : ""}
                            <div class="card-item-target font-mono">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                                <span>${escapeHtml(reader.target_player)}</span>
                            </div>
                        </div>
                        <div class="card-item-footer">
                            <span class="card-footer-label">ABS Token:</span>
                            <div>${tokenBadge}</div>
                        </div>
                    </div>
                `;
            }).join("");
        }
    }

    function renderHistoryTable(items) {
        if (!items || items.length === 0) {
            elHistoryTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">${t("history_empty")}</td></tr>`;
            return;
        }

        elHistoryTableBody.innerHTML = items.map((item, idx) => {
            let statusBadge = `<span class="badge badge-info">${escapeHtml(item.status)}</span>`;
            if (item.action_executed === "warning") statusBadge = `<span class="badge badge-warning">⚠️ Warnung</span>`;
            if (item.action_executed === "stop") statusBadge = `<span class="badge badge-type">⏹ Stop</span>`;
            if (item.action_executed === "media") statusBadge = `<span class="badge badge-configured">▶ Media</span>`;

            return `
                <tr>
                    <td>${formatDate(item.timestamp)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <strong class="font-mono">${escapeHtml(formatTagId(item.tag_id))}</strong>
                        ${item.tag_alias ? `<div class="text-muted text-xs">${escapeHtml(item.tag_alias)}</div>` : ""}
                    </td>
                    <td class="font-mono">${escapeHtml(item.reader_id)}</td>
                    <td><code>${escapeHtml(item.action_executed || "—")}</code></td>
                    <td>
                        <div class="payload-cell">
                            <span class="font-mono text-muted text-xs" title="${escapeHtml(item.payload || "")}">
                                ${escapeHtml(truncate(item.payload || "", 36))}
                            </span>
                            <button class="btn btn-xs btn-secondary" onclick="window.copyPayload(${idx})" title="${t("copied_to_clipboard")}">
                                📋
                            </button>
                            <button class="btn btn-xs btn-secondary" onclick="window.viewPayload(${idx})" title="Payload">
                                👁️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    // Payload Clipboard & Viewer
    window.copyPayload = function(idx) {
        const item = historyList[idx];
        if (!item || !item.payload) return;
        navigator.clipboard.writeText(item.payload).then(() => {
            alert(t("copied_to_clipboard"));
        }).catch(err => {
            console.error("Kopieren fehlgeschlagen:", err);
        });
    };

    window.viewPayload = function(idx) {
        const item = historyList[idx];
        if (!item) return;
        try {
            const parsed = JSON.parse(item.payload);
            elPayloadModalContent.textContent = JSON.stringify(parsed, null, 2);
        } catch {
            elPayloadModalContent.textContent = item.payload || "";
        }
        btnCopyPayloadModal.onclick = () => {
            navigator.clipboard.writeText(elPayloadModalContent.textContent);
            alert(t("copied_to_clipboard"));
        };
        elPayloadModal.classList.remove("hidden");
    };

    // System Logs Viewer
    async function loadSystemLogs() {
        if (!elSystemLogsContent) return;
        elSystemLogsContent.textContent = "Loading logs...";
        try {
            const res = await fetch("/api/system/logs");
            if (res.ok) {
                const data = await res.json();
                elSystemLogsContent.textContent = (data.logs || []).join("\n") || "No logs available.";
                elSystemLogsContent.scrollTop = elSystemLogsContent.scrollHeight;
            } else {
                elSystemLogsContent.textContent = "HTTP " + res.status;
            }
        } catch (e) {
            elSystemLogsContent.textContent = "Error: " + e;
        }
    }

    if (btnOpenLogs) {
        btnOpenLogs.addEventListener("click", () => {
            if (elLogsModal) elLogsModal.classList.remove("hidden");
            loadSystemLogs();
        });
    }

    if (btnRefreshLogs) {
        btnRefreshLogs.addEventListener("click", loadSystemLogs);
    }

    if (btnCopyLogs) {
        btnCopyLogs.addEventListener("click", () => {
            if (elSystemLogsContent && elSystemLogsContent.textContent) {
                navigator.clipboard.writeText(elSystemLogsContent.textContent).then(() => {
                    alert(t("copied_to_clipboard"));
                }).catch(err => {
                    console.error("Kopieren fehlgeschlagen:", err);
                });
            }
        });
    }

    // Filter listeners
    elSearchInput.addEventListener("input", renderTagsTable);
    elFilterStatus.addEventListener("change", renderTagsTable);
    elFilterType.addEventListener("change", renderTagsTable);
    btnRefreshHistory.addEventListener("click", loadHistory);

    // =========================================================================
    // TAG CRUD MODAL
    // =========================================================================

    btnAddTag.addEventListener("click", () => {
        currentEditingTagId = null;
        elTagModalTitle.textContent = t("modal_tag_title_new");
        inputTagId.value = "";
        inputTagId.disabled = false;
        inputTagAlias.value = "";
        selectTagActionType.value = "";
        if (inputTagLibraryId) inputTagLibraryId.value = "";
        inputTagVolume.value = "";
        inputTagTargetId.value = "";
        if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = false;
        if (checkTagRandom) checkTagRandom.checked = false;
        inputTagExtraParams.value = "{}";
        elModalAbsPickerBox.classList.add("hidden");
        selectTagActionType.dispatchEvent(new Event("change"));
        elTagModal.classList.remove("hidden");
    });

    if (btnDeleteUnconfigured) {
        btnDeleteUnconfigured.addEventListener("click", async () => {
            const confirmMsg = t("confirm_delete_unconfigured", "Are you sure you want to delete all unconfigured tags?");
            if (!confirm(confirmMsg)) return;
            try {
                const res = await fetch("/api/tags/unconfigured", { method: "DELETE" });
                if (res.ok) {
                    const data = await res.json();
                    const count = data.deleted_count || 0;
                    const succTemplate = t("deleted_unconfigured_count", "Deleted {count} unconfigured tags.");
                    alert(succTemplate.replace("{count}", count));
                    await loadTags();
                } else {
                    alert("Failed to delete unconfigured tags.");
                }
            } catch (err) {
                console.error("Error deleting unconfigured tags:", err);
                alert("Error communicating with server: " + err);
            }
        });
    }

    window.editTag = function(tagId) {
        const tag = tagsList.find(t => t.tag_id === tagId);
        if (!tag) return;

        currentEditingTagId = tagId;
        elTagModalTitle.textContent = `${t("modal_tag_title_edit")}${tagId}`;
        inputTagId.value = tag.tag_id;
        inputTagId.disabled = true;
        inputTagAlias.value = tag.alias || "";
        selectTagActionType.value = tag.action_type || "";
        if (inputTagLibraryId) inputTagLibraryId.value = tag.library_id || "";
        inputTagVolume.value = tag.volume !== null ? tag.volume : "";
        inputTagTargetId.value = tag.target_id || "";
        if (checkTagStartFromBeginning) checkTagStartFromBeginning.checked = !!tag.start_from_beginning;
        if (checkTagRandom) checkTagRandom.checked = !!tag.random;
        inputTagExtraParams.value = tag.extra_params || "{}";
        elModalAbsPickerBox.classList.add("hidden");
        selectTagActionType.dispatchEvent(new Event("change"));
        elTagModal.classList.remove("hidden");
    };

    window.deleteTagConfirm = async function(tagId) {
        const confirmMsg = t("confirm_delete_tag").replace("{id}", tagId);
        if (!confirm(confirmMsg)) return;
        try {
            const res = await fetch(`/api/tags/${encodeURIComponent(tagId)}`, { method: "DELETE" });
            if (res.ok) {
                await loadTags();
            }
        } catch (e) {
            alert("Error: " + e);
        }
    };

    elTagForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const tagId = inputTagId.value.trim();
        const alias = inputTagAlias.value.trim();
        const actionType = selectTagActionType.value;
        const libraryId = inputTagLibraryId ? inputTagLibraryId.value.trim() : "";
        const volumeVal = inputTagVolume.value !== "" ? parseInt(inputTagVolume.value, 10) : null;
        const targetId = inputTagTargetId.value.trim();
        
        let startFromBeginning = checkTagStartFromBeginning ? checkTagStartFromBeginning.checked : false;
        let random = checkTagRandom ? checkTagRandom.checked : false;

        // Restriction rules:
        if (!["Serie", "Hoerbuch"].includes(actionType)) {
            startFromBeginning = false;
        }
        if (["Serie", "Hoerbuch", "Licht", "Szene", "Podcast"].includes(actionType)) {
            random = false;
        }

        const extraParams = inputTagExtraParams.value.trim() || "{}";

        if (!tagId || !alias) {
            alert(t("validation_required_fields"));
            return;
        }

        if ((actionType === "Serie" || actionType === "Hoerbuch") && (!libraryId || !targetId)) {
            alert(t("validation_abs_fields"));
            return;
        }

        try {
            JSON.parse(extraParams);
        } catch (err) {
            alert(t("validation_json"));
            return;
        }

        const payload = {
            tag_id: tagId,
            alias: alias,
            action_type: actionType,
            library_id: libraryId,
            target_id: targetId,
            volume: volumeVal,
            random: random,
            start_from_beginning: startFromBeginning,
            extra_params: extraParams
        };

        try {
            const res = await fetch("/api/tags", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                elTagModal.classList.add("hidden");
                await loadTags();
            } else {
                const err = await res.json();
                alert("Error: " + (err.detail || JSON.stringify(err)));
            }
        } catch (err) {
            alert("Network Error: " + err);
        }
    });

    // =========================================================================
    // READER CRUD MODAL
    // =========================================================================

    btnAddReader.addEventListener("click", () => {
        elReaderModalTitle.textContent = t("modal_reader_title_new");
        inputReaderId.value = "";
        inputReaderId.disabled = false;
        inputReaderTargetPlayer.value = "media_player.";
        inputReaderAbsToken.value = "";
        inputReaderAbsPrefix.value = "";
        inputReaderNotes.value = "";
        elReaderModal.classList.remove("hidden");
    });

    window.editReader = function(readerId) {
        const reader = readersList.find(r => r.reader_id === readerId);
        if (!reader) return;

        elReaderModalTitle.textContent = `${t("modal_reader_title_edit")}${readerId}`;
        inputReaderId.value = reader.reader_id;
        inputReaderId.disabled = true;
        inputReaderTargetPlayer.value = reader.target_player || "";
        inputReaderAbsToken.value = reader.abs_user_token || "";
        inputReaderAbsPrefix.value = reader.abs_provider_prefix || "";
        inputReaderNotes.value = reader.notes || "";
        elReaderModal.classList.remove("hidden");
    };

    window.deleteReaderConfirm = async function(readerId) {
        const confirmMsg = t("confirm_delete_reader").replace("{id}", readerId);
        if (!confirm(confirmMsg)) return;
        try {
            const res = await fetch(`/api/readers/${encodeURIComponent(readerId)}`, { method: "DELETE" });
            if (res.ok) {
                await loadReaders();
            }
        } catch (e) {
            alert("Error: " + e);
        }
    };

    elReaderForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const readerId = inputReaderId.value.trim();
        const targetPlayer = inputReaderTargetPlayer.value.trim();
        const absToken = inputReaderAbsToken.value.trim();
        const absPrefix = inputReaderAbsPrefix.value.trim();
        const notes = inputReaderNotes.value.trim();

        if (!readerId || !targetPlayer) {
            alert("Please provide Reader ID and Target Player.");
            return;
        }

        const payload = {
            reader_id: readerId,
            target_player: targetPlayer,
            abs_user_token: absToken,
            abs_provider_prefix: absPrefix,
            notes: notes
        };

        try {
            const res = await fetch("/api/readers", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                elReaderModal.classList.add("hidden");
                await loadReaders();
            } else {
                const err = await res.json();
                alert("Error: " + (err.detail || JSON.stringify(err)));
            }
        } catch (err) {
            alert("Network Error: " + err);
        }
    });

    // =========================================================================
    // TEST SIMULATOR & ABS BROWSER TAB
    // =========================================================================

    async function runSimulation(status) {
        const readerId = inputSimReaderId.value.trim();
        const tagId = inputSimTagId.value.trim();

        if (!readerId || !tagId) {
            alert("Please provide Reader ID and Tag ID.");
            return;
        }

        try {
            const res = await fetch("/api/test/scan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    reader_id: readerId,
                    tag_id: tagId,
                    status: status
                })
            });

            const data = await res.json();
            elSimResultContainer.classList.remove("hidden");
            elSimResultOutput.textContent = JSON.stringify(data, null, 2);
            await loadTags();
            await loadReaders();
        } catch (e) {
            alert("Simulation Error: " + e);
        }
    }

    btnSimScan.addEventListener("click", () => runSimulation("scanned"));
    btnSimRemove.addEventListener("click", () => runSimulation("removed"));

    // ABS Tab Explorer
    btnAbsTabSeries.addEventListener("click", () => {
        absCurrentTab = "series";
        btnAbsTabSeries.className = "btn btn-sm btn-primary";
        btnAbsTabItems.className = "btn btn-sm btn-secondary";
        if (btnAbsTabPodcasts) btnAbsTabPodcasts.className = "btn btn-sm btn-secondary";
        loadAbsContent();
    });

    btnAbsTabItems.addEventListener("click", () => {
        absCurrentTab = "items";
        btnAbsTabItems.className = "btn btn-sm btn-primary";
        btnAbsTabSeries.className = "btn btn-sm btn-secondary";
        if (btnAbsTabPodcasts) btnAbsTabPodcasts.className = "btn btn-sm btn-secondary";
        loadAbsContent();
    });

    if (btnAbsTabPodcasts) {
        btnAbsTabPodcasts.addEventListener("click", () => {
            absCurrentTab = "podcasts";
            btnAbsTabPodcasts.className = "btn btn-sm btn-primary";
            btnAbsTabSeries.className = "btn btn-sm btn-secondary";
            btnAbsTabItems.className = "btn btn-sm btn-secondary";
            loadAbsContent();
        });
    }

    let absExplorerSearchTimeout = null;
    inputAbsSearch.addEventListener("input", () => {
        clearTimeout(absExplorerSearchTimeout);
        absExplorerSearchTimeout = setTimeout(() => {
            loadAbsContent();
        }, 250);
    });

    async function loadAbsContent() {
        const query = inputAbsSearch.value.trim();
        elAbsContentList.innerHTML = `<p class="text-muted text-center py-4">${t("abs_loading")}</p>`;
        
        let endpoint = "";
        if (absCurrentTab === "series") {
            endpoint = `/api/abs/series${query ? "?q=" + encodeURIComponent(query) : ""}`;
        } else if (absCurrentTab === "podcasts") {
            endpoint = `/api/abs/podcasts${query ? "?q=" + encodeURIComponent(query) : ""}`;
        } else {
            endpoint = `/api/abs/items?limit=200${query ? "&q=" + encodeURIComponent(query) : ""}`;
        }

        try {
            const res = await fetch(endpoint);
            if (res.ok) {
                absContentList = await res.json();
                renderAbsContentList();
            } else {
                elAbsContentList.innerHTML = `<p class="text-danger text-center py-4">HTTP ${res.status}</p>`;
            }
        } catch (e) {
            elAbsContentList.innerHTML = `<p class="text-danger text-center py-4">${t("abs_not_reachable")} ${e}</p>`;
        }
    }

    function renderAbsContentList() {
        const query = (inputAbsSearch.value || "").toLowerCase().trim();
        const filtered = (absContentList || []).filter(item => {
            if (!query) return true;
            const title = (item.name || item.title || "").toLowerCase();
            const id = (item.id || "").toLowerCase();
            const author = (item.author || "").toLowerCase();
            return title.includes(query) || id.includes(query) || author.includes(query);
        });

        if (filtered.length === 0) {
            let emptyMsg = t("abs_empty_items");
            if (absCurrentTab === "series") emptyMsg = t("abs_empty_series");
            if (absCurrentTab === "podcasts") emptyMsg = t("abs_empty_podcasts");
            elAbsContentList.innerHTML = `<p class="text-muted text-center py-4">${emptyMsg}</p>`;
            return;
        }

        elAbsContentList.innerHTML = filtered.map(item => {
            const isSeries = absCurrentTab === "series";
            const isPodcast = absCurrentTab === "podcasts";
            const title = item.name || item.title || t("unnamed");
            
            let meta = "";
            let itemTypeParam = "Hoerbuch";
            if (isSeries) {
                meta = `Serie (${item.num_books} Bücher) • ID: ${item.id}`;
                itemTypeParam = "Serie";
            } else if (isPodcast) {
                meta = `Podcast (${item.num_episodes || 0} Folgen) • ID: ${item.id}`;
                itemTypeParam = "Podcast";
            } else {
                meta = `${item.author ? item.author + " • " : ""}ID: ${item.id}`;
                itemTypeParam = "Hoerbuch";
            }

            return `
                <div class="abs-series-item">
                    <div>
                        <div class="abs-series-title">${escapeHtml(title)}</div>
                        <div class="abs-series-meta font-mono">${escapeHtml(meta)}</div>
                    </div>
                    <button type="button" class="btn btn-sm btn-primary" onclick="window.selectAbsItem('${escapeHtml(item.id)}')">
                        ${t("abs_btn_apply")}
                    </button>
                </div>
            `;
        }).join("");
    }

    window.selectAbsItem = function(id, libraryId, title, itemType) {
        if (!libraryId && !title && !itemType) {
            const item = (absContentList || []).find(x => x.id === id);
            if (item) {
                const isSeries = absCurrentTab === "series";
                const isPodcast = absCurrentTab === "podcasts";
                libraryId = item.library_id || "";
                title = item.name || item.title || "";
                itemType = isSeries ? "Serie" : (isPodcast ? "Podcast" : "Hoerbuch");
            }
        }
        inputTagTargetId.value = id;
        if (inputTagLibraryId) {
            inputTagLibraryId.value = libraryId || "";
        }
        if (!inputTagAlias.value.trim() && title) {
            inputTagAlias.value = title;
        }
        if (itemType) {
            selectTagActionType.value = (itemType === true || itemType === "Serie") ? "Serie" : (itemType === "Podcast" ? "Podcast" : "Hoerbuch");
            selectTagActionType.dispatchEvent(new Event("change"));
        }
        elTagModal.classList.remove("hidden");
    };

    // =========================================================================
    // WEBSOCKET & REALTIME EVENTS
    // =========================================================================

    let liveToastTimeout = null;

    if (btnCloseLiveToast) {
        btnCloseLiveToast.addEventListener("click", () => {
            if (elLiveBanner) elLiveBanner.classList.add("hidden");
            if (liveToastTimeout) clearTimeout(liveToastTimeout);
        });
    }

    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            elStatusWs.className = "status-indicator status-connected";
            elStatusWs.querySelector(".label").textContent = t("status_ws_live");
            if (elMobileDotWs) elMobileDotWs.className = "dot-sm dot-connected";
        };

        ws.onclose = () => {
            elStatusWs.className = "status-indicator status-disconnected";
            elStatusWs.querySelector(".label").textContent = "Offline";
            if (elMobileDotWs) elMobileDotWs.className = "dot-sm dot-disconnected";
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            ws.close();
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleRealtimeEvent(data);
            } catch (e) {
                console.error("WS Parse Error:", e);
            }
        };
    }

    function handleRealtimeEvent(data) {
        if (data.type === "rfid_event") {
            showLiveBanner(data);
            loadTags();
            loadHistory();
        } else if (data.type === "reader_discovered") {
            loadReaders();
        } else if (data.type === "mqtt_status") {
            checkSystemStatus();
        }
    }

    function showLiveBanner(event) {
        if (!elLiveBanner) return;
        if (liveToastTimeout) clearTimeout(liveToastTimeout);

        elLiveBanner.classList.remove("hidden", "status-scanned", "status-warning", "status-removed");
        const displayTagId = formatTagId(event.tag_id);
        const isDebug = (typeof window.IS_DEBUG !== "undefined" && window.IS_DEBUG) ||
                        (window.APP_ENV === "test") ||
                        (document.documentElement.getAttribute("data-env") === "test") ||
                        document.documentElement.classList.contains("debug-mode");
        const prefix = isDebug ? "[TEST EVENT] " : "";

        if (event.status === "removed") {
            elLiveBanner.classList.add("status-removed");
            elLiveEventType.textContent = isDebug ? "[TEST] REMOVED" : "REMOVED";
            elLiveEventType.style.background = "var(--status-danger)";
            elLiveTagName.textContent = `${prefix}Tag ${displayTagId} removed`;
            elLiveEventDetails.textContent = `Stop at ${event.target_player || "target player"}`;
            btnLiveEdit.classList.add("hidden");

            // Auto-dismiss tag removal after 30 seconds (or manual dismiss via close button)
            liveToastTimeout = setTimeout(() => {
                elLiveBanner.classList.add("hidden");
            }, 30000);
        } else if (event.status === "warning") {
            elLiveBanner.classList.add("status-warning");
            elLiveEventType.textContent = isDebug ? "[TEST] UNKNOWN" : "NEW TAG";
            elLiveEventType.style.background = "var(--status-warning)";
            elLiveTagName.textContent = `${prefix}Tag: ${displayTagId}`;
            elLiveEventDetails.textContent = `Reader: ${event.reader_id || "Reader"}. Unconfigured tag detected.`;
            btnLiveEdit.classList.remove("hidden");
            btnLiveEdit.onclick = () => window.editTag(event.tag_id);
            // Stays permanently visible until manually closed or replaced by next scan
        } else {
            elLiveBanner.classList.add("status-scanned");
            elLiveEventType.textContent = isDebug ? "[TEST] SCANNED" : "SCANNED";
            elLiveEventType.style.background = "var(--status-success)";
            elLiveTagName.textContent = `${prefix}${event.alias || ("Tag " + displayTagId)}`;
            elLiveEventDetails.textContent = `${event.action_type || "Action"} -> ${event.target_player || "target player"}`;
            btnLiveEdit.classList.remove("hidden");
            btnLiveEdit.onclick = () => window.editTag(event.tag_id);
            // Stays permanently visible until manually closed or replaced by next scan
        }
    }

    // =========================================================================
    // FIRMWARE & FLASHER LOGIC
    // =========================================================================

    async function loadFirmwareTemplates() {
        try {
            const res = await fetch("/api/firmware/templates");
            if (res.ok) {
                firmwareTemplates = await res.json();
                if (flasherHwSelect) {
                    const currentVal = flasherHwSelect.value;
                    flasherHwSelect.innerHTML = firmwareTemplates.map(t => 
                        `<option value="${t.id}" ${t.id === currentVal ? "selected" : (t.recommended && !currentVal ? "selected" : "")}>
                            ${t.recommended ? "⭐ " : ""}${escapeHtml(t.name)}
                        </option>`
                    ).join("");
                }
                updateHardwareDetails();
            }
        } catch (e) {
            console.error("Fehler beim Laden der Firmware-Templates:", e);
        }
    }

    function updateFlasherReadersList() {
        if (!flasherReaderSelect) return;
        const currentSelected = flasherReaderSelect.value;
        let html = `<option value="__custom__">${t("flasher_new_reader")}</option>`;
        readersList.forEach(r => {
            html += `<option value="${escapeHtml(r.reader_id)}">${escapeHtml(r.reader_id)} (${escapeHtml(r.target_player)})</option>`;
        });
        flasherReaderSelect.innerHTML = html;
        if (currentSelected && currentSelected !== "__custom__") {
            flasherReaderSelect.value = currentSelected;
        }
    }

    if (flasherReaderSelect) {
        flasherReaderSelect.addEventListener("change", () => {
            if (flasherReaderSelect.value === "__custom__") {
                flasherReaderIdInput.disabled = false;
                flasherReaderIdInput.focus();
            } else {
                flasherReaderIdInput.value = flasherReaderSelect.value;
                flasherReaderIdInput.disabled = false;
            }
            generateYamlPreview();
        });
    }

    function getSelectedHardwareProfile() {
        const hwId = flasherHwSelect ? flasherHwSelect.value : "esp32_pn5180";
        return firmwareTemplates.find(t => t.id === hwId) || firmwareTemplates[0] || null;
    }

    function updateHardwareDetails() {
        const profile = getSelectedHardwareProfile();
        if (!profile) return;

        if (flasherHwName) flasherHwName.textContent = profile.name;
        if (flasherHwDesc) flasherHwDesc.textContent = profile.description;

        const isPlatformIO = profile.framework === "platformio";

        // Step 2 Titles & Descriptions
        if (flasherStep2Title) {
            flasherStep2Title.textContent = isPlatformIO 
                ? t("flasher_step2_title_platformio", "2. Custom Firmware Configuration (config.h)")
                : t("flasher_step2_title_esphome", "2. ESPHome Configuration (.yaml)");
        }
        if (flasherStep2Desc) {
            flasherStep2Desc.textContent = isPlatformIO
                ? t("flasher_step2_desc_platformio", "Dedicated C++ / PlatformIO firmware for Toniebox SLIX2 / native NFC presence. Settings are generated into config.h.")
                : t("flasher_step2_desc_esphome", "Credentials from your Docker server are automatically inserted. Download the .yaml file or copy it for Home Assistant.");
        }

        if (flasherPreviewTitle) {
            flasherPreviewTitle.textContent = isPlatformIO
                ? t("flasher_preview_configh", "Generated config.h Preview:")
                : t("flasher_preview_yaml", "Generated YAML Preview:");
        }

        if (btnDownloadYaml) {
            btnDownloadYaml.textContent = isPlatformIO
                ? t("flasher_download_configh", "Download config.h")
                : t("flasher_download_yaml", "Download ESPHome YAML");
        }

        // Action Buttons Visibility
        if (btnDownloadZip) {
            btnDownloadZip.style.display = isPlatformIO ? "inline-flex" : "none";
        }

        // Download Bin Button visibility (esp32_pn5180, m5atom_lite_rfid, m5atom_lite_rfid_native)
        if (btnDownloadBin) {
            btnDownloadBin.style.display = (profile.id === "m5atom_lite_rfid" || profile.id === "m5atom_lite_rfid_native" || profile.id === "esp32_pn5180") ? "inline-flex" : "none";
        }

        // Step 3 Instructions Toggle
        if (flasherInstructionsEsphome) {
            flasherInstructionsEsphome.style.display = isPlatformIO ? "none" : "grid";
        }
        if (flasherInstructionsPlatformio) {
            flasherInstructionsPlatformio.style.display = isPlatformIO ? "grid" : "none";
        }

        // Render Pinout Table
        if (flasherPinoutTable) {
            if (profile.pinout && profile.pinout.length > 0) {
                let tableHtml = `<table class="pinout-table-compact">
                    <thead><tr><th>Pin</th><th>Signal</th><th>GPIO</th></tr></thead><tbody>`;
                profile.pinout.forEach(p => {
                    tableHtml += `<tr>
                        <td><strong>${escapeHtml(p.pin)}</strong></td>
                        <td>${escapeHtml(p.signal)}</td>
                        <td><code class="font-mono">${escapeHtml(p.gpio)}</code></td>
                    </tr>`;
                });
                tableHtml += `</tbody></table>`;
                flasherPinoutTable.innerHTML = tableHtml;
            } else {
                flasherPinoutTable.innerHTML = `<p class="text-xs text-muted">No pinout details available.</p>`;
            }
        }

        // Render LED Guide
        if (flasherLedGuideSection) {
            if (profile.led_states && profile.led_states.length > 0) {
                flasherLedGuideSection.style.display = "block";
                if (flasherLedGuideList) {
                    flasherLedGuideList.innerHTML = profile.led_states.map(s => `
                        <div class="led-guide-item">
                            <span class="led-dot" style="background: ${s.color}; color: ${s.color};"></span>
                            <span class="led-name">${escapeHtml(s.name)}</span>
                            <span class="led-state-desc">${escapeHtml(s.state)}</span>
                        </div>
                    `).join("");
                }
            } else {
                flasherLedGuideSection.style.display = "none";
            }
        }
    }

    let yamlDebounceTimer = null;
    function triggerYamlPreviewDebounced() {
        clearTimeout(yamlDebounceTimer);
        yamlDebounceTimer = setTimeout(generateYamlPreview, 200);
    }

    if (flasherHwSelect) {
        flasherHwSelect.addEventListener("change", () => {
            updateHardwareDetails();
            generateYamlPreview();
        });
    }

    if (flasherReaderIdInput) flasherReaderIdInput.addEventListener("input", triggerYamlPreviewDebounced);
    if (flasherWifiSsid) flasherWifiSsid.addEventListener("input", triggerYamlPreviewDebounced);
    if (flasherWifiPass) flasherWifiPass.addEventListener("input", triggerYamlPreviewDebounced);

    async function generateYamlPreview() {
        if (!flasherYamlPreview) return;
        const hwType = flasherHwSelect ? flasherHwSelect.value : "esp32_pn5180";
        const readerId = flasherReaderIdInput ? (flasherReaderIdInput.value.trim() || "reader_box1") : "reader_box1";
        const wifiSsid = flasherWifiSsid ? flasherWifiSsid.value.trim() : "";
        const wifiPass = flasherWifiPass ? flasherWifiPass.value.trim() : "";

        const params = new URLSearchParams({
            hardware_type: hwType,
            reader_id: readerId,
        });
        if (wifiSsid) params.append("wifi_ssid", wifiSsid);
        if (wifiPass) params.append("wifi_password", wifiPass);

        try {
            const res = await fetch(`/api/firmware/generate-yaml?${params.toString()}`);
            if (res.ok) {
                const data = await res.json();
                flasherYamlPreview.textContent = data.yaml;
                if (yamlFilenameBadge) yamlFilenameBadge.textContent = data.filename;
            } else {
                flasherYamlPreview.textContent = "# Could not generate configuration";
            }
        } catch (e) {
            flasherYamlPreview.textContent = "# Error generating configuration";
        }
    }

    if (btnDownloadYaml) {
        btnDownloadYaml.addEventListener("click", () => {
            const hwType = flasherHwSelect ? flasherHwSelect.value : "m5atom_lite_rfid";
            const readerId = flasherReaderIdInput ? (flasherReaderIdInput.value.trim() || "reader_atom_1") : "reader_atom_1";
            const wifiSsid = flasherWifiSsid ? flasherWifiSsid.value.trim() : "";
            const wifiPass = flasherWifiPass ? flasherWifiPass.value.trim() : "";

            const params = new URLSearchParams({
                hardware_type: hwType,
                reader_id: readerId,
                download: "true"
            });
            if (wifiSsid) params.append("wifi_ssid", wifiSsid);
            if (wifiPass) params.append("wifi_password", wifiPass);

            window.location.href = `/api/firmware/generate-yaml?${params.toString()}`;
        });
    }

    if (btnDownloadZip) {
        btnDownloadZip.addEventListener("click", () => {
            const hwType = flasherHwSelect ? flasherHwSelect.value : "esp32_pn5180";
            const readerId = flasherReaderIdInput ? (flasherReaderIdInput.value.trim() || "reader_box1") : "reader_box1";
            const wifiSsid = flasherWifiSsid ? flasherWifiSsid.value.trim() : "";
            const wifiPass = flasherWifiPass ? flasherWifiPass.value.trim() : "";

            const params = new URLSearchParams();
            if (readerId) params.append("reader_id", readerId);
            if (wifiSsid) params.append("wifi_ssid", wifiSsid);
            if (wifiPass) params.append("wifi_password", wifiPass);

            window.location.href = `/api/firmware/download-zip/${hwType}?${params.toString()}`;
        });
    }

    if (btnDownloadBin) {
        btnDownloadBin.addEventListener("click", () => {
            const profile = getSelectedHardwareProfile();
            const hw = profile ? profile.id : "esp32_pn5180";
            window.location.href = `/api/firmware/download-bin/${hw}`;
        });
    }

    if (btnCopyYaml) {
        btnCopyYaml.addEventListener("click", async () => {
            if (!flasherYamlPreview) return;
            const text = flasherYamlPreview.textContent;
            try {
                await navigator.clipboard.writeText(text);
                const originalText = btnCopyYaml.textContent;
                btnCopyYaml.textContent = "✓ Copied!";
                btnCopyYaml.classList.add("btn-success");
                setTimeout(() => {
                    btnCopyYaml.textContent = originalText;
                    btnCopyYaml.classList.remove("btn-success");
                }, 2000);
            } catch (err) {
                console.error("Kopieren fehlgeschlagen:", err);
            }
        });
    }

    // =========================================================================
    // UTILS
    // =========================================================================

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function truncate(str, max) {
        if (!str) return "";
        return str.length > max ? str.substring(0, max) + "..." : str;
    }

    function formatDate(dateStr) {
        if (!dateStr) return "";
        try {
            let s = String(dateStr).trim();
            if (!s.endsWith("Z") && !s.includes("+") && !s.includes("-", 11)) {
                s = s.replace(" ", "T") + "Z";
            }
            const d = new Date(s);
            if (isNaN(d.getTime())) return dateStr;
            const locale = (window.APP_LANG && window.APP_LANG.startsWith("de")) ? "de-DE" : "en-US";
            return d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) + 
                   " " + d.toLocaleDateString(locale, { day: "2-digit", month: "2-digit", year: "numeric" });
        } catch (e) {
            return dateStr;
        }
    }

    // Initial Load & Intervals
    loadTags();
    loadReaders();
    checkSystemStatus();
    connectWebSocket();
    setInterval(checkSystemStatus, 15000);
});