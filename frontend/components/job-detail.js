/**
 * daita-studio – Job-Detail Komponente (C4)
 *
 * Zeigt alle Details eines ETL-Jobs: Meta-Informationen, Steps,
 * Run-Button mit Live-Polling, Run-History.
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   <script src="/components/job-detail.js"></script>
 *
 *   <!-- Als Custom Element: -->
 *   <studio-job-detail></studio-job-detail>
 *   <script>
 *     document.querySelector('studio-job-detail').load(jobId);
 *   </script>
 *
 *   <!-- Oder per JS-Instanz: -->
 *   const detail = new JobDetail(containerEl);
 *   detail.load(42);
 *
 * Custom Events (gefeuert auf document):
 *   studio:job-started    { detail: { job_id, run_id } }
 *   studio:job-finished   { detail: { job_id, run_id, status } }
 *   studio:job-deleted    { detail: { job_id } }
 *   studio:job-edit       { detail: { job_id } }   ← Seite soll Editor öffnen
 *
 * Abhängigkeiten: api.js (window.api)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Styles
    // ----------------------------------------------------------------
    const STYLE = `
        .jd-root { font-size: 0.88em; display: flex; flex-direction: column; height: 100%; }

        /* Leer-Zustand */
        .jd-empty { display: flex; align-items: center; justify-content: center;
                    height: 100%; color: var(--text-secondary, #888); font-size: 0.95em; }

        /* Header */
        .jd-header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff; padding: 14px 18px;
            display: flex; align-items: center; gap: 12px;
        }
        .jd-header-info { flex: 1; min-width: 0; }
        .jd-title { font-weight: 700; font-size: 1.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .jd-subtitle { font-size: 0.78em; opacity: 0.85; margin-top: 2px; }
        .jd-header-actions { display: flex; gap: 6px; flex-shrink: 0; }

        /* Buttons */
        .jd-btn {
            padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
            font-size: 0.85em; font-weight: 600; transition: opacity 0.15s; display: inline-flex; align-items: center; gap: 5px;
        }
        .jd-btn:hover { opacity: 0.85; }
        .jd-btn:disabled { opacity: 0.45; cursor: not-allowed; }
        .jd-btn-run      { background: #fff; color: #667eea; }
        .jd-btn-edit     { background: rgba(255,255,255,0.2); color: #fff; }
        .jd-btn-delete   { background: rgba(244,67,54,0.25); color: #fff; }
        .jd-btn-primary  { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; }
        .jd-btn-secondary{ background: #f0f0f0; color: #444; border: 1px solid #ddd; }
        .jd-btn-orange   { background: linear-gradient(135deg, #f7971e, #ffd200); color: #333; }

        /* Tabs */
        .jd-tabs { display: flex; border-bottom: 1px solid var(--border-color, #e8e8e8); padding: 0 14px; }
        .jd-tab {
            background: none; border: none; padding: 9px 14px; cursor: pointer;
            border-bottom: 2px solid transparent; color: #888; font-size: 0.85em; transition: color 0.15s;
        }
        .jd-tab:hover { color: #667eea; }
        .jd-tab.active { color: #667eea; border-bottom-color: #667eea; font-weight: 600; }

        /* Body */
        .jd-body { flex: 1; overflow-y: auto; padding: 14px 18px; }

        /* Meta-Tabelle */
        .jd-meta-table { width: 100%; border-collapse: collapse; }
        .jd-meta-table td { padding: 5px 0; vertical-align: top; }
        .jd-meta-table td:first-child { width: 120px; color: #888; font-size: 0.85em; }
        .jd-meta-table td:last-child { font-size: 0.88em; font-weight: 500; }

        /* Badge */
        .jd-badge {
            display: inline-block; padding: 2px 9px; border-radius: 10px;
            font-size: 0.78em; font-weight: 700;
        }
        .jd-badge-ok     { background: #e8f5e9; color: #2e7d32; }
        .jd-badge-warn   { background: #fff8e1; color: #f57f17; }
        .jd-badge-err    { background: #ffebee; color: #c62828; }
        .jd-badge-blue   { background: #e8eaf6; color: #3949ab; }
        .jd-badge-purple { background: #f3e5f5; color: #7b1fa2; }
        .jd-badge-grey   { background: #f5f5f5; color: #616161; }

        /* Steps */
        .jd-step-list { display: flex; flex-direction: column; gap: 8px; }
        .jd-step {
            border: 1px solid #e8e8e8; border-radius: 8px;
            overflow: hidden; transition: border-color 0.15s;
        }
        .jd-step.running  { border-color: #667eea; }
        .jd-step.success  { border-color: #4caf50; }
        .jd-step.failed   { border-color: #f44336; }
        .jd-step.skipped  { opacity: 0.6; }
        .jd-step-header {
            display: flex; align-items: center; gap: 10px;
            padding: 9px 12px; cursor: pointer; user-select: none;
        }
        .jd-step-header:hover { background: #fafafa; }
        .jd-step-num {
            width: 24px; height: 24px; border-radius: 50%; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            font-weight: 700; font-size: 0.78em;
            background: #e8eaf6; color: #3949ab;
        }
        .jd-step.running .jd-step-num  { background: #e3f2fd; color: #1565c0; }
        .jd-step.success .jd-step-num  { background: #e8f5e9; color: #2e7d32; }
        .jd-step.failed  .jd-step-num  { background: #ffebee; color: #c62828; }
        .jd-step-name  { flex: 1; font-weight: 600; font-size: 0.88em; }
        .jd-step-cat   { font-size: 0.75em; color: #888; }
        .jd-step-body  { padding: 0 12px 10px 46px; font-size: 0.82em; color: #666; }
        .jd-step-metrics { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
        .jd-step-metric span:first-child { color: #888; }
        .jd-step-metric span:last-child  { font-weight: 600; }
        .jd-step-error {
            background: #fff0f0; border-radius: 4px; padding: 8px 10px; margin-top: 6px;
            color: #c62828; font-family: monospace; font-size: 0.85em; white-space: pre-wrap; word-break: break-all;
        }

        /* Execution-Progress */
        .jd-progress-bar {
            height: 4px; background: #e8eaf6; border-radius: 2px; margin: 10px 0;
        }
        .jd-progress-fill {
            height: 100%; background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 2px; transition: width 0.4s;
        }
        .jd-progress-text { font-size: 0.8em; color: #888; text-align: center; }

        /* Initial Load Warning */
        .jd-init-load {
            background: #fff8e1; border-left: 3px solid #ff9800;
            border-radius: 4px; padding: 10px 12px; margin: 10px 0;
            font-size: 0.85em;
        }
        .jd-init-load label { cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; color: #e65100; }
        .jd-init-load-warn {
            display: none; background: #ffebee; border-radius: 4px; padding: 8px;
            margin-top: 8px; color: #c62828; font-size: 0.85em;
        }

        /* Run History */
        .jd-run-list { display: flex; flex-direction: column; gap: 6px; }
        .jd-run-item {
            display: flex; align-items: center; gap: 10px;
            border: 1px solid #e8e8e8; border-radius: 7px; padding: 8px 12px;
            cursor: pointer; transition: background 0.15s;
        }
        .jd-run-item:hover { background: #f8f8ff; }
        .jd-run-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
        .jd-run-info { flex: 1; }
        .jd-run-id   { font-weight: 600; font-size: 0.85em; }
        .jd-run-time { font-size: 0.78em; color: #888; }
        .jd-run-dur  { font-size: 0.82em; color: #666; }

        /* Spinner */
        @keyframes jd-spin { to { transform: rotate(360deg); } }
        .jd-spinner {
            width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.4);
            border-top-color: #fff; border-radius: 50%;
            animation: jd-spin 0.8s linear infinite; display: inline-block;
        }
    `;

    function injectStyles() {
        if (document.getElementById('studio-job-detail-style')) return;
        const s = document.createElement('style');
        s.id = 'studio-job-detail-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    // ----------------------------------------------------------------
    // Hilfsfunktionen
    // ----------------------------------------------------------------

    function formatDur(secs) {
        if (secs == null) return '–';
        secs = Math.round(secs);
        if (secs < 60) return `${secs}s`;
        const m = Math.floor(secs / 60), s2 = secs % 60;
        return m < 60 ? `${m}m ${s2}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
    }

    function statusBadge(status) {
        const map = {
            'SUCCESS': ['jd-badge-ok', '✅ OK'],
            'FAILED':  ['jd-badge-err', '❌ Fehler'],
            'RUNNING': ['jd-badge-blue', '⟳ Läuft'],
            'STARTING':['jd-badge-blue', '⟳ Startet'],
            'SKIPPED': ['jd-badge-grey', '⤳ Skip'],
            'PENDING': ['jd-badge-grey', '○ Ausstehend'],
        };
        const [cls, lbl] = map[status] || ['jd-badge-grey', status || '?'];
        return `<span class="jd-badge ${cls}">${lbl}</span>`;
    }

    // ----------------------------------------------------------------
    // Kern-Klasse JobDetail
    // ----------------------------------------------------------------

    class JobDetail {
        constructor(container) {
            injectStyles();
            this._el = container;
            this._jobId = null;
            this._job = null;
            this._pollTimer = null;
            this._initialLoad = false;
            this._el.innerHTML = `<div class="jd-root"><div class="jd-empty">Kein Job ausgewählt.</div></div>`;
        }

        /** Lädt Job-Detail anhand ID. */
        async load(jobId) {
            this._stopPoll();
            this._jobId = jobId;
            this._el.innerHTML = `<div class="jd-root"><div class="jd-empty">Lade…</div></div>`;

            const [job, steps] = await Promise.all([
                window.api.etl.jobs.get(jobId).catch(() => null),
                window.api.etl.jobs.steps(jobId).catch(() => []),
            ]);

            if (!job) {
                this._el.innerHTML = `<div class="jd-root"><div class="jd-empty">Job nicht gefunden.</div></div>`;
                return;
            }
            this._job   = job;
            this._steps = Array.isArray(steps) ? steps : [];
            this._render();
        }

        clear() {
            this._stopPoll();
            this._jobId = null;
            this._el.innerHTML = `<div class="jd-root"><div class="jd-empty">Kein Job ausgewählt.</div></div>`;
        }

        // ---- Render ----

        _render() {
            const j = this._job;
            const typeMap = { 'SCD2': 'jd-badge-purple', 'SCD1': 'jd-badge-ok', 'FULL': 'jd-badge-blue' };
            const typeBadge = j.historization_type
                ? `<span class="jd-badge ${typeMap[j.historization_type] || 'jd-badge-grey'}">${j.historization_type}</span>` : '';

            this._el.innerHTML = `
                <div class="jd-root">
                    <div class="jd-header">
                        <div class="jd-header-info">
                            <div class="jd-title">${j.job_name || j.name || `Job #${j.etl_job_id}`}</div>
                            <div class="jd-subtitle">${j.source_table_name || ''} → ${j.target_table_name || ''}</div>
                        </div>
                        <div class="jd-header-actions">
                            <button class="jd-btn jd-btn-run"    id="jd-btn-run">▶ Run</button>
                            <button class="jd-btn jd-btn-edit"   id="jd-btn-edit">✏</button>
                            <button class="jd-btn jd-btn-delete" id="jd-btn-delete">🗑</button>
                        </div>
                    </div>
                    <div class="jd-tabs">
                        <button class="jd-tab active" data-tab="info">Info</button>
                        <button class="jd-tab"        data-tab="steps">Steps (${this._steps.length})</button>
                        <button class="jd-tab"        data-tab="run">▶ Ausführen</button>
                        <button class="jd-tab"        data-tab="history">History</button>
                    </div>
                    <div class="jd-body" id="jd-body"></div>
                </div>`;

            // Tab-Switching
            this._el.querySelectorAll('.jd-tab').forEach(btn => {
                btn.addEventListener('click', () => {
                    this._el.querySelectorAll('.jd-tab').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this._loadTab(btn.dataset.tab);
                });
            });

            // Buttons
            this._el.querySelector('#jd-btn-run').addEventListener('click', () => {
                this._el.querySelectorAll('.jd-tab').forEach(b => b.classList.remove('active'));
                this._el.querySelector('[data-tab="run"]').classList.add('active');
                this._loadTab('run');
            });
            this._el.querySelector('#jd-btn-edit').addEventListener('click', () => {
                document.dispatchEvent(new CustomEvent('studio:job-edit', { detail: { job_id: this._jobId } }));
            });
            this._el.querySelector('#jd-btn-delete').addEventListener('click', () => this._deleteJob());

            this._loadTab('info');
        }

        _loadTab(tab) {
            const body = this._el.querySelector('#jd-body');
            if (!body) return;
            this._stopPoll();
            if      (tab === 'info')    this._renderInfo(body);
            else if (tab === 'steps')   this._renderSteps(body, null);
            else if (tab === 'run')     this._renderRun(body);
            else if (tab === 'history') this._renderHistory(body);
        }

        // ---- Tab: Info ----

        _renderInfo(body) {
            const j = this._job;
            const rows = [
                ['Job-ID',       j.etl_job_id],
                ['Status',       statusBadge(j.is_active === 'Y' ? 'SUCCESS' : 'PENDING').replace('✅ OK','✅ Aktiv').replace('○ Ausstehend','○ Inaktiv')],
                ['Typ',          j.historization_type ? `<span class="jd-badge jd-badge-purple">${j.historization_type}</span>` : '–'],
                ['Source',       j.source_table_name  || '–'],
                ['Target',       j.target_table_name  || '–'],
                ['Layer',        j.source_layer_name  ? `${j.source_layer_name} → ${j.target_layer_name || '?'}` : '–'],
                ['Template',     j.template_name      || '–'],
                ['Erstellt',     j.created_at         || '–'],
                ['Geändert',     j.updated_at         || '–'],
                ['Beschreibung', j.description        || '–'],
            ];
            body.innerHTML = `
                <table class="jd-meta-table">
                    ${rows.map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}
                </table>`;
        }

        // ---- Tab: Steps ----

        _renderSteps(body, runDetails) {
            if (!this._steps.length) {
                body.innerHTML = `<div class="jd-empty" style="height:auto;padding:20px">Keine Steps konfiguriert.</div>`;
                return;
            }
            body.innerHTML = `<div class="jd-step-list" id="jd-step-list"></div>`;
            const list = body.querySelector('#jd-step-list');
            this._steps.forEach(step => list.appendChild(this._buildStepEl(step, runDetails)));
        }

        _buildStepEl(step, runDetails) {
            let stepRun = null;
            if (runDetails?.step_runs) {
                stepRun = runDetails.step_runs.find(sr => sr.etl_job_step_id === step.etl_job_step_id);
            }

            let cls = '', statusHtml = statusBadge('PENDING');
            let metricsHtml = '', expanded = false;

            if (stepRun) {
                if (stepRun.was_skipped === 'Y') {
                    cls = 'skipped'; statusHtml = statusBadge('SKIPPED');
                } else if (stepRun.status === 'RUNNING') {
                    cls = 'running'; statusHtml = `<span class="jd-badge jd-badge-blue"><span class="jd-spinner"></span> Läuft</span>`;
                    expanded = true;
                } else if (stepRun.status === 'SUCCESS') {
                    cls = 'success'; statusHtml = statusBadge('SUCCESS');
                    metricsHtml = `
                        <div class="jd-step-metrics">
                            <div class="jd-step-metric"><span>Gelesen</span> <span>${stepRun.rows_read ?? '–'}</span></div>
                            <div class="jd-step-metric"><span>Eingefügt</span> <span>${stepRun.rows_inserted ?? '–'}</span></div>
                            <div class="jd-step-metric"><span>Aktualisiert</span> <span>${stepRun.rows_updated ?? '–'}</span></div>
                            <div class="jd-step-metric"><span>Dauer</span> <span>${formatDur(stepRun.duration_seconds)}</span></div>
                        </div>`;
                } else if (stepRun.status === 'FAILED') {
                    cls = 'failed'; statusHtml = statusBadge('FAILED');
                    expanded = true;
                    metricsHtml = `<div class="jd-step-error">${(stepRun.error_message || 'Unbekannter Fehler').replace(/</g,'&lt;')}</div>`;
                }
            }

            const div = document.createElement('div');
            div.className = `jd-step ${cls}`;
            div.innerHTML = `
                <div class="jd-step-header">
                    <span class="jd-step-num">${step.step_order}</span>
                    <span class="jd-step-name">${step.step_name}</span>
                    <span class="jd-step-cat">${step.step_category || ''}</span>
                    ${statusHtml}
                </div>
                <div class="jd-step-body" style="${expanded ? '' : 'display:none'}">
                    ${step.sql_template_path ? `<div style="margin-bottom:4px;color:#888">Template: ${step.sql_template_path}</div>` : ''}
                    ${metricsHtml}
                </div>`;

            // Toggle Expand
            div.querySelector('.jd-step-header').addEventListener('click', () => {
                const b = div.querySelector('.jd-step-body');
                b.style.display = b.style.display === 'none' ? '' : 'none';
            });
            return div;
        }

        // ---- Tab: Ausführen ----

        _renderRun(body) {
            body.innerHTML = `
                <div style="margin-bottom:12px">
                    <div class="jd-init-load">
                        <label>
                            <input type="checkbox" id="jd-init-chk" style="width:16px;height:16px">
                            ⚠️ Initial Load Mode – Zieltabelle vorher leeren
                        </label>
                        <div class="jd-init-load-warn" id="jd-init-warn">
                            <strong>🔥 Destruktive Operation!</strong> Alle Daten werden gelöscht. Nicht rückgängig machbar.
                        </div>
                    </div>

                    <div id="jd-progress-wrap" style="display:none">
                        <div class="jd-progress-bar"><div class="jd-progress-fill" id="jd-progress-fill" style="width:0%"></div></div>
                        <div class="jd-progress-text" id="jd-progress-text"></div>
                    </div>

                    <div style="display:flex;gap:8px;margin-top:10px">
                        <button class="jd-btn jd-btn-primary" id="jd-start-btn" style="flex:1;justify-content:center;padding:10px">▶ Job starten</button>
                        <button class="jd-btn jd-btn-secondary" id="jd-cancel-btn" style="display:none">■ Abbrechen</button>
                    </div>
                </div>

                <div class="jd-step-list" id="jd-run-steps"></div>`;

            // Initial-Load Toggle
            const chk  = body.querySelector('#jd-init-chk');
            const warn = body.querySelector('#jd-init-warn');
            const btn  = body.querySelector('#jd-start-btn');
            chk.addEventListener('change', () => {
                this._initialLoad = chk.checked;
                warn.style.display = chk.checked ? '' : 'none';
                btn.textContent = chk.checked ? '🔥 Initial Load starten' : '▶ Job starten';
                btn.style.background = chk.checked
                    ? 'linear-gradient(135deg,#f44336,#c62828)'
                    : 'linear-gradient(135deg,#667eea,#764ba2)';
            });

            // Steps als Preview rendern
            const stepsEl = body.querySelector('#jd-run-steps');
            this._steps.forEach(s => stepsEl.appendChild(this._buildStepEl(s, null)));

            btn.addEventListener('click', () => this._executeJob(body));
        }

        async _executeJob(body) {
            const btn      = body.querySelector('#jd-start-btn');
            const cancelBtn= body.querySelector('#jd-cancel-btn');
            const progWrap = body.querySelector('#jd-progress-wrap');
            const progFill = body.querySelector('#jd-progress-fill');
            const progText = body.querySelector('#jd-progress-text');

            if (!confirm(`Job "${this._job?.job_name || this._jobId}" starten?${this._initialLoad ? '\n\n⚠️ Initial Load Mode: Alle Daten werden gelöscht!' : ''}`)) return;

            btn.disabled = true;
            btn.innerHTML = `<span class="jd-spinner"></span> Starte…`;
            progWrap.style.display = '';
            progText.textContent = 'Job wird gestartet…';

            let runId = null;
            try {
                const result = await window.api.etl.jobs.execute(this._jobId);
                runId = result?.etl_job_run_id || result?.run_id;
                document.dispatchEvent(new CustomEvent('studio:job-started', {
                    detail: { job_id: this._jobId, run_id: runId }
                }));
                cancelBtn.style.display = '';
            } catch (e) {
                btn.disabled = false;
                btn.innerHTML = '▶ Job starten';
                progText.textContent = `❌ Fehler: ${e.message}`;
                return;
            }

            // Polling
            let polls = 0;
            const MAX_POLLS = 360; // 12 Minuten

            this._pollTimer = setInterval(async () => {
                polls++;
                if (polls > MAX_POLLS) {
                    this._stopPoll();
                    progText.textContent = 'Timeout – bitte manuell prüfen';
                    btn.disabled = false;
                    btn.innerHTML = '▶ Neu starten';
                    return;
                }

                try {
                    const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 1 });
                    if (!runs?.length) { progText.textContent = `Warte… (${polls * 2}s)`; return; }

                    const run = await window.api.etl.runs.get(runs[0].etl_job_run_id);

                    // Steps neu rendern
                    const stepsEl = body.querySelector('#jd-run-steps');
                    if (stepsEl) {
                        stepsEl.innerHTML = '';
                        this._steps.forEach(s => stepsEl.appendChild(this._buildStepEl(s, run)));
                    }

                    // Fortschritt
                    const done  = (run.step_runs || []).filter(s => s.status !== 'RUNNING').length;
                    const total = this._steps.length;
                    const pct   = total ? Math.round((done / total) * 100) : 0;
                    progFill.style.width = pct + '%';
                    progText.textContent = `${pct}% (${done}/${total} Steps) – ${formatDur(run.duration_seconds || polls * 2)}`;

                    if (run.status === 'SUCCESS' || run.status === 'FAILED') {
                        this._stopPoll();
                        cancelBtn.style.display = 'none';
                        btn.disabled = false;
                        btn.innerHTML = '▶ Erneut starten';
                        progFill.style.background = run.status === 'SUCCESS' ? '#4caf50' : '#f44336';
                        progFill.style.width = '100%';
                        progText.textContent = run.status === 'SUCCESS'
                            ? `✅ Erfolgreich in ${formatDur(run.duration_seconds)}`
                            : `❌ Fehlgeschlagen nach ${formatDur(run.duration_seconds)}`;

                        document.dispatchEvent(new CustomEvent('studio:job-finished', {
                            detail: { job_id: this._jobId, run_id: run.etl_job_run_id, status: run.status }
                        }));
                    }
                } catch (e) {
                    console.warn('[JobDetail] Polling-Fehler:', e.message);
                }
            }, 2000);

            cancelBtn.addEventListener('click', async () => {
                this._stopPoll();
                const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 1 }).catch(() => []);
                if (runs?.length) {
                    await window.api.etl.runs.cancel(runs[0].etl_job_run_id).catch(() => {});
                }
                cancelBtn.style.display = 'none';
                btn.disabled = false;
                btn.innerHTML = '▶ Job starten';
                progText.textContent = 'Abgebrochen.';
            }, { once: true });
        }

        // ---- Tab: History ----

        async _renderHistory(body) {
            body.innerHTML = `<div class="jd-empty" style="height:auto;padding:16px">Lade History…</div>`;
            const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 20 }).catch(() => []);

            if (!runs?.length) {
                body.innerHTML = `<div class="jd-empty" style="height:auto;padding:16px">Noch keine Runs.</div>`;
                return;
            }

            const dotColor = { SUCCESS: '#4caf50', FAILED: '#f44336', RUNNING: '#667eea' };
            body.innerHTML = `<div class="jd-run-list">
                ${runs.map(r => `
                    <div class="jd-run-item" data-run="${r.etl_job_run_id}">
                        <div class="jd-run-dot" style="background:${dotColor[r.status] || '#bbb'}"></div>
                        <div class="jd-run-info">
                            <div class="jd-run-id">Run #${r.etl_job_run_id}</div>
                            <div class="jd-run-time">${r.started_at || '–'}</div>
                        </div>
                        ${statusBadge(r.status)}
                        <div class="jd-run-dur">${formatDur(r.duration_seconds)}</div>
                    </div>`).join('')}
            </div>`;

            // Klick → Run-Details laden und Steps-Tab zeigen
            body.querySelectorAll('.jd-run-item').forEach(item => {
                item.addEventListener('click', async () => {
                    const runId  = parseInt(item.dataset.run);
                    const run    = await window.api.etl.runs.get(runId).catch(() => null);
                    if (!run) return;
                    this._el.querySelectorAll('.jd-tab').forEach(b => b.classList.remove('active'));
                    this._el.querySelector('[data-tab="steps"]').classList.add('active');
                    this._renderSteps(this._el.querySelector('#jd-body'), run);
                });
            });
        }

        // ---- Job löschen ----

        async _deleteJob() {
            if (!confirm(`Job #${this._jobId} wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
            await window.api.etl.jobs.delete(this._jobId).catch(e => alert(`Fehler: ${e.message}`));
            document.dispatchEvent(new CustomEvent('studio:job-deleted', { detail: { job_id: this._jobId } }));
            this.clear();
        }

        _stopPoll() {
            if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
        }
    }

    // ----------------------------------------------------------------
    // Custom Element <studio-job-detail>
    // ----------------------------------------------------------------

    class StudioJobDetail extends HTMLElement {
        connectedCallback() {
            injectStyles();
            this._detail = new JobDetail(this);
        }

        load(jobId) {
            if (!this._detail) this._detail = new JobDetail(this);
            this._detail.load(jobId);
        }

        clear() {
            if (this._detail) this._detail.clear();
        }
    }

    customElements.define('studio-job-detail', StudioJobDetail);
    window.JobDetail = JobDetail;

})();
