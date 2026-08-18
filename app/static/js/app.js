/**
 * NFC Media Controller - Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // State
    let tagsList = [];
    let readersList = [];
    let historyList = [];
    let absContentList = [];
    let absCurrentTab = 'series'; // 'series' or 'items'
    let modalAbsCurrentTab = 'series';
    let ws = null;
    let currentEditingTagId = null;

    // DOM Elements - Status
    const elStatusMqtt = document.getElementById('status-mqtt');
    const elStatusAbs = document.getElementById('status-abs');
    const elStatusWs = document.getElementById('status-ws');

    // DOM Elements - Tabs
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    // DOM Elements - Tags Table
    const elTagsTableBody = document.getElementById('tags-table-body');
    const elTagsEmptyState = document.getElementById('tags-empty-state');
    const elTagsCount = document.getElementById('tags-count');
    const elSearchInput = document.getElementById('tags-search-input');
    const elFilterStatus = document.getElementById('tags-filter-status');
    const elFilterType = document.getElementById('tags-filter-type');
    const btnAddTag = document.getElementById('btn-add-tag');

    // DOM Elements - Readers Table
    const elReadersTableBody = document.getElementById('readers-table-body');
    const elReadersEmptyState = document.getElementById('readers-empty-state');
    const elReadersCount = document.getElementById('readers-count');
    const btnAddReader = document.getElementById('btn-add-reader');

    // DOM Elements - History
    const elHistoryTableBody = document.getElementById('history-table-body');
    const btnRefreshHistory = document.getElementById('btn-refresh-history');

    // DOM Elements - Live Banner
    const elLiveBanner = document.getElementById('live-scan-banner');
    const elLiveEventType = document.getElementById('live-event-type');
    const elLiveTagName = document.getElementById('live-tag-name');
    const elLiveEventDetails = document.getElementById('live-event-details');
    const btnLiveEdit = document.getElementById('live-banner-edit-btn');

    // DOM Elements - Modals
    const elTagModal = document.getElementById('tag-modal');
    const elTagForm = document.getElementById('tag-form');
    const elTagModalTitle = document.getElementById('tag-modal-title');
    const inputTagId = document.getElementById('tag-id-input');
    const inputTagAlias = document.getElementById('tag-alias-input');
    const selectTagActionType = document.getElementById('tag-action-type');
    const groupLibraryId = document.getElementById('group-library-id');
    const inputTagLibraryId = document.getElementById('tag-library-id');
    const inputTagVolume = document.getElementById('tag-volume');
    const inputTagTargetId = document.getElementById('tag-target-id');
    const checkTagRandom = document.getElementById('tag-random');
    const inputTagExtraParams = document.getElementById('tag-extra-params');
    const btnToggleModalAbsPicker = document.getElementById('btn-toggle-modal-abs-picker');
    const elTargetIdHelper = document.getElementById('target-id-helper');

    // In-Modal ABS Picker Elements
    const elModalAbsPickerBox = document.getElementById('modal-abs-picker-box');
    const btnModalAbsTabSeries = document.getElementById('btn-modal-abs-tab-series');
    const btnModalAbsTabItems = document.getElementById('btn-modal-abs-tab-items');
    const btnCloseModalAbsPicker = document.getElementById('btn-close-modal-abs-picker');
    const inputModalAbsSearch = document.getElementById('modal-abs-search-input');
    const elModalAbsResultsList = document.getElementById('modal-abs-results-list');

    const elReaderModal = document.getElementById('reader-modal');
    const elReaderForm = document.getElementById('reader-form');
    const elReaderModalTitle = document.getElementById('reader-modal-title');
    const inputReaderId = document.getElementById('reader-id-input');
    const inputReaderTargetPlayer = document.getElementById('reader-target-player');
    const inputReaderAbsToken = document.getElementById('reader-abs-token');
    const inputReaderNotes = document.getElementById('reader-notes');

    const elPayloadModal = document.getElementById('payload-modal');
    const elPayloadModalContent = document.getElementById('payload-modal-content');
    const btnCopyPayloadModal = document.getElementById('btn-copy-payload-modal');

    const elLogsModal = document.getElementById('logs-modal');
    const btnOpenLogs = document.getElementById('btn-open-logs');
    const elSystemLogsContent = document.getElementById('system-logs-content');
    const btnRefreshLogs = document.getElementById('btn-refresh-logs');
    const btnCopyLogs = document.getElementById('btn-copy-logs');

    // DOM Elements - Simulator & ABS Tab
    const inputSimReaderId = document.getElementById('sim-reader-id');
    const inputSimTagId = document.getElementById('sim-tag-id');
    const btnSimScan = document.getElementById('btn-sim-scan');
    const btnSimRemove = document.getElementById('btn-sim-remove');
    const elSimResultContainer = document.getElementById('sim-result-container');
    const elSimResultOutput = document.getElementById('sim-result-output');
    
    const btnAbsTabSeries = document.getElementById('btn-abs-tab-series');
    const btnAbsTabItems = document.getElementById('btn-abs-tab-items');
    const inputAbsSearch = document.getElementById('abs-search-input');
    const elAbsContentList = document.getElementById('abs-content-list');

    // =========================================================================
    // INITIALIZATION & TAB NAVIGATION
    // =========================================================================

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetTab = document.getElementById(btn.dataset.tab);
            if (targetTab) {
                targetTab.classList.add('active');
            }

            if (btn.dataset.tab === 'history-tab') {
                loadHistory();
            } else if (btn.dataset.tab === 'tools-tab') {
                loadAbsContent();
            }
        });
    });

    // Close Modals via Close-Buttons & Backdrop
    document.querySelectorAll('[data-close-modal]').forEach(el => {
        el.addEventListener('click', () => {
            if (elTagModal) elTagModal.classList.add('hidden');
            if (elReaderModal) elReaderModal.classList.add('hidden');
            if (elPayloadModal) elPayloadModal.classList.add('hidden');
            if (elLogsModal) elLogsModal.classList.add('hidden');
        });
    });

    document.querySelectorAll('.modal-backdrop').forEach(bd => {
        bd.addEventListener('click', () => {
            if (elTagModal) elTagModal.classList.add('hidden');
            if (elReaderModal) elReaderModal.classList.add('hidden');
            if (elPayloadModal) elPayloadModal.classList.add('hidden');
            if (elLogsModal) elLogsModal.classList.add('hidden');
        });
    });

    // Dynamic Helper Text on Action Type Change
    selectTagActionType.addEventListener('change', () => {
        const val = selectTagActionType.value;
        if (val === 'Serie') {
            if (groupLibraryId) groupLibraryId.classList.remove('hidden');
            if (inputTagLibraryId) inputTagLibraryId.required = true;
            elTargetIdHelper.textContent = 'Audiobookshelf Serien-ID (z. B. 01048bbc...). Ermittelt live das nächste unfertige Buch (z. B. Folge 4/10).';
            inputTagTargetId.placeholder = '01048bbc-3909-4db4-af85-ed81d2f087b3';
            btnToggleModalAbsPicker.classList.remove('hidden');
            btnToggleModalAbsPicker.textContent = '📚 In ABS suchen';
        } else if (val === 'Hoerbuch') {
            if (groupLibraryId) groupLibraryId.classList.remove('hidden');
            if (inputTagLibraryId) inputTagLibraryId.required = true;
            elTargetIdHelper.textContent = 'ABS Item-ID (z. B. 5dcb6e5d-...).';
            inputTagTargetId.placeholder = '5dcb6e5d-962d-434f-b26d-60a6a8cc30f8';
            btnToggleModalAbsPicker.classList.remove('hidden');
            btnToggleModalAbsPicker.textContent = '🎧 In ABS suchen';
        } else if (val === 'Album') {
            if (groupLibraryId) groupLibraryId.classList.add('hidden');
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ''; }
            elTargetIdHelper.textContent = 'Music Assistant Album (z. B. mass://album/xyz oder Spotify/Tidal Album-URI).';
            inputTagTargetId.placeholder = 'mass://album/mein_album';
            btnToggleModalAbsPicker.classList.add('hidden');
            elModalAbsPickerBox.classList.add('hidden');
        } else if (val === 'Playlist') {
            if (groupLibraryId) groupLibraryId.classList.add('hidden');
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ''; }
            elTargetIdHelper.textContent = 'Music Assistant Playlist (z. B. mass://playlist/gute_nacht oder Spotify Playlist-URI).';
            inputTagTargetId.placeholder = 'mass://playlist/schlafenszeit';
            btnToggleModalAbsPicker.classList.add('hidden');
            elModalAbsPickerBox.classList.add('hidden');
        } else if (val === 'Licht' || val === 'Szene') {
            if (groupLibraryId) groupLibraryId.classList.add('hidden');
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ''; }
            elTargetIdHelper.textContent = 'Home Assistant Entitäts-ID (z. B. light.kinderzimmer oder scene.schlafenszeit)';
            inputTagTargetId.placeholder = val === 'Licht' ? 'light.kinderzimmer' : 'scene.schlafenszeit';
            btnToggleModalAbsPicker.classList.add('hidden');
            elModalAbsPickerBox.classList.add('hidden');
        } else {
            if (groupLibraryId) groupLibraryId.classList.add('hidden');
            if (inputTagLibraryId) { inputTagLibraryId.required = false; inputTagLibraryId.value = ''; }
            elTargetIdHelper.textContent = 'Ziel-ID oder Befehl';
            inputTagTargetId.placeholder = 'Ziel-ID';
            btnToggleModalAbsPicker.classList.add('hidden');
            elModalAbsPickerBox.classList.add('hidden');
        }
    });

    // =========================================================================
    // IN-MODAL ABS PICKER LOGIC
    // =========================================================================

    btnToggleModalAbsPicker.addEventListener('click', () => {
        const isHidden = elModalAbsPickerBox.classList.contains('hidden');
        if (isHidden) {
            elModalAbsPickerBox.classList.remove('hidden');
            if (selectTagActionType.value === 'Hoerbuch') {
                setModalAbsTab('items');
            } else {
                setModalAbsTab('series');
            }
            loadModalAbsContent();
            inputModalAbsSearch.focus();
        } else {
            elModalAbsPickerBox.classList.add('hidden');
        }
    });

    btnCloseModalAbsPicker.addEventListener('click', () => {
        elModalAbsPickerBox.classList.add('hidden');
    });

    btnModalAbsTabSeries.addEventListener('click', () => setModalAbsTab('series'));
    btnModalAbsTabItems.addEventListener('click', () => setModalAbsTab('items'));

    function setModalAbsTab(tab) {
        modalAbsCurrentTab = tab;
        if (tab === 'series') {
            btnModalAbsTabSeries.className = 'btn btn-xs btn-primary';
            btnModalAbsTabItems.className = 'btn btn-xs btn-secondary';
        } else {
            btnModalAbsTabItems.className = 'btn btn-xs btn-primary';
            btnModalAbsTabSeries.className = 'btn btn-xs btn-secondary';
        }
        loadModalAbsContent();
    }

    inputModalAbsSearch.addEventListener('input', () => {
        renderModalAbsResults();
    });

    async function loadModalAbsContent() {
        elModalAbsResultsList.innerHTML = `<p class="text-muted text-center py-2 text-xs">Lade Inhalte aus allen ABS-Bibliotheken...</p>`;
        const endpoint = modalAbsCurrentTab === 'series' ? '/api/abs/series' : '/api/abs/items?limit=100';
        try {
            const res = await fetch(endpoint);
            if (res.ok) {
                absContentList = await res.json();
                renderModalAbsResults();
            } else {
                elModalAbsResultsList.innerHTML = `<p class="text-danger text-center py-2 text-xs">Fehler beim Laden (HTTP ${res.status}).</p>`;
            }
        } catch (e) {
            elModalAbsResultsList.innerHTML = `<p class="text-danger text-center py-2 text-xs">ABS nicht erreichbar: ${e}</p>`;
        }
    }

    function renderModalAbsResults() {
        const query = inputModalAbsSearch.value.toLowerCase().trim();
        const filtered = absContentList.filter(item => {
            const title = (item.name || item.title || '').toLowerCase();
            const id = (item.id || '').toLowerCase();
            const author = (item.author || '').toLowerCase();
            return title.includes(query) || id.includes(query) || author.includes(query);
        });

        if (filtered.length === 0) {
            const msg = modalAbsCurrentTab === 'series'
                ? 'Keine Serien gefunden (wechsle oben zu "🎧 Hörbücher" falls nicht als Serie angelegt).'
                : 'Keine Hörbücher gefunden.';
            elModalAbsResultsList.innerHTML = `<p class="text-muted text-center py-2 text-xs">${msg}</p>`;
            return;
        }

        elModalAbsResultsList.innerHTML = filtered.map(item => {
            const isSeries = modalAbsCurrentTab === 'series';
            const title = item.name || item.title || 'Unbekannt';
            const meta = isSeries
                ? `Serie (${item.num_books} Bücher) • ID: ${item.id}`
                : `${item.author ? item.author + ' • ' : ''}ID: ${item.id}`;

            return `
                <div class="abs-series-item py-1">
                    <div style="max-width: 70%;">
                        <div class="abs-series-title text-xs"><strong>${escapeHtml(title)}</strong></div>
                        <div class="abs-series-meta font-mono" style="font-size: 10px;">${escapeHtml(meta)}</div>
                    </div>
                    <button type="button" class="btn btn-xs btn-primary" onclick="window.applyModalAbsItem('${escapeHtml(item.id)}', '${escapeHtml(item.library_id || '')}', '${escapeHtml(title)}', ${isSeries})">
                        Übernehmen
                    </button>
                </div>
            `;
        }).join('');
    }

    window.applyModalAbsItem = function(id, libraryId, title, isSeries) {
        inputTagTargetId.value = id;
        if (inputTagLibraryId) {
            inputTagLibraryId.value = libraryId || '';
        }
        if (!inputTagAlias.value.trim()) {
            inputTagAlias.value = title;
        }
        selectTagActionType.value = isSeries ? 'Serie' : 'Hoerbuch';
        selectTagActionType.dispatchEvent(new Event('change'));
        elModalAbsPickerBox.classList.add('hidden');
        
        // Highlight Effect
        inputTagTargetId.style.borderColor = '#10b981';
        if (inputTagLibraryId) inputTagLibraryId.style.borderColor = '#10b981';
        setTimeout(() => { 
            inputTagTargetId.style.borderColor = ''; 
            if (inputTagLibraryId) inputTagLibraryId.style.borderColor = '';
        }, 1200);
    };

    // =========================================================================
    // API CALLS & DATA LOADING
    // =========================================================================

    async function loadTags() {
        try {
            const res = await fetch('/api/tags');
            if (res.ok) {
                tagsList = await res.json();
                renderTagsTable();
            }
        } catch (e) {
            console.error('Fehler beim Laden der Tags:', e);
        }
    }

    async function loadReaders() {
        try {
            const res = await fetch('/api/readers');
            if (res.ok) {
                readersList = await res.json();
                renderReadersTable();
            }
        } catch (e) {
            console.error('Fehler beim Laden der Reader:', e);
        }
    }

    async function loadHistory() {
        try {
            const res = await fetch('/api/history?limit=50');
            if (res.ok) {
                historyList = await res.json();
                renderHistoryTable(historyList);
            }
        } catch (e) {
            console.error('Fehler beim Laden der Historie:', e);
        }
    }

    async function checkSystemStatus() {
        try {
            const res = await fetch('/api/system/status');
            if (res.ok) {
                const data = await res.json();
                
                // MQTT
                if (data.mqtt.connected) {
                    elStatusMqtt.className = 'status-indicator status-connected';
                    elStatusMqtt.querySelector('.label').textContent = `MQTT: ${data.mqtt.broker}`;
                } else {
                    elStatusMqtt.className = 'status-indicator status-disconnected';
                    elStatusMqtt.querySelector('.label').textContent = `MQTT: Getrennt`;
                }

                // ABS
                if (data.audiobookshelf.reachable) {
                    elStatusAbs.className = 'status-indicator status-connected';
                    const userLabel = data.audiobookshelf.username ? data.audiobookshelf.username : 'Verbunden';
                    elStatusAbs.querySelector('.label').textContent = `ABS: ${userLabel}`;
                } else {
                    elStatusAbs.className = 'status-indicator status-unknown';
                    elStatusAbs.querySelector('.label').textContent = `ABS: Nicht erreichbar`;
                }
            }
        } catch (e) {
            console.error('Status-Check Fehler:', e);
        }
    }

    // =========================================================================
    // TABLE RENDERING
    // =========================================================================

    function renderTagsTable() {
        const query = elSearchInput.value.toLowerCase().trim();
        const statusFilter = elFilterStatus.value;
        const typeFilter = elFilterType.value;

        const filtered = tagsList.filter(tag => {
            const matchesQuery = (tag.tag_id && tag.tag_id.toLowerCase().includes(query)) ||
                                 (tag.alias && tag.alias.toLowerCase().includes(query)) ||
                                 (tag.target_id && tag.target_id.toLowerCase().includes(query));

            const isUnconfigured = !tag.action_type || tag.action_type.trim() === '';
            let matchesStatus = true;
            if (statusFilter === 'unconfigured') matchesStatus = isUnconfigured;
            if (statusFilter === 'configured') matchesStatus = !isUnconfigured;

            let matchesType = true;
            if (typeFilter !== 'all') matchesType = (tag.action_type === typeFilter);

            return matchesQuery && matchesStatus && matchesType;
        });

        elTagsCount.textContent = tagsList.length;

        if (filtered.length === 0) {
            elTagsTableBody.innerHTML = '';
            elTagsEmptyState.classList.remove('hidden');
            return;
        }

        elTagsEmptyState.classList.add('hidden');
        elTagsTableBody.innerHTML = filtered.map(tag => {
            const isUnconfigured = !tag.action_type || tag.action_type.trim() === '';
            const statusBadge = isUnconfigured
                ? `<span class="badge badge-warning">⚠️ Unkonfiguriert</span>`
                : `<span class="badge badge-configured">✅ Bereit</span>`;

            const actionTypeBadge = tag.action_type && tag.action_type.trim() !== ''
                ? `<span class="badge badge-type">${escapeHtml(tag.action_type)}</span>`
                : `<span class="text-muted">—</span>`;

            const targetDisplay = (!isUnconfigured && tag.target_id)
                ? `<span title="${escapeHtml(tag.target_id)}">${escapeHtml(truncate(tag.target_id, 28))}</span>`
                : `<span class="text-muted">—</span>`;

            const volumeDisplay = isUnconfigured
                ? `<span class="text-muted">—</span>`
                : (tag.volume !== null ? `${tag.volume}%` : `<span class="text-muted">Standard</span>`);

            const randomDisplay = isUnconfigured
                ? `<span class="text-muted">—</span>`
                : (tag.random ? '🔀 Ja' : '<span class="text-muted">Nein</span>');

            const lastScannedDisplay = tag.last_scanned ? formatDate(tag.last_scanned) : '<span class="text-muted">Nie</span>';

            return `
                <tr>
                    <td>${statusBadge}</td>
                    <td class="font-mono"><strong>${escapeHtml(tag.tag_id)}</strong></td>
                    <td>${escapeHtml(tag.alias || 'Unbenannt')}</td>
                    <td>${actionTypeBadge}</td>
                    <td class="font-mono text-muted">${targetDisplay}</td>
                    <td>${volumeDisplay}</td>
                    <td>${randomDisplay}</td>
                    <td>${lastScannedDisplay}</td>
                    <td class="actions-cell">
                        <button class="btn btn-sm btn-secondary" onclick="window.editTag('${escapeHtml(tag.tag_id)}')">
                            ✏️ Bearbeiten
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="window.deleteTagConfirm('${escapeHtml(tag.tag_id)}')">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderReadersTable() {
        elReadersCount.textContent = readersList.length;

        if (readersList.length === 0) {
            elReadersTableBody.innerHTML = '';
            elReadersEmptyState.classList.remove('hidden');
            return;
        }

        elReadersEmptyState.classList.add('hidden');
        elReadersTableBody.innerHTML = readersList.map(reader => {
            const tokenBadge = reader.abs_user_token
                ? `<span class="badge badge-configured">Gesetzt</span>`
                : `<span class="badge badge-type text-muted">Standard</span>`;

            return `
                <tr>
                    <td class="font-mono"><strong>${escapeHtml(reader.reader_id)}</strong></td>
                    <td class="font-mono">${escapeHtml(reader.target_player)}</td>
                    <td>${tokenBadge}</td>
                    <td>${escapeHtml(reader.notes || '—')}</td>
                    <td class="actions-cell">
                        <button class="btn btn-sm btn-secondary" onclick="window.editReader('${escapeHtml(reader.reader_id)}')">
                            ✏️ Bearbeiten
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="window.deleteReaderConfirm('${escapeHtml(reader.reader_id)}')">
                            🗑️
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderHistoryTable(items) {
        if (!items || items.length === 0) {
            elHistoryTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-4">Noch keine Scans aufgezeichnet.</td></tr>`;
            return;
        }

        elHistoryTableBody.innerHTML = items.map((item, idx) => {
            let statusBadge = `<span class="badge badge-info">${escapeHtml(item.status)}</span>`;
            if (item.action_executed === 'warning') statusBadge = `<span class="badge badge-warning">⚠️ Warnung</span>`;
            if (item.action_executed === 'stop') statusBadge = `<span class="badge badge-type">⏹ Stop</span>`;
            if (item.action_executed === 'media') statusBadge = `<span class="badge badge-configured">▶ Media</span>`;

            return `
                <tr>
                    <td>${formatDate(item.timestamp)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <strong class="font-mono">${escapeHtml(item.tag_id)}</strong>
                        ${item.tag_alias ? `<div class="text-muted text-xs">${escapeHtml(item.tag_alias)}</div>` : ''}
                    </td>
                    <td class="font-mono">${escapeHtml(item.reader_id)}</td>
                    <td><code>${escapeHtml(item.action_executed || '—')}</code></td>
                    <td>
                        <div class="payload-cell">
                            <span class="font-mono text-muted text-xs" title="${escapeHtml(item.payload || '')}">
                                ${escapeHtml(truncate(item.payload || '', 36))}
                            </span>
                            <button class="btn btn-xs btn-secondary" onclick="window.copyPayload(${idx})" title="In Zwischenablage kopieren">
                                📋
                            </button>
                            <button class="btn btn-xs btn-secondary" onclick="window.viewPayload(${idx})" title="Vollständigen Payload anzeigen">
                                👁️
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    // Payload Clipboard & Viewer
    window.copyPayload = function(idx) {
        const item = historyList[idx];
        if (!item || !item.payload) return;
        navigator.clipboard.writeText(item.payload).then(() => {
            alert('Payload in die Zwischenablage kopiert! ✅');
        }).catch(err => {
            console.error('Kopieren fehlgeschlagen:', err);
        });
    };

    window.viewPayload = function(idx) {
        const item = historyList[idx];
        if (!item) return;
        try {
            const parsed = JSON.parse(item.payload);
            elPayloadModalContent.textContent = JSON.stringify(parsed, null, 2);
        } catch {
            elPayloadModalContent.textContent = item.payload || '';
        }
        btnCopyPayloadModal.onclick = () => {
            navigator.clipboard.writeText(elPayloadModalContent.textContent);
            alert('Kopiert! ✅');
        };
        elPayloadModal.classList.remove('hidden');
    };

    // System Logs Viewer
    async function loadSystemLogs() {
        if (!elSystemLogsContent) return;
        elSystemLogsContent.textContent = 'Lade Server-Logs...';
        try {
            const res = await fetch('/api/system/logs');
            if (res.ok) {
                const data = await res.json();
                elSystemLogsContent.textContent = (data.logs || []).join('\n') || 'Keine Logs vorhanden.';
                elSystemLogsContent.scrollTop = elSystemLogsContent.scrollHeight;
            } else {
                elSystemLogsContent.textContent = 'Fehler beim Laden der Logs (HTTP ' + res.status + ')';
            }
        } catch (e) {
            elSystemLogsContent.textContent = 'Netzwerkfehler: ' + e;
        }
    }

    if (btnOpenLogs) {
        btnOpenLogs.addEventListener('click', () => {
            if (elLogsModal) elLogsModal.classList.remove('hidden');
            loadSystemLogs();
        });
    }

    if (btnRefreshLogs) {
        btnRefreshLogs.addEventListener('click', loadSystemLogs);
    }

    if (btnCopyLogs) {
        btnCopyLogs.addEventListener('click', () => {
            if (elSystemLogsContent && elSystemLogsContent.textContent) {
                navigator.clipboard.writeText(elSystemLogsContent.textContent).then(() => {
                    alert('Logs in Zwischenablage kopiert! ✅');
                }).catch(err => {
                    console.error('Kopieren fehlgeschlagen:', err);
                });
            }
        });
    }

    // Filter listeners
    elSearchInput.addEventListener('input', renderTagsTable);
    elFilterStatus.addEventListener('change', renderTagsTable);
    elFilterType.addEventListener('change', renderTagsTable);
    btnRefreshHistory.addEventListener('click', loadHistory);

    // =========================================================================
    // TAG CRUD MODAL
    // =========================================================================

    btnAddTag.addEventListener('click', () => {
        currentEditingTagId = null;
        elTagModalTitle.textContent = 'Neuen Tag anlegen';
        inputTagId.value = '';
        inputTagId.disabled = false;
        inputTagAlias.value = '';
        selectTagActionType.value = '';
        if (inputTagLibraryId) inputTagLibraryId.value = '';
        inputTagVolume.value = '';
        inputTagTargetId.value = '';
        checkTagRandom.checked = false;
        inputTagExtraParams.value = '{}';
        elModalAbsPickerBox.classList.add('hidden');
        selectTagActionType.dispatchEvent(new Event('change'));
        elTagModal.classList.remove('hidden');
    });

    window.editTag = function(tagId) {
        const tag = tagsList.find(t => t.tag_id === tagId);
        if (!tag) return;

        currentEditingTagId = tagId;
        elTagModalTitle.textContent = `Tag bearbeiten: ${tagId}`;
        inputTagId.value = tag.tag_id;
        inputTagId.disabled = true;
        inputTagAlias.value = tag.alias || '';
        selectTagActionType.value = tag.action_type || '';
        if (inputTagLibraryId) inputTagLibraryId.value = tag.library_id || '';
        inputTagVolume.value = tag.volume !== null ? tag.volume : '';
        inputTagTargetId.value = tag.target_id || '';
        checkTagRandom.checked = !!tag.random;
        inputTagExtraParams.value = tag.extra_params || '{}';
        elModalAbsPickerBox.classList.add('hidden');
        selectTagActionType.dispatchEvent(new Event('change'));
        elTagModal.classList.remove('hidden');
    };

    window.deleteTagConfirm = async function(tagId) {
        if (!confirm(`Soll der Tag '${tagId}' wirklich gelöscht werden?`)) return;
        try {
            const res = await fetch(`/api/tags/${encodeURIComponent(tagId)}`, { method: 'DELETE' });
            if (res.ok) {
                await loadTags();
            }
        } catch (e) {
            alert('Fehler beim Löschen des Tags: ' + e);
        }
    };

    elTagForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const tagId = inputTagId.value.trim();
        const alias = inputTagAlias.value.trim();
        const actionType = selectTagActionType.value;
        const libraryId = inputTagLibraryId ? inputTagLibraryId.value.trim() : '';
        const volumeVal = inputTagVolume.value !== '' ? parseInt(inputTagVolume.value, 10) : null;
        const targetId = inputTagTargetId.value.trim();
        const random = checkTagRandom.checked;
        const extraParams = inputTagExtraParams.value.trim() || '{}';

        if (!tagId || !alias) {
            alert('Bitte Tag ID und Name angeben.');
            return;
        }

        if ((actionType === 'Serie' || actionType === 'Hoerbuch') && (!libraryId || !targetId)) {
            alert('Für Serien und Hörbücher bitte sowohl Bibliotheks-ID als auch Ziel-ID angeben (nutze am besten "In ABS suchen").');
            return;
        }

        try {
            JSON.parse(extraParams);
        } catch (err) {
            alert('Zusatz-Parameter müssen ein gültiges JSON sein (z.B. {} oder {"brightness": 255})');
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
            extra_params: extraParams
        };

        try {
            const res = await fetch('/api/tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                elTagModal.classList.add('hidden');
                await loadTags();
            } else {
                const err = await res.json();
                alert('Fehler beim Speichern: ' + (err.detail || JSON.stringify(err)));
            }
        } catch (err) {
            alert('Netzwerkfehler: ' + err);
        }
    });

    // =========================================================================
    // READER CRUD MODAL
    // =========================================================================

    btnAddReader.addEventListener('click', () => {
        elReaderModalTitle.textContent = 'Neuen Reader anlegen';
        inputReaderId.value = '';
        inputReaderId.disabled = false;
        inputReaderTargetPlayer.value = 'media_player.';
        inputReaderAbsToken.value = '';
        inputReaderNotes.value = '';
        elReaderModal.classList.remove('hidden');
    });

    window.editReader = function(readerId) {
        const reader = readersList.find(r => r.reader_id === readerId);
        if (!reader) return;

        elReaderModalTitle.textContent = `Reader bearbeiten: ${readerId}`;
        inputReaderId.value = reader.reader_id;
        inputReaderId.disabled = true;
        inputReaderTargetPlayer.value = reader.target_player || '';
        inputReaderAbsToken.value = reader.abs_user_token || '';
        inputReaderNotes.value = reader.notes || '';
        elReaderModal.classList.remove('hidden');
    };

    window.deleteReaderConfirm = async function(readerId) {
        if (!confirm(`Soll der Reader '${readerId}' wirklich gelöscht werden?`)) return;
        try {
            const res = await fetch(`/api/readers/${encodeURIComponent(readerId)}`, { method: 'DELETE' });
            if (res.ok) {
                await loadReaders();
            }
        } catch (e) {
            alert('Fehler beim Löschen des Readers: ' + e);
        }
    };

    elReaderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const readerId = inputReaderId.value.trim();
        const targetPlayer = inputReaderTargetPlayer.value.trim();
        const absToken = inputReaderAbsToken.value.trim();
        const notes = inputReaderNotes.value.trim();

        if (!readerId || !targetPlayer) {
            alert('Bitte Reader ID und Ziel-Player angeben.');
            return;
        }

        const payload = {
            reader_id: readerId,
            target_player: targetPlayer,
            abs_user_token: absToken,
            notes: notes
        };

        try {
            const res = await fetch('/api/readers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                elReaderModal.classList.add('hidden');
                await loadReaders();
            } else {
                const err = await res.json();
                alert('Fehler beim Speichern: ' + (err.detail || JSON.stringify(err)));
            }
        } catch (err) {
            alert('Netzwerkfehler: ' + err);
        }
    });

    // =========================================================================
    // TEST SIMULATOR & ABS BROWSER TAB
    // =========================================================================

    async function runSimulation(status) {
        const readerId = inputSimReaderId.value.trim();
        const tagId = inputSimTagId.value.trim();

        if (!readerId || !tagId) {
            alert('Bitte Reader ID und Tag ID angeben.');
            return;
        }

        try {
            const res = await fetch('/api/test/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    reader_id: readerId,
                    tag_id: tagId,
                    status: status
                })
            });

            const data = await res.json();
            elSimResultContainer.classList.remove('hidden');
            elSimResultOutput.textContent = JSON.stringify(data, null, 2);
            await loadTags();
            await loadReaders();
        } catch (e) {
            alert('Simulationsfehler: ' + e);
        }
    }

    btnSimScan.addEventListener('click', () => runSimulation('scanned'));
    btnSimRemove.addEventListener('click', () => runSimulation('removed'));

    // ABS Tab Explorer
    btnAbsTabSeries.addEventListener('click', () => {
        absCurrentTab = 'series';
        btnAbsTabSeries.className = 'btn btn-sm btn-primary';
        btnAbsTabItems.className = 'btn btn-sm btn-secondary';
        loadAbsContent();
    });

    btnAbsTabItems.addEventListener('click', () => {
        absCurrentTab = 'items';
        btnAbsTabItems.className = 'btn btn-sm btn-primary';
        btnAbsTabSeries.className = 'btn btn-sm btn-secondary';
        loadAbsContent();
    });

    inputAbsSearch.addEventListener('input', () => {
        renderAbsContentList();
    });

    async function loadAbsContent() {
        elAbsContentList.innerHTML = `<p class="text-muted text-center py-4">Lade Inhalte aus allen ABS-Bibliotheken...</p>`;
        const endpoint = absCurrentTab === 'series' ? '/api/abs/series' : '/api/abs/items?limit=100';
        try {
            const res = await fetch(endpoint);
            if (res.ok) {
                absContentList = await res.json();
                renderAbsContentList();
            } else {
                elAbsContentList.innerHTML = `<p class="text-danger text-center py-4">Fehler beim Laden von ABS (HTTP ${res.status}).</p>`;
            }
        } catch (e) {
            elAbsContentList.innerHTML = `<p class="text-danger text-center py-4">ABS nicht erreichbar: ${e}</p>`;
        }
    }

    function renderAbsContentList() {
        const query = inputAbsSearch.value.toLowerCase().trim();
        const filtered = absContentList.filter(item => {
            const title = (item.name || item.title || '').toLowerCase();
            const id = (item.id || '').toLowerCase();
            const author = (item.author || '').toLowerCase();
            return title.includes(query) || id.includes(query) || author.includes(query);
        });

        if (filtered.length === 0) {
            const emptyMsg = absCurrentTab === 'series'
                ? 'Keine Serien in Audiobookshelf gefunden (prüfe, ob in ABS Serien angelegt sind oder wechsle zu "Hörbücher / Tracks").'
                : 'Keine Hörbücher in Audiobookshelf gefunden.';
            elAbsContentList.innerHTML = `<p class="text-muted text-center py-4">${emptyMsg}</p>`;
            return;
        }

        elAbsContentList.innerHTML = filtered.map(item => {
            const isSeries = absCurrentTab === 'series';
            const title = item.name || item.title || 'Unbekannt';
            const meta = isSeries
                ? `Serie (${item.num_books} Bücher) • ID: ${item.id}`
                : `${item.author ? item.author + ' • ' : ''}ID: ${item.id}`;

            return `
                <div class="abs-series-item">
                    <div>
                        <div class="abs-series-title">${escapeHtml(title)}</div>
                        <div class="abs-series-meta font-mono">${escapeHtml(meta)}</div>
                    </div>
                    <button type="button" class="btn btn-sm btn-primary" onclick="window.selectAbsItem('${escapeHtml(item.id)}', '${escapeHtml(item.library_id || '')}', '${escapeHtml(title)}', ${isSeries})">
                        Übernehmen
                    </button>
                </div>
            `;
        }).join('');
    }

    window.selectAbsItem = function(id, libraryId, title, isSeries) {
        inputTagTargetId.value = id;
        if (inputTagLibraryId) {
            inputTagLibraryId.value = libraryId || '';
        }
        if (!inputTagAlias.value.trim()) {
            inputTagAlias.value = title;
        }
        selectTagActionType.value = isSeries ? 'Serie' : 'Hoerbuch';
        selectTagActionType.dispatchEvent(new Event('change'));
        elTagModal.classList.remove('hidden');
    };

    // =========================================================================
    // WEBSOCKET & REALTIME EVENTS
    // =========================================================================

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            elStatusWs.className = 'status-indicator status-connected';
            elStatusWs.querySelector('.label').textContent = 'Live';
        };

        ws.onclose = () => {
            elStatusWs.className = 'status-indicator status-disconnected';
            elStatusWs.querySelector('.label').textContent = 'Offline';
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
                console.error('WS Parse Error:', e);
            }
        };
    }

    function handleRealtimeEvent(data) {
        if (data.type === 'rfid_event') {
            showLiveBanner(data);
            loadTags();
            loadHistory();
        } else if (data.type === 'reader_discovered') {
            loadReaders();
        } else if (data.type === 'mqtt_status') {
            checkSystemStatus();
        }
    }

    function showLiveBanner(event) {
        elLiveBanner.classList.remove('hidden');
        if (event.status === 'removed') {
            elLiveEventType.textContent = 'REMOVED';
            elLiveEventType.style.background = '#ef4444';
            elLiveTagName.textContent = `Tag ${event.tag_id} entfernt`;
            elLiveEventDetails.textContent = `Stop an ${event.target_player}`;
            btnLiveEdit.classList.add('hidden');
        } else if (event.status === 'warning') {
            elLiveEventType.textContent = 'NEUER TAG';
            elLiveEventType.style.background = '#f59e0b';
            elLiveTagName.textContent = `Unkonfigurierter Tag: ${event.tag_id}`;
            elLiveEventDetails.textContent = `Auf Reader '${event.reader_id}'. Warn-Sound ausgelöst.`;
            btnLiveEdit.classList.remove('hidden');
            btnLiveEdit.onclick = () => window.editTag(event.tag_id);
        } else {
            elLiveEventType.textContent = 'SCANNED';
            elLiveEventType.style.background = '#10b981';
            elLiveTagName.textContent = event.alias || `Tag ${event.tag_id}`;
            elLiveEventDetails.textContent = `${event.action_type || 'Aktion'} an ${event.target_player}`;
            btnLiveEdit.classList.remove('hidden');
            btnLiveEdit.onclick = () => window.editTag(event.tag_id);
        }
    }

    // =========================================================================
    // UTILS
    // =========================================================================

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function truncate(str, max) {
        if (!str) return '';
        return str.length > max ? str.substring(0, max) + '...' : str;
    }

    function formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            let s = String(dateStr).trim();
            // Wenn der String ein SQLite UTC Format ohne Zeitzone ist (z. B. "2026-08-18 23:03:12"),
            // fügen wir T und Z an, damit der Browser ihn korrekt in die lokale Zeitzone (Berlin) umrechnet.
            if (!s.endsWith('Z') && !s.includes('+') && !s.includes('-', 11)) {
                s = s.replace(' ', 'T') + 'Z';
            }
            const d = new Date(s);
            if (isNaN(d.getTime())) return dateStr;
            return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + 
                   ' ' + d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
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
