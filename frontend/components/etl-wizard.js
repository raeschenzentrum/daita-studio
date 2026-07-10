/**
 * daita-studio – ETL-Wizard Komponente (C6)
 *
 * 3-Schritt-Wizard: ETL-Job + Zieltabelle in einem Schritt anlegen.
 * Dieselbe Komponente in flow.html (Modal) und jobs.html (Inline).
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   <script src="/components/column-selector.js"></script>
 *   <script src="/components/etl-wizard.js"></script>
 *
 *   <!-- Modal per JS: -->
 *   ETLWizard.openModal({ sourceTableId: 5 });
 *
 *   <!-- Inline per JS-Instanz: -->
 *   const wiz = new ETLWizard(containerEl, { sourceTableId: 5 });
 *   wiz.open();
 *
 * Custom Events (gefeuert auf document):
 *   studio:job-created   { detail: { job_id, target_table_id, target_created, job_name, target_table_name } }
 *   studio:wizard-closed { detail: {} }
 *
 * Abhängigkeiten: api.js (C1), column-selector.js (C5)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Styles
    // ----------------------------------------------------------------
    const STYLE = `
        /* Modal-Overlay */
        .ew-overlay {
            position: fixed; inset: 0; z-index: 2000;
            background: rgba(0,0,0,0.45);
            display: flex; align-items: center; justify-content: center;
            padding: 16px;
        }
        .ew-modal {
            background: #fff; border-radius: 12px;
            box-shadow: 0 8px 40px rgba(0,0,0,0.22);
            width: 100%; max-width: 700px; max-height: 90vh;
            display: flex; flex-direction: column; overflow: hidden;
        }

        /* Inline-Modus */
        .ew-inline {
            border: 1px solid #e8e8e8; border-radius: 10px;
            background: #fff; overflow: hidden;
        }

        /* Header */
        .ew-header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff; padding: 14px 20px;
            display: flex; align-items: center; justify-content: space-between;
        }
        .ew-header-title { font-weight: 700; font-size: 1.05em; }
        .ew-header-sub   { font-size: 0.8em; opacity: 0.85; margin-top: 2px; }
        .ew-close-btn    { background: none; border: none; color: #fff; font-size: 1.3em; cursor: pointer; opacity: 0.8; padding: 0 4px; }
        .ew-close-btn:hover { opacity: 1; }

        /* Stepper */
        .ew-stepper {
            display: flex; gap: 0; border-bottom: 1px solid #e8e8e8;
            background: #fafafa;
        }
        .ew-step-indicator {
            flex: 1; padding: 10px 8px; text-align: center;
            font-size: 0.82em; color: #aaa; border-bottom: 3px solid transparent;
            transition: color 0.2s, border-color 0.2s;
            display: flex; align-items: center; justify-content: center; gap: 6px;
        }
        .ew-step-indicator.active { color: #667eea; border-bottom-color: #667eea; font-weight: 700; }
        .ew-step-indicator.done   { color: #4caf50; border-bottom-color: #4caf50; }
        .ew-step-num {
            width: 20px; height: 20px; border-radius: 50%; border: 2px solid currentColor;
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 0.78em; font-weight: 700; flex-shrink: 0;
        }
        .ew-step-indicator.done .ew-step-num { background: #4caf50; color: #fff; border-color: #4caf50; }
        .ew-step-indicator.active .ew-step-num { background: #667eea; color: #fff; border-color: #667eea; }

        /* Body */
        .ew-body { flex: 1; overflow-y: auto; padding: 20px; min-height: 200px; }

        /* Footer */
        .ew-footer {
            padding: 12px 20px; border-top: 1px solid #e8e8e8;
            display: flex; justify-content: space-between; align-items: center;
            background: #fafafa; gap: 8px;
        }
        .ew-footer-left  { display: flex; gap: 8px; }
        .ew-footer-right { display: flex; gap: 8px; }

        /* Buttons */
        .ew-btn {
            padding: 8px 18px; border-radius: 7px; border: none; cursor: pointer;
            font-size: 0.88em; font-weight: 600; transition: opacity 0.15s;
            display: inline-flex; align-items: center; gap: 5px;
        }
        .ew-btn:hover    { opacity: 0.87; }
        .ew-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .ew-btn-primary  { background: linear-gradient(135deg,#667eea,#764ba2); color: #fff; }
        .ew-btn-secondary{ background: #f0f0f0; color: #444; border: 1px solid #ddd; }
        .ew-btn-success  { background: linear-gradient(135deg,#11998e,#38ef7d); color: #fff; }
        .ew-btn-cancel   { background: none; border: none; color: #888; font-size: 0.85em; cursor: pointer; }
        .ew-btn-cancel:hover { color: #333; }

        /* Formular (Step 1) */
        .ew-form-row     { margin-bottom: 14px; }
        .ew-form-label   { display: block; font-size: 0.82em; font-weight: 700; color: #555; margin-bottom: 4px; }
        .ew-form-input   { width: 100%; padding: 7px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 0.9em; box-sizing: border-box; }
        .ew-form-input:focus { outline: none; border-color: #667eea; }
        .ew-form-hint    { font-size: 0.78em; color: #999; margin-top: 3px; }
        .ew-form-select  { appearance: auto; }

        /* Source-Info */
        .ew-source-info {
            background: #f3f4ff; border-left: 3px solid #667eea;
            border-radius: 0 6px 6px 0; padding: 10px 14px; margin-bottom: 16px;
            font-size: 0.85em;
        }
        .ew-source-name { font-weight: 700; color: #3949ab; }
        .ew-source-db   { color: #888; font-size: 0.9em; }

        /* SCD2-Preview (Step 2) */
        .ew-tech-cols {
            background: #f9f5ff; border: 1px dashed #9575cd;
            border-radius: 6px; padding: 10px 14px; margin-top: 14px;
        }
        .ew-tech-cols-title { font-size: 0.8em; font-weight: 700; color: #7b1fa2; margin-bottom: 6px; }
        .ew-tech-col-list   { font-size: 0.8em; color: #666; line-height: 1.8; }
        .ew-tech-col-badge  { display: inline-block; padding: 1px 8px; border-radius: 8px; background: #ede7f6; color: #6a1b9a; font-size: 0.85em; margin: 1px 3px; }
        .ew-tech-col-sk     { background: #f3e5f5; color: #7b1fa2; font-weight: 600; border: 1px solid #ce93d8; }

        /* FK-Block (Step 2) */
        .ew-fk-block        { margin-top: 14px; border: 1px solid #c8e6c9; border-radius: 8px; padding: 12px 14px; background: #f1f8e9; }
        .ew-fk-title        { font-size: 0.85em; font-weight: 700; color: #2e7d32; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
        .ew-fk-hint         { font-weight: 400; color: #555; font-size: 0.9em; }
        .ew-fk-row          { display: flex; align-items: flex-start; gap: 6px; background: #fff; border: 1px solid #dcedc8; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
        .ew-fk-fields       { flex: 1; display: flex; flex-wrap: wrap; gap: 8px; }
        .ew-fk-fields label { font-size: 0.78em; color: #555; display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 160px; }
        .ew-fk-fields input { font-size: 0.85em; padding: 3px 6px; border: 1px solid #a5d6a7; border-radius: 4px; }
        .ew-fk-remove       { background: none; border: none; cursor: pointer; color: #e53935; font-size: 1em; padding: 2px 6px; flex-shrink: 0; margin-top: 18px; }
        .ew-fk-add          { font-size: 0.82em; margin-top: 4px; padding: 4px 10px; }

        /* FK über Master-Tabelle (F6-A) */
        .ew-fkm-add-row     { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
        .ew-fkm-select      { flex: 1; font-size: 0.85em; padding: 4px 8px; border: 1px solid #a5d6a7; border-radius: 4px; background: #fff; }
        .ew-fkm-list        { display: flex; flex-wrap: wrap; gap: 6px; }
        .ew-fkm-row         { display: flex; align-items: center; gap: 4px; background: #fff; border: 1px solid #dcedc8; border-radius: 6px; padding: 4px 8px; }
        .ew-fkm-tag         { font-size: 0.82em; color: #2e7d32; font-weight: 600; }
        .ew-fkm-row .ew-fk-remove { margin-top: 0; }

        /* Zusammenfassung (Step 3) */
        .ew-summary      { display: flex; flex-direction: column; gap: 10px; }
        .ew-summary-item {
            display: flex; align-items: flex-start; gap: 10px;
            background: #f5f5f5; border-radius: 8px; padding: 12px 14px;
        }
        .ew-summary-icon { font-size: 1.2em; flex-shrink: 0; margin-top: 1px; }
        .ew-summary-text { flex: 1; font-size: 0.88em; }
        .ew-summary-title{ font-weight: 700; margin-bottom: 2px; }
        .ew-summary-val  { color: #555; font-family: monospace; }
        .ew-summary-note { color: #f57f17; font-size: 0.82em; margin-top: 4px; }

        /* Preview-Blöcke in Schritt 3 */
        .ew-preview-block { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; padding: 10px 14px; margin-top: 4px; }
        .ew-preview-block-title { font-size: 0.78em; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
        .ew-step-badges { display: flex; flex-wrap: wrap; gap: 4px; }
        .ew-step-badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 10px; font-size: 0.74em; font-weight: 600; background: #e8eaf6; color: #3949ab; }
        .ew-step-badge-num { background: #c5cae9; border-radius: 50%; width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75em; flex-shrink: 0; }
        .ew-params-grid { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 0.78em; }
        .ew-params-key { color: #888; font-family: monospace; white-space: nowrap; padding: 1px 0; }
        .ew-params-val { color: #333; font-family: monospace; word-break: break-all; padding: 1px 0; }
        .ew-preview-loading { color: #aaa; font-size: 0.8em; font-style: italic; }
        .ew-summary-divider { border: none; border-top: 1px solid #e0e0e0; margin: 4px 0; }

        /* Preview-Blöcke in Schritt 3 */
        .ew-preview-block { background: #fff; border: 1px solid #e8e8e8; border-radius: 8px; padding: 10px 14px; margin-top: 4px; }
        .ew-preview-block-title { font-size: 0.78em; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
        .ew-step-badges { display: flex; flex-wrap: wrap; gap: 4px; }
        .ew-step-badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 10px; font-size: 0.74em; font-weight: 600; background: #e8eaf6; color: #3949ab; }
        .ew-step-badge-num { background: #c5cae9; border-radius: 50%; width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75em; flex-shrink: 0; }
        .ew-tech-col-badges { display: flex; flex-wrap: wrap; gap: 4px; }
        .ew-params-grid { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 0.78em; }
        .ew-params-key { color: #888; font-family: monospace; white-space: nowrap; padding: 1px 0; }
        .ew-params-val { color: #333; font-family: monospace; word-break: break-all; padding: 1px 0; }
        .ew-preview-loading { color: #aaa; font-size: 0.8em; font-style: italic; }

        /* Ergebnis (Step 4 = Erfolg/Fehler) */
        .ew-result        { text-align: center; padding: 24px 10px; }
        .ew-result-icon   { font-size: 3em; margin-bottom: 10px; }
        .ew-result-title  { font-weight: 700; font-size: 1.1em; margin-bottom: 6px; }
        .ew-result-detail { font-size: 0.85em; color: #666; line-height: 1.6; }
        .ew-result-error  { color: #c62828; background: #ffebee; border-radius: 6px; padding: 10px; margin-top: 10px; font-size: 0.85em; }

        /* Spinner */
        @keyframes ew-spin { to { transform: rotate(360deg); } }
        .ew-spinner {
            width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.35);
            border-top-color: #fff; border-radius: 50%;
            animation: ew-spin 0.7s linear infinite; display: inline-block;
        }
    `;

    function injectStyles() {
        if (document.getElementById('studio-etl-wizard-style')) return;
        const s = document.createElement('style');
        s.id = 'studio-etl-wizard-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    // ----------------------------------------------------------------
    // SCD2-Technische-Spalten Vorschau (aus Backend-Defaults)
    // ----------------------------------------------------------------
    const SCD2_TECH_COLS = [
        '{NAME}_SK', 'VALID_FROM', 'VALID_TO', 'IS_CURRENT',
        'RECORD_HASH', 'ERSTERFASSUNGSDATUM', 'AENDERUNGSDATUM',
    ];

    // ----------------------------------------------------------------
    // Hilfsfunktion: Job-Name aus Tabellennamen generieren
    // ----------------------------------------------------------------
    function generateJobName(sourceName, targetName, templateName) {
        if (templateName) {
            // Template-Kürzel aus Template-Name extrahieren
            const parts = templateName.split(/[\s_-]+/).map(p => p.toUpperCase());
        }
        return `LOAD_${(sourceName || 'SRC').toUpperCase()}_TO_${(targetName || 'TGT').toUpperCase()}`;
    }

    function generateTargetName(sourceName, templateName) {
        const src = (sourceName || '').replace(/^(RAW_|STAGING_)/i, '');
        return src.toUpperCase();
    }

    // ----------------------------------------------------------------
    // Core-Name aus Tabellennamen extrahieren (identisch zur Backend-Logik
    // template_service.extract_core_name) – bestimmt den SK-Spaltennamen.
    // ----------------------------------------------------------------
    function extractCoreName(tableName) {
        if (!tableName) return '';
        const prefixes = ['TAAA_', 'TAAS_', 'TAA_', 'ZAS_'];
        const nameUpper = tableName.toUpperCase();
        for (const p of prefixes) {
            if (nameUpper.startsWith(p)) return tableName.slice(p.length);
        }
        // Fallback: nach erstem _ splitten wenn Präfix kurz (≤4 Zeichen)
        if (tableName.includes('_')) {
            const idx = tableName.indexOf('_');
            if (idx <= 4) return tableName.slice(idx + 1);
        }
        return tableName;
    }

    // ----------------------------------------------------------------
    // Kern-Klasse ETLWizard
    // ----------------------------------------------------------------

    class ETLWizard {
        /**
         * @param {HTMLElement} container
         * @param {{ sourceTableId?: number, sourceTableName?: string, mode?: 'modal'|'inline', onSuccess?: function }} opts
         */
        constructor(container, opts = {}) {
            injectStyles();
            this._el          = container;
            this._opts        = opts;
            this._sourceId    = opts.sourceTableId || null;
            this._sourceName  = opts.sourceTableName || null;
            this._sourceDb    = opts.sourceDbName || null;
            this._sourceLayerId = opts.sourceLayerId || null;
            this._mode        = opts.mode || 'inline';
            this._step        = 1;
            this._templates   = [];
            this._selection   = null; // { bk_columns, pk_columns, pi_columns, hash_columns, select_columns }
            this._colSelector = null;
            this._targetExists = opts.targetExists ?? null; // null=unbekannt, false=fehlt, true=vorhanden

            // Form-State
            this._form = {
                template_id:       null,
                template_name:     '',
                job_name:          '',
                // Zieltabellenname sofort mit Quelltabelle vorbelegen falls bekannt
                target_table_name: this._sourceName ? this._sourceName.toUpperCase() : '',
                target_table_id:   null, // wenn bereits existierende Zieltabelle
                fk_definitions:    [], // [{sk_column, key_table, key_database, natural_key_expr, domain}] – alter Block (deaktiviert)
                fk_master_table_ids: [], // F6-A: gewählte Master-Tabellen (Parent für FK-Surrogate-Keys)
                fk_master_mappings: [], // F6-Beladung: [{table_id, table_name, db_name, source_column, master_sk, master_bk}]
            };
            this._sourceColumns = null;  // Quellspalten (für FK-Mapping-Dropdown), lazy geladen
            this._useSk = false;         // F7: SK-Anzeige aktiv?
            this._skCol = '';            // SK-Spaltenname
        }

        async open() {
            await this._loadTemplates();
            if (this._sourceId && !this._sourceName) {
                await this._loadSourceInfo();
            }
            this._renderShell();
            this._goStep(1);
        }

        // ---- Laden ----

        async _loadTemplates() {
            this._templates = await window.api.templates.listJobs().catch(() => []);
        }

        async _loadSourceInfo() {
            try {
                const tables = await window.api.modeler.tables.get(this._sourceId).catch(() => null);
                if (tables) {
                    this._sourceName = tables.table_name || tables.name;
                    this._sourceDb   = tables.db_name || tables.database_name;
                    // Zieltabellenname vorschlagen falls noch nicht gesetzt
                    if (!this._form.target_table_name && this._sourceName) {
                        this._form.target_table_name = this._sourceName.toUpperCase();
                        this._form.job_name = 'LOAD_' + this._sourceName.toUpperCase();
                    } else if (this._form.target_table_name === '' && this._sourceName) {
                        this._form.target_table_name = this._sourceName.toUpperCase();
                    }
                }
            } catch (_) {}
        }

        // ---- Shell rendern ----

        _renderShell() {
            const isModal = this._mode === 'modal';
            this._el.innerHTML = `
                <div class="${isModal ? 'ew-modal' : 'ew-inline'}">
                    <div class="ew-header">
                        <div>
                            <div class="ew-header-title">⬡ ETL-Job erstellen</div>
                            <div class="ew-header-sub">
                                ${this._sourceName ? `Quelltabelle: ${this._sourceName}` : 'Neuen ETL-Job anlegen'}
                            </div>
                        </div>
                        ${isModal ? `<button class="ew-close-btn" id="ew-close">✕</button>` : ''}
                    </div>
                    <div class="ew-stepper">
                        <div class="ew-step-indicator active" data-step="1">
                            <span class="ew-step-num">1</span> Template & Namen
                        </div>
                        <div class="ew-step-indicator" data-step="2">
                            <span class="ew-step-num">2</span> Spalten
                        </div>
                        <div class="ew-step-indicator" data-step="3">
                            <span class="ew-step-num">3</span> Zusammenfassung
                        </div>
                    </div>
                    <div class="ew-body" id="ew-body"></div>
                    <div class="ew-footer" id="ew-footer"></div>
                </div>`;

            if (isModal) {
                this._el.querySelector('#ew-close')?.addEventListener('click', () => this._close());
            }
        }

        // ---- Schritte ----

        _goStep(n) {
            this._step = n;
            // Stepper-Indikatoren
            this._el.querySelectorAll('.ew-step-indicator').forEach(el => {
                const s = parseInt(el.dataset.step);
                el.classList.remove('active', 'done');
                if (s < n)  el.classList.add('done');
                if (s === n) el.classList.add('active');
            });

            const body   = this._el.querySelector('#ew-body');
            const footer = this._el.querySelector('#ew-footer');
            if (!body || !footer) return;

            if      (n === 1) this._renderStep1(body, footer);
            else if (n === 2) this._renderStep2(body, footer);
            else if (n === 3) this._renderStep3(body, footer);
        }

        // ---- Step 1: Template + Namen ----

        _renderStep1(body, footer) {
            const tplOptions = this._templates.map(t =>
                `<option value="${t.template_id}" ${this._form.template_id === t.template_id ? 'selected' : ''}>${t.template_name}</option>`
            ).join('');

            body.innerHTML = `
                ${this._targetExists === false ? `
                <div style="margin-bottom:12px;padding:10px 14px;background:#fff8e1;border:1px solid #ffe082;border-radius:6px;font-size:0.85em;color:#7d5a00">
                    ⚠️ Für diese Quelltabelle existiert noch kein ETL-Job und keine Zieltabelle.
                    Name und Zieltabelle wurden vorausgefüllt — bitte prüfen und anpassen.
                </div>` : ''}
                ${this._sourceName ? `
                <div class="ew-source-info">
                    <div class="ew-source-name">${this._sourceName}</div>
                    <div class="ew-source-db">${this._sourceDb || ''}</div>
                </div>` : ''}

                <div class="ew-form-row">
                    <label class="ew-form-label">Template *</label>
                    <select id="ew-template" class="ew-form-input ew-form-select">
                        <option value="">— Template wählen —</option>
                        ${tplOptions}
                    </select>
                    <div class="ew-form-hint">Bestimmt Typ (SCD1/SCD2/FULL) und generierte Steps</div>
                </div>

                <div class="ew-form-row">
                    <label class="ew-form-label">Zieltabellen-Name *</label>
                    <input id="ew-target-name" class="ew-form-input" type="text"
                           value="${this._form.target_table_name}"
                           placeholder="z.B. DISC_PARTNER">
                    <div class="ew-form-hint">Wird in META_TABLE angelegt (DDL noch separat)</div>
                </div>

                <div class="ew-form-row">
                    <label class="ew-form-label">Job-Name *</label>
                    <input id="ew-job-name" class="ew-form-input" type="text"
                           value="${this._form.job_name}"
                           placeholder="z.B. LOAD_PARTNER_TO_DISC">
                    <div class="ew-form-hint">Automatisch befüllt, editierbar</div>
                </div>`;

            // Auto-Generierung
            const tplSel    = body.querySelector('#ew-template');
            const targetEl  = body.querySelector('#ew-target-name');
            const jobEl     = body.querySelector('#ew-job-name');

            const autoFill = () => {
                const tpl = this._templates.find(t => t.template_id === parseInt(tplSel.value));
                if (!this._form.job_name && !jobEl.dataset.manual) {
                    const t = generateJobName(this._sourceName, targetEl.value, tpl?.template_name);
                    jobEl.value = t;
                    this._form.job_name = t;
                }
            };

            tplSel.addEventListener('change', () => {
                const tpl = this._templates.find(t => t.template_id === parseInt(tplSel.value));
                this._form.template_id   = tpl?.template_id || null;
                this._form.template_name = tpl?.template_name || '';
                if (!targetEl.dataset.manual && this._sourceName) {
                    targetEl.value = generateTargetName(this._sourceName, tpl?.template_name);
                    this._form.target_table_name = targetEl.value;
                }
                autoFill();
            });
            targetEl.addEventListener('input', e => {
                targetEl.dataset.manual  = '1';
                this._form.target_table_name = e.target.value.trim().toUpperCase();
                targetEl.value = this._form.target_table_name;
                // Job-Name neu generieren
                delete jobEl.dataset.manual;
                this._form.job_name = '';
                autoFill();
            });
            jobEl.addEventListener('input', e => {
                jobEl.dataset.manual    = '1';
                this._form.job_name    = e.target.value.trim().toUpperCase();
                jobEl.value = this._form.job_name;
            });

            // Initialwert aus vorherigem Schritt wiederherstellen
            if (this._form.template_id) tplSel.value = this._form.template_id;

            footer.innerHTML = `
                <div class="ew-footer-left">
                    <button class="ew-btn-cancel" id="ew-cancel">Abbrechen</button>
                </div>
                <div class="ew-footer-right">
                    <button class="ew-btn ew-btn-primary" id="ew-next1">Weiter: Spalten →</button>
                </div>`;

            footer.querySelector('#ew-cancel').addEventListener('click', () => this._close());
            footer.querySelector('#ew-next1').addEventListener('click', async () => {
                // Validieren
                this._form.template_id        = parseInt(tplSel.value) || null;
                this._form.target_table_name  = targetEl.value.trim().toUpperCase();
                this._form.job_name           = jobEl.value.trim().toUpperCase();

                if (!this._form.template_id) {
                    tplSel.style.borderColor = '#f44336'; return;
                }
                if (!this._form.target_table_name) {
                    targetEl.style.borderColor = '#f44336'; return;
                }
                if (!this._form.job_name) {
                    jobEl.style.borderColor = '#f44336'; return;
                }

                // Zieltabelle in META_TABLE suchen → wenn vorhanden, Spalten als _selection laden
                const nextBtn = footer.querySelector('#ew-next1');
                nextBtn.disabled = true;
                nextBtn.textContent = '⏳ Prüfe Zieltabelle…';
                try {
                    const tables = await window.api.modeler.tables.list({ search: this._form.target_table_name }).catch(() => []);
                    const exact  = (tables || []).find(t =>
                        (t.table_name || '').toUpperCase() === this._form.target_table_name
                        && t.table_id !== this._sourceId  // Source-Tabelle ausschließen
                    );
                    if (exact) {
                        this._form.target_table_id = exact.table_id;
                        // Spalten der Zieltabelle laden und als _selection vorbefüllen
                        const cols = await window.api.modeler.tables.columns(exact.table_id).catch(() => []);
                        if (cols?.length) {
                            const bk = [], pk = [], pi = [], hash = [], load = [];
                            for (const c of cols) {
                                const name = (c.column_name || '').toUpperCase();
                                if (!name) continue;
                                if (['Y','y'].includes(c.bk_flag || '')) bk.push(name);
                                if (['Y','y'].includes(c.pk_flag || '')) pk.push(name);
                                if (['Y','y'].includes(c.is_pi   || '')) pi.push(name);
                                if (['Y','y'].includes(c.is_hash || '')) hash.push(name);
                                load.push(name); // alle Spalten als "laden" vorbelegen
                            }
                            this._selection = { bk_columns: bk, pk_columns: pk, pi_columns: pi, hash_columns: hash, select_columns: load };
                        }
                        // Hinweis im Step 1 anzeigen
                        const hint = body.querySelector('.ew-target-exists-hint');
                        if (hint) hint.style.display = '';
                        else {
                            const hintEl = document.createElement('div');
                            hintEl.className = 'ew-target-exists-hint';
                            hintEl.style.cssText = 'margin-top:8px;padding:8px 12px;background:#e8f5e9;border:1px solid #a5d6a7;border-radius:6px;font-size:0.83em;color:#1b5e20';
                            hintEl.innerHTML = `✓ Zieltabelle <strong>${exact.table_name}</strong> (ID ${exact.table_id}) existiert bereits – Metadaten vorgeladen.`;
                            body.querySelector('#ew-form-row-target')?.after(hintEl) || body.appendChild(hintEl);
                        }
                    } else {
                        this._form.target_table_id = null;
                    }
                } catch (_) { /* ignore */ } finally {
                    nextBtn.disabled = false;
                    nextBtn.textContent = 'Weiter: Spalten →';
                }
                this._goStep(2);
            });
        }

        // ---- Step 2: Spalten ----

        _renderStep2(body, footer) {
            const tpl = this._templates.find(t => t.template_id === this._form.template_id);
            // F7: SK-Anzeige template-abhängig über Flag USE_SK (NICHT über Namen).
            const useSk = (tpl?.use_sk || 'N').toUpperCase() === 'Y';

            // SK-Spaltenname identisch zur Backend-Logik (Source-Core, Fallback Target)
            const coreName = extractCoreName(this._sourceName || this._form.target_table_name || '').toUpperCase();
            const skCol    = coreName ? `${coreName}_SK` : 'SURROGATE_KEY';
            // Für Tech-Zeilen-Aufbau merken
            this._useSk = useSk;
            this._skCol = skCol;

            const techColHtml = useSk ? `
                <div class="ew-tech-cols">
                    <div class="ew-tech-cols-title">⚙ Weitere technische Spalten (automatisch hinzugefügt)</div>
                    <div class="ew-tech-col-list">
                        ${SCD2_TECH_COLS.filter(c => c !== '{NAME}_SK').map(c =>
                            `<span class="ew-tech-col-badge">${c.replace('{NAME}', this._form.target_table_name)}</span>`
                        ).join('')}
                    </div>
                </div>` : '';

            body.innerHTML = `
                <p style="font-size:0.83em;color:#666;margin:0 0 10px">
                    Wähle die Spalten aus <strong>${this._sourceName || `Tabelle #${this._sourceId}`}</strong>,
                    die in den ETL-Job übernommen werden sollen.
                </p>
                <div id="ew-col-selector-wrap"></div>
                ${techColHtml}
                <div id="ew-fk-master-wrap"></div>
                <div id="ew-fk-block-wrap"></div>`;

            // ColumnSelector einbetten
            const wrap = body.querySelector('#ew-col-selector-wrap');
            if (this._sourceId) {
                // F7/F6: SK + FK als fixe (read-only) Zeilen oben in der Spaltentabelle
                const techRows = this._buildTechRows();
                this._colSelector = new window.ColumnSelector(wrap, {
                    tableId: this._sourceId,
                    initial: this._selection || null,
                    techRows,
                    onChange: sel => { this._selection = sel; },
                });
                this._colSelector.load();
            } else {
                wrap.innerHTML = `<div style="color:#888;font-size:0.85em;padding:10px 0">
                    Keine Quelltabelle angegeben – Spaltenauswahl übersprungen.</div>`;
                this._selection = { bk_columns: [], pk_columns: [], pi_columns: [], hash_columns: [], select_columns: [] };
            }

            // FK-Block einbetten
            this._renderFkMasterBlock(body.querySelector('#ew-fk-master-wrap'));
            this._renderFkBlock(body.querySelector('#ew-fk-block-wrap'));

            footer.innerHTML = `
                <div class="ew-footer-left">
                    <button class="ew-btn ew-btn-secondary" id="ew-back2">← Zurück</button>
                </div>
                <div class="ew-footer-right">
                    <button class="ew-btn ew-btn-primary" id="ew-next2">Weiter: Zusammenfassung →</button>
                </div>`;

            footer.querySelector('#ew-back2').addEventListener('click', () => this._goStep(1));
            footer.querySelector('#ew-next2').addEventListener('click', () => {
                if (this._colSelector) this._selection = this._colSelector.getSelection();
                if (!this._selection?.select_columns?.length && this._sourceId) {
                    if (!confirm('Keine Spalten ausgewählt – wirklich weiter?')) return;
                }
                this._goStep(3);
            });
        }

        // ---- Tech-Zeilen (SK + FK) für die Spaltentabelle ----

        /** Baut die fixen Tech-Zeilen: SK (wenn USE_SK) + je Master-Mapping eine FK-Zeile. */
        _buildTechRows() {
            const rows = [];
            if (this._useSk && this._skCol) {
                rows.push({ name: this._skCol, type: 'BIGINT', badge: 'SK', pk: true, pi: true, piEditable: true, load: true });
            }
            (this._form.fk_master_mappings || []).forEach(m => {
                if (m.master_sk) {
                    rows.push({ name: `${m.master_sk}_FK`, type: 'BIGINT', badge: 'FK', load: true });
                }
            });
            return rows;
        }

        /** Aktualisiert die Tech-Zeilen im ColumnSelector (nach Master-Änderung). */
        _refreshTechRows() {
            if (this._colSelector?.setTechRows) {
                this._colSelector.setTechRows(this._buildTechRows());
            }
        }

        /** Lädt die Quellspalten (für FK-Mapping-Dropdown), einmalig gecacht. */
        async _loadSourceColumns() {
            if (this._sourceColumns) return this._sourceColumns;
            try {
                this._sourceColumns = await window.api.etl.tables.columns(this._sourceId) || [];
            } catch (_) {
                this._sourceColumns = [];
            }
            return this._sourceColumns;
        }

        // ---- FK über Master-Tabelle (F6-A) ----

        async _renderFkMasterBlock(container) {
            const wrap = document.createElement('div');
            wrap.className = 'ew-fk-block';
            wrap.innerHTML = `
                <div class="ew-fk-title">
                    🧩 Foreign Keys über Master-Tabelle
                    <span class="ew-fk-hint">Master-Tabelle wählen + Quellspalte zuordnen – FK-Spalte, Beziehung &amp; Beladung werden abgeleitet</span>
                </div>
                <div class="ew-fkm-add-row">
                    <select id="ew-fkm-select" class="ew-fkm-select">
                        <option value="">– Master-Tabelle wählen –</option>
                    </select>
                    <button class="ew-btn ew-btn-secondary" id="ew-fkm-add" type="button">＋ hinzufügen</button>
                </div>
                <div id="ew-fkm-list" class="ew-fkm-list"></div>`;
            container.appendChild(wrap);

            const selectEl = wrap.querySelector('#ew-fkm-select');

            // Tabellen einmalig laden + cachen
            if (!this._allTables) {
                try {
                    this._allTables = await window.api.modeler.tables.list() || [];
                } catch (e) {
                    this._allTables = [];
                }
            }
            // Quellspalten laden (für Mapping-Dropdown)
            await this._loadSourceColumns();

            // Quelltabelle selbst nicht als Master anbieten
            const tables = (this._allTables || [])
                .filter(t => t.table_id !== this._sourceId)
                .sort((a, b) => (a.table_name || '').localeCompare(b.table_name || ''));
            tables.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t.table_id;
                opt.textContent = `${t.table_name}${t.db_name ? ' (' + t.db_name + ')' : ''}`;
                selectEl.appendChild(opt);
            });

            const tableById = (id) => (this._allTables || []).find(t => String(t.table_id) === String(id));

            // Master-Spalten laden → SK (is_technical_key) + BK (is_business_key) ermitteln
            const loadMasterKeys = async (masterId) => {
                let cols = [];
                try { cols = await window.api.etl.tables.columns(masterId) || []; } catch (_) { cols = []; }
                const findFlag = (flag) => {
                    const c = cols.find(x => x[flag] === true || x[flag] === 'Y' || x[flag] === 'y');
                    return c ? (c.column_name || '').toUpperCase() : '';
                };
                let sk = findFlag('is_technical_key');
                if (!sk) {
                    const c = cols.find(x => (x.column_name || '').toUpperCase().endsWith('_SK'));
                    sk = c ? (c.column_name || '').toUpperCase() : '';
                }
                const bk = findFlag('is_business_key');
                return { master_sk: sk, master_bk: bk };
            };

            const sourceColOptions = (selected) => {
                const opts = ['<option value="">– Quellspalte –</option>'];
                (this._sourceColumns || []).forEach(c => {
                    const n = (c.column_name || '').toUpperCase();
                    if (!n) return;
                    opts.push(`<option value="${n}" ${n === (selected || '').toUpperCase() ? 'selected' : ''}>${n}</option>`);
                });
                return opts.join('');
            };

            const renderMasterItems = () => {
                const listEl = wrap.querySelector('#ew-fkm-list');
                listEl.innerHTML = '';
                (this._form.fk_master_mappings || []).forEach((m, idx) => {
                    const t = tableById(m.table_id);
                    const fkColName = m.master_sk ? `${m.master_sk}_FK` : '(SK unbekannt)';
                    const row = document.createElement('div');
                    row.className = 'ew-fkm-row';
                    row.style.cssText = 'flex-direction:column;align-items:stretch;gap:6px;width:100%';
                    row.innerHTML = `
                        <div style="display:flex;align-items:center;gap:8px">
                            <span class="ew-fkm-tag">🔗 ${t ? t.table_name : ('#' + m.table_id)}</span>
                            <span style="font-size:0.78em;color:#2e7d32;font-family:monospace">→ ${fkColName}</span>
                            <button class="ew-fk-remove" title="entfernen" style="margin-left:auto">✕</button>
                        </div>
                        <div style="display:flex;align-items:center;gap:6px;font-size:0.78em;color:#555">
                            <span>Quellspalte → ${m.master_bk || 'BK'}:</span>
                            <select class="ew-fkm-srccol ew-fkm-select" style="flex:1">${sourceColOptions(m.source_column)}</select>
                        </div>`;
                    row.querySelector('.ew-fk-remove').addEventListener('click', () => {
                        this._form.fk_master_mappings.splice(idx, 1);
                        renderMasterItems();
                        this._refreshTechRows();
                    });
                    row.querySelector('.ew-fkm-srccol').addEventListener('change', (e) => {
                        this._form.fk_master_mappings[idx].source_column = e.target.value.toUpperCase();
                    });
                    listEl.appendChild(row);
                });
            };

            wrap.querySelector('#ew-fkm-add').addEventListener('click', async () => {
                const val = selectEl.value;
                if (!val) return;
                const id = parseInt(val, 10);
                if (!this._form.fk_master_mappings) this._form.fk_master_mappings = [];
                if (this._form.fk_master_mappings.some(m => m.table_id === id)) { selectEl.value = ''; return; }
                const t = tableById(id);
                const keys = await loadMasterKeys(id);
                this._form.fk_master_mappings.push({
                    table_id:      id,
                    table_name:    t ? t.table_name : '',
                    db_name:       t ? (t.db_name || '') : '',
                    source_column: '',
                    master_sk:     keys.master_sk,
                    master_bk:     keys.master_bk,
                });
                selectEl.value = '';
                renderMasterItems();
                this._refreshTechRows();
            });

            renderMasterItems();
        }

        // ---- FK-Block rendern ----

        _renderFkBlock(container) {
            const wrap = document.createElement('div');
            wrap.className = 'ew-fk-block';
            wrap.innerHTML = `
                <div class="ew-fk-title">
                    🔗 Foreign Surrogate Keys (optional)
                    <span class="ew-fk-hint">SK-Lookup auf andere KEY-Tabellen beim INSERT</span>
                </div>
                <div id="ew-fk-list"></div>
                <button class="ew-btn ew-btn-secondary ew-fk-add" id="ew-fk-add">＋ FK hinzufügen</button>`;
            container.appendChild(wrap);

            const renderFkItems = () => {
                const listEl = wrap.querySelector('#ew-fk-list');
                listEl.innerHTML = '';
                (this._form.fk_definitions || []).forEach((fk, idx) => {
                    const row = document.createElement('div');
                    row.className = 'ew-fk-row';
                    row.innerHTML = `
                        <div class="ew-fk-fields">
                            <label>SK-Spaltenname<br>
                                <input class="ew-fk-sk" type="text" value="${fk.sk_column || ''}" placeholder="z.B. GESCHAEFT_SK">
                            </label>
                            <label>Key-Database<br>
                                <input class="ew-fk-kdb" type="text" value="${fk.key_database || 'MDP01_DISCOVERABLE_LAYER'}" placeholder="MDP01_DISCOVERABLE_LAYER">
                            </label>
                            <label>Key-Tabelle<br>
                                <input class="ew-fk-ktbl" type="text" value="${fk.key_table || ''}" placeholder="z.B. KEY_TAAS_GESCHAEFT">
                            </label>
                            <label>Natural-Key-Expression (src.)<br>
                                <input class="ew-fk-nk" type="text" value="${fk.natural_key_expr || ''}" placeholder="CAST(src.GESCHAEFT_ID AS VARCHAR(255))">
                            </label>
                            <label>Domain<br>
                                <input class="ew-fk-domain" type="text" value="${fk.domain || ''}" placeholder="z.B. UZMS01">
                            </label>
                        </div>
                        <button class="ew-fk-remove" data-idx="${idx}" title="FK entfernen">✕</button>`;
                    // Live-Update ins _form
                    const update = () => {
                        this._form.fk_definitions[idx] = {
                            sk_column:        row.querySelector('.ew-fk-sk').value.trim().toUpperCase(),
                            key_database:     row.querySelector('.ew-fk-kdb').value.trim(),
                            key_table:        row.querySelector('.ew-fk-ktbl').value.trim(),
                            natural_key_expr: row.querySelector('.ew-fk-nk').value.trim(),
                            domain:           row.querySelector('.ew-fk-domain').value.trim(),
                        };
                    };
                    row.querySelectorAll('input').forEach(inp => inp.addEventListener('input', update));
                    row.querySelector('.ew-fk-remove').addEventListener('click', () => {
                        this._form.fk_definitions.splice(idx, 1);
                        renderFkItems();
                    });
                    listEl.appendChild(row);
                });
            };

            wrap.querySelector('#ew-fk-add').addEventListener('click', () => {
                if (!this._form.fk_definitions) this._form.fk_definitions = [];
                this._form.fk_definitions.push({ sk_column: '', key_database: 'MDP01_DISCOVERABLE_LAYER', key_table: '', natural_key_expr: '', domain: '' });
                renderFkItems();
            });

            renderFkItems();
        }

        // ---- Step 3: Zusammenfassung ----

        _renderStep3(body, footer) {
            const sel  = this._selection || { bk_columns: [], pk_columns: [], pi_columns: [], hash_columns: [], select_columns: [] };
            const tpl  = this._templates.find(t => t.template_id === this._form.template_id);
            const tgtName  = this._form.target_table_name || '';
            // F7: SK-Anzeige template-abhängig über Flag USE_SK
            const useSk = (tpl?.use_sk || 'N').toUpperCase() === 'Y';
            // Core-Name für SK-Spalte: Source-Tabelle (Fallback Target), identisch zur Backend-Logik
            const coreName = extractCoreName(this._sourceName || tgtName).toUpperCase();
            const skCol    = coreName ? `${coreName}_SK` : 'SURROGATE_KEY';

            body.innerHTML = `
                <div class="ew-summary">
                    <div class="ew-summary-item">
                        <div class="ew-summary-icon">📋</div>
                        <div class="ew-summary-text">
                            <div class="ew-summary-title">Template</div>
                            <div class="ew-summary-val">${tpl?.template_name || '–'}</div>
                        </div>
                    </div>
                    <div class="ew-summary-item">
                        <div class="ew-summary-icon">⚙</div>
                        <div class="ew-summary-text">
                            <div class="ew-summary-title">Job-Name</div>
                            <div class="ew-summary-val">${this._form.job_name}</div>
                        </div>
                    </div>
                    <div class="ew-summary-item">
                        <div class="ew-summary-icon">✅</div>
                        <div class="ew-summary-text">
                            <div class="ew-summary-title">Zieltabelle</div>
                            <div class="ew-summary-val">${tgtName}</div>
                            <div class="ew-summary-note">
                                Wird in META_TABLE + META_COLUMN angelegt.
                                DDL-Ausführung auf Teradata ist ein separater Schritt.
                            </div>
                        </div>
                    </div>
                    <div class="ew-summary-item">
                        <div class="ew-summary-icon">⬤</div>
                        <div class="ew-summary-text">
                            <div class="ew-summary-title">Spalten</div>
                            <div class="ew-summary-val">
                                ${sel.select_columns.length} laden &nbsp;·&nbsp;
                                ${sel.bk_columns.length} BK &nbsp;·&nbsp;
                                ${sel.pk_columns.length} PK &nbsp;·&nbsp;
                                ${sel.pi_columns.length} PI &nbsp;·&nbsp;
                                ${sel.hash_columns.length} Hash
                            </div>
                            ${sel.bk_columns.length > 0
                                ? `<div class="ew-summary-note" style="color:#2e7d32">✓ Business Keys: ${sel.bk_columns.join(', ')}</div>`
                                : `<div class="ew-summary-note" style="color:#e65100">⚠ Kein Business Key ausgewählt (SCD2 benötigt mind. 1 BK)</div>`}
                        </div>
                    </div>

                    <!-- FK über Master-Tabellen (F6) -->
                    ${(() => {
                        const fks = (this._form.fk_master_mappings || []).filter(m => m.table_id && m.master_sk);
                        if (!fks.length) return '';
                        return `<div class="ew-preview-block">
                            <div class="ew-preview-block-title">🔗 Foreign Keys über Master-Tabelle (${fks.length})</div>
                            <div class="ew-step-badges">
                                ${fks.map(m => {
                                    const fkCol = `${m.master_sk}_FK`;
                                    const mapped = m.source_column
                                        ? `src.${m.source_column} → ${m.table_name}.${m.master_bk}`
                                        : '⚠ keine Quellspalte gemappt (keine Beladung)';
                                    return `<span class="ew-step-badge" style="background:#e8f5e9;color:#1b5e20" title="${mapped}">${fkCol}</span>`;
                                }).join('')}
                            </div>
                        </div>`;
                    })()}

                    <!-- Steps Preview (wird asynchron nachgeladen) -->
                    <div class="ew-preview-block" id="ew-steps-preview">
                        <div class="ew-preview-block-title">🗂 Steps (werden angelegt)</div>
                        <div class="ew-preview-loading" id="ew-steps-loading">Lade…</div>
                        <div class="ew-step-badges" id="ew-step-badges"></div>
                    </div>

                    <!-- Technische Spalten (nur wenn USE_SK) -->
                    ${useSk ? `
                    <div class="ew-preview-block">
                        <div class="ew-preview-block-title">⚙ Technische Spalten (werden automatisch angelegt)</div>
                        <div class="ew-step-badges">
                            <span class="ew-step-badge" style="background:#f3e5f5;color:#7b1fa2" title="Surrogate Key – ist immer Primary Key">${skCol} 🔑 PK</span>
                            <span class="ew-step-badge" style="background:#e8eaf6;color:#3949ab">VALID_FROM</span>
                            <span class="ew-step-badge" style="background:#e8eaf6;color:#3949ab">VALID_TO</span>
                            <span class="ew-step-badge" style="background:#e8eaf6;color:#3949ab">IS_CURRENT</span>
                            <span class="ew-step-badge" style="background:#e0f2f1;color:#00695c">RECORD_HASH</span>
                            <span class="ew-step-badge" style="background:#f5f5f5;color:#616161">ERSTERFASSUNGSDATUM</span>
                            <span class="ew-step-badge" style="background:#f5f5f5;color:#616161">AENDERUNGSDATUM</span>
                        </div>
                    </div>` : ''}

                    <!-- Berechnete Parameter -->
                    <div class="ew-preview-block">
                        <div class="ew-preview-block-title">📊 Berechnete Parameter</div>
                        <div class="ew-params-grid">
                            <span class="ew-params-key">SOURCE_TABLE</span><span class="ew-params-val">${this._sourceName || '–'}</span>
                            <span class="ew-params-key">SOURCE_DATABASE</span><span class="ew-params-val">${this._sourceDb || '–'}</span>
                            <span class="ew-params-key">TARGET_TABLE</span><span class="ew-params-val">${tgtName || '–'}</span>
                            ${useSk ? `<span class="ew-params-key">SK_COLUMN</span><span class="ew-params-val">${skCol}</span>` : ''}
                            <span class="ew-params-key">STAGING_TABLE</span><span class="ew-params-val">temp_${tgtName.toLowerCase()}_stg</span>
                            ${useSk ? `<span class="ew-params-key">KEY_TABLE</span><span class="ew-params-val">KEY_${coreName}</span>` : ''}
                            ${sel.bk_columns.length > 0 ? `<span class="ew-params-key">BUSINESS_KEY</span><span class="ew-params-val">${sel.bk_columns.join(', ')}</span>` : ''}
                            ${sel.pk_columns.length > 0 ? `<span class="ew-params-key">PRIMARY_KEY</span><span class="ew-params-val">${sel.pk_columns.join(', ')}</span>` : ''}
                            ${sel.hash_columns.length > 0 ? `<span class="ew-params-key">HASH_COLUMNS</span><span class="ew-params-val">${sel.hash_columns.join(', ')}</span>` : ''}
                        </div>
                        ${useSk ? `<div class="ew-summary-note" style="margin-top:6px">🔑 KEY_${coreName} wird automatisch angelegt falls nicht vorhanden.</div>` : ''}
                    </div>
                </div>
                <div id="ew-create-error" style="display:none" class="ew-result-error"></div>`;

            // Steps asynchron nachladen
            if (tpl?.template_id) {
                window.api.templates.listSteps({ template_id: tpl.template_id })
                    .then(steps => {
                        const loadingEl = body.querySelector('#ew-steps-loading');
                        const badgesEl  = body.querySelector('#ew-step-badges');
                        if (!loadingEl || !badgesEl) return;
                        loadingEl.style.display = 'none';
                        if (!steps || steps.length === 0) {
                            badgesEl.innerHTML = '<span style="color:#aaa;font-size:0.8em">Keine Steps gefunden</span>';
                            return;
                        }
                        badgesEl.innerHTML = steps
                            .sort((a, b) => a.step_order - b.step_order)
                            .map(s => `<span class="ew-step-badge"><span class="ew-step-badge-num">${s.step_order}</span>${s.step_name}</span>`)
                            .join('');
                    })
                    .catch(() => {
                        const loadingEl = body.querySelector('#ew-steps-loading');
                        if (loadingEl) loadingEl.textContent = 'Steps nicht verfügbar';
                    });
            } else {
                const loadingEl = body.querySelector('#ew-steps-loading');
                if (loadingEl) loadingEl.style.display = 'none';
            }

            footer.innerHTML = `
                <div class="ew-footer-left">
                    <button class="ew-btn ew-btn-secondary" id="ew-back3">← Zurück</button>
                </div>
                <div class="ew-footer-right">
                    <button class="ew-btn-cancel" id="ew-cancel3" style="margin-right:8px">Abbrechen</button>
                    <button class="ew-btn ew-btn-success" id="ew-create">✅ Anlegen</button>
                </div>`;

            footer.querySelector('#ew-back3').addEventListener('click', () => this._goStep(2));
            footer.querySelector('#ew-cancel3').addEventListener('click', () => this._close());
            footer.querySelector('#ew-create').addEventListener('click', () => this._create());
        }

        // ---- API-Aufruf: Anlegen ----

        async _create() {
            const footer   = this._el.querySelector('#ew-footer');
            const createBtn= footer?.querySelector('#ew-create');
            const errEl    = this._el.querySelector('#ew-create-error');

            if (createBtn) { createBtn.disabled = true; createBtn.innerHTML = `<span class="ew-spinner"></span> Anlegen…`; }
            if (errEl)       errEl.style.display = 'none';

            const sel  = this._selection || { bk_columns: [], pk_columns: [], pi_columns: [], hash_columns: [], select_columns: [] };
            // F6: Master-Tabellen-Auswahl + Quellspalten-Mapping → Backend leitet
            //     FK-Spalte, Beziehung UND Beladung (SK-Lookup) ab.
            const fkMappings = (this._form.fk_master_mappings || []).filter(m => m.table_id);
            const fkMasterTableIds = fkMappings.map(m => m.table_id);
            // F7: SK-PI ist editierbar – Wahl aus der SK-Tech-Zeile auslesen (Default Y)
            const techState = this._colSelector?.getTechState ? this._colSelector.getTechState() : {};
            const skKey = (this._skCol || '').toUpperCase();
            const skTech = techState[skKey] || Object.values(techState)[0];
            const skIsPi = skTech ? (skTech.pi ? 'Y' : 'N') : 'Y';
            const payload = {
                source_table_id:   this._sourceId,
                target_table_name: this._form.target_table_name,
                target_table_id:   this._form.target_table_id || null,
                job_name:          this._form.job_name,
                parameters: {
                    primary_key_columns: sel.bk_columns,
                    pk_columns:          sel.pk_columns,
                    pi_columns:          sel.pi_columns,
                    hash_columns:        sel.hash_columns,
                    select_columns:      sel.select_columns,
                    fk_definitions:      [],                  // F6: alten 5-Felder-Block bewusst leer lassen
                    fk_master_table_ids: fkMasterTableIds,    // F6-A: Master-Tabellen (für META-Beziehung)
                    fk_master_mappings:  fkMappings,          // F6-Beladung: Master + Quellspalten-Mapping
                    sk_is_pi:            skIsPi,              // F7: SK als Primary Index? (editierbar)
                },
            };

            try {
                const result = await window.api.templates.applyJob(this._form.template_id, payload);
                this._renderSuccess(result);
            } catch (e) {
                if (createBtn) { createBtn.disabled = false; createBtn.innerHTML = '✅ Anlegen'; }
                if (errEl) { errEl.textContent = e.message; errEl.style.display = ''; }
            }
        }

        // ---- Erfolg ----

        _renderSuccess(result) {
            const body   = this._el.querySelector('#ew-body');
            const footer = this._el.querySelector('#ew-footer');
            if (!body || !footer) return;

            // Stepper: alle done
            this._el.querySelectorAll('.ew-step-indicator').forEach(el => {
                el.classList.remove('active'); el.classList.add('done');
            });

            body.innerHTML = `
                <div class="ew-result">
                    <div class="ew-result-icon">🎉</div>
                    <div class="ew-result-title">Erfolgreich angelegt!</div>
                    <div class="ew-result-detail">
                        <strong>Job:</strong> ${this._form.job_name}<br>
                        <strong>Job-ID:</strong> ${result.job_id}<br>
                        ${result.target_created
                            ? `<strong>Zieltabelle:</strong> ${this._form.target_table_name} (ID ${result.target_table_id}) – neu angelegt<br>`
                            : `<strong>Zieltabelle:</strong> ${this._form.target_table_name} – bereits vorhanden<br>`}
                        <br>
                        <span style="color:#f57f17">⚠ DDL muss noch auf Teradata ausgeführt werden.</span>
                    </div>
                </div>`;

            footer.innerHTML = `
                <div class="ew-footer-right" style="width:100%;justify-content:center">
                    <button class="ew-btn ew-btn-primary" id="ew-done">Fertig</button>
                </div>`;

            footer.querySelector('#ew-done').addEventListener('click', () => {
                document.dispatchEvent(new CustomEvent('studio:job-created', {
                    detail: {
                        job_id:            result.job_id,
                        target_table_id:   result.target_table_id,
                        target_created:    result.target_created,
                        job_name:          this._form.job_name,
                        target_table_name: this._form.target_table_name,
                    }
                }));
                this._close();
                if (this._opts.onSuccess) this._opts.onSuccess(result);
            });
        }

        _close() {
            if (this._mode === 'modal') {
                // Overlay entfernen
                const overlay = this._el.closest('.ew-overlay');
                if (overlay) overlay.remove();
            } else {
                this._el.innerHTML = '';
            }
            document.dispatchEvent(new CustomEvent('studio:wizard-closed', { detail: {} }));
        }

        // ---- Statische Hilfsmethode: Modal öffnen ----

        /**
         * Öffnet den Wizard als Modal.
         * @param {{ sourceTableId?, sourceTableName?, sourceDbName?, onSuccess? }} opts
         * @returns {ETLWizard}
         */
        static openModal(opts = {}) {
            injectStyles();
            const overlay = document.createElement('div');
            overlay.className = 'ew-overlay';
            document.body.appendChild(overlay);

            // Klick außerhalb schließt Modal
            overlay.addEventListener('click', e => {
                if (e.target === overlay) {
                    overlay.remove();
                    document.dispatchEvent(new CustomEvent('studio:wizard-closed', { detail: {} }));
                }
            });

            const wiz = new ETLWizard(overlay, { ...opts, mode: 'modal' });
            wiz.open();
            return wiz;
        }
    }

    // ----------------------------------------------------------------
    // Custom Element <studio-etl-wizard>
    // ----------------------------------------------------------------

    class StudioEtlWizard extends HTMLElement {
        static get observedAttributes() { return ['source-table-id', 'source-table-name']; }

        connectedCallback() {
            injectStyles();
            const tid  = parseInt(this.getAttribute('source-table-id')) || null;
            const name = this.getAttribute('source-table-name') || null;
            this._wiz  = new ETLWizard(this, {
                sourceTableId:   tid,
                sourceTableName: name,
                mode: 'inline',
            });
            if (tid || name) this._wiz.open();
        }

        open(opts = {}) {
            if (!this._wiz) this._wiz = new ETLWizard(this, { mode: 'inline' });
            Object.assign(this._wiz._opts, opts);
            Object.assign(this._wiz, {
                _sourceId:   opts.sourceTableId   ?? this._wiz._sourceId,
                _sourceName: opts.sourceTableName ?? this._wiz._sourceName,
            });
            this._wiz.open();
        }
    }

    if (!customElements.get('studio-etl-wizard')) {
        customElements.define('studio-etl-wizard', StudioEtlWizard);
    }
    window.ETLWizard = ETLWizard;

})();
