/**
 * daita-studio – Spalten-Auswahl Komponente (C5)
 *
 * Zeigt alle Spalten einer Source-Tabelle mit drei Checkbox-Spalten:
 *   PK    – Business Key / Primary Key Spalten (für SCD2-Historisierung)
 *   Hash  – Spalten die in den Record-Hash einfließen (Änderungserkennung)
 *   Laden – Spalten die in das SELECT / in die Zieltabelle übernommen werden
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   <script src="/components/column-selector.js"></script>
 *
 *   <!-- Als Custom Element: -->
 *   <studio-column-selector table-id="5"></studio-column-selector>
 *   <script>
 *     const cs = document.querySelector('studio-column-selector');
 *     cs.addEventListener('change', e => console.log(e.detail));
 *   </script>
 *
 *   <!-- Oder per JS-Instanz: -->
 *   const cs = new ColumnSelector(containerEl, { tableId: 5, onChange: sel => ... });
 *   cs.load();
 *   const sel = cs.getSelection();  // { pk_columns, hash_columns, select_columns }
 *
 * Custom Events (gefeuert auf dem Host-Element):
 *   change  { detail: { pk_columns: [], hash_columns: [], select_columns: [] } }
 *
 * Abhängigkeiten: api.js (window.api)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Styles
    // ----------------------------------------------------------------
    const STYLE = `
        .cs-root { font-size: 0.87em; }

        /* Toolbar */
        .cs-toolbar {
            display: flex; gap: 8px; align-items: center;
            padding: 8px 0 10px; flex-wrap: wrap;
        }
        .cs-search {
            flex: 1; min-width: 120px; padding: 5px 9px;
            border: 1px solid var(--border-color, #e0e0e0);
            border-radius: 6px; font-size: 0.9em;
        }
        .cs-search:focus { outline: none; border-color: var(--primary-color, #667eea); }
        .cs-tool-btn {
            padding: 5px 11px; border-radius: 5px; border: 1px solid #ddd;
            background: #f5f5f5; cursor: pointer; font-size: 0.82em;
            white-space: nowrap; transition: background 0.15s;
        }
        .cs-tool-btn:hover { background: #eaeaea; }
        .cs-tool-btn.active { background: #e8eaf6; border-color: #9fa8da; color: #3949ab; }

        /* Tabelle */
        .cs-wrap { overflow-x: auto; }
        .cs-table { width: 100%; border-collapse: collapse; }
        .cs-table thead tr { background: #f5f5f5; }
        .cs-table th {
            padding: 6px 10px; text-align: left; font-size: 0.82em;
            font-weight: 700; color: #555; position: sticky; top: 0;
            background: #f5f5f5; white-space: nowrap;
        }
        .cs-table th.chk-col { text-align: center; width: 52px; }
        .cs-table td { padding: 5px 10px; border-bottom: 1px solid #f0f0f0; }
        .cs-table td.chk-col { text-align: center; }
        .cs-table tr:hover td { background: #fafafa; }
        .cs-table tr.cs-row-excluded td { opacity: 0.38; }
        .cs-table tr.cs-row-excluded td.chk-col { opacity: 1; }

        /* Spalten-Anzeige */
        .cs-col-name { font-weight: 600; font-size: 0.9em; }
        .cs-col-type { color: #888; font-size: 0.82em; }
        .cs-col-bk   { font-size: 0.72em; font-weight: 700; padding: 1px 6px;
                        border-radius: 8px; background: #e8eaf6; color: #3949ab; margin-left: 4px; }
        .cs-col-pk   { font-size: 0.72em; font-weight: 700; padding: 1px 6px;
                        border-radius: 8px; background: #fff9e6; color: #b45309; margin-left: 4px; }

        /* Technische Zeilen (z.B. Surrogate Key) – nicht editierbar */
        .cs-table tr.cs-row-tech td { background: #f3e9fb; }
        .cs-table tr.cs-row-tech:hover td { background: #eddcf7; }
        .cs-table tr.cs-row-tech-fk td { background: #e8f5e9; }
        .cs-table tr.cs-row-tech-fk:hover td { background: #d7eddb; }
        .cs-col-sk   { font-size: 0.72em; font-weight: 700; padding: 1px 6px;
                        border-radius: 8px; background: #f3e5f5; color: #7b1fa2; margin-left: 4px; }
        .cs-col-fk   { background: #c8e6c9; color: #1b5e20; }
        .cs-chk:disabled { cursor: not-allowed; opacity: 0.85; }
        /* Checkboxen */
        .cs-chk { width: 16px; height: 16px; cursor: pointer; accent-color: #667eea; }
        .cs-chk-bk   { accent-color: #f59e0b; }
        .cs-chk-pk   { accent-color: #e53935; }
        .cs-chk-pi   { accent-color: #0288d1; }
        .cs-chk-hash { accent-color: #9575cd; }
        .cs-chk-load { accent-color: #4caf50; }

        /* Header-Checkboxen (alle auswählen) */
        .cs-table th.chk-col label {
            display: flex; flex-direction: column; align-items: center;
            gap: 2px; font-size: 0.78em; cursor: pointer;
        }

        /* Summary */
        .cs-summary {
            display: flex; gap: 14px; padding: 8px 2px 0;
            font-size: 0.82em; color: #666; flex-wrap: wrap;
        }
        .cs-summary-item span:first-child { color: #888; }
        .cs-summary-item span:last-child  { font-weight: 700; color: #3949ab; }

        /* Leer / Lade */
        .cs-placeholder { text-align: center; padding: 20px; color: #aaa; font-size: 0.9em; }
    `;

    function injectStyles() {
        if (document.getElementById('studio-column-selector-style')) return;
        const s = document.createElement('style');
        s.id = 'studio-column-selector-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    // ----------------------------------------------------------------
    // Kern-Klasse ColumnSelector
    // ----------------------------------------------------------------

    class ColumnSelector {
        /**
         * @param {HTMLElement} container
         * @param {{ tableId: number, onChange?: function, initial?: object }} opts
         *   initial = { pk_columns: [], hash_columns: [], select_columns: [] }
         */
        constructor(container, opts = {}) {
            injectStyles();
            this._el       = container;
            this._tableId  = opts.tableId || null;
            this._onChange = opts.onChange || null;
            this._initial  = opts.initial || null;
            this._techRows = opts.techRows || [];  // fixe, nicht-editierbare Zeilen (z.B. Surrogate Key)
            this._cols     = [];
            this._state    = {};   // colName → { pk, hash, load }
            this._techState= {};   // techRowName → pi (editierbarer PI-Zustand technischer Zeilen)
            this._filter   = '';
            this._el.innerHTML = `<div class="cs-root"><div class="cs-placeholder">Keine Tabelle ausgewählt.</div></div>`;
        }

        /** Setzt fixe technische Zeilen (z.B. Surrogate Key) und rendert neu. */
        setTechRows(techRows) {
            this._techRows = techRows || [];
            if (this._cols.length) { this._renderRows(); }
        }

        /** Liefert den editierbaren Zustand technischer Zeilen, z.B. { '..._SK': { pi: true } }. */
        getTechState() {
            const out = {};
            this._techRows.forEach(tr0 => {
                const name = (tr0.name || '').toUpperCase();
                out[name] = { pi: this._techState[name] !== undefined ? this._techState[name] : !!tr0.pi };
            });
            return out;
        }

        /** Setzt eine neue Tabelle und lädt Spalten. */
        setTable(tableId, initial = null) {
            this._tableId = tableId;
            if (initial) this._initial = initial;
            this.load();
        }

        /** Lädt Spalten der aktuellen Tabelle. */
        async load() {
            if (!this._tableId) return;
            this._el.innerHTML = `<div class="cs-root"><div class="cs-placeholder">Lade Spalten…</div></div>`;

            const cols = await window.api.etl.tables.columns(this._tableId).catch(() => []);
            if (!cols?.length) {
                this._el.innerHTML = `<div class="cs-root"><div class="cs-placeholder">Keine Spalten gefunden.</div></div>`;
                return;
            }

            this._cols = cols;
            this._initState();
            this._render();
        }

        /** Gibt aktuelle Selektion zurück. */
        getSelection() {
            const bk = [], pk = [], pi = [], hash = [], load = [];
            for (const [name, s] of Object.entries(this._state)) {
                if (s.bk)   bk.push(name);
                if (s.pk)   pk.push(name);
                if (s.pi)   pi.push(name);
                if (s.hash) hash.push(name);
                if (s.load) load.push(name);
            }
            return { bk_columns: bk, pk_columns: pk, pi_columns: pi, hash_columns: hash, select_columns: load };
        }

        /** Setzt eine externe Selektion (z.B. aus Template-Defaults). */
        setSelection(sel) {
            const bkSet   = new Set((sel.bk_columns   || []).map(s => s.toUpperCase()));
            const pkSet   = new Set((sel.pk_columns   || []).map(s => s.toUpperCase()));
            const piSet   = new Set((sel.pi_columns   || []).map(s => s.toUpperCase()));
            const hashSet = new Set((sel.hash_columns || []).map(s => s.toUpperCase()));
            const loadSet = new Set((sel.select_columns || []).map(s => s.toUpperCase()));
            for (const [name, s] of Object.entries(this._state)) {
                const u = name.toUpperCase();
                s.bk   = bkSet.has(u);
                s.pk   = pkSet.has(u);
                s.pi   = piSet.has(u);
                s.hash = hashSet.has(u);
                s.load = loadSet.has(u);
            }
            this._renderRows();
            this._updateSummary();
        }

        // ---- Private ----

        _initState() {
            this._state = {};
            const initBk   = new Set((this._initial?.bk_columns   || []).map(s => s.toUpperCase()));
            const initPk   = new Set((this._initial?.pk_columns   || []).map(s => s.toUpperCase()));
            const initPi   = new Set((this._initial?.pi_columns   || []).map(s => s.toUpperCase()));
            const initHash = new Set((this._initial?.hash_columns || []).map(s => s.toUpperCase()));
            const initLoad = new Set((this._initial?.select_columns|| []).map(s => s.toUpperCase()));
            const hasInit  = initLoad.size > 0 || initBk.size > 0 || initPk.size > 0 || initPi.size > 0 || initHash.size > 0;

            this._cols.forEach(c => {
                const name = (c.column_name || c.COLUMN_NAME || '').toUpperCase();
                const isBk = ['Y','y'].includes(c.bk_flag || c.is_business_key || '');
                const isPk = ['Y','y'].includes(c.pk_flag || c.is_technical_key || '');

                if (hasInit) {
                    this._state[name] = {
                        bk:   initBk.has(name),
                        pk:   initPk.has(name),
                        pi:   initPi.has(name),
                        hash: initHash.has(name),
                        load: initLoad.has(name),
                    };
                } else {
                    const isAudit = ['Y','y'].includes(c.audit_flag || c.is_audit_column || '');
                    const isPI    = ['Y','y'].includes(c.pi_flag || c.is_pi || '');
                    this._state[name] = {
                        bk:   isBk,
                        pk:   isPk,
                        pi:   isPI,
                        hash: !isAudit && !isPk,
                        load: !isAudit,
                    };
                }
                // Metadaten cachen
                this._state[name]._col = c;
            });
        }

        _render() {
            this._el.innerHTML = `
                <div class="cs-root">
                    <div class="cs-toolbar">
                        <input class="cs-search" type="text" placeholder="🔍 Spalten filtern…" id="cs-search">
                        <button class="cs-tool-btn" id="cs-all-load" title="Alle Laden-Checkboxen">☑ Alle laden</button>
                        <button class="cs-tool-btn" id="cs-pk-hash" title="BK-Spalten auch als Hash markieren">🏷 BK→Hash</button>
                        <button class="cs-tool-btn" id="cs-none-load" title="Alle Laden abwählen">☐ Keiner</button>
                    </div>
                    <div class="cs-wrap">
                        <table class="cs-table">
                            <thead>
                                <tr>
                                    <th>Spaltenname</th>
                                    <th>Typ</th>
                                    <th class="chk-col">
                                        <label title="Business Key – Natural Key für SCD2-Historisierung">
                                            <input type="checkbox" class="cs-chk cs-chk-bk" id="cs-all-bk"> BK
                                        </label>
                                    </th>
                                    <th class="chk-col">
                                        <label title="Technischer PK der Quelltabelle (IS_TECHNICAL_KEY)">
                                            <input type="checkbox" class="cs-chk cs-chk-pk" id="cs-all-pk"> PK
                                        </label>
                                    </th>
                                    <th class="chk-col">
                                        <label title="Primary Index Teradata (IS_PI)">
                                            <input type="checkbox" class="cs-chk cs-chk-pi" id="cs-all-pi"> PI
                                        </label>
                                    </th>
                                    <th class="chk-col">
                                        <label title="Record-Hash (alle)">
                                            <input type="checkbox" class="cs-chk cs-chk-hash" id="cs-all-hash"> Hash
                                        </label>
                                    </th>
                                    <th class="chk-col">
                                        <label title="Laden/SELECT (alle)">
                                            <input type="checkbox" class="cs-chk cs-chk-load" id="cs-all-load-chk"> Laden
                                        </label>
                                    </th>
                                </tr>
                            </thead>
                            <tbody id="cs-tbody"></tbody>
                        </table>
                    </div>
                    <div class="cs-summary" id="cs-summary"></div>
                </div>`;

            this._renderRows();
            this._updateSummary();
            this._bindEvents();
        }

        _visibleCols() {
            if (!this._filter) return this._cols;
            const f = this._filter.toLowerCase();
            return this._cols.filter(c => {
                const name = (c.column_name || c.COLUMN_NAME || '').toLowerCase();
                return name.includes(f);
            });
        }

        _renderRows() {
            const tbody = this._el.querySelector('#cs-tbody');
            if (!tbody) return;
            tbody.innerHTML = '';

            // Fixe technische Zeilen (z.B. Surrogate Key) – read-only, fließen NICHT in getSelection()
            const f = this._filter.toLowerCase();
            this._techRows.forEach(tr0 => {
                const name = (tr0.name || '').toUpperCase();
                if (f && !name.toLowerCase().includes(f)) return;
                const type = tr0.type || '';
                // PI-Zustand persistieren (editierbar bei piEditable)
                if (this._techState[name] === undefined) this._techState[name] = !!tr0.pi;
                const piChecked = this._techState[name];
                const piDisabled = tr0.piEditable ? '' : 'disabled';
                const badgeTxt  = tr0.badge || 'SK';
                const isFk      = badgeTxt === 'FK';
                const badgeIcon = isFk ? '🔗' : '🔑';
                const tr = document.createElement('tr');
                tr.className = isFk ? 'cs-row-tech cs-row-tech-fk' : 'cs-row-tech';
                tr.innerHTML = `
                    <td>
                        <span class="cs-col-name">${name}</span>
                        <span class="cs-col-sk ${isFk ? 'cs-col-fk' : ''}" title="Technische Spalte – wird automatisch erzeugt">${badgeTxt} ${badgeIcon}</span>
                    </td>
                    <td><span class="cs-col-type">${type}</span></td>
                    <td class="chk-col"><input type="checkbox" class="cs-chk cs-chk-bk"   disabled ${tr0.bk   ? 'checked' : ''}></td>
                    <td class="chk-col"><input type="checkbox" class="cs-chk cs-chk-pk"   disabled ${tr0.pk   ? 'checked' : ''}></td>
                    <td class="chk-col"><input type="checkbox" class="cs-chk cs-chk-pi cs-tech-pi" data-tech="${name}" ${piDisabled} ${piChecked ? 'checked' : ''}></td>
                    <td class="chk-col"><input type="checkbox" class="cs-chk cs-chk-hash" disabled ${tr0.hash ? 'checked' : ''}></td>
                    <td class="chk-col"><input type="checkbox" class="cs-chk cs-chk-load" disabled ${tr0.load ? 'checked' : ''}></td>`;
                tbody.appendChild(tr);
                const piChk = tr.querySelector('.cs-tech-pi');
                if (tr0.piEditable && piChk) {
                    piChk.addEventListener('change', () => {
                        this._techState[name] = piChk.checked;
                        this._fireChange();
                    });
                }
            });

            this._visibleCols().forEach(c => {
                const name  = (c.column_name || c.COLUMN_NAME || '').toUpperCase();
                const type  = c.data_type || c.COLUMN_TYPE || '';
                const len   = c.data_length || c.COLUMN_LENGTH;
                const typeStr = len ? `${type}(${len})` : type;
                const isBk  = ['Y','y'].includes(c.bk_flag || c.is_business_key || '');
                const isPk  = ['Y','y'].includes(c.pk_flag || c.is_technical_key || '');
                const s     = this._state[name] || { bk: false, pk: false, pi: false, hash: false, load: false };

                const tr = document.createElement('tr');
                tr.dataset.col = name;
                tr.className = s.load ? '' : 'cs-row-excluded';
                tr.innerHTML = `
                    <td>
                        <span class="cs-col-name">${name}</span>
                        ${isBk ? '<span class="cs-col-bk">BK</span>' : ''}
                        ${isPk ? '<span class="cs-col-pk">PK</span>' : ''}
                    </td>
                    <td><span class="cs-col-type">${typeStr}</span></td>
                    <td class="chk-col">
                        <input type="checkbox" class="cs-chk cs-chk-bk  cs-row-bk"   data-col="${name}" ${s.bk   ? 'checked' : ''}>
                    </td>
                    <td class="chk-col">
                        <input type="checkbox" class="cs-chk cs-chk-pk  cs-row-pk"   data-col="${name}" ${s.pk   ? 'checked' : ''}>
                    </td>
                    <td class="chk-col">
                        <input type="checkbox" class="cs-chk cs-chk-pi  cs-row-pi"   data-col="${name}" ${s.pi   ? 'checked' : ''}>
                    </td>
                    <td class="chk-col">
                        <input type="checkbox" class="cs-chk cs-chk-hash cs-row-hash" data-col="${name}" ${s.hash ? 'checked' : ''}>
                    </td>
                    <td class="chk-col">
                        <input type="checkbox" class="cs-chk cs-chk-load cs-row-load" data-col="${name}" ${s.load ? 'checked' : ''}>
                    </td>`;

                tbody.appendChild(tr);
            });

            // Row-Events
            tbody.querySelectorAll('.cs-row-bk').forEach(chk => {
                chk.addEventListener('change', () => { this._state[chk.dataset.col].bk = chk.checked; this._onRowChange(chk.dataset.col); });
            });
            tbody.querySelectorAll('.cs-row-pk').forEach(chk => {
                chk.addEventListener('change', () => { this._state[chk.dataset.col].pk = chk.checked; this._onRowChange(chk.dataset.col); });
            });
            tbody.querySelectorAll('.cs-row-pi').forEach(chk => {
                chk.addEventListener('change', () => { this._state[chk.dataset.col].pi = chk.checked; this._onRowChange(chk.dataset.col); });
            });
            tbody.querySelectorAll('.cs-row-hash').forEach(chk => {
                chk.addEventListener('change', () => { this._state[chk.dataset.col].hash = chk.checked; this._onRowChange(chk.dataset.col); });
            });
            tbody.querySelectorAll('.cs-row-load').forEach(chk => {
                chk.addEventListener('change', () => {
                    this._state[chk.dataset.col].load = chk.checked;
                    // Wenn nicht laden: auch hash/bk/pk deaktivieren
                    if (!chk.checked) {
                        this._state[chk.dataset.col].bk   = false;
                        this._state[chk.dataset.col].pk   = false;
                        this._state[chk.dataset.col].pi   = false;
                        this._state[chk.dataset.col].hash = false;
                    }
                    this._onRowChange(chk.dataset.col);
                    // Zeile visuell ausblenden
                    const tr = tbody.querySelector(`tr[data-col="${chk.dataset.col}"]`);
                    if (tr) tr.className = chk.checked ? '' : 'cs-row-excluded';
                    // Andere Checkboxen in dieser Zeile synchronisieren
                    if (tr) {
                        tr.querySelector('.cs-row-bk').checked   = this._state[chk.dataset.col].bk;
                        tr.querySelector('.cs-row-pk').checked   = this._state[chk.dataset.col].pk;
                        tr.querySelector('.cs-row-pi').checked   = this._state[chk.dataset.col].pi;
                        tr.querySelector('.cs-row-hash').checked = this._state[chk.dataset.col].hash;
                    }
                });
            });
        }

        _onRowChange(colName) {
            this._updateSummary();
            this._fireChange();
            // Header-Checkboxen synchronisieren
            this._syncHeaderChecks();
        }

        _syncHeaderChecks() {
            const allBk   = this._el.querySelector('#cs-all-bk');
            const allPk   = this._el.querySelector('#cs-all-pk');
            const allPi   = this._el.querySelector('#cs-all-pi');
            const allHash = this._el.querySelector('#cs-all-hash');
            const allLoad = this._el.querySelector('#cs-all-load-chk');
            if (!allBk) return;
            const vals = Object.values(this._state);
            allBk.indeterminate   = vals.some(s => s.bk)   && !vals.every(s => s.bk);
            allPk.indeterminate   = vals.some(s => s.pk)   && !vals.every(s => s.pk);
            allPi.indeterminate   = vals.some(s => s.pi)   && !vals.every(s => s.pi);
            allHash.indeterminate = vals.some(s => s.hash) && !vals.every(s => s.hash);
            allLoad.indeterminate = vals.some(s => s.load) && !vals.every(s => s.load);
            if (!allBk.indeterminate)   allBk.checked   = vals.every(s => s.bk);
            if (!allPk.indeterminate)   allPk.checked   = vals.every(s => s.pk);
            if (!allPi.indeterminate)   allPi.checked   = vals.every(s => s.pi);
            if (!allHash.indeterminate) allHash.checked = vals.every(s => s.hash);
            if (!allLoad.indeterminate) allLoad.checked = vals.every(s => s.load);
        }

        _updateSummary() {
            const summary = this._el.querySelector('#cs-summary');
            if (!summary) return;
            const sel = this.getSelection();
            summary.innerHTML = `
                <div class="cs-summary-item"><span>Laden:</span> <span>${sel.select_columns.length} / ${this._cols.length}</span></div>
                <div class="cs-summary-item"><span>BK:</span> <span>${sel.bk_columns.length}</span></div>
                <div class="cs-summary-item"><span>PK:</span> <span>${sel.pk_columns.length}</span></div>
                <div class="cs-summary-item"><span>PI:</span> <span>${sel.pi_columns.length}</span></div>
                <div class="cs-summary-item"><span>Hash:</span> <span>${sel.hash_columns.length}</span></div>`;
        }

        _fireChange() {
            const sel = this.getSelection();
            if (this._onChange) this._onChange(sel);
            this._el.dispatchEvent(new CustomEvent('change', { detail: sel, bubbles: true }));
        }

        _bindEvents() {
            // Suche
            const searchEl = this._el.querySelector('#cs-search');
            searchEl?.addEventListener('input', e => {
                this._filter = e.target.value.trim();
                this._renderRows();
            });

            // Alle laden
            this._el.querySelector('#cs-all-load')?.addEventListener('click', () => {
                Object.values(this._state).forEach(s => { s.load = true; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });

            // Keiner
            this._el.querySelector('#cs-none-load')?.addEventListener('click', () => {
                Object.values(this._state).forEach(s => { s.load = false; s.bk = false; s.pk = false; s.pi = false; s.hash = false; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });

            // BK→Hash
            this._el.querySelector('#cs-pk-hash')?.addEventListener('click', () => {
                Object.values(this._state).forEach(s => { if (s.bk) s.hash = true; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });

            // Header-Checkboxen (Alle BK / alle PK / alle Hash / alle Laden)
            this._el.querySelector('#cs-all-bk')?.addEventListener('change', e => {
                Object.values(this._state).forEach(s => { if (s.load) s.bk = e.target.checked; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });
            this._el.querySelector('#cs-all-pk')?.addEventListener('change', e => {
                Object.values(this._state).forEach(s => { if (s.load) s.pk = e.target.checked; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });
            this._el.querySelector('#cs-all-pi')?.addEventListener('change', e => {
                Object.values(this._state).forEach(s => { if (s.load) s.pi = e.target.checked; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });
            this._el.querySelector('#cs-all-hash')?.addEventListener('change', e => {
                Object.values(this._state).forEach(s => { if (s.load) s.hash = e.target.checked; });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });
            this._el.querySelector('#cs-all-load-chk')?.addEventListener('change', e => {
                Object.values(this._state).forEach(s => {
                    s.load = e.target.checked;
                    if (!e.target.checked) { s.bk = false; s.pk = false; s.pi = false; s.hash = false; }
                });
                this._renderRows(); this._updateSummary(); this._fireChange();
            });
        }
    }

    // ----------------------------------------------------------------
    // Custom Element <studio-column-selector table-id="5">
    // ----------------------------------------------------------------

    class StudioColumnSelector extends HTMLElement {
        static get observedAttributes() { return ['table-id']; }

        connectedCallback() {
            injectStyles();
            this._cs = new ColumnSelector(this, { tableId: parseInt(this.getAttribute('table-id')) || null });
            if (this._cs._tableId) this._cs.load();
        }

        attributeChangedCallback(name, _, newVal) {
            if (name === 'table-id' && this._cs) this._cs.setTable(parseInt(newVal));
        }

        load()                { this._cs?.load(); }
        getSelection()        { return this._cs?.getSelection(); }
        setSelection(sel)     { this._cs?.setSelection(sel); }
        setTable(id, init)    { this._cs?.setTable(id, init); }
    }

    if (!customElements.get('studio-column-selector')) {
        customElements.define('studio-column-selector', StudioColumnSelector);
    }
    window.ColumnSelector = ColumnSelector;

})();
