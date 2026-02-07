/**
 * AbracaDABra Logger WebUI - Main Application
 */

function appData() {
    return {
        // UI State
        activeTab: 'table',
        isLoading: false,
        filterText: '',

        // Status
        status: {
            status: 'unknown',
            last_csv_file: null,
            last_csv_time: null,
            mux_count: 0,
            tii_count: 0,
        },

        // Table Data
        muxGroups: [],
        expandedTII: {},
        lastUpdate: null,

        // Map
        map: null,
        mapInitialized: false,
        mapLoadError: false,
        rxMarker: null,
        txMarkers: [],
        connectionLines: [],
        mapData: null,
        showRecentTX: true,
        showOldTX: true,

        // Auto-refresh
        autoRefresh: true,
        refreshInterval: 60,
        refreshTimer: null,

        // Config Form
        configForm: {
            rx: { name: '', lat: 0, lon: 0 },
            paths: { csv_dir: '', tx_db_path: '', out_dir: '' },
            telegram: { token: '', allowed_chats: '', poll_interval_sec: 20, enabled: false },
        },
        gpsCoordinates: '',

        // Password protection
        showPasswordModal: false,
        passwordInput: '',
        passwordError: '',
        configAuthenticated: false,
        configHasPassword: false,
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',

        // Toast
        toast: {
            show: false,
            message: '',
            type: 'info',
        },

        // File Browser
        fileBrowser: {
            show: false,
            mode: 'dir',  // 'dir' or 'file'
            filterExt: null,
            currentPath: '',
            items: [],
            target: null,  // 'csv_dir' or 'tx_db_path'
            title: '',
        },

        // Computed
        get filteredMuxGroups() {
            if (!this.filterText) return this.muxGroups;

            const search = this.filterText.toLowerCase();
            return this.muxGroups.filter(mux =>
                mux.bloc.toLowerCase().includes(search) ||
                mux.ensemble.toLowerCase().includes(search) ||
                mux.tii_list.some(tii => tii.location.toLowerCase().includes(search))
            );
        },

        get totalTII() {
            return this.muxGroups.reduce((sum, mux) => sum + mux.tii_list.length, 0);
        },

        // Methods
        async init() {
            // IMPORTANT: install the tab watcher immediately (before awaits).
            // Otherwise a fast click to "Carte" can happen before the watcher exists,
            // and initMap() will never be called (loader infinite).
            this.$watch('activeTab', (tab) => {
                if (tab === 'map') {
                    this.$nextTick(() => {
                        // If map already exists, just refresh sizing (tabs/mobile Safari)
                        if (this.map) {
                            try { this.map.invalidateSize(true); } catch (e) {}
                            return;
                        }
                        this.initMap();
                    });
                }
            });

            // If the tab is already on map (restore state / very fast navigation), init now
            if (this.activeTab === 'map') {
                this.$nextTick(() => this.initMap());
            }

            await this.loadStatus();
            await this.loadPasswordStatus();
            await this.loadTableData();
            this.startAutoRefresh();

            // Catch-up: if the user switched to map during the awaits, make sure we still init
            if (this.activeTab === 'map' && !this.map) {
                this.$nextTick(() => this.initMap());
            }
        },

        async loadStatus() {
            try {
                const response = await fetch('/api/status');
                this.status = await response.json();
            } catch (error) {
                console.error('Failed to load status:', error);
            }
        },

        async loadConfig() {
            try {
                const response = await fetch('/api/config');
                const config = await response.json();

                this.configForm.rx = config.rx;
                // Format GPS coordinates for display
                this.gpsCoordinates = `${config.rx.lat}, ${config.rx.lon}`;
                this.configForm.paths = config.paths;
                this.configForm.telegram = {
                    token: config.telegram.token || '',
                    allowed_chats: config.telegram.allowed_chats,
                    poll_interval_sec: config.telegram.poll_interval_sec,
                    enabled: config.telegram.enabled,
                };
            } catch (error) {
                console.error('Failed to load config:', error);
            }
        },

        async loadTableData() {
            this.isLoading = true;
            try {
                const response = await fetch('/api/dx/table');
                const data = await response.json();

                this.muxGroups = data.mux_groups;
                this.lastUpdate = new Date().toLocaleTimeString('fr-FR');

                await this.loadStatus();
            } catch (error) {
                console.error('Failed to load table data:', error);
                this.showToast('Erreur lors du chargement des données', 'error');
            } finally {
                this.isLoading = false;
            }
        },

        async loadMapData() {
            const CACHE_KEY = 'abracadabra_map_data';
            const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

            try {
                // ÉTAPE 1: Vérifier le cache (stale-while-revalidate)
                const cached = localStorage.getItem(CACHE_KEY);
                if (cached) {
                    try {
                        const { data, timestamp } = JSON.parse(cached);
                        const age = Date.now() - timestamp;

                        // Si le cache est frais (< 5 min), l'utiliser directement
                        if (age < CACHE_TTL) {
                            console.log('[CACHE] Using fresh cached data (age:', Math.round(age / 1000), 's)');
                            return data;
                        }

                        // Si le cache est périmé mais existe, l'utiliser pendant qu'on recharge
                        console.log('[CACHE] Using stale cache while revalidating...');
                        // Retourner les données périmées immédiatement
                        setTimeout(() => this.revalidateMapData(), 100);
                        return data;
                    } catch (e) {
                        console.warn('[CACHE] Invalid cache, clearing...', e);
                        localStorage.removeItem(CACHE_KEY);
                    }
                }

                // ÉTAPE 2: Pas de cache, charger depuis l'API
                console.log('[API] Fetching fresh map data...');
                const response = await fetch('/api/map/markers');
                const data = await response.json();

                // ÉTAPE 3: Mettre en cache
                try {
                    localStorage.setItem(CACHE_KEY, JSON.stringify({
                        data,
                        timestamp: Date.now()
                    }));
                    console.log('[CACHE] Data cached successfully');
                } catch (e) {
                    console.warn('[CACHE] Failed to cache data:', e);
                }

                return data;
            } catch (error) {
                console.error('[API] Failed to load map data:', error);

                // En cas d'erreur réseau, essayer de retourner le cache périmé
                const cached = localStorage.getItem(CACHE_KEY);
                if (cached) {
                    try {
                        const { data } = JSON.parse(cached);
                        console.warn('[CACHE] Network error, using stale cache as fallback');
                        return data;
                    } catch (e) {
                        // Ignore
                    }
                }

                return null;
            }
        },

        async revalidateMapData() {
            // Recharger les données en arrière-plan et mettre à jour la carte
            const CACHE_KEY = 'abracadabra_map_data';
            try {
                console.log('[CACHE] Revalidating in background...');
                const response = await fetch('/api/map/markers');
                const data = await response.json();

                localStorage.setItem(CACHE_KEY, JSON.stringify({
                    data,
                    timestamp: Date.now()
                }));

                // Mettre à jour la carte si elle existe
                if (this.map && data) {
                    console.log('[CACHE] Updating map with fresh data');
                    this.updateMapMarkersFromData(data);
                }
            } catch (error) {
                console.warn('[CACHE] Background revalidation failed:', error);
            }
        },

        toggleTII(key) {
            this.expandedTII[key] = !this.expandedTII[key];
        },

        startAutoRefresh() {
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
            }

            if (this.autoRefresh) {
                this.refreshTimer = setInterval(() => {
                    this.loadTableData();
                    if (this.map) {
                        this.updateMapMarkers();
                    }
                }, this.refreshInterval * 1000);
            }
        },

        toggleAutoRefresh() {
            this.autoRefresh = !this.autoRefresh;
            this.startAutoRefresh();
        },

        updateRefreshInterval() {
            this.startAutoRefresh();
        },

        async initMap() {
            console.log('[MAP] === INIT START ===');
            console.log('[MAP] User agent:', navigator.userAgent);
            console.log('[MAP] Alpine context check - this:', typeof this, 'has $nextTick:', typeof this.$nextTick);
            console.log('[MAP] Initial state - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);

            // TIMEOUT DE SÉCURITÉ : forcer l'affichage de l'erreur après 10s max
            console.log('[MAP] Setting safety timeout (10s)...');
            const safetyTimeout = setTimeout(() => {
                console.error('[MAP] ⏰ SAFETY TIMEOUT TRIGGERED (10s elapsed)');
                console.error('[MAP] Current state before timeout - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);

                if (!this.mapInitialized) {
                    console.error('[MAP] 🚨 FORCING error state via Alpine $nextTick');
                    // Forcer via Alpine pour garantir la réactivité
                    if (this.$nextTick) {
                        this.$nextTick(() => {
                            this.mapInitialized = true;
                            this.mapLoadError = true;
                            console.error('[MAP] ✅ Error state set via $nextTick - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                        });
                    } else {
                        // Fallback si $nextTick pas disponible
                        this.mapInitialized = true;
                        this.mapLoadError = true;
                        console.error('[MAP] ✅ Error state set directly (no $nextTick) - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                    }
                } else {
                    console.log('[MAP] Timeout fired but map already initialized, ignoring');
                }
            }, 10000);

            // DOUBLE SÉCURITÉ : timeout de 15s au cas où le premier échouerait
            const fallbackTimeout = setTimeout(() => {
                console.error('[MAP] 🔥 FALLBACK TIMEOUT (15s) - Force hiding loader');
                this.mapInitialized = true;
                this.mapLoadError = true;
                console.error('[MAP] Fallback state - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
            }, 15000);

            // If map already exists, just refresh it
            if (this.map) {
                clearTimeout(safetyTimeout);
                clearTimeout(fallbackTimeout);
                console.log('[MAP] Map already exists, refreshing size...');

                // Multi-invalidateSize pour Safari mobile
                this.map.invalidateSize(true);
                requestAnimationFrame(() => {
                    if (this.map) {
                        this.map.invalidateSize(true);
                        setTimeout(() => this.map && this.map.invalidateSize(true), 200);
                    }
                });
                return;
            }

            // Vérifier que Leaflet est chargé
            if (typeof L === 'undefined') {
                clearTimeout(safetyTimeout);
                clearTimeout(fallbackTimeout);
                console.error('[MAP] Leaflet library not loaded!');
                console.error('[MAP] Setting error state - mapInitialized=true, mapLoadError=true');
                this.mapInitialized = true;
                this.mapLoadError = true;
                console.error('[MAP] After setting - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                return;
            }
            console.log('[MAP] Leaflet version:', L.version);

            try {
                // ATTENDRE que le conteneur soit visible (Safari mobile = plus lent)
                console.log('[MAP] Waiting for container visibility...');
                await new Promise(resolve => setTimeout(resolve, 500));

                const mapContainer = document.getElementById('map');
                if (!mapContainer) {
                    clearTimeout(safetyTimeout);
                    clearTimeout(fallbackTimeout);
                    console.error('[MAP] Container #map not found in DOM');
                    console.error('[MAP] Setting error state - mapInitialized=true, mapLoadError=true');
                    this.mapInitialized = true;
                    this.mapLoadError = true;
                    console.error('[MAP] After setting - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                    return;
                }

                // LOG détaillé du conteneur
                const computed = window.getComputedStyle(mapContainer);
                console.log('[MAP] Container #map:', {
                    offsetWidth: mapContainer.offsetWidth,
                    offsetHeight: mapContainer.offsetHeight,
                    clientWidth: mapContainer.clientWidth,
                    clientHeight: mapContainer.clientHeight,
                    display: computed.display,
                    visibility: computed.visibility,
                    height: computed.height,
                    minHeight: computed.minHeight
                });

                // Forcer la visibilité si nécessaire
                if (mapContainer.offsetWidth === 0 || mapContainer.offsetHeight === 0) {
                    console.warn('[MAP] Container has zero size, forcing...');
                    mapContainer.style.display = 'block';
                    mapContainer.style.visibility = 'visible';
                    mapContainer.style.height = '550px';
                    mapContainer.style.minHeight = '550px';
                    await new Promise(resolve => setTimeout(resolve, 100));
                    console.log('[MAP] After forcing - size:', mapContainer.offsetWidth, 'x', mapContainer.offsetHeight);
                }

                console.log('[MAP] Creating Leaflet map instance...');

                // CRÉER LA MAP (sans canvas renderer pour Safari)
                this.map = L.map('map', {
                    preferCanvas: false,
                    zoomControl: true,
                    attributionControl: true
                }).setView([48.8566, 2.3522], 6);

                console.log('[MAP] Map created, adding tile layer...');

                // AJOUTER LES TILES avec gestion complète des événements
                const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                    maxZoom: 19,
                    crossOrigin: true,
                    errorTileUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
                });

                let tilesLoaded = false;
                let tileErrors = 0;

                tileLayer.on('loading', () => {
                    console.log('[TILES] Loading started...');
                });

                tileLayer.on('load', () => {
                    if (!tilesLoaded) {
                        tilesLoaded = true;
                        clearTimeout(safetyTimeout);
                        clearTimeout(fallbackTimeout);
                        console.log('[TILES] ✅ First load complete');
                        console.log('[TILES] Setting success state - mapInitialized=true, mapLoadError=false');
                        this.mapInitialized = true;
                        this.mapLoadError = false;
                        console.log('[TILES] After setting - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                    }
                });

                tileLayer.on('tileerror', (error) => {
                    tileErrors++;
                    console.error('[TILES] ❌ Tile error #' + tileErrors + ':', error);

                    // Si trop d'erreurs, cacher le loader
                    if (tileErrors > 5 && !this.mapInitialized) {
                        clearTimeout(safetyTimeout);
                        clearTimeout(fallbackTimeout);
                        console.error('[TILES] Too many errors (>5), hiding loader');
                        console.error('[TILES] Setting error state - mapInitialized=true, mapLoadError=true');
                        this.mapInitialized = true;
                        this.mapLoadError = true;
                        console.error('[TILES] After setting - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
                    }
                });

                tileLayer.addTo(this.map);
                console.log('[MAP] Tile layer added');

                // FORCER RECALCUL DE TAILLE (critique pour Safari mobile)
                console.log('[MAP] Calling invalidateSize()...');
                requestAnimationFrame(() => {
                    if (this.map) {
                        this.map.invalidateSize(true);
                        console.log('[MAP] invalidateSize() done (RAF)');

                        setTimeout(() => {
                            if (this.map) {
                                this.map.invalidateSize(true);
                                console.log('[MAP] invalidateSize() done (100ms)');
                            }
                        }, 100);

                        setTimeout(() => {
                            if (this.map) {
                                this.map.invalidateSize(true);
                                console.log('[MAP] invalidateSize() done (500ms)');
                            }
                        }, 500);
                    }
                });

                // CHARGER LES DONNÉES en asynchrone
                console.log('[MAP] Loading markers data...');
                this.loadMapData()
                    .then(mapData => {
                        if (!mapData) {
                            console.warn('[MAP] No data returned from API');
                            return;
                        }

                        console.log('[MAP] Data received, centering map...');
                        this.map.setView([mapData.center_lat, mapData.center_lon], mapData.zoom);

                        // Marker RX
                        const rxIcon = L.divIcon({
                            className: 'rx-marker',
                            html: '<div style="background:#3b82f6;width:24px;height:24px;border-radius:50%;border:2px solid white;display:flex;align-items:center;justify-content:center;color:white;font-size:12px;box-shadow:0 2px 4px rgba(0,0,0,0.3);">🏠</div>',
                            iconSize: [24, 24],
                            iconAnchor: [12, 12],
                        });

                        this.rxMarker = L.marker([mapData.rx.lat, mapData.rx.lon], { icon: rxIcon })
                            .bindPopup(`<b>${mapData.rx.name}</b><br>Récepteur`, {
                                minWidth: 200,
                                maxWidth: 400,
                                autoPan: true,
                                closeButton: true,
                                className: 'dab-leaflet-popup'
                            })
                            .addTo(this.map);

                        this.updateMapMarkersFromData(mapData);
                        console.log('[MAP] ✅ All markers added (' + mapData.tx_markers.length + ' TX)');
                    })
                    .catch(error => {
                        console.error('[MAP] ❌ Error loading data:', error);
                    });

                console.log('[MAP] === INIT END (waiting for tiles) ===');

            } catch (error) {
                clearTimeout(safetyTimeout);
                clearTimeout(fallbackTimeout);
                console.error('[MAP] ❌ CRITICAL ERROR:', error);
                console.error('[MAP] Error type:', error.name);
                console.error('[MAP] Error message:', error.message);
                console.error('[MAP] Stack:', error.stack);
                console.error('[MAP] Setting error state - mapInitialized=true, mapLoadError=true');
                this.mapInitialized = true;
                this.mapLoadError = true;
                console.error('[MAP] After setting - mapInitialized:', this.mapInitialized, 'mapLoadError:', this.mapLoadError);
            }
        },

        async updateMapMarkers() {
            const mapData = await this.loadMapData();
            if (!mapData || !this.map) return;

            this.updateMapMarkersFromData(mapData);
        },

        updateMapMarkersFromData(mapData) {
            // Use stored mapData if no parameter provided
            if (!mapData) {
                mapData = this.mapData;
            }

            // Store mapData for future use
            if (mapData) {
                this.mapData = mapData;
            }

            if (!mapData || !this.map) return;

            // Clear existing markers
            this.txMarkers.forEach(m => this.map.removeLayer(m));
            this.connectionLines.forEach(l => this.map.removeLayer(l));
            this.txMarkers = [];
            this.connectionLines = [];

            // Add TX markers
            mapData.tx_markers.forEach(tx => {
                // Determine if this site has any live or historical ensembles
                const hasLive = tx.ensembles && tx.ensembles.some(e => e.is_live);
                const hasHistorical = tx.ensembles && tx.ensembles.some(e => !e.is_live);

                // Filter based on checkbox state
                // A site should be shown if:
                // - It has live data AND showRecentTX is checked, OR
                // - It has historical data AND showOldTX is checked
                const shouldShow = (hasLive && this.showRecentTX) || (hasHistorical && this.showOldTX);
                if (!shouldShow) return;

                // Connection line
                const line = L.polyline(
                    [[mapData.rx.lat, mapData.rx.lon], [tx.lat, tx.lon]],
                    { color: '#3b82f6', weight: 2, opacity: 0.6 }
                ).addTo(this.map);
                this.connectionLines.push(line);

                // TX marker color: adapt to active filters
                // If only showing recent → all green
                // If only showing old → all red
                // If showing both → green if has live, red otherwise
                let markerColor;
                if (this.showRecentTX && !this.showOldTX) {
                    markerColor = '#22c55e'; // All visible sites are recent (green)
                } else if (!this.showRecentTX && this.showOldTX) {
                    markerColor = '#ef4444'; // All visible sites are old (red)
                } else {
                    markerColor = hasLive ? '#22c55e' : '#ef4444'; // Both filters: prioritize live
                }

                const marker = L.circleMarker([tx.lat, tx.lon], {
                    radius: 8,
                    fillColor: markerColor,
                    color: '#000',
                    weight: 1,
                    fillOpacity: 0.9,
                }).bindPopup(this.buildTXPopup(tx), {
                    minWidth: 650,
                    maxWidth: 900,
                    autoPan: true,
                    closeButton: true,
                    className: 'dab-leaflet-popup'
                }).addTo(this.map);

                this.txMarkers.push(marker);
            });
        },

        buildTXPopup(tx) {
            // Helper function to get SNR background color
            const getSnrColor = (snr) => {
                if (snr === null || snr === undefined) return '#e5e7eb'; // gray
                if (snr >= 20) return '#22c55e'; // green
                if (snr >= 10) return '#f59e0b'; // orange
                if (snr >= 6) return '#eab308'; // yellow
                return '#ef4444'; // red
            };

            // Helper function to format SNR value
            const formatSnr = (snr) => {
                if (snr === null || snr === undefined) return '—';
                return snr.toFixed(1);
            };

            // Helper function to format date (compact format without seconds)
            const formatDate = (dateStr) => {
                if (!dateStr) return '—';
                const date = new Date(dateStr);
                return date.toLocaleString('fr-FR', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            };

            // Build table rows
            let tableRows = '';
            if (tx.ensembles && tx.ensembles.length > 0) {
                // Sort ensembles by date (most recent first)
                const sortedEnsembles = [...tx.ensembles].sort((a, b) => {
                    if (!a.last_rx_time) return 1;
                    if (!b.last_rx_time) return -1;
                    return new Date(b.last_rx_time) - new Date(a.last_rx_time);
                });

                // ERP power of the site (same for all ensembles)
                const erpText = tx.erp_kw !== null && tx.erp_kw !== undefined
                    ? tx.erp_kw.toFixed(1) + ' kW'
                    : '—';

                tableRows = sortedEnsembles.map(ens => {
                    return `
                        <tr style="border-bottom:1px solid #eaecef;">
                            <td style="padding:6px 4px;font-size:10px;white-space:nowrap;line-height:1.3;color:#24292e;">${formatDate(ens.last_rx_time)}</td>
                            <td style="padding:6px 4px;font-weight:600;text-align:center;font-size:11px;color:#0969da;">${ens.bloc}</td>
                            <td style="padding:6px 4px;font-size:9px;text-align:center;color:#57606a;font-family:monospace;">${ens.eid}</td>
                            <td style="padding:6px 6px;font-size:11px;line-height:1.3;color:#24292e;">${ens.ensemble}</td>
                            <td style="padding:6px 4px;text-align:center;font-size:10px;font-weight:500;color:#57606a;">${erpText}</td>
                            <td style="padding:6px 4px;text-align:center;font-weight:600;background:${getSnrColor(ens.snr_min)};color:#000;font-size:11px;border-radius:3px;">${formatSnr(ens.snr_min)}</td>
                            <td style="padding:6px 4px;text-align:center;font-weight:600;background:${getSnrColor(ens.snr_max)};color:#000;font-size:11px;border-radius:3px;">${formatSnr(ens.snr_max)}</td>
                            <td style="padding:6px 4px;text-align:center;font-weight:600;background:${getSnrColor(ens.is_live ? ens.snr_max : null)};color:#000;font-size:11px;border-radius:3px;">${ens.is_live ? formatSnr(ens.snr_max) : '—'}</td>
                            <td style="padding:6px 4px;text-align:center;font-size:10px;color:#57606a;font-family:monospace;">${ens.main}</td>
                            <td style="padding:6px 4px;text-align:center;font-size:10px;color:#57606a;font-family:monospace;">${ens.sub}</td>
                        </tr>
                    `;
                }).join('');
            }

            // Determine if this site has live ensembles (for status indicator)
            const hasLive = tx.ensembles && tx.ensembles.some(e => e.is_live);
            const statusColor = hasLive ? '#22c55e' : '#ef4444';
            const statusLabel = hasLive ? 'Récent' : 'Ancien';

            return `
                <div class="dab-popup">
                    <div class="dab-popup-header">
                        <div class="dab-popup-title">
                            <span class="dab-popup-status" style="background:${statusColor};"></span>
                            ${tx.location}
                        </div>
                        <div class="dab-popup-subtitle">
                            <span style="color:${statusColor};font-weight:600;">${statusLabel}</span> •
                            Distance: ${tx.distance_km.toFixed(1)} km${tx.azimuth_deg ? ` • Azimut: ${tx.azimuth_deg.toFixed(0)}°` : ''}
                        </div>
                    </div>

                    ${tx.ensembles && tx.ensembles.length > 0 ? `
                        <div class="dab-popup-body">
                            <table style="width:100%;border-collapse:collapse;font-size:11px;background:white;">
                                <thead style="background:#f6f8fa;position:sticky;top:0;">
                                    <tr>
                                        <th style="padding:8px 4px;text-align:left;font-size:9px;border-bottom:2px solid #d0d7de;white-space:nowrap;line-height:1.2;">Date/Heure</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">Bloc</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">EId</th>
                                        <th style="padding:8px 6px;text-align:left;font-size:9px;border-bottom:2px solid #d0d7de;">Label</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">PAR</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">SNR Min</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">SNR Max</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">SNR Live</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">Main</th>
                                        <th style="padding:8px 4px;text-align:center;font-size:9px;border-bottom:2px solid #d0d7de;">Sub</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${tableRows}
                                </tbody>
                            </table>
                        </div>
                    ` : '<div class="dab-popup-body" style="color:#999;padding:8px;">Aucune donnée disponible</div>'}
                </div>
            `;
        },

        async saveConfig() {
            try {
                // Parse GPS coordinates from "lat, lon" format
                const coords = this.gpsCoordinates.split(',').map(s => s.trim());
                if (coords.length === 2) {
                    const lat = parseFloat(coords[0]);
                    const lon = parseFloat(coords[1]);
                    if (!isNaN(lat) && !isNaN(lon)) {
                        this.configForm.rx.lat = lat;
                        this.configForm.rx.lon = lon;
                    }
                }

                const response = await fetch('/api/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        rx: this.configForm.rx,
                        paths: this.configForm.paths,
                        telegram: this.configForm.telegram.token ? this.configForm.telegram : null,
                    }),
                });

                const result = await response.json();

                if (result.success) {
                    this.showToast('Configuration enregistrée', 'success');

                    // Reload data with new config
                    await this.loadTableData();

                    // Update map if it exists
                    if (this.map) {
                        // Clear map cache to force reload with new RX position
                        localStorage.removeItem('abracadabra_map_data');

                        // Update RX marker position and name if it exists
                        if (this.rxMarker) {
                            const newLatLng = [this.configForm.rx.lat, this.configForm.rx.lon];
                            this.rxMarker.setLatLng(newLatLng);
                            this.rxMarker.setPopupContent(`<b>${this.configForm.rx.name}</b><br>Récepteur`);
                            this.map.setView(newLatLng, this.map.getZoom());
                        }

                        // Reload all map data (will recalculate distances/azimuths)
                        await this.updateMapMarkers();
                    }
                } else {
                    this.showToast('Erreur: ' + (result.message || 'Échec'), 'error');
                }
            } catch (error) {
                this.showToast('Erreur lors de l\'enregistrement', 'error');
            }
        },

        async testTelegram() {
            try {
                const token = (this.configForm.telegram.token || '').trim();
                const allowedChats = (this.configForm.telegram.allowed_chats || '').trim();
                const chatId = allowedChats ? allowedChats.split(',')[0].trim() : '';

                if (!token) {
                    this.showToast('Token non configuré', 'error');
                    return;
                }
                if (!chatId) {
                    this.showToast('Aucun Chat ID renseigné', 'error');
                    return;
                }

                const response = await fetch('/api/telegram/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: token, chat_id: chatId }),
                });

                const result = await response.json();

                if (result.success) {
                    this.showToast('Message de test envoyé sur Telegram', 'success');
                } else {
                    this.showToast('Échec: ' + (result.message || result.detail || 'Erreur inconnue'), 'error');
                }
            } catch (error) {
                this.showToast('Erreur de connexion', 'error');
            }
        },


        async loadPasswordStatus() {
            try {
                const resp = await fetch('/api/config/password-status');
                const data = await resp.json();
                this.configHasPassword = data.has_password;
            } catch (e) {}
        },

        openConfigTab() {
            if (this.configHasPassword && !this.configAuthenticated) {
                this.showPasswordModal = true;
                this.passwordInput = '';
                this.passwordError = '';
                this.$nextTick(() => {
                    if (this.$refs.passwordField) this.$refs.passwordField.focus();
                });
                return;
            }
            this.activeTab = 'config';
            this.loadConfig();
        },

        async verifyPassword() {
            try {
                const resp = await fetch('/api/config/verify-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: this.passwordInput }),
                });
                const data = await resp.json();
                if (data.success) {
                    this.configAuthenticated = true;
                    this.showPasswordModal = false;
                    this.passwordInput = '';
                    this.passwordError = '';
                    this.activeTab = 'config';
                    this.loadConfig();
                } else {
                    this.passwordError = data.message || 'Mot de passe incorrect';
                }
            } catch (e) {
                this.passwordError = 'Erreur de connexion';
            }
        },

        async changePassword() {
            // Verify confirmation matches if a new password is set
            if (this.newPassword && this.newPassword !== this.confirmPassword) {
                this.showToast('Les mots de passe ne correspondent pas', 'error');
                return;
            }
            try {
                const resp = await fetch('/api/config/set-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: this.currentPassword,
                        new_password: this.newPassword,
                    }),
                });
                const data = await resp.json();
                if (data.success) {
                    this.configHasPassword = !!this.newPassword;
                    this.currentPassword = '';
                    this.newPassword = '';
                    this.confirmPassword = '';
                    this.showToast(this.configHasPassword ? 'Mot de passe mis à jour' : 'Mot de passe supprimé', 'success');
                } else {
                    this.showToast('Erreur: ' + (data.message || 'Échec'), 'error');
                }
            } catch (e) {
                this.showToast('Erreur de connexion', 'error');
            }
        },

        showToast(message, type = 'info') {
            this.toast = { show: true, message, type };
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        },

        async openFileBrowser(target, mode = 'dir', filterExt = null) {
            this.fileBrowser.target = target;
            this.fileBrowser.mode = mode;
            this.fileBrowser.filterExt = filterExt;
            this.fileBrowser.title = mode === 'dir' ? 'Sélectionner un dossier' : 'Sélectionner un fichier';

            // Start from current value or home
            let startPath = '~';
            if (target === 'csv_dir' && this.configForm.paths.csv_dir) {
                startPath = this.configForm.paths.csv_dir;
            } else if (target === 'tx_db_path' && this.configForm.paths.tx_db_path) {
                startPath = this.configForm.paths.tx_db_path;
            }

            await this.browsePath(startPath);
            this.fileBrowser.show = true;
        },

        async browsePath(path) {
            try {
                const params = new URLSearchParams({
                    path: path,
                    mode: this.fileBrowser.mode,
                });
                if (this.fileBrowser.filterExt) {
                    params.append('filter_ext', this.fileBrowser.filterExt);
                }

                const response = await fetch(`/api/config/browse?${params}`);
                const data = await response.json();

                this.fileBrowser.currentPath = data.current_path;
                this.fileBrowser.items = data.items;
            } catch (error) {
                console.error('Browse failed:', error);
                this.showToast('Erreur lors de la navigation', 'error');
            }
        },

        async selectBrowserItem(item) {
            if (item.is_dir) {
                // Navigate into directory
                await this.browsePath(item.path);
            } else {
                // Select file
                this.selectBrowserPath(item.path);
            }
        },

        selectBrowserPath(path = null) {
            const selectedPath = path || this.fileBrowser.currentPath;

            if (this.fileBrowser.target === 'csv_dir') {
                this.configForm.paths.csv_dir = selectedPath;
            } else if (this.fileBrowser.target === 'tx_db_path') {
                this.configForm.paths.tx_db_path = selectedPath;
            }

            this.fileBrowser.show = false;
        },

        closeBrowser() {
            this.fileBrowser.show = false;
        },

        formatFileSize(bytes) {
            if (bytes === null) return '';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        },
    };
}
