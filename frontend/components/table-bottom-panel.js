/**
 * TableBottomPanel – wiederverwendbares Bottom-Panel für Tabellen-Verwaltung
 *
 * Zeigt DBC (physisch) vs META (logisch) Spaltenvergleich, DDL-Generator/Executor,
 * Wartungsfunktionen (Stats, DELETE, TRUNCATE, DROP).
 *
 * Verwendung:
 *   const bp = new TableBottomPanel(document.getElementById('bottom-panel'));
 *   bp.show(tableObject);  // { table_id, table_name, db_name }
 *   bp.hide();
 *
 * Eigene HTML-Struktur wird in den übergebenen Container gerendert.
 * Kein globaler State — jede Instanz ist eigenständig.
 *
 * Benötigt:
 *   - window.api (api.js)
 *   - window.METADAITA_CONFIG.backend_url (config.js)
 */
(() => {
'use strict';

const STYLE_ID = 'tbp-style';

function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `
        .tbp-panel {
            display: flex; flex-direction: column;
            background: var(--card-bg, #fff);
            border-top: 2px solid var(--border-color, #ddd);
        }
        .tbp-resize-handle {
            height: 4px; cursor: ns-resize; flex-shrink: 0;
            background: linear-gradient(135deg, #667eea44, #764ba244);
            transition: background 0.15s;
        }
        .tbp-resize-handle:hover { background: linear-gradient(135deg, #667eea, #764ba2); }
        .tbp-header {
            display: flex; align-items: center; gap: 8px; padding: 6px 12px;
            border-bottom: 1px solid var(--border-color, #eee);
            background: var(--bg-color, #f5f5f5); flex-shrink: 0;
        }
        .tbp-title { font-weight: 700; font-size: 0.88em; }
        .tbp-db-badge {
            font-size: 0.75em; background: #667eea22; color: #667eea;
            padding: 1px 6px; border-radius: 4px;
        }
        .tbp-tabs { display: flex; gap: 2px; margin-left: auto; }
        .tbp-tab {
            padding: 3px 10px; border: 1px solid var(--border-color, #ddd);
            border-radius: 4px; background: transparent; cursor: pointer; font-size: 0.78em;
        }
        .tbp-tab.active { background: #667eea; color: #fff; border-color: #667eea; }
        .tbp-toggle-btn {
            padding: 3px 8px; border: 1px solid var(--border-color, #ddd);
            border-radius: 4px; background: transparent; cursor: pointer; font-size: 0.75em;
        }
        .tbp-toggle-btn.active { background: #764ba222; border-color: #764ba2; }
        .tbp-close-btn {
            padding: 2px 8px; border: none; background: transparent; cursor: pointer;
            font-size: 1.1em; color: #aaa;
        }
        .tbp-close-btn:hover { color: #555; }
        .tbp-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
        .tbp-tab-pane { display: none; flex: 1; overflow: hidden; }

        /* Spalten-Tab */
        .tbp-spalten-pane { flex: 1; overflow: hidden; }
        .tbp-split { display: flex; flex: 1; overflow: hidden; }
        .tbp-side { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
        .tbp-divider { width: 3px; background: var(--border-color, #ddd); cursor: col-resize; flex-shrink: 0; }
        .tbp-side-title {
            padding: 5px 10px; font-size: 0.78em; font-weight: 700;
            background: var(--bg-color, #f8f8f8); border-bottom: 1px solid var(--border-color, #eee);
            display: flex; align-items: center; gap: 8px; flex-shrink: 0;
        }
        .tbp-save-btn {
            padding: 2px 8px; border: 1px solid #667eea; border-radius: 4px;
            background: transparent; color: #667eea; cursor: pointer; font-size: 0.8em;
        }
        .tbp-save-btn:hover { background: #667eea; color: #fff; }
        .tbp-scroll { flex: 1; overflow: auto; }
        .tbp-no-data { padding: 12px; color: #aaa; font-size: 0.83em; }

        /* Tabelle */
        .tbp-table { width: 100%; border-collapse: collapse; font-size: 0.75em; }
        .tbp-table th, .tbp-table td {
            border-bottom: 1px solid var(--border-color, #eee); padding: 3px 6px;
            white-space: nowrap;
        }
        .tbp-table th { background: var(--bg-color, #f5f5f5); font-weight: 600; position: sticky; top: 0; z-index: 1; }
        .tbp-table tr:hover td { background: #f4f0ff; }
        .tbp-cb { text-align: center; width: 28px; }
        .tbp-flag-y { color: #27ae60; font-weight: 700; }
        .tbp-flag-n { color: #ccc; }
        .tbp-zusatz { display: none; }
        .tbp-table.show-zusatz .tbp-zusatz { display: table-cell; }
        .tbp-edit { font-size: 0.85em; padding: 1px 4px; border: 1px solid transparent; border-radius: 2px; background: transparent; }
        .tbp-edit:focus { border-color: #667eea; outline: none; background: #fff; }
        .tbp-txt { width: 100%; min-width: 60px; }

        /* DDL-Tab */
        .tbp-ddl-pane { flex-direction: column; flex: 1; }
        .tbp-ddl-toolbar {
            padding: 8px 10px; display: flex; align-items: center; gap: 8px;
            border-bottom: 1px solid var(--border-color, #eee); flex-shrink: 0;
        }
        .tbp-tool-btn {
            padding: 4px 10px; border: 1px solid var(--border-color, #ddd);
            border-radius: 4px; cursor: pointer; background: transparent; font-size: 0.82em;
        }
        .tbp-tool-btn--run { border-color: #27ae60; color: #27ae60; }
        .tbp-tool-btn--run:hover { background: #27ae60; color: #fff; }
        .tbp-ddl-textarea {
            flex: 1; padding: 10px; font-family: monospace; font-size: 0.83em;
            border: none; resize: none; background: var(--bg-color, #f8f8f8);
            color: var(--text-primary, #333);
        }
        .tbp-status-msg { font-size: 0.82em; color: #888; }
        .tbp-status-msg.ok  { color: #27ae60; }
        .tbp-status-msg.err { color: #e74c3c; }

        /* Wartung-Tab */
        .tbp-wartung-pane { overflow: auto; padding: 12px; }
        .tbp-wartung-section { margin-bottom: 14px; }
        .tbp-wartung-title { font-weight: 700; font-size: 0.83em; margin-bottom: 8px; }
        .tbp-wartung-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
        .tbp-danger-btn {
            padding: 4px 10px; border: 1px solid #e74c3c; border-radius: 4px;
            color: #e74c3c; background: transparent; cursor: pointer; font-size: 0.8em;
        }
        .tbp-danger-btn:hover { background: #e74c3c; color: #fff; }
        .tbp-danger-btn--red { border-color: #c0392b; color: #c0392b; }
        .tbp-danger-btn--red:hover { background: #c0392b; color: #fff; }
        .tbp-danger-hint { font-size: 0.78em; color: #aaa; }
        .tbp-danger-zone { border: 1px solid #f5c6cb; border-radius: 6px; padding: 10px; background: #fff8f8; }
    `;
    document.head.appendChild(s);
}

function _apiBase() {
    return ((window.METADAITA_CONFIG?.backend_url || '') + '/api').replace(/\/+$/, '');
}

function _esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _flag(val) {
    return (String(val||'').trim() === 'Y')
        ? '<span class="tbp-flag-y">✓</span>'
        : '<span class="tbp-flag-n">–</span>';
}

function _fmtType(type, len, prec, scale) {
    if (!type) return '—';
    const t = String(type).trim();
    const TD = {I:'INTEGER',I1:'BYTEINT',I2:'SMALLINT',I8:'BIGINT',F:'FLOAT',D:'DECIMAL',N:'NUMBER',
                CV:'VARCHAR',CF:'CHAR',UC:'VARCHAR(UNICODE)',DA:'DATE',TS:'TIMESTAMP',
                TZ:'TIMESTAMP WITH TIME ZONE',AT:'TIME',BF:'BYTE',BV:'VARBYTE'};
    const name = TD[t] || t;
    if ((t==='D'||t==='N') && prec) return `${name}(${prec},${scale||0})`;
    if ((t==='CV'||t==='CF'||t==='UC') && len) return `${name}(${len})`;
    return name;
}

// ─────────────────────────────────────────────────────────────────────────────
class TableBottomPanel {
    /**
     * @param {HTMLElement} container  – das Panel-Element
     * @param {object}      opts       – { height: 300, onClose: fn }
     */
    constructor(container, opts = {}) {
        injectStyles();
        this._el      = container;
        this._opts    = opts;
        this._tableId = null;
        this._zusatz  = false;
        this._rendered = false;
        this._pendingAction = null;
    }

    // ── Öffentliche API ───────────────────────────────────────────────

    /** Zeigt das Panel und lädt Daten für die angegebene Tabelle */
    show(table) {
        if (!this._rendered) this._render();
        this._el.style.display = 'flex';
        this._el.style.height  = (this._opts.height || 300) + 'px';
        this._tableId = table.table_id;
        this._pendingAction = null;
        const _cr = this._domConfirmRow   || this._q('.tbp-confirm-row');
        const _mr = this._domMaintResult  || this._q('.tbp-maint-result');
        if (_cr) _cr.style.display = 'none';
        if (_mr) _mr.textContent = '';
        this._q('.tbp-title').textContent    = table.table_name || '—';
        this._q('.tbp-db-badge').textContent = table.db_name || '';
        this._switchTab('spalten');
        this._loadSpalten();
    }

    hide() {
        this._el.style.display = 'none';
        if (this._opts.onClose) this._opts.onClose();
    }

    // ── Render ────────────────────────────────────────────────────────

    _render() {
        this._el.className = 'tbp-panel';
        this._el.style.display = 'none';
        this._el.innerHTML = `
            <div class="tbp-resize-handle"></div>
            <div class="tbp-header">
                <span class="tbp-title">—</span>
                <span class="tbp-db-badge"></span>
                <nav class="tbp-tabs">
                    <button class="tbp-tab active" data-tab="spalten">📋 Spalten</button>
                    <button class="tbp-tab"        data-tab="ddl">🔧 DDL</button>
                    <button class="tbp-tab"        data-tab="wartung">⚙ Wartung</button>
                </nav>
                <button class="tbp-toggle-btn tbp-zusatz-toggle">⊞ Zusatz</button>
                <button class="tbp-close-btn">✕</button>
            </div>
            <div class="tbp-body">
                <div class="tbp-tab-pane tbp-spalten-pane" data-pane="spalten" style="display:flex">
                    <div class="tbp-split">
                        <div class="tbp-side">
                            <div class="tbp-side-title">🗄 DBC (physisch)</div>
                            <div class="tbp-scroll tbp-dbc-content"><div class="tbp-no-data">Lade…</div></div>
                        </div>
                        <div class="tbp-divider"></div>
                        <div class="tbp-side">
                            <div class="tbp-side-title">
                                📋 META
                                <button class="tbp-save-btn tbp-meta-save">💾 Speichern</button>
                            </div>
                            <div class="tbp-scroll tbp-meta-content"><div class="tbp-no-data">Lade…</div></div>
                        </div>
                    </div>
                </div>
                <div class="tbp-tab-pane tbp-ddl-pane" data-pane="ddl" style="display:none;flex-direction:column">
                    <div class="tbp-ddl-toolbar">
                        <button class="tbp-tool-btn tbp-ddl-gen">⚡ Generieren</button>
                        <button class="tbp-tool-btn tbp-tool-btn--run tbp-ddl-exec">▶ Ausführen</button>
                        <span class="tbp-status-msg tbp-ddl-status"></span>
                    </div>
                    <textarea class="tbp-ddl-textarea tbp-ddl-text" spellcheck="false"
                              placeholder="DDL generieren oder eingeben…"></textarea>
                </div>
                <div class="tbp-tab-pane tbp-wartung-pane" data-pane="wartung" style="display:none">
                    <div class="tbp-wartung-section">
                        <div class="tbp-wartung-title">📊 Statistiken</div>
                        <div class="tbp-wartung-row">
                            <button class="tbp-tool-btn tbp-stats-load">Laden</button>
                            <span class="tbp-status-msg tbp-stats-result"></span>
                        </div>
                    </div>
                    <div class="tbp-wartung-section tbp-danger-zone">
                        <div class="tbp-wartung-title">⚠ Gefahrenzone</div>
                        <div class="tbp-wartung-row">
                            <button class="tbp-danger-btn tbp-maint-btn" data-action="delete-meta">🗑 Aus META löschen</button>
                            <span class="tbp-danger-hint">Entfernt Tabelle + Spalten + Indizes + FKs aus META</span>
                        </div>
                        <div class="tbp-wartung-row">
                            <button class="tbp-danger-btn tbp-maint-btn" data-action="truncate">✂ Tabelle leeren</button>
                            <span class="tbp-danger-hint">DELETE ALL – alle Zeilen löschen, Struktur bleibt</span>
                        </div>
                        <div class="tbp-wartung-row">
                            <button class="tbp-danger-btn tbp-danger-btn--red tbp-maint-btn" data-action="drop">💣 DROP TABLE</button>
                            <span class="tbp-danger-hint">Tabelle physisch in Teradata droppen (irreversibel!)</span>
                        </div>
                        <div class="tbp-confirm-row" style="display:none">
                            <span class="tbp-confirm-label"></span>
                            <button class="tbp-danger-btn tbp-danger-btn--red tbp-confirm-yes">✓ Ja, ausführen</button>
                            <button class="tbp-tool-btn tbp-confirm-no">Abbrechen</button>
                        </div>
                        <div class="tbp-status-msg tbp-maint-result" style="margin-top:8px"></div>
                    </div>
                </div>
            </div>`;

        this._initResize();
        this._initTabs();
        this._initButtons();
        // DOM-Referenzen cachen, damit sie nicht bei jedem Aufruf neu gesucht werden
        this._domConfirmRow   = this._q('.tbp-confirm-row');
        this._domConfirmLabel = this._q('.tbp-confirm-label');
        this._domMaintResult  = this._q('.tbp-maint-result');
        this._rendered = true;
    }

    _q(selector) { return this._el.querySelector(selector); }

    // ── Resize ────────────────────────────────────────────────────────

    _initResize() {
        const handle = this._q('.tbp-resize-handle');
        let _startY = 0, _startH = 0;
        handle.addEventListener('mousedown', e => {
            _startY = e.clientY; _startH = this._el.offsetHeight;
            const onMove = ev => {
                const dy = _startY - ev.clientY;
                this._el.style.height = Math.max(150, Math.min(window.innerHeight * 0.65, _startH + dy)) + 'px';
            };
            const onUp = () => {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            e.preventDefault();
        });
    }

    // ── Tabs ──────────────────────────────────────────────────────────

    _initTabs() {
        this._el.querySelectorAll('.tbp-tab').forEach(btn => {
            btn.addEventListener('click', () => this._switchTab(btn.dataset.tab));
        });
    }

    _switchTab(tab) {
        this._el.querySelectorAll('.tbp-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        this._el.querySelectorAll('.tbp-tab-pane').forEach(p => {
            const show = p.dataset.pane === tab;
            p.style.display = show ? (tab === 'spalten' ? 'flex' : 'flex') : 'none';
            if (show && tab !== 'spalten') p.style.flexDirection = 'column';
        });
        this._q('.tbp-zusatz-toggle').style.display = tab === 'spalten' ? '' : 'none';
        if (tab === 'ddl' && !this._q('.tbp-ddl-text').value && this._tableId) {
            this._ddlGenerate();
        }
    }

    // ── Buttons ───────────────────────────────────────────────────────

    _initButtons() {
        this._q('.tbp-close-btn').addEventListener('click', () => this.hide());
        this._q('.tbp-zusatz-toggle').addEventListener('click', () => {
            this._zusatz = !this._zusatz;
            this._q('.tbp-zusatz-toggle').classList.toggle('active', this._zusatz);
            this._el.querySelectorAll('.tbp-table').forEach(t => t.classList.toggle('show-zusatz', this._zusatz));
        });
        this._q('.tbp-meta-save').addEventListener('click', () => this._saveMeta());
        this._q('.tbp-ddl-gen').addEventListener('click', () => this._ddlGenerate());
        this._q('.tbp-ddl-exec').addEventListener('click', () => this._ddlExecute());
        this._q('.tbp-stats-load').addEventListener('click', () => this._statsLoad());
        this._el.querySelectorAll('.tbp-maint-btn').forEach(btn => {
            btn.addEventListener('click', () => this._maintConfirm(btn.dataset.action));
        });
        this._q('.tbp-confirm-yes').addEventListener('click', () => this._maintExecute());
        this._q('.tbp-confirm-no').addEventListener('click',  () => this._maintCancelConfirm());
    }

    // ── Spalten laden ─────────────────────────────────────────────────

    async _loadSpalten() {
        const dbcEl  = this._q('.tbp-dbc-content');
        const metaEl = this._q('.tbp-meta-content');
        dbcEl.innerHTML  = '<div class="tbp-no-data">Lade…</div>';
        metaEl.innerHTML = '<div class="tbp-no-data">Lade…</div>';
        try {
            const data = await fetch(`${_apiBase()}/modeler/tables/${this._tableId}/column-panel`).then(r => r.json());
            if (data.error) {
                const msg = `<div class="tbp-no-data">Fehler: ${_esc(data.error)}</div>`;
                dbcEl.innerHTML = msg; metaEl.innerHTML = msg;
                return;
            }
            this._renderDbc(data, dbcEl);
            this._renderMeta(data, metaEl);
        } catch (e) {
            dbcEl.innerHTML = `<div class="tbp-no-data">Netzwerkfehler: ${_esc(e.message)}</div>`;
        }
    }

    _renderDbc(data, el) {
        if (!data.dbc_cols?.length) {
            el.innerHTML = `<div class="tbp-no-data">${data.dbc_error ? 'DBC: ' + _esc(data.dbc_error) : 'Keine DBC-Daten'}</div>`;
            return;
        }
        el.innerHTML = `<table class="tbp-table"><thead><tr>
            <th class="tbp-cb">PK</th><th class="tbp-cb">FK</th><th class="tbp-cb">BKey</th>
            <th class="tbp-cb">PI</th><th class="tbp-cb">Hash</th><th class="tbp-cb">Null</th>
            <th class="tbp-cb">CS</th><th>Attribut</th><th>Datentyp</th><th>Charset</th>
            <th>Kommentar</th>
            <th class="tbp-zusatz">Business Name</th><th class="tbp-zusatz">Masking</th><th class="tbp-zusatz tbp-cb">PII</th>
            </tr></thead><tbody>${
            data.dbc_cols.map(c => `<tr>
                <td class="tbp-cb">${_flag(c._pk)}</td>
                <td class="tbp-cb">${_flag(c._fk)}</td>
                <td class="tbp-cb">–</td>
                <td class="tbp-cb">${_flag(c._pi)}</td>
                <td class="tbp-cb">–</td>
                <td class="tbp-cb">${_flag(c.nullable)}</td>
                <td class="tbp-cb">–</td>
                <td>${_esc(c.column_name||'')}</td>
                <td>${_fmtType(c.column_type,c.column_length,c.decimal_precision,c.decimal_scale)}</td>
                <td>${_esc(c.charset||'–')}</td>
                <td>–</td>
                <td class="tbp-zusatz">–</td><td class="tbp-zusatz">–</td><td class="tbp-zusatz tbp-cb">–</td>
            </tr>`).join('')
        }</tbody></table>`;
    }

    _renderMeta(data, el) {
        if (!data.meta_cols?.length) {
            el.innerHTML = '<div class="tbp-no-data">Keine META-Spalten</div>';
            return;
        }
        const cb  = (cid, field, val) =>
            `<input type="checkbox" class="tbp-edit" data-cid="${cid}" data-field="${field}" ${String(val||'').trim()==='Y'?'checked':''}>`;
        const txt = (cid, field, val, w) =>
            `<input type="text" class="tbp-edit tbp-txt" data-cid="${cid}" data-field="${field}"
             value="${_esc(val||'')}" style="width:${w||80}px">`;
        const sel = (cid, field, val, opts) =>
            `<select class="tbp-edit" data-cid="${cid}" data-field="${field}">${
                opts.map(o => `<option value="${o}" ${(val||'')===(o||'')?'selected':''}>${o||'–'}</option>`).join('')
            }</select>`;
        el.innerHTML = `<table class="tbp-table"><thead><tr>
            <th class="tbp-cb">PK</th><th class="tbp-cb">FK</th><th class="tbp-cb">BKey</th>
            <th class="tbp-cb">PI</th><th class="tbp-cb">Hash</th><th class="tbp-cb">Null</th>
            <th class="tbp-cb">CS</th><th>Attribut</th><th>Datentyp</th><th>Charset</th>
            <th>Kommentar</th>
            <th class="tbp-zusatz">Business Name</th><th class="tbp-zusatz">Masking</th><th class="tbp-zusatz tbp-cb">PII</th>
            </tr></thead><tbody>${
            data.meta_cols.map(c => {
                const cid = c.column_id;
                return `<tr>
                    <td class="tbp-cb">${cb(cid,'is_pk',    c.is_pk)}</td>
                    <td class="tbp-cb">${cb(cid,'is_fk',    c.is_fk)}</td>
                    <td class="tbp-cb">${cb(cid,'is_business_key', c.bk_flag)}</td>
                    <td class="tbp-cb">${cb(cid,'is_pi',    c.is_pi)}</td>
                    <td class="tbp-cb">${cb(cid,'is_hash',  c.is_hash)}</td>
                    <td class="tbp-cb">${cb(cid,'nullable', c.nullable||'Y')}</td>
                    <td class="tbp-cb">${cb(cid,'is_casespecific', c.is_casespecific)}</td>
                    <td>${_esc(c.column_name||'')}</td>
                    <td>${_fmtType(c.data_type,c.data_length,c.decimal_precision,c.decimal_scale)}</td>
                    <td>${sel(cid,'charset',(c.charset||'').trim(),['','UNICODE','LATIN'])}</td>
                    <td>${txt(cid,'comment',c.column_desc,120)}</td>
                    <td class="tbp-zusatz">${txt(cid,'business_name',c.business_name,100)}</td>
                    <td class="tbp-zusatz">${txt(cid,'masking_rule',c.masking_rule,100)}</td>
                    <td class="tbp-zusatz tbp-cb">${cb(cid,'is_pii',c.pii_flag)}</td>
                </tr>`;
            }).join('')
        }</tbody></table>`;
    }

    // ── META speichern ────────────────────────────────────────────────

    async _saveMeta() {
        const btn = this._q('.tbp-meta-save');
        btn.textContent = '⏳'; btn.disabled = true;
        const updates = {};
        this._el.querySelectorAll('.tbp-meta-content .tbp-edit').forEach(el => {
            const cid   = parseInt(el.dataset.cid);
            const field = el.dataset.field;
            if (!updates[cid]) updates[cid] = {};
            updates[cid][field] = el.type === 'checkbox' ? (el.checked ? 'Y' : 'N') : (el.value.trim() || null);
        });
        const saves = Object.entries(updates).map(([cid, f]) =>
            window.api.modeler.columns.update(cid, {
                is_pk: f.is_pk, is_fk: f.is_fk, bk_flag: f.is_business_key,
                is_pi: f.is_pi, is_hash: f.is_hash, nullable: f.nullable,
                is_casespecific: f.is_casespecific, charset: f.charset || null,
                comment: f.comment || null, business_name: f.business_name || null,
                masking_rule: f.masking_rule || null, is_pii: f.is_pii,
            })
        );
        try {
            await Promise.all(saves);
            btn.textContent = '✅ Gespeichert';
        } catch (e) {
            btn.textContent = '❌ Fehler';
        }
        setTimeout(() => { btn.textContent = '💾 Speichern'; btn.disabled = false; }, 2000);
    }

    // ── DDL ───────────────────────────────────────────────────────────

    async _ddlGenerate() {
        if (!this._tableId) return;
        const btn    = this._q('.tbp-ddl-gen');
        const status = this._q('.tbp-ddl-status');
        btn.disabled = true; status.textContent = 'Generiere…'; status.className = 'tbp-status-msg';
        try {
            const r = await fetch(`${_apiBase()}/modeler/tables/${this._tableId}/ddl`).then(r => r.json());
            if (r.error) {
                status.textContent = '❌ ' + r.error; status.className = 'tbp-status-msg err';
            } else {
                this._q('.tbp-ddl-text').value = r.ddl || '';
                status.textContent = '✓ DDL generiert'; status.className = 'tbp-status-msg ok';
            }
        } catch (e) {
            status.textContent = '❌ ' + e.message; status.className = 'tbp-status-msg err';
        }
        btn.disabled = false;
        setTimeout(() => { status.textContent = ''; status.className = 'tbp-status-msg'; }, 4000);
    }

    async _ddlExecute() {
        const ddl = (this._q('.tbp-ddl-text').value || '').trim();
        if (!ddl) { alert('DDL-Text ist leer.'); return; }
        if (!confirm('DDL wirklich gegen Teradata ausführen?\n\n' + ddl.slice(0, 200) + (ddl.length > 200 ? '…' : ''))) return;
        const btn    = this._q('.tbp-ddl-exec');
        const status = this._q('.tbp-ddl-status');
        btn.disabled = true; status.textContent = 'Ausführen…'; status.className = 'tbp-status-msg';
        try {
            const r = await fetch(`${_apiBase()}/modeler/tables/${this._tableId}/ddl/execute`, {
                method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ ddl })
            }).then(r => r.json());
            if (r.error) {
                status.textContent = '❌ ' + r.error; status.className = 'tbp-status-msg err';
            } else {
                status.textContent = '✅ ' + (r.message||'Ausgeführt'); status.className = 'tbp-status-msg ok';
            }
        } catch (e) {
            status.textContent = '❌ ' + e.message; status.className = 'tbp-status-msg err';
        }
        btn.disabled = false;
    }

    // ── Statistiken ───────────────────────────────────────────────────

    async _statsLoad() {
        if (!this._tableId) return;
        const btn    = this._q('.tbp-stats-load');
        const result = this._q('.tbp-stats-result');
        btn.disabled = true; result.textContent = 'Lade…'; result.className = 'tbp-status-msg';
        try {
            const r = await fetch(`${_apiBase()}/modeler/tables/${this._tableId}/stats`).then(r => r.json());
            if (r.error) {
                result.textContent = '❌ ' + r.error; result.className = 'tbp-status-msg err';
            } else {
                const mb = r.perm_bytes != null ? (r.perm_bytes/1024/1024).toFixed(2) + ' MB' : 'n/a';
                result.textContent = `Zeilen: ${r.row_count??'n/a'} | Größe: ${mb}`;
                result.className = 'tbp-status-msg ok';
            }
        } catch (e) {
            result.textContent = '❌ ' + e.message; result.className = 'tbp-status-msg err';
        }
        btn.disabled = false;
    }

    // ── Wartung ───────────────────────────────────────────────────────

    _maintConfirm(action) {
        if (!this._tableId) return;
        const labels = {
            'delete-meta': 'Tabelle aus META löschen (nicht rückgängig)?',
            'truncate':    'Alle Zeilen der Tabelle löschen (DELETE ALL)?',
            'drop':        '⚠ DROP TABLE in Teradata? Dies ist IRREVERSIBEL!',
        };
        this._pendingAction = action;
        const row   = this._domConfirmRow   || this._q('.tbp-confirm-row');
        const label = this._domConfirmLabel || this._q('.tbp-confirm-label');
        const res   = this._domMaintResult  || this._q('.tbp-maint-result');
        if (!row || !label) { console.error('[TBP] confirm DOM missing'); return; }
        if (res) res.textContent = '';
        label.textContent = labels[action] || 'Aktion ausführen?';
        row.style.display = 'flex';
        row.style.gap = '8px';
        row.style.alignItems = 'center';
        row.style.marginTop = '8px';
    }

    _maintCancelConfirm() {
        this._pendingAction = null;
        const row = this._domConfirmRow || this._q('.tbp-confirm-row');
        if (row) row.style.display = 'none';
    }

    async _maintExecute() {
        const action = this._pendingAction;
        if (!action || !this._tableId) return;
        const row    = this._domConfirmRow  || this._q('.tbp-confirm-row');
        const result = this._domMaintResult || this._q('.tbp-maint-result');
        if (row)    row.style.display = 'none';
        this._pendingAction = null;
        if (!result) { console.error('[TBP] maint-result DOM missing'); return; }
        const endpoints = {
            'delete-meta': { method: 'DELETE', url: `/modeler/tables/${this._tableId}/meta` },
            'truncate':    { method: 'POST',   url: `/modeler/tables/${this._tableId}/truncate` },
            'drop':        { method: 'POST',   url: `/modeler/tables/${this._tableId}/drop` },
        };
        const ep     = endpoints[action];
        result.textContent = 'Ausführen…'; result.className = 'tbp-status-msg';
        try {
            const r = await fetch(_apiBase() + ep.url, { method: ep.method }).then(r => r.json());
            if (r.error) {
                result.textContent = '❌ ' + r.error; result.className = 'tbp-status-msg err';
            } else {
                result.textContent = '✅ ' + (r.message||'Erledigt'); result.className = 'tbp-status-msg ok';
                if (action === 'delete-meta') {
                    this._el.dispatchEvent(new CustomEvent('tbp:tableDeleted', {
                        bubbles: true,
                        detail: { table_id: this._tableId }
                    }));
                    setTimeout(() => this.hide(), 1500);
                }
            }
        } catch (e) {
            result.textContent = '❌ ' + e.message; result.className = 'tbp-status-msg err';
        }
    }
}

window.TableBottomPanel = TableBottomPanel;
})();
