/**
 * NFC Media Controller - Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    // State
    let tagsList = [];
    let readersList = [];
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
    const inputTagVolume = document.getElementById('tag-volume');
    const inputTagTargetId = document.getElementById('tag-target-id');
    const checkTagRandom = document.getElementById('tag-random');
    const inputTagExtraParams = document.getElementById('tag-extra-params');
    const btnPickAbsSeries = document.getElementById('btn-pick-abs-series');
    const elTargetIdHelper = document.getElementById('target-id-helper');

    const elReaderModal = document.getElementById('reader-modal');
    const elReaderForm = document.getElementById('reader-form');
    const elReaderModalTitle = document.getElementById('reader-modal-title');
    const inputReaderId = document.getElementById('reader-id-input');
    const inputReaderTargetPlayer = document.getElementById('reader-target-player');
    const inputReaderAbsToken = document.getElementById('reader-abs-token');
    const inputReaderNotes = document.getElementById('reader-notes');

    // DOM Elements - Simulator & ABS
    const inputSimReaderId = document.getElementById('sim-reader-id');
    const inputSimTagId = document.getElementById('sim-tag-id');
    const btnSimScan = document.getElementById('btn-sim-scan');
    const btnSimRemove = document.getElementById('btn-sim-remove');
    const elSimResultContainer = document.getElementById('sim-result-container');
    const elSimResultOutput = document.getElementById('sim-result-output');
    const btnLoadAbsSeries = document.getElementById('btn-load-abs-series');
    const elAbsSeriesList = document.getElementById('abs-series-list');

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
            }
        });
    });

    // Close Modals via Close-Buttons & Backdrop
    document.querySelectorAll('[data-close-modal]').forEach(el => {
        el.addEventListener('click', () => {
            elTagModal.classList.add('hidden');
            elReaderModal.classList.add('hidden');
        });
    });

    document.querySelectorAll('.modal-backdrop').forEach(bd => {
        bd.addEventListener('click', () => {
            elTagModal.classList.add('hidden');
            elReaderModal.classList.add('hidden');
        });
    });

    // Dynamic Helper Text on Action Type Change
    selectTagActionType.addEventListener('change', () => {
        const val = selectTagActionType.value;
        if (val === 'Serie') {
            elTargetIdHelper.textContent = 'Audiobookshelf Serien-ID (z. B. ser_xyz)';
            inputTagTargetId.placeholder = 'ser_xyz';
            btnPickAbsSeries.classList.remove('hidden');
        } else if (val === 'Hoerbuch' || val === 'Playlist') {
            elTargetIdHelper.textContent = 'Medien-URI oder ABS-Item-ID (z. B. mass://track/123)';
            inputTagTargetId.placeholder = 'mass://track/123 oder abs-item-id';
            btnPickAbsSeries.classList.add('hidden');
        } else if (val === 'Licht' || val === 'Szene') {
            elTargetIdHelper.textContent = 'Home Assistant Entitäts-ID (z. B. light.kinderzimmer oder scene.schlafenszeit)';
            inputTagTargetId.placeholder = 'light.kinderzimmer';
            btnPickAbsSeries.classList.add('hidden');
        } else {
            elTargetIdHelper.textContent = 'Ziel-ID oder Befehl';
            inputTagTargetId.placeholder = 'Ziel-ID';
            btnPickAbsSeries.classList.add('hidden');
        }
    });

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
                const history = await res.json();
                renderHistoryTable(history);
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
                    elStatusAbs.querySelector('.label').textContent = `ABS: ${data.audiobookshelf.username || 'Verbunden'}`;
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
                ? `<span class="badge badge-warning">⚠️ Neu / Unkonfiguriert</span>`
                : `<span class="badge badge-configured">✅ Bereit</span>`;

            const actionTypeBadge = tag.action_type
                ? `<span class="badge badge-type">${escapeHtml(tag.action_type)}</span>`
                : `<span class="text-muted">—</span>`;

            const volumeDisplay = tag.volume !== null ? `${tag.volume}%` : `<span class="text-muted">Standard</span>`;
            const randomDisplay = tag.random ? '🔀 Ja' : '<span class="text-muted">Nein</span>';
            const lastScannedDisplay = tag.last_scanned ? formatDate(tag.last_scanned) : '<span class="text-muted">Nie</span>';

            return `
                <tr>
                    <td>${statusBadge}</td>
                    <td class="font-mono"><strong>${escapeHtml(tag.tag_id)}</strong></td>
                    <td>${escapeHtml(tag.alias || 'Unbenannt')}</td>
                    <td>${actionTypeBadge}</td>
                    <td class="font-mono text-muted" title="${escapeHtml(tag.target_id || '')}">
                        ${escapeHtml(truncate(tag.target_id || '—', 28))}
                    </td>
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

        elHistoryTableBody.innerHTML = items.map(item => {
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
                    <td class="font-mono text-muted text-xs">${escapeHtml(truncate(item.payload || '', 40))}</td>
                </tr>
            `;
        }).join('');
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
        inputTagVolume.value = '';
        inputTagTargetId.value = '';
        checkTagRandom.checked = false;
        inputTagExtraParams.value = '{}';
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
        inputTagVolume.value = tag.volume !== null ? tag.volume : '';
        inputTagTargetId.value = tag.target_id || '';
        checkTagRandom.checked = !!tag.random;
        inputTagExtraParams.value = tag.extra_params || '{}';
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
        const volumeVal = inputTagVolume.value ? parseInt(inputTagVolume.value, 10) : null;
        const targetId = inputTagTargetId.value.trim();
        const random = checkTagRandom.checked;
        const extraParams = inputTagExtraParams.value.trim() || '{}';

        // Validierung
        if (!tagId || !alias) {
            alert('Bitte Tag ID und Name angeben.');
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
    // TEST SIMULATOR & ABS BROWSER
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
        } catch (e) {
            alert('Simulationsfehler: ' + e);
        }
    }

    btnSimScan.addEventListener('click', () => runSimulation('scanned'));
    btnSimRemove.addEventListener('click', () => runSimulation('removed'));

    btnLoadAbsSeries.addEventListener('click', async () => {
        elAbsSeriesList.innerHTML = `<p class="text-muted text-center py-4">Lade Serien aus Audiobookshelf...</p>`;
        try {
            const res = await fetch('/api/abs/series');
            if (res.ok) {
                const series = await res.json();
                if (series.length === 0) {
                    elAbsSeriesList.innerHTML = `<p class="text-muted text-center py-4">Keine Serien in Audiobookshelf gefunden.</p>`;
                    return;
                }
                elAbsSeriesList.innerHTML = series.map(s => `
                    <div class="abs-series-item">
                        <div>
                            <div class="abs-series-title">${escapeHtml(s.name)}</div>
                            <div class="abs-series-meta font-mono">ID: ${escapeHtml(s.id)} (${s.num_books} Bücher)</div>
                        </div>
                        <button type="button" class="btn btn-sm btn-primary" onclick="window.selectAbsSeries('${escapeHtml(s.id)}', '${escapeHtml(s.name)}')">
                            Übernehmen
                        </button>
                    </div>
                `).join('');
            } else {
                elAbsSeriesList.innerHTML = `<p class="text-danger text-center py-4">Fehler beim Laden der Serien.</p>`;
            }
        } catch (e) {
            elAbsSeriesList.innerHTML = `<p class="text-danger text-center py-4">ABS nicht erreichbar: ${e}</p>`;
        }
    });

    window.selectAbsSeries = function(seriesId, seriesName) {
        inputTagTargetId.value = seriesId;
        if (!inputTagAlias.value) {
            inputTagAlias.value = seriesName;
        }
        selectTagActionType.value = 'Serie';
        selectTagActionType.dispatchEvent(new Event('change'));
        // Modal anzeigen falls nicht offen
        elTagModal.classList.remove('hidden');
    };

    btnPickAbsSeries.addEventListener('click', () => {
        // Tab wechseln zum Tools-Tab & Serien laden
        document.querySelector('[data-tab="tools-tab"]').click();
        btnLoadAbsSeries.click();
    });

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
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + 
                   ' ' + d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
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
