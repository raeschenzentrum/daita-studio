/**
 * daita-studio – Tabellen-Editor Komponente (C3)
 *
 * Kapselt den vollständigen Properties-Panel aus daita-modeler:
 * Tabs: Tabelle | Spalten | Indizes | Rev-Eng
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   <script src="/components/table-editor.js"></script>
 *
 *   <!-- Als Custom Element: -->
 *   <studio-table-editor></studio-table-editor>
 *   <script>
 *     document.querySelector('studio-table-editor').load({ table_id: 42, table_name: 'FOO', db_name: 'MDP01_RAW' });
 *   </script>
 *
 *   <!-- Oder per JS-Instanz (für Properties-Panel): -->
 *   const editor = new TableEditor(containerEl);
 *   editor.load(tableObject);
 *
 * Custom Events (gefeuert auf document):
 *   studio:table-updated  { detail: { table_id, field, value } }
 *   studio:column-updated { detail: { column_id, table_id, payload } }
 *   studio:indexes-saved  { detail: { table_id } }
 *   studio:dbc-synced     { detail: { table_id, updated } }
 *
 * Abhängigkeiten: api.js (window.api)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Styles
    // ----------------------------------------------------------------
    const STYLE = `
        .te-root { font-size: 0.88em; height: 100%; display: flex; flex-direction: column; }

        /* Header */
        .te-header { padding: 10px 14px 8px; border-bottom: 1px solid var(--border-color, #e0e0e0); }
        .te-title { font-weight: 700; font-size: 1.05em; color: var(--text-primary, #333); }
        .te-db-badge {
            display: inline-block; font-size: 0.78em; padding: 1px 7px;
            background: var(--primary-color, #667eea); color: #fff;
            border-radius: 10px; margin-left: 6px; vertical-align: middle;
        }

        /* Tabs */
        .te-tabs { display: flex; gap: 2px; padding: 6px 10px 0; border-bottom: 1px solid var(--border-color, #e0e0e0); }
        .te-tab {
            background: none; border: none; padding: 6px 12px; cursor: pointer;
            border-bottom: 2px solid transparent; color: var(--text-secondary, #666);
            font-size: 0.88em; transition: color 0.15s;
        }
        .te-tab:hover { color: var(--primary-color, #667eea); }
        .te-tab.active { color: var(--primary-color, #667eea); border-bottom-color: var(--primary-color, #667eea); font-weight: 600; }

        /* Body */
        .te-body { flex: 1; overflow-y: auto; padding: 12px 14px; }

        /* Forms */
        .te-form-label { display: block; font-size: 0.82em; font-weight: 600; color: var(--text-secondary, #666); margin: 8px 0 2px; }
        .te-form-input {
            width: 100%; padding: 5px 8px; border: 1px solid var(--border-color, #e0e0e0);
            border-radius: 4px; font-size: 0.9em; background: #fff;
        }
        .te-form-input:focus { outline: none; border-color: var(--primary-color, #667eea); }
        .te-form-save { margin-top: 14px; width: 100%; padding: 7px; }

        /* Buttons */
        .te-btn {
            padding: 5px 12px; border-radius: 5px; border: none; cursor: pointer;
            font-size: 0.88em; transition: opacity 0.15s;
        }
        .te-btn:hover { opacity: 0.85; }
        .te-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .te-btn-primary { background: var(--primary-color, #667eea); color: #fff; }
        .te-btn-secondary { background: var(--border-color, #e0e0e0); color: var(--text-primary, #333); }
        .te-btn-danger { background: var(--danger-color, #f44336); color: #fff; }

        /* Spalten-Tabelle */
        .te-col-hint { font-size: 0.8em; color: var(--text-secondary, #666); margin-bottom: 6px; }
        .te-col-wrap { overflow-x: auto; }
        .te-col-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
        .te-col-table th { background: #f5f5f5; padding: 4px 6px; text-align: left; font-weight: 600; position: sticky; top: 0; }
        .te-col-table td { padding: 3px 6px; border-bottom: 1px solid #f0f0f0; }
        .te-col-table tr:hover { background: #fafafa; }
        .te-col-table tr.editing { background: #fff9e6; }
        .te-col-edit-row td { padding: 0; }
        .te-col-edit-form { padding: 8px 10px; background: #fffde7; border-top: 2px solid var(--warning-color, #ff9800); }
        .te-col-edit-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 6px; }
        .te-col-edit-grid label { display: flex; flex-direction: column; font-size: 0.82em; font-weight: 600; gap: 2px; }
        .te-col-edit-grid input[type="text"],
        .te-col-edit-grid input[type="number"] { padding: 3px 5px; border: 1px solid var(--border-color, #e0e0e0); border-radius: 3px; width: 100%; }
        .te-col-edit-actions { display: flex; gap: 6px; margin-top: 4px; }
        .te-col-edit-actions button { flex: 1; }

        /* Index-Editor */
        .te-idx-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
        .te-idx-item { border: 1px solid var(--border-color, #e0e0e0); border-radius: 6px; padding: 8px 10px; }
        .te-idx-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .te-idx-badge {
            font-size: 0.75em; font-weight: 700; padding: 2px 8px;
            background: var(--info-color, #9575cd); color: #fff; border-radius: 10px;
        }
        .te-idx-type-sel { flex: 1; padding: 3px 5px; font-size: 0.85em; border: 1px solid var(--border-color, #e0e0e0); border-radius: 4px; }
        .te-idx-col-sel { width: 100%; min-height: 60px; border: 1px solid var(--border-color, #e0e0e0); border-radius: 4px; font-size: 0.85em; }
        .te-idx-actions { display: flex; gap: 8px; }

        /* Rev-Eng */
        .te-rev-table { width: 100%; border-collapse: collapse; font-size: 0.85em; margin-top: 8px; }
        .te-rev-table th { background: #f5f5f5; padding: 4px 6px; text-align: left; }
        .te-rev-table td { padding: 3px 6px; border-bottom: 1px solid #f0f0f0; }
        .te-rev-ok     { color: var(--success-color, #4caf50); }
        .te-rev-diff   { color: var(--warning-color, #ff9800); }
        .te-rev-new    { color: var(--info-color, #9575cd); }
        .te-rev-only   { color: var(--danger-color, #f44336); }

        /* Placeholder */
        .te-placeholder { text-align: center; padding: 20px; color: var(--text-secondary, #666); font-size: 0.9em; }
    `;

    function injectStyles() {
        if (document.getElementById('studio-table-editor-style')) return;
        const s = document.createElement('style');
        s.id = 'studio-table-editor-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    // ----------------------------------------------------------------
    // Kern-Klasse TableEditor
    // ----------------------------------------------------------------

    class TableEditor {
        /**
         * @param {HTMLElement} container – Ziel-DOM-Element
         */
        constructor(container) {
            injectStyles();
            this._el = container;
            this._table = null;
            this._el.innerHTML = `<div class="te-root"><div class="te-placeholder">Keine Tabelle ausgewählt.</div></div>`;
        }

        /** Lädt eine Tabelle in den Editor. */
        load(tableObj) {
            this._table = tableObj;
            this._render();
        }

        /** Entlädt / leert den Editor. */
        clear() {
            this._table = null;
            this._el.innerHTML = `<div class="te-root"><div class="te-placeholder">Keine Tabelle ausgewählt.</div></div>`;
        }

        // ---- Render-Grundstruktur ----

        _render() {
            const t = this._table;
            this._el.innerHTML = `
                <div class="te-root">
                    <div class="te-header">
                        <span class="te-title">${t.table_name}</span>
                        <span class="te-db-badge">${t.db_name || ''}</span>
                    </div>
                    <div class="te-tabs">
                        <button class="te-tab active" data-tab="tab-table">⚙ Tabelle</button>
                        <button class="te-tab"        data-tab="tab-cols">⬤ Spalten</button>
                        <button class="te-tab"        data-tab="tab-idx">🗂 Indizes</button>
                        <button class="te-tab"        data-tab="tab-rev">↕ Rev-Eng</button>
                    </div>
                    <div class="te-body">
                        <div id="te-panel-tab-table"></div>
                        <div id="te-panel-tab-cols"  style="display:none"></div>
                        <div id="te-panel-tab-idx"   style="display:none"></div>
                        <div id="te-panel-tab-rev"   style="display:none"></div>
                    </div>
                </div>`;

            // Tab-Switching
            this._el.querySelectorAll('.te-tab').forEach(btn => {
                btn.addEventListener('click', () => {
                    this._el.querySelectorAll('.te-tab').forEach(b => b.classList.remove('active'));
                    this._el.querySelectorAll('[id^="te-panel-"]').forEach(p => p.style.display = 'none');
                    btn.classList.add('active');
                    const panel = this._el.querySelector(`#te-panel-${btn.dataset.tab}`);
                    panel.style.display = '';
                    if (!panel.dataset.loaded) this._loadTab(btn.dataset.tab, panel);
                });
            });

            // Ersten Tab direkt laden
            this._loadTab('tab-table', this._el.querySelector('#te-panel-tab-table'));
        }

        _loadTab(tabId, panel) {
            panel.dataset.loaded = '1';
            if      (tabId === 'tab-table') this._renderTableTab(panel);
            else if (tabId === 'tab-cols')  this._renderColsTab(panel);
            else if (tabId === 'tab-idx')   this._renderIdxTab(panel);
            else if (tabId === 'tab-rev')   this._renderRevTab(panel);
        }

        // ---- Tab: Tabelle ----

        async _renderTableTab(panel) {
            const t = this._table;
            panel.innerHTML = `<div class="te-placeholder">Lade…</div>`;
            const detail = await window.api.modeler.tables.get(t.table_id).catch(() => ({}));

            panel.innerHTML = `
                <label class="te-form-label">Kommentar</label>
                <textarea id="te-comment" class="te-form-input" rows="3">${detail.table_desc || ''}</textarea>

                <label class="te-form-label">Historisiert</label>
                <select id="te-historized" class="te-form-input">
                    <option value="N" ${(detail.is_historized||'N').trim()==='N'?'selected':''}>Nein</option>
                    <option value="Y" ${(detail.is_historized||'').trim()==='Y'?'selected':''}>Ja</option>
                </select>

                <label class="te-form-label">Historisierungstyp</label>
                <select id="te-hist-type" class="te-form-input">
                    <option value="">—</option>
                    <option value="SCD1" ${detail.historization_type==='SCD1'?'selected':''}>SCD1</option>
                    <option value="SCD2" ${detail.historization_type==='SCD2'?'selected':''}>SCD2</option>
                    <option value="FULL" ${detail.historization_type==='FULL'?'selected':''}>FULL</option>
                </select>

                <label class="te-form-label">Valid-From Spalte</label>
                <input id="te-valid-from" class="te-form-input" type="text" value="${detail.valid_from_column || ''}">

                <label class="te-form-label">Valid-To Spalte</label>
                <input id="te-valid-to" class="te-form-input" type="text" value="${detail.valid_to_column || ''}">

                <label class="te-form-label">Is-Current Spalte</label>
                <input id="te-is-current" class="te-form-input" type="text" value="${detail.is_current_column || ''}">

                <button id="te-table-save" class="te-btn te-btn-primary te-form-save">💾 Speichern</button>`;

            panel.querySelector('#te-table-save').addEventListener('click', async () => {
                const btn = panel.querySelector('#te-table-save');
                btn.disabled = true;
                const payload = {
                    comment:            panel.querySelector('#te-comment').value.trim() || null,
                    is_historized:      panel.querySelector('#te-historized').value,
                    historization_type: panel.querySelector('#te-hist-type').value || null,
                    valid_from_column:  panel.querySelector('#te-valid-from').value.trim() || null,
                    valid_to_column:    panel.querySelector('#te-valid-to').value.trim() || null,
                    is_current_column:  panel.querySelector('#te-is-current').value.trim() || null,
                };
                const resp = await window.api.modeler.tables.update(t.table_id, payload).catch(e => ({ error: e.message }));
                btn.disabled = false;
                btn.textContent = resp?.error ? '❌ Fehler' : '✅ Gespeichert';
                setTimeout(() => { btn.textContent = '💾 Speichern'; }, 2000);
                if (!resp?.error) {
                    document.dispatchEvent(new CustomEvent('studio:table-updated', {
                        detail: { table_id: t.table_id, payload }
                    }));
                }
            });
        }

        // ---- Tab: Spalten ----

        async _renderColsTab(panel) {
            const t = this._table;
            panel.innerHTML = `<div class="te-placeholder">Lade Spalten…</div>`;
            const cols = await window.api.modeler.tables.columnsFull(t.table_id).catch(() => []);

            if (!cols.length || cols[0]?.error) {
                panel.innerHTML = `<div class="te-placeholder">${cols[0]?.error || 'Keine Spalten gefunden'}</div>`;
                return;
            }

            panel.innerHTML = `
                <div class="te-col-hint">Doppelklick zum Bearbeiten</div>
                <div class="te-col-wrap">
                    <table class="te-col-table">
                        <thead><tr>
                            <th title="Primary Key">PK</th>
                            <th title="Business Key">BK</th>
                            <th>Spaltenname</th>
                            <th>Typ</th>
                            <th title="Länge">Len</th>
                            <th title="Scale">Sc</th>
                            <th title="Nullable">N</th>
                        </tr></thead>
                        <tbody id="te-col-body"></tbody>
                    </table>
                </div>`;

            const tbody = panel.querySelector('#te-col-body');
            cols.forEach(c => this._appendColRow(c, tbody, t.table_id));
        }

        _appendColRow(c, tbody, tableId) {
            const tr = document.createElement('tr');
            tr.dataset.colId = c.column_id;
            tr.innerHTML = `
                <td class="te-col-chk">${(c.pk_flag||'N').trim()==='Y'?'🔑':''}</td>
                <td class="te-col-chk">${(c.bk_flag||'N').trim()==='Y'?'🏷':''}</td>
                <td>${c.column_name}</td>
                <td>${c.data_type||''}</td>
                <td>${c.data_length != null ? c.data_length : ''}</td>
                <td>${c.decimal_scale != null ? c.decimal_scale : ''}</td>
                <td>${(c.nullable||'Y').trim()==='N'?'NN':'Y'}</td>`;
            tr.addEventListener('dblclick', () => this._openColEdit(tr, c, tbody, tableId));
            tbody.appendChild(tr);
        }

        _openColEdit(tr, c, tbody, tableId) {
            // Bereits offene Edit-Rows schliessen
            tbody.querySelectorAll('.te-col-edit-row').forEach(r => r.remove());
            tbody.querySelectorAll('tr.editing').forEach(r => r.classList.remove('editing'));

            // Toggle: nochmals klicken schließt
            if (tr.dataset.editing === '1') { delete tr.dataset.editing; return; }
            tr.dataset.editing = '1';
            tr.classList.add('editing');

            const editTr = document.createElement('tr');
            editTr.className = 'te-col-edit-row';
            editTr.innerHTML = `
                <td colspan="7">
                    <div class="te-col-edit-form">
                        <div class="te-col-edit-grid">
                            <label>PK<input type="checkbox" id="ce-pk" ${(c.pk_flag||'N').trim()==='Y'?'checked':''}></label>
                            <label>BK<input type="checkbox" id="ce-bk" ${(c.bk_flag||'N').trim()==='Y'?'checked':''}></label>
                            <label>Audit<input type="checkbox" id="ce-audit" ${(c.audit_flag||'N').trim()==='Y'?'checked':''}></label>
                            <label>Nullable<input type="checkbox" id="ce-null" ${(c.nullable||'Y').trim()!=='N'?'checked':''}></label>
                        </div>
                        <div class="te-col-edit-grid">
                            <label>Typ<input type="text" id="ce-type" value="${c.data_type||''}"></label>
                            <label>Länge<input type="number" id="ce-len" value="${c.data_length||''}" min="0"></label>
                            <label>Prec<input type="number" id="ce-prec" value="${c.decimal_precision||''}" min="0"></label>
                            <label>Scale<input type="number" id="ce-scale" value="${c.decimal_scale||''}" min="0"></label>
                        </div>
                        <label style="display:block;margin-top:4px;font-size:0.82em;font-weight:600">
                            Kommentar
                            <input type="text" id="ce-comment" value="${(c.column_desc||'').replace(/"/g,'&quot;')}" class="te-form-input" style="margin-top:2px">
                        </label>
                        <div class="te-col-edit-actions">
                            <button class="te-btn te-btn-primary ce-save">💾 Speichern</button>
                            <button class="te-btn te-btn-secondary ce-cancel">✕</button>
                        </div>
                    </div>
                </td>`;
            tr.after(editTr);

            editTr.querySelector('.ce-cancel').addEventListener('click', () => {
                editTr.remove();
                tr.classList.remove('editing');
                delete tr.dataset.editing;
            });

            editTr.querySelector('.ce-save').addEventListener('click', async (evt) => {
                const btn = evt.currentTarget;
                btn.disabled = true;
                const payload = {
                    data_type:         editTr.querySelector('#ce-type').value.trim() || null,
                    data_length:       parseInt(editTr.querySelector('#ce-len').value) || null,
                    decimal_precision: parseInt(editTr.querySelector('#ce-prec').value) || null,
                    decimal_scale:     parseInt(editTr.querySelector('#ce-scale').value) || null,
                    nullable:          editTr.querySelector('#ce-null').checked  ? 'Y' : 'N',
                    pk_flag:           editTr.querySelector('#ce-pk').checked    ? 'Y' : 'N',
                    bk_flag:           editTr.querySelector('#ce-bk').checked    ? 'Y' : 'N',
                    audit_flag:        editTr.querySelector('#ce-audit').checked ? 'Y' : 'N',
                    comment:           editTr.querySelector('#ce-comment').value.trim() || null,
                };
                const resp = await window.api.modeler.columns.update(c.column_id, payload).catch(e => ({ error: e.message }));
                btn.disabled = false;
                if (resp?.error) {
                    btn.textContent = '❌';
                    setTimeout(() => { btn.textContent = '💾 Speichern'; }, 2000);
                } else {
                    // Angezeigte Zeile aktualisieren
                    tr.cells[0].textContent = payload.pk_flag === 'Y' ? '🔑' : '';
                    tr.cells[1].textContent = payload.bk_flag === 'Y' ? '🏷' : '';
                    tr.cells[3].textContent = payload.data_type || '';
                    tr.cells[4].textContent = payload.data_length != null ? payload.data_length : '';
                    tr.cells[5].textContent = payload.decimal_scale != null ? payload.decimal_scale : '';
                    tr.cells[6].textContent = payload.nullable === 'N' ? 'NN' : 'Y';
                    editTr.remove();
                    tr.classList.remove('editing');
                    delete tr.dataset.editing;
                    document.dispatchEvent(new CustomEvent('studio:column-updated', {
                        detail: { column_id: c.column_id, table_id: tableId, payload }
                    }));
                }
            });
        }

        // ---- Tab: Indizes ----

        async _renderIdxTab(panel) {
            const t = this._table;
            panel.innerHTML = `<div class="te-placeholder">Lade Indizes…</div>`;

            const [indexes, allCols] = await Promise.all([
                window.api.modeler.tables.indexes(t.table_id).catch(() => []),
                window.api.modeler.tables.columnsFull(t.table_id).catch(() => []),
            ]);

            const colOpts = (Array.isArray(allCols) ? allCols : [])
                .filter(c => !c.error)
                .map(c => `<option value="${c.column_id}">${c.column_name}</option>`)
                .join('');

            let _state = (Array.isArray(indexes) && !indexes.error ? indexes : [])
                .map(ix => ({ ...ix }));

            const render = () => {
                const list = panel.querySelector('#te-idx-list');
                if (!list) return;
                list.innerHTML = '';
                if (!_state.length) {
                    list.innerHTML = `<div class="te-placeholder">Keine Indizes definiert</div>`;
                }
                const TYPE_SHORT = {
                    'PRIMARY INDEX': 'PI', 'UNIQUE PRIMARY INDEX': 'UPI',
                    'SECONDARY INDEX': 'SI', 'UNIQUE SECONDARY INDEX': 'USI',
                };
                _state.forEach((ix, i) => {
                    const div = document.createElement('div');
                    div.className = 'te-idx-item';
                    div.innerHTML = `
                        <div class="te-idx-header">
                            <span class="te-idx-badge">${TYPE_SHORT[ix.index_type] || ix.index_type}</span>
                            <select class="te-idx-type-sel">
                                ${['PRIMARY INDEX','UNIQUE PRIMARY INDEX','SECONDARY INDEX','UNIQUE SECONDARY INDEX']
                                    .map(tp => `<option value="${tp}" ${ix.index_type===tp?'selected':''}>${tp}</option>`).join('')}
                            </select>
                            <button class="te-btn te-btn-danger idx-del" title="Entfernen">✕</button>
                        </div>
                        <select class="te-idx-col-sel" multiple size="4">${colOpts}</select>`;

                    const sel = div.querySelector('.te-idx-col-sel');
                    const selIds = new Set((ix.columns||[]).map(c => String(c.column_id)));
                    Array.from(sel.options).forEach(o => { if (selIds.has(o.value)) o.selected = true; });

                    div.querySelector('.te-idx-type-sel').addEventListener('change', e => { _state[i].index_type = e.target.value; });
                    sel.addEventListener('change', () => {
                        _state[i].columns = Array.from(sel.selectedOptions).map((o, pos) => ({
                            column_id: parseInt(o.value), column_position: pos + 1,
                        }));
                    });
                    div.querySelector('.idx-del').addEventListener('click', () => { _state.splice(i, 1); render(); });
                    list.appendChild(div);
                });
            };

            panel.innerHTML = `
                <div id="te-idx-list" class="te-idx-list"></div>
                <div class="te-idx-actions">
                    <button id="te-idx-add"    class="te-btn te-btn-secondary">＋ Hinzufügen</button>
                    <button id="te-idx-save"   class="te-btn te-btn-primary">💾 Speichern</button>
                    <button id="te-idx-reimport" class="te-btn te-btn-secondary" title="PI aus DBC.IndicesV">🔄 PI aus DBC</button>
                </div>`;
            render();

            panel.querySelector('#te-idx-add').addEventListener('click', () => {
                _state.push({ index_type: 'PRIMARY INDEX', is_unique: 'N', columns: [] });
                render();
            });

            panel.querySelector('#te-idx-save').addEventListener('click', async () => {
                const btn = panel.querySelector('#te-idx-save');
                btn.disabled = true;
                const payload = _state.map(ix => ({
                    index_type: ix.index_type, is_unique: ix.is_unique || 'N', columns: ix.columns || [],
                }));
                const resp = await window.api.modeler.tables.saveIndexes(t.table_id, payload).catch(e => ({ error: e.message }));
                btn.disabled = false;
                btn.textContent = resp?.error ? '❌ Fehler' : '✅ Gespeichert';
                setTimeout(() => { btn.textContent = '💾 Speichern'; }, 2000);
                if (!resp?.error) {
                    document.dispatchEvent(new CustomEvent('studio:indexes-saved', { detail: { table_id: t.table_id } }));
                }
            });

            panel.querySelector('#te-idx-reimport').addEventListener('click', async () => {
                if (!t.db_name || !t.table_name) {
                    alert('db_name oder table_name fehlt – Tabelle nicht in META_DATABASE?');
                    return;
                }
                const btn = panel.querySelector('#te-idx-reimport');
                btn.disabled = true;
                btn.textContent = '⏳…';
                // Nutzt direkt modeler syncDbc (POST /modeler/tables/{id}/sync-from-dbc)
                const resp = await window.api.modeler.tables.syncDbc(t.table_id).catch(e => ({ error: e.message }));
                btn.disabled = false;
                if (resp?.error) {
                    btn.textContent = '❌ Fehler';
                    alert('Fehler beim Index-Nachimport:\n' + resp.error);
                } else {
                    btn.textContent = '✅ Fertig';
                    // Index-Tab neu laden
                    delete panel.dataset.loaded;
                    await this._renderIdxTab(panel);
                }
                setTimeout(() => { btn.textContent = '🔄 PI aus DBC'; }, 3000);
            });
        }

        // ---- Tab: Reverse Engineering ----

        _renderRevTab(panel) {
            const t = this._table;
            panel.innerHTML = `
                <label class="te-form-label">DB-Schema (Teradata)</label>
                <input id="te-rev-db"    class="te-form-input" type="text" value="${t.db_name || ''}" placeholder="z.B. MDP01_RAW_LAYER">
                <label class="te-form-label">Tabellenname</label>
                <input id="te-rev-table" class="te-form-input" type="text" value="${t.table_name || ''}">
                <button id="te-rev-start" class="te-btn te-btn-primary te-form-save">🔍 Abgleich starten</button>
                <div id="te-rev-result" style="margin-top:8px"></div>`;

            panel.querySelector('#te-rev-start').addEventListener('click', async () => {
                const btn    = panel.querySelector('#te-rev-start');
                const dbName = panel.querySelector('#te-rev-db').value.trim();
                const tName  = panel.querySelector('#te-rev-table').value.trim();
                const result = panel.querySelector('#te-rev-result');
                if (!dbName || !tName) return;
                btn.disabled = true;
                result.innerHTML = `<div class="te-placeholder">Lade…</div>`;

                const diff = await window.api.modeler.tables.reverseEng(t.table_id).catch(e => ({ error: e.message }));
                btn.disabled = false;

                if (diff?.error) {
                    result.innerHTML = `<div class="te-placeholder" style="color:var(--danger-color,#f44336)">${diff.error}</div>`;
                    return;
                }

                const ICON    = { ok: '✅', diff: '⚠️', new_in_db: '🆕', only_in_meta: '🗑' };
                const CSSMAP  = { ok: 'te-rev-ok', diff: 'te-rev-diff', new_in_db: 'te-rev-new', only_in_meta: 'te-rev-only' };
                const rows    = (diff.columns_diff || []).map(c => `
                    <tr class="${CSSMAP[c.status]||''}">
                        <td>${ICON[c.status]||'?'}</td>
                        <td>${c.column_name}</td>
                        <td>${c.label}</td>
                    </tr>`).join('');

                const piDiff  = diff.indexes_diff || {};
                const piStatus = piDiff.status === 'ok'
                    ? '✅ PI stimmt überein'
                    : `⚠️ PI-Diff: DB=[${(piDiff.dbc_pi||[]).join(',')}] META=[${(piDiff.meta_pi||[]).join(',')}]`;

                const hasSync = (diff.columns_diff || []).some(c => c.status === 'diff');
                result.innerHTML = `
                    <div style="font-size:0.85em;margin-bottom:4px">${piStatus}</div>
                    <table class="te-rev-table">
                        <thead><tr><th></th><th>Spalte</th><th>Status</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                    ${hasSync ? `<button id="te-rev-sync" class="te-btn te-btn-primary" style="margin-top:8px;width:100%">⬇ Typ/Länge/Nullable aus DB übernehmen</button>` : ''}`;

                if (hasSync) {
                    result.querySelector('#te-rev-sync').addEventListener('click', async () => {
                        const syncBtn = result.querySelector('#te-rev-sync');
                        syncBtn.disabled = true;
                        const resp = await window.api.modeler.tables.syncDbc(t.table_id).catch(e => ({ error: e.message }));
                        syncBtn.textContent = resp?.error
                            ? `❌ ${resp.error}`
                            : `✅ ${resp.updated || ''} Spalten aktualisiert`;
                        if (!resp?.error) {
                            document.dispatchEvent(new CustomEvent('studio:dbc-synced', {
                                detail: { table_id: t.table_id, updated: resp.updated }
                            }));
                        }
                    });
                }
            });
        }
    }

    // ----------------------------------------------------------------
    // Custom Element <studio-table-editor>
    // ----------------------------------------------------------------

    class StudioTableEditor extends HTMLElement {
        connectedCallback() {
            injectStyles();
            this._editor = new TableEditor(this);
        }

        /** Lädt Tabelle aus JS: el.load(tableObj) */
        load(tableObj) {
            if (!this._editor) this._editor = new TableEditor(this);
            this._editor.load(tableObj);
        }

        clear() {
            if (this._editor) this._editor.clear();
        }
    }

    customElements.define('studio-table-editor', StudioTableEditor);

    // ----------------------------------------------------------------
    // Export als window.TableEditor für nicht-Custom-Element Nutzung
    // ----------------------------------------------------------------
    window.TableEditor = TableEditor;

})();
