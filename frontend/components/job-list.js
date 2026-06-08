/**
 * daita-studio – Job-Liste Komponente (C7)
 *
 * Zeigt alle ETL-Jobs mit Filter (Layer, Status) und Textsuche.
 * Klick auf einen Job feuert studio:job-selected und ruft onSelect-Callback auf.
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   <script src="/components/job-list.js"></script>
 *
 *   <!-- Als Custom Element: -->
 *   <studio-job-list></studio-job-list>
 *
 *   <!-- Oder per JS-Instanz: -->
 *   const jl = new JobList(containerEl, { onSelect: (jobId) => detail.load(jobId) });
 *   jl.load();
 *
 *   <!-- Oder statisch: -->
 *   JobList.render(containerEl, { filter: { layerId: 2 }, onSelect: (id) => ... });
 *
 * Custom Events (gefeuert auf document):
 *   studio:job-selected   { detail: { job_id, job_name } }
 *
 * Abhängigkeiten: api.js (window.api)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Styles
    // ----------------------------------------------------------------
    const STYLE = `
        .jl-root { font-size: 0.88em; display: flex; flex-direction: column; height: 100%; min-height: 0; }

        /* Toolbar */
        .jl-toolbar {
            display: flex; gap: 8px; padding: 10px 12px;
            background: var(--bg-secondary, #f8f9fa);
            border-bottom: 1px solid var(--border-color, #e0e0e0);
            flex-wrap: wrap;
        }
        .jl-search {
            flex: 1; min-width: 120px;
            padding: 5px 10px; border: 1px solid var(--border-color, #ddd);
            border-radius: 6px; font-size: 0.9em;
            background: var(--bg-primary, #fff);
            color: var(--text-primary, #333);
        }
        .jl-search:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 2px rgba(102,126,234,0.15); }
        .jl-select {
            padding: 5px 8px; border: 1px solid var(--border-color, #ddd);
            border-radius: 6px; font-size: 0.85em; cursor: pointer;
            background: var(--bg-primary, #fff); color: var(--text-primary, #333);
        }
        .jl-select:focus { outline: none; border-color: #667eea; }
        .jl-btn-refresh {
            padding: 5px 10px; border: 1px solid #667eea;
            border-radius: 6px; background: transparent; color: #667eea;
            cursor: pointer; font-size: 0.85em; white-space: nowrap;
        }
        .jl-btn-refresh:hover { background: #667eea; color: #fff; }

        /* Zähler */
        .jl-count {
            padding: 4px 12px; font-size: 0.78em;
            color: var(--text-secondary, #888);
            border-bottom: 1px solid var(--border-color, #e0e0e0);
        }

        /* Liste */
        .jl-list {
            flex: 1; overflow-y: auto;
            list-style: none; margin: 0; padding: 0;
        }

        /* Einzel-Eintrag */
        .jl-item {
            display: flex; align-items: center; gap: 10px;
            padding: 9px 14px;
            border-bottom: 1px solid var(--border-color, #eee);
            cursor: pointer; transition: background 0.12s;
        }
        .jl-item:hover  { background: var(--bg-hover, #f0f2ff); }
        .jl-item.active { background: #ede9fb; border-left: 3px solid #764ba2; }

        /* Status-Punkt */
        .jl-dot {
            width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
        }
        .jl-dot.ok      { background: #27ae60; }
        .jl-dot.error   { background: #e74c3c; }
        .jl-dot.running { background: #f39c12; animation: jl-pulse 1s infinite; }
        .jl-dot.never   { background: #bbb; }
        @keyframes jl-pulse {
            0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
        }

        /* Texte */
        .jl-body { flex: 1; min-width: 0; }
        .jl-name { font-weight: 600; font-size: 0.93em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .jl-meta { font-size: 0.78em; color: var(--text-secondary, #888); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .jl-arrow { color: #aaa; font-size: 0.75em; margin: 0 2px; }

        /* Badges */
        .jl-badges { display: flex; gap: 4px; flex-shrink: 0; flex-wrap: wrap; justify-content: flex-end; }
        .jl-badge {
            font-size: 0.7em; padding: 2px 6px; border-radius: 4px;
            font-weight: 600; white-space: nowrap;
        }
        .jl-badge.scd2    { background: #6c5ce7; color: #fff; }
        .jl-badge.scd1    { background: #0984e3; color: #fff; }
        .jl-badge.full    { background: #00b894; color: #fff; }
        .jl-badge.layer   { background: var(--bg-secondary, #f0f0f0); color: #555; border: 1px solid #ddd; }
        .jl-badge.time    { background: transparent; color: #aaa; border: none; font-size: 0.68em; }

        /* Leer-/Lade-Zustand */
        .jl-empty, .jl-loading {
            display: flex; align-items: center; justify-content: center;
            height: 80px; color: var(--text-secondary, #888); font-size: 0.9em;
        }
        .jl-loading::before { content: '⏳ '; }
        .jl-error-msg {
            padding: 12px; color: #c0392b; font-size: 0.85em;
            background: #fff5f5; border-bottom: 1px solid #f5c6cb;
        }
    `;

    // ----------------------------------------------------------------
    // Hilfsfunktionen
    // ----------------------------------------------------------------
    function injectStyle(id, css) {
        if (document.getElementById(id)) return;
        const s = document.createElement('style');
        s.id = id;
        s.textContent = css;
        document.head.appendChild(s);
    }

    function dotClass(job) {
        const s = (job.last_run_status || '').toLowerCase();
        if (s === 'running')  return 'running';
        if (s === 'ok' || s === 'success' || s === 'completed') return 'ok';
        if (s === 'error' || s === 'failed') return 'error';
        return 'never';
    }

    function histType(job) {
        const ht = (job.historization_type || '').toUpperCase();
        return ht || 'FULL';
    }

    function formatTs(ts) {
        if (!ts) return '';
        try {
            const d = new Date(ts);
            const pad = n => String(n).padStart(2, '0');
            return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
                 + `${pad(d.getHours())}:${pad(d.getMinutes())}`;
        } catch { return ts; }
    }

    function esc(str) {
        return String(str ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ----------------------------------------------------------------
    // Haupt-Klasse
    // ----------------------------------------------------------------
    class JobList {
        /**
         * @param {HTMLElement} container
         * @param {{
         *   filter?: { layerId?: number|null, status?: string|null },
         *   onSelect?: (jobId: number, job: object) => void,
         *   selectedJobId?: number|null,
         * }} opts
         */
        constructor(container, opts = {}) {
            this._container  = container;
            this._opts       = opts;
            this._jobs       = [];         // alle geladenen Jobs
            this._layers     = [];         // Layer für Filter-Dropdown
            this._filtered   = [];         // nach Filter/Suche
            this._search     = '';
            this._filterLayer  = opts.filter?.layerId  ?? null;
            this._filterStatus = opts.filter?.status   ?? null;
            this._selectedId   = opts.selectedJobId    ?? null;

            injectStyle('studio-jl-style', STYLE);
            this._render();
        }

        // ---- statische Fabrikmethode ----
        static render(container, opts = {}) {
            const jl = new JobList(container, opts);
            jl.load();
            return jl;
        }

        // ---- Scaffold ----
        _render() {
            this._container.innerHTML = `
                <div class="jl-root">
                    <div class="jl-toolbar">
                        <input class="jl-search" type="search" placeholder="Job suchen …" value="${esc(this._search)}">
                        <select class="jl-select jl-sel-layer" title="Layer filtern">
                            <option value="">Alle Layer</option>
                        </select>
                        <select class="jl-select jl-sel-status" title="Status filtern">
                            <option value="">Alle Status</option>
                            <option value="ok">✅ OK</option>
                            <option value="error">❌ Fehler</option>
                            <option value="running">⏳ Läuft</option>
                            <option value="never">⬜ Nie gelaufen</option>
                        </select>
                        <button class="jl-btn-refresh" title="Neu laden">↺</button>
                    </div>
                    <div class="jl-count"></div>
                    <ul class="jl-list">
                        <li class="jl-loading">Lade Jobs …</li>
                    </ul>
                </div>`;

            const root = this._container.querySelector('.jl-root');
            this._elSearch    = root.querySelector('.jl-search');
            this._elSelLayer  = root.querySelector('.jl-sel-layer');
            this._elSelStatus = root.querySelector('.jl-sel-status');
            this._elCount     = root.querySelector('.jl-count');
            this._elList      = root.querySelector('.jl-list');

            // Vorselektierung übernehmen
            if (this._filterStatus) this._elSelStatus.value = this._filterStatus;
            if (this._filterLayer)  this._elSelLayer.value  = String(this._filterLayer);

            this._bindEvents();
        }

        _bindEvents() {
            this._elSearch.addEventListener('input', () => {
                this._search = this._elSearch.value;
                this._applyFilter();
            });
            this._elSelLayer.addEventListener('change', () => {
                this._filterLayer = this._elSelLayer.value ? Number(this._elSelLayer.value) : null;
                this._applyFilter();
            });
            this._elSelStatus.addEventListener('change', () => {
                this._filterStatus = this._elSelStatus.value || null;
                this._applyFilter();
            });
            this._container.querySelector('.jl-btn-refresh')
                .addEventListener('click', () => this.load());

            this._elList.addEventListener('click', (e) => {
                const item = e.target.closest('.jl-item');
                if (!item) return;
                const jobId = Number(item.dataset.jobId);
                const job   = this._jobs.find(j => j.job_id === jobId);
                this._select(jobId, job);
            });
        }

        // ---- Daten laden ----
        async load() {
            this._elList.innerHTML = '<li class="jl-loading">Lade Jobs …</li>';
            try {
                const [jobs, layers] = await Promise.all([
                    window.api.etl.jobs.list(),
                    window.api.etl.layers().catch(() => []),
                ]);
                this._jobs   = Array.isArray(jobs)   ? jobs   : (jobs?.items ?? []);
                this._layers = Array.isArray(layers) ? layers : [];
                this._populateLayerFilter();
                this._applyFilter();
            } catch (err) {
                this._elList.innerHTML = `<li class="jl-error-msg">Fehler: ${esc(err.message)}</li>`;
            }
        }

        // ---- Layer-Dropdown befüllen ----
        _populateLayerFilter() {
            // vorhandene Optionen ab Option 1 löschen
            while (this._elSelLayer.options.length > 1) {
                this._elSelLayer.remove(1);
            }
            for (const l of this._layers) {
                const opt = document.createElement('option');
                opt.value       = l.layer_id;
                opt.textContent = l.layer_name ?? l.layer_id;
                if (this._filterLayer && l.layer_id === this._filterLayer) opt.selected = true;
                this._elSelLayer.appendChild(opt);
            }
        }

        // ---- Filter / Suche ----
        _applyFilter() {
            const q = this._search.toLowerCase().trim();
            this._filtered = this._jobs.filter(job => {
                // Layer-Filter
                if (this._filterLayer !== null) {
                    if ((job.source_layer_id ?? job.layer_id) !== this._filterLayer) return false;
                }
                // Status-Filter
                if (this._filterStatus) {
                    if (dotClass(job) !== this._filterStatus) return false;
                }
                // Textsuche
                if (q) {
                    const hay = [job.job_name, job.source_table_name, job.target_table_name,
                                 job.source_db_name, job.target_db_name]
                                .map(x => (x ?? '').toLowerCase()).join(' ');
                    if (!hay.includes(q)) return false;
                }
                return true;
            });
            this._renderList();
        }

        // ---- Liste rendern ----
        _renderList() {
            this._elCount.textContent = `${this._filtered.length} von ${this._jobs.length} Jobs`;

            if (this._filtered.length === 0) {
                this._elList.innerHTML = '<li class="jl-empty">Keine Jobs gefunden.</li>';
                return;
            }

            this._elList.innerHTML = this._filtered.map(job => {
                const ht     = histType(job);
                const dc     = dotClass(job);
                const active = job.job_id === this._selectedId ? ' active' : '';
                const src    = esc(job.source_table_name ?? '?');
                const tgt    = esc(job.target_table_name ?? '?');
                const srcDb  = esc(job.source_db_name ?? '');
                const layerLabel = esc(job.source_layer_name ?? job.layer_name ?? '');
                const ts     = formatTs(job.last_run_at);

                return `
                <li class="jl-item${active}" data-job-id="${job.job_id}" title="${esc(job.job_name)}">
                    <span class="jl-dot ${dc}" title="${dc}"></span>
                    <span class="jl-body">
                        <div class="jl-name">${esc(job.job_name)}</div>
                        <div class="jl-meta">
                            ${srcDb ? `<span>${srcDb}</span> <span class="jl-arrow">›</span> ` : ''}
                            <span>${src}</span>
                            <span class="jl-arrow">→</span>
                            <span>${tgt}</span>
                        </div>
                    </span>
                    <span class="jl-badges">
                        ${layerLabel ? `<span class="jl-badge layer">${layerLabel}</span>` : ''}
                        <span class="jl-badge ${ht.toLowerCase()}">${ht}</span>
                        ${ts ? `<span class="jl-badge time" title="Letzter Run">${ts}</span>` : ''}
                    </span>
                </li>`;
            }).join('');
        }

        // ---- Selektion ----
        _select(jobId, job) {
            this._selectedId = jobId;
            // Aktiv-Klasse setzen
            this._elList.querySelectorAll('.jl-item').forEach(el => {
                el.classList.toggle('active', Number(el.dataset.jobId) === jobId);
            });
            // Callback
            if (typeof this._opts.onSelect === 'function') {
                this._opts.onSelect(jobId, job);
            }
            // Custom Event
            document.dispatchEvent(new CustomEvent('studio:job-selected', {
                detail: { job_id: jobId, job_name: job?.job_name ?? '' }
            }));
        }

        // ---- Öffentliche API ----
        /**
         * Selektion programmatisch setzen (ohne onSelect zu triggern).
         * @param {number} jobId
         */
        setSelected(jobId) {
            this._selectedId = jobId;
            this._renderList();
        }

        /**
         * Filter setzen und Liste neu filtern.
         * @param {{ layerId?: number|null, status?: string|null }} filter
         */
        setFilter(filter = {}) {
            if ('layerId' in filter) this._filterLayer  = filter.layerId;
            if ('status' in filter)  this._filterStatus = filter.status;
            this._applyFilter();
        }

        /** Jobs manuell übergeben (z.B. für Demo / Tests). */
        setJobs(jobs, layers = []) {
            this._jobs   = jobs;
            this._layers = layers;
            this._populateLayerFilter();
            this._applyFilter();
        }
    }

    // ----------------------------------------------------------------
    // Custom Element
    // ----------------------------------------------------------------
    class JobListElement extends HTMLElement {
        connectedCallback() {
            const filter = {};
            if (this.hasAttribute('layer-id')) filter.layerId = Number(this.getAttribute('layer-id'));
            if (this.hasAttribute('status'))   filter.status  = this.getAttribute('status');
            this._instance = new JobList(this, {
                filter,
                onSelect: (jobId, job) => {
                    this.dispatchEvent(new CustomEvent('select', { detail: { job_id: jobId, job_name: job?.job_name ?? '' }, bubbles: true }));
                },
            });
            this._instance.load();
        }
        load()             { this._instance?.load(); }
        setSelected(id)    { this._instance?.setSelected(id); }
        setFilter(filter)  { this._instance?.setFilter(filter); }
    }

    if (!customElements.get('studio-job-list')) {
        customElements.define('studio-job-list', JobListElement);
    }

    // ----------------------------------------------------------------
    // Export
    // ----------------------------------------------------------------
    window.JobList = JobList;

})();
