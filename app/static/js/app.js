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
        rxMarker: null,
        txMarkers: [],
        connectionLines: [],

        // Auto-refresh
        autoRefresh: true,
        refreshInterval: 60,
        refreshTimer: null,

        // Config Form
        configForm: {
            rx: { name: '', lat: 0, lon: 0 },
            paths: { csv_dir: '', tx_db_path: '', out_dir: '' },
            telegram: { token: '', allowed_chats: '', poll_interval_sec: 20, enabled: false },
            ftp: { server: '', username: '', password: '', remote_dir: '/', remote_filename: '', enabled: false },
        },

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
            await this.loadStatus();
            await this.loadConfig();
            await this.loadTableData();
            this.startAutoRefresh();

            // Watch for tab changes to init map
            this.$watch('activeTab', (tab) => {
                if (tab === 'map') {
                    this.$nextTick(() => this.initMap());
                }
            });
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
                this.configForm.paths = config.paths;
                this.configForm.telegram = {
                    token: '',  // Don't show masked token
                    allowed_chats: config.telegram.allowed_chats,
                    poll_interval_sec: config.telegram.poll_interval_sec,
                    enabled: config.telegram.enabled,
                };
                this.configForm.ftp = {
                    server: config.ftp.server,
                    username: config.ftp.username,
                    password: '',  // Don't show masked password
                    remote_dir: config.ftp.remote_dir,
                    remote_filename: config.ftp.remote_filename,
                    enabled: config.ftp.enabled,
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
            try {
                const response = await fetch('/api/map/markers');
                return await response.json();
            } catch (error) {
                console.error('Failed to load map data:', error);
                return null;
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
            // Wait for DOM
            await new Promise(resolve => setTimeout(resolve, 100));

            const mapContainer = document.getElementById('map');
            if (!mapContainer) return;

            // Destroy existing map
            if (this.map) {
                this.map.remove();
                this.map = null;
            }

            // Get map data
            const mapData = await this.loadMapData();
            if (!mapData) return;

            // Create map
            this.map = L.map('map').setView([mapData.center_lat, mapData.center_lon], mapData.zoom);

            // Add tile layer
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(this.map);

            // Add RX marker
            const rxIcon = L.divIcon({
                className: 'rx-marker',
                html: '<div style="background:#3b82f6;width:24px;height:24px;border-radius:50%;border:2px solid white;display:flex;align-items:center;justify-content:center;color:white;font-size:12px;box-shadow:0 2px 4px rgba(0,0,0,0.3);">🏠</div>',
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            });

            this.rxMarker = L.marker([mapData.rx.lat, mapData.rx.lon], { icon: rxIcon })
                .bindPopup(`<b>${mapData.rx.name}</b><br>Récepteur`)
                .addTo(this.map);

            // Add TX markers and lines
            this.updateMapMarkersFromData(mapData);
        },

        async updateMapMarkers() {
            const mapData = await this.loadMapData();
            if (!mapData || !this.map) return;

            this.updateMapMarkersFromData(mapData);
        },

        updateMapMarkersFromData(mapData) {
            // Clear existing markers
            this.txMarkers.forEach(m => this.map.removeLayer(m));
            this.connectionLines.forEach(l => this.map.removeLayer(l));
            this.txMarkers = [];
            this.connectionLines = [];

            // Add TX markers
            mapData.tx_markers.forEach(tx => {
                // Connection line
                const line = L.polyline(
                    [[mapData.rx.lat, mapData.rx.lon], [tx.lat, tx.lon]],
                    { color: '#3b82f6', weight: 2, opacity: 0.6 }
                ).addTo(this.map);
                this.connectionLines.push(line);

                // TX marker
                const marker = L.circleMarker([tx.lat, tx.lon], {
                    radius: 8,
                    fillColor: '#ef4444',
                    color: '#000',
                    weight: 1,
                    fillOpacity: 0.9,
                }).bindPopup(this.buildTXPopup(tx))
                  .addTo(this.map);

                this.txMarkers.push(marker);
            });
        },

        buildTXPopup(tx) {
            let snrHtml = '';
            if (tx.snr_min !== null || tx.snr_max !== null) {
                const snrMin = tx.snr_min !== null ? tx.snr_min.toFixed(1) : '?';
                const snrMax = tx.snr_max !== null ? tx.snr_max.toFixed(1) : '?';
                snrHtml = `<div>SNR: ${snrMin} - ${snrMax} dB</div>`;
            }

            return `
                <div style="font-family:system-ui;min-width:200px;">
                    <div style="font-weight:700;font-size:14px;margin-bottom:4px;">${tx.location}</div>
                    <div style="color:#666;font-size:12px;">TII: ${tx.tii_code}</div>
                    <div style="margin-top:8px;font-size:12px;">
                        <div>Bloc: ${tx.bloc} (${tx.ensemble})</div>
                        <div>Distance: ${tx.distance_km.toFixed(1)} km</div>
                        ${snrHtml}
                        ${tx.erp_kw ? `<div>ERP: ${tx.erp_kw} kW</div>` : ''}
                    </div>
                </div>
            `;
        },

        async saveConfig() {
            try {
                const response = await fetch('/api/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        rx: this.configForm.rx,
                        paths: this.configForm.paths,
                        telegram: this.configForm.telegram.token ? this.configForm.telegram : null,
                        ftp: this.configForm.ftp.server ? this.configForm.ftp : null,
                    }),
                });

                const result = await response.json();

                if (result.success) {
                    this.showToast('Configuration enregistrée', 'success');
                    // Reload data with new config
                    await this.loadTableData();
                } else {
                    this.showToast('Erreur: ' + (result.message || 'Échec'), 'error');
                }
            } catch (error) {
                this.showToast('Erreur lors de l\'enregistrement', 'error');
            }
        },

        async testFtp() {
            try {
                const response = await fetch('/api/config/test-ftp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.configForm.ftp),
                });

                const result = await response.json();

                if (result.success) {
                    this.showToast('Connexion FTP réussie', 'success');
                } else {
                    this.showToast('Échec: ' + result.message, 'error');
                }
            } catch (error) {
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
