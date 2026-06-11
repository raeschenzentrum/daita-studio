/**
 * daita-studio – Job-Detail Komponente (C4)  –  Master-Detail Layout
 *
 * Toolbar: ▶ Starten | SQL Export | Als Template | Im Dashboard | 🗑
 * Tabs:    Info | Steps | ▶ Ausführen | History
 * Steps-Tab: Links Step-Liste (klickbar), rechts vollständiges Step-Detail-Panel
 *            Step-Detail: Informationen | Ausführung | Einstellungen | Parameter
 *
 * Verwendung:
 *   const detail = new JobDetail(containerEl);
 *   detail.load(42);
 *   detail.clear();
 *
 * Custom Events (auf document):
 *   studio:job-started    { detail: { job_id, run_id } }
 *   studio:job-finished   { detail: { job_id, run_id, status } }
 *   studio:job-deleted    { detail: { job_id } }
 *
 * Abhängigkeiten: api.js (window.api)
 */

(() => {
'use strict';

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────
const STYLE = `
    .jd-root { font-size: 0.88em; display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    .jd-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: #aaa; font-size: 0.92em; }

    /* Header */
    .jd-header { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; padding: 10px 14px; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    .jd-header-info { flex: 1; min-width: 0; }
    .jd-title { font-weight: 700; font-size: 1.0em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .jd-subtitle { font-size: 0.74em; opacity: 0.85; margin-top: 1px; }

    /* Toolbar */
    .jd-toolbar { display: flex; align-items: center; gap: 4px; padding: 5px 10px; border-bottom: 1px solid #e8e8e8; flex-wrap: wrap; flex-shrink: 0; background: #fafafa; }
    .jd-tbtn { padding: 4px 10px; border-radius: 5px; border: 1px solid #d0d0d0; background: #fff; cursor: pointer; font-size: 0.77em; color: #444; display: inline-flex; align-items: center; gap: 4px; transition: all 0.12s; white-space: nowrap; }
    .jd-tbtn:hover { background: #ede9fb; border-color: #667eea; color: #667eea; }
    .jd-tbtn:disabled { opacity: 0.45; cursor: not-allowed; }
    .jd-tbtn-run { background: linear-gradient(135deg, #2e7d32, #43a047); color: #fff; border: none; font-weight: 700; padding: 4px 14px; }
    .jd-tbtn-run:hover { opacity: 0.88; background: linear-gradient(135deg, #2e7d32, #43a047); color: #fff; }
    .jd-tbtn-del { border-color: #ef9a9a; color: #b71c1c; }
    .jd-tbtn-del:hover { background: #ffebee; border-color: #f44336; color: #b71c1c; }
    .jd-tbtn-sep { width: 1px; height: 16px; background: #ddd; flex-shrink: 0; margin: 0 2px; }

    /* Tabs */
    .jd-tabs { display: flex; border-bottom: 1px solid #e8e8e8; padding: 0 10px; flex-shrink: 0; overflow-x: auto; }
    .jd-tab { background: none; border: none; padding: 7px 11px; cursor: pointer; border-bottom: 2px solid transparent; color: #888; font-size: 0.8em; transition: color 0.12s; white-space: nowrap; }
    .jd-tab:hover { color: #667eea; }
    .jd-tab.active { color: #667eea; border-bottom-color: #667eea; font-weight: 600; }

    /* Body */
    .jd-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
    .jd-body-scroll { flex: 1; overflow-y: auto; padding: 12px 14px; }

    /* Meta-Tabelle */
    .jd-meta-table { width: 100%; border-collapse: collapse; }
    .jd-meta-table td { padding: 4px 0; vertical-align: top; }
    .jd-meta-table td:first-child { width: 110px; color: #888; font-size: 0.82em; }
    .jd-meta-table td:last-child { font-size: 0.85em; font-weight: 500; }

    /* Badge */
    .jd-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.74em; font-weight: 700; }
    .jd-badge-ok     { background: #e8f5e9; color: #2e7d32; }
    .jd-badge-err    { background: #ffebee; color: #c62828; }
    .jd-badge-blue   { background: #e3f2fd; color: #1565c0; }
    .jd-badge-purple { background: #f3e5f5; color: #7b1fa2; }
    .jd-badge-grey   { background: #f5f5f5; color: #616161; }

    /* Kategorie-Badges */
    .jd-cat { display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 0.68em; font-weight: 700; white-space: nowrap; }
    .jd-cat-delete  { background: #ffebee; color: #c62828; }
    .jd-cat-staging { background: #e3f2fd; color: #1565c0; }
    .jd-cat-sk      { background: #f3e5f5; color: #7b1fa2; }
    .jd-cat-scd2    { background: #e8eaf6; color: #3949ab; }
    .jd-cat-stats   { background: #e8f5e9; color: #2e7d32; }
    .jd-cat-tpt     { background: #fff3e0; color: #e65100; }
    .jd-cat-ddl     { background: #e0f2f1; color: #00695c; }
    .jd-cat-default { background: #f5f5f5; color: #616161; }

    /* ── Master-Detail ─────────────────────────────────────────────── */
    .jd-steps-layout { display: flex; flex: 1; overflow: hidden; min-height: 0; }
    .jd-step-list-panel  { width: 230px; flex-shrink: 0; border-right: 1px solid #e8e8e8; overflow-y: auto; display: flex; flex-direction: column; }
    .jd-step-detail-panel { flex: 1; overflow-y: auto; min-width: 0; }
    .jd-steps-layout.narrow .jd-step-list-panel  { width: 100%; border-right: none; }
    .jd-steps-layout.narrow .jd-step-list-panel.hidden { display: none; }
    .jd-steps-layout.narrow .jd-step-detail-panel:not(.visible) { display: none; }
    .jd-steps-layout.narrow .jd-step-detail-panel.visible { display: flex; flex-direction: column; flex: 1; }

    .jd-step-item { display: flex; align-items: flex-start; gap: 7px; padding: 7px 10px; cursor: pointer; border-bottom: 1px solid #f0f0f0; transition: background 0.1s; }
    .jd-step-item:hover { background: #f4f0ff; }
    .jd-step-item.active { background: #ede9fb; border-left: 3px solid #667eea; padding-left: 7px; }
    .jd-step-item.active .jd-si-num { background: #667eea; color: #fff; }
    .jd-step-item.jd-step-inactive { opacity: 0.45; }
    .jd-step-item.jd-step-inactive .jd-si-name { text-decoration: line-through; color: #999; }
    .jd-si-num  { width: 20px; height: 20px; border-radius: 50%; background: #e8eaf6; color: #3949ab; font-size: 0.68em; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
    .jd-si-info { flex: 1; min-width: 0; }
    .jd-si-name { font-size: 0.79em; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .jd-si-cat  { margin-top: 2px; }
    .jd-si-toggle { flex-shrink: 0; background: none; border: none; cursor: pointer; font-size: 1em; padding: 0 2px; line-height: 1; opacity: 0.7; transition: opacity 0.15s; }
    .jd-si-toggle:hover { opacity: 1; }
    .jd-step-list-footer { padding: 8px 10px; flex-shrink: 0; }
    .jd-step-add-btn { width: 100%; padding: 5px; border: 1px dashed #ccc; border-radius: 5px; background: transparent; cursor: pointer; font-size: 0.74em; color: #888; }
    .jd-step-add-btn:hover { border-color: #667eea; color: #667eea; background: #f4f0ff; }

    /* ── Step-Detail ───────────────────────────────────────────────── */
    .jd-sd-root { padding: 10px 12px; }
    .jd-sd-back { display: none; margin-bottom: 8px; padding: 4px 10px; border: 1px solid #ddd; border-radius: 5px; background: #fff; cursor: pointer; font-size: 0.76em; color: #667eea; }
    .jd-steps-layout.narrow .jd-sd-back { display: inline-flex; align-items: center; gap: 4px; }
    .jd-sd-empty { padding: 40px 20px; text-align: center; color: #bbb; font-size: 0.83em; }

    .jd-sd-section { margin-bottom: 10px; border: 1px solid #e8e8e8; border-radius: 7px; overflow: hidden; }
    .jd-sd-hdr { display: flex; align-items: center; justify-content: space-between; padding: 7px 11px; background: #f7f7fb; font-weight: 700; font-size: 0.79em; color: #555; cursor: pointer; user-select: none; }
    .jd-sd-hdr:hover { background: #ede9fb; }
    .jd-sd-body { padding: 8px 11px; }
    .jd-sd-body.hidden { display: none; }
    .jd-sd-row { display: flex; gap: 8px; padding: 3px 0; font-size: 0.79em; align-items: flex-start; }
    .jd-sd-key { width: 120px; flex-shrink: 0; color: #888; padding-top: 1px; }
    .jd-sd-val { flex: 1; font-weight: 500; word-break: break-all; }
    .jd-sd-mono { font-family: monospace; font-size: 0.9em; color: #333; }
    .jd-sd-actions { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
    .jd-sd-btn { padding: 4px 10px; border: 1px solid #d0d0d0; border-radius: 4px; background: #f8f8f8; cursor: pointer; font-size: 0.75em; color: #555; }
    .jd-sd-btn:hover { background: #ede9fb; border-color: #667eea; color: #667eea; }
    .jd-sd-btn-primary { background: #667eea; color: #fff; border-color: #667eea; }
    .jd-sd-btn-primary:hover { background: #5567d5; }
    .jd-sd-btn-green { background: #43a047; color: #fff; border-color: #43a047; }
    .jd-sd-btn-green:hover { background: #388e3c; }
    .jd-sql-pre { background: #1e1e2e; color: #cdd6f4; font-family: monospace; font-size: 0.73em; padding: 8px 10px; border-radius: 5px; overflow: auto; max-height: 180px; white-space: pre-wrap; word-break: break-all; margin-top: 8px; }

    /* Toggle */
    .jd-toggle-row { display: flex; align-items: center; gap: 10px; padding: 4px 0; font-size: 0.79em; }
    .jd-toggle-lbl  { width: 150px; flex-shrink: 0; color: #444; }
    .jd-toggle-wrap { position: relative; width: 34px; height: 18px; flex-shrink: 0; }
    .jd-toggle-wrap input { opacity: 0; width: 0; height: 0; position: absolute; }
    .jd-toggle-sl { position: absolute; inset: 0; background: #ccc; border-radius: 18px; cursor: pointer; transition: background 0.2s; }
    .jd-toggle-sl::before { position: absolute; content: ''; height: 12px; width: 12px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: transform 0.2s; }
    .jd-toggle-wrap input:checked + .jd-toggle-sl { background: #43a047; }
    .jd-toggle-wrap input:checked + .jd-toggle-sl::before { transform: translateX(16px); }
    .jd-toggle-hint { font-size: 0.73em; color: #aaa; }
    .jd-toggle-warn .jd-toggle-lbl { color: #b71c1c; font-weight: 600; }
    .jd-toggle-warn .jd-toggle-wrap input:checked + .jd-toggle-sl { background: #b71c1c; }
    .jd-save-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
    .jd-save-msg { font-size: 0.73em; color: #888; }
    .jd-save-msg.ok  { color: #43a047; }
    .jd-save-msg.err { color: #c62828; }

    /* Parameter-Tabelle */
    .jd-params-tbl { width: 100%; border-collapse: collapse; font-size: 0.77em; margin-top: 4px; }
    .jd-params-tbl th, .jd-params-tbl td { padding: 3px 5px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }
    .jd-params-tbl th { background: #f8f8f8; font-weight: 700; color: #666; text-align: left; }
    .jd-params-tbl tr:hover td { background: #f8f4ff; }
    .jd-p-key { width: 38%; font-family: monospace; color: #333; }
    .jd-p-val { width: 57%; }
    .jd-p-inp { width: 100%; border: 1px solid transparent; border-radius: 3px; padding: 2px 4px; font-size: 1em; font-family: monospace; background: transparent; color: #333; }
    .jd-p-inp:focus { border-color: #667eea; background: #fff; outline: none; }
    .jd-p-del { width: 20px; text-align: center; }
    .jd-p-del-btn { background: none; border: none; cursor: pointer; color: #ddd; font-size: 0.9em; padding: 0; line-height: 1; }
    .jd-p-del-btn:hover { color: #f44336; }
    .jd-params-footer { display: flex; align-items: center; gap: 8px; margin-top: 8px; }

    /* Run-Tab */
    .jd-run-body { flex: 1; overflow-y: auto; padding: 12px 14px; }
    .jd-progress-bar  { height: 4px; background: #e8eaf6; border-radius: 2px; margin: 10px 0; }
    .jd-progress-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 2px; transition: width 0.4s; }
    .jd-progress-text { font-size: 0.77em; color: #888; text-align: center; }
    .jd-init-load { background: #fff8e1; border-left: 3px solid #ff9800; border-radius: 4px; padding: 8px 10px; margin: 8px 0; font-size: 0.82em; }
    .jd-init-load label { cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; color: #e65100; }
    .jd-init-load-warn { display: none; background: #ffebee; border-radius: 4px; padding: 8px; margin-top: 6px; color: #c62828; font-size: 0.83em; }
    .jd-btn { padding: 5px 12px; border-radius: 5px; border: none; cursor: pointer; font-size: 0.82em; font-weight: 600; transition: opacity 0.15s; display: inline-flex; align-items: center; gap: 5px; }
    .jd-btn:hover { opacity: 0.85; }
    .jd-btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .jd-btn-primary   { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; }
    .jd-btn-secondary { background: #f0f0f0; color: #444; border: 1px solid #ddd; }

    /* Run-Steps (Polling-Visualisierung) */
    .jd-step-list { display: flex; flex-direction: column; gap: 5px; }
    .jd-step { border: 1px solid #e8e8e8; border-radius: 7px; overflow: hidden; transition: border-color 0.15s; }
    .jd-step.running { border-color: #667eea; }
    .jd-step.success { border-color: #4caf50; }
    .jd-step.failed  { border-color: #f44336; }
    .jd-step.skipped { opacity: 0.6; }
    .jd-step-header  { display: flex; align-items: center; gap: 8px; padding: 7px 10px; cursor: pointer; user-select: none; }
    .jd-step-header:hover { background: #fafafa; }
    .jd-step-num  { width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.74em; background: #e8eaf6; color: #3949ab; }
    .jd-step.running .jd-step-num { background: #e3f2fd; color: #1565c0; }
    .jd-step.success .jd-step-num { background: #e8f5e9; color: #2e7d32; }
    .jd-step.failed  .jd-step-num { background: #ffebee; color: #c62828; }
    .jd-step-name { flex: 1; font-weight: 600; font-size: 0.84em; }
    .jd-step-cat  { font-size: 0.72em; color: #888; }
    .jd-step-body { padding: 0 10px 8px 38px; font-size: 0.79em; color: #666; }
    .jd-step-metrics { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 4px; }
    .jd-step-metric span:first-child { color: #888; }
    .jd-step-metric span:last-child  { font-weight: 600; }
    .jd-step-error { background: #fff0f0; border-radius: 4px; padding: 6px 8px; margin-top: 4px; color: #c62828; font-family: monospace; font-size: 0.82em; white-space: pre-wrap; word-break: break-all; }

    /* History */
    .jd-run-list { display: flex; flex-direction: column; gap: 5px; }
    .jd-run-item { display: flex; align-items: center; gap: 8px; border: 1px solid #e8e8e8; border-radius: 6px; padding: 7px 10px; cursor: pointer; transition: background 0.1s; }
    .jd-run-item:hover { background: #f8f8ff; }
    .jd-run-dot  { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
    .jd-run-info { flex: 1; }
    .jd-run-id   { font-weight: 600; font-size: 0.82em; }
    .jd-run-time { font-size: 0.74em; color: #888; }
    .jd-run-dur  { font-size: 0.79em; color: #666; }

    /* Spinner */
    @keyframes jd-spin { to { transform: rotate(360deg); } }
    .jd-spinner { width: 13px; height: 13px; border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff; border-radius: 50%; animation: jd-spin 0.8s linear infinite; display: inline-block; }

    /* Template-Editor Modal */
    .jd-tpl-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 24px; }
    .jd-tpl-modal { background: #fff; border-radius: 10px; box-shadow: 0 8px 40px rgba(0,0,0,0.35); display: flex; flex-direction: column; width: 100%; max-width: 860px; height: 78vh; }
    .jd-tpl-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid #e8e8e8; flex-shrink: 0; background: #f7f7fb; border-radius: 10px 10px 0 0; }
    .jd-tpl-path { flex: 1; font-family: monospace; font-size: 0.83em; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .jd-tpl-close { background: none; border: none; cursor: pointer; font-size: 1.1em; color: #888; line-height: 1; padding: 2px 6px; border-radius: 4px; }
    .jd-tpl-close:hover { background: #f0f0f0; color: #333; }
    .jd-tpl-content { flex: 1; display: flex; overflow: hidden; min-height: 0; }
    .jd-tpl-textarea { flex: 1; width: 100%; height: 100%; border: none; outline: none; padding: 12px 14px; font-family: 'Courier New', monospace; font-size: 0.82em; line-height: 1.5; resize: none; background: #1e1e2e; color: #cdd6f4; tab-size: 4; }
    .jd-tpl-footer { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-top: 1px solid #e8e8e8; flex-shrink: 0; background: #fafafa; border-radius: 0 0 10px 10px; }
    .jd-tpl-status { flex: 1; font-size: 0.79em; }
`;

function injectStyles() {
    if (document.getElementById('studio-jd-style')) return;
    const s = document.createElement('style');
    s.id = 'studio-jd-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
}

// ─────────────────────────────────────────────────────────────────────────────
// Hilfsfunktionen
// ─────────────────────────────────────────────────────────────────────────────

function formatDur(secs) {
    if (secs == null) return '–';
    secs = Math.round(secs);
    if (secs < 60) return `${secs}s`;
    const m = Math.floor(secs / 60), s = secs % 60;
    return m < 60 ? `${m}m ${s}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function statusBadge(status) {
    const map = {
        SUCCESS: ['jd-badge-ok',  '✅ OK'],
        FAILED:  ['jd-badge-err', '❌ Fehler'],
        RUNNING: ['jd-badge-blue','⟳ Läuft'],
        STARTING:['jd-badge-blue','⟳ Startet'],
        SKIPPED: ['jd-badge-grey','⤳ Skip'],
        PENDING: ['jd-badge-grey','○ Ausstehend'],
    };
    const [cls, lbl] = map[status] || ['jd-badge-grey', status || '?'];
    return `<span class="jd-badge ${cls}">${lbl}</span>`;
}

function catCls(cat) {
    if (!cat) return 'jd-cat-default';
    const c = cat.toUpperCase();
    if (c.includes('DELETE'))   return 'jd-cat-delete';
    if (c.includes('STAGING'))  return 'jd-cat-staging';
    if (c.includes('SK_GEN') || c.includes('_SK') || c.includes('SURROGATE')) return 'jd-cat-sk';
    if (c.includes('SCD') || c.includes('IDENTIFY') || c.includes('CLOSE') || c.includes('INSERT') || c.includes('CHANGED')) return 'jd-cat-scd2';
    if (c.includes('STAT'))     return 'jd-cat-stats';
    if (c.includes('TPT') || c.includes('LOAD')) return 'jd-cat-tpt';
    if (c.includes('DDL') || c.includes('CREATE')) return 'jd-cat-ddl';
    return 'jd-cat-default';
}

function catBadge(cat) {
    return `<span class="jd-cat ${catCls(cat)}">${esc(cat || '—')}</span>`;
}

function parseParams(step) {
    if (!step?.parameters) return {};
    if (typeof step.parameters === 'object') return { ...step.parameters };
    try { return JSON.parse(step.parameters); } catch { return {}; }
}

function yesNo(val) {
    return String(val || '').trim().toUpperCase() === 'Y';
}

// ─────────────────────────────────────────────────────────────────────────────
// Kern-Klasse JobDetail
// ─────────────────────────────────────────────────────────────────────────────

class JobDetail {
    constructor(container) {
        injectStyles();
        this._el          = container;
        this._jobId       = null;
        this._job         = null;
        this._steps       = [];
        this._pollTimer   = null;
        this._initialLoad = false;
        this._el.innerHTML = `<div class="jd-root"><div class="jd-empty">Kein Job ausgewählt.</div></div>`;
    }

    // ── Public API ──────────────────────────────────────────────────

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

    // ── Shell ───────────────────────────────────────────────────────

    _render() {
        const j = this._job;
        this._el.innerHTML = `
            <div class="jd-root">
                <div class="jd-header">
                    <div class="jd-header-info">
                        <div class="jd-title">${esc(j.job_name || `Job #${j.etl_job_id}`)}</div>
                        <div class="jd-subtitle">${esc(j.source_table_name || '')} → ${esc(j.target_table_name || '')}</div>
                    </div>
                    ${j.historization_type ? `<span class="jd-badge jd-badge-purple">${esc(j.historization_type)}</span>` : ''}
                </div>
                <div class="jd-toolbar">
                    <button class="jd-tbtn jd-tbtn-run" id="jd-tb-run">▶ Starten</button>
                    <div class="jd-tbtn-sep"></div>
                    <button class="jd-tbtn" id="jd-tb-sql">⬇ SQL Export</button>
                    <button class="jd-tbtn" id="jd-tb-tpl">📋 Als Template</button>
                    <button class="jd-tbtn" id="jd-tb-dash">📊 Im Dashboard</button>
                    <div class="jd-tbtn-sep"></div>
                    <button class="jd-tbtn jd-tbtn-del" id="jd-tb-del">🗑 Löschen</button>
                </div>
                <div class="jd-tabs">
                    <button class="jd-tab" data-tab="info">Info</button>
                    <button class="jd-tab active" data-tab="steps">Steps (${this._steps.length})</button>
                    <button class="jd-tab" data-tab="run">▶ Ausführen</button>
                    <button class="jd-tab" data-tab="history">History</button>
                </div>
                <div class="jd-body" id="jd-body"></div>
            </div>`;

        this._el.querySelectorAll('.jd-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                this._el.querySelectorAll('.jd-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this._loadTab(btn.dataset.tab);
            });
        });

        this._q('#jd-tb-run').addEventListener('click',  () => this._switchTab('run'));
        this._q('#jd-tb-del').addEventListener('click',  () => this._deleteJob());
        this._q('#jd-tb-sql').addEventListener('click',  () => this._sqlExport());
        this._q('#jd-tb-tpl').addEventListener('click',  () => this._saveAsTemplate());
        this._q('#jd-tb-dash').addEventListener('click', () => { window.location.href = '/index.html'; });

        this._loadTab('steps');
    }

    _q(sel) { return this._el.querySelector(sel); }

    _switchTab(name) {
        this._el.querySelectorAll('.jd-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
        this._loadTab(name);
    }

    _loadTab(tab) {
        const body = this._q('#jd-body');
        if (!body) return;
        this._stopPoll();
        if      (tab === 'info')    this._renderInfo(body);
        else if (tab === 'steps')   this._renderStepsMasterDetail(body);
        else if (tab === 'run')     this._renderRun(body);
        else if (tab === 'history') this._renderHistory(body);
    }

    // ── Tab: Info ───────────────────────────────────────────────────

    _renderInfo(body) {
        const j = this._job;
        const rows = [
            ['Job-ID',    j.etl_job_id],
            ['Status',    j.is_active === 'Y' ? '<span class="jd-badge jd-badge-ok">✅ Aktiv</span>' : '<span class="jd-badge jd-badge-grey">○ Inaktiv</span>'],
            ['Typ',       j.historization_type ? `<span class="jd-badge jd-badge-purple">${esc(j.historization_type)}</span>` : '–'],
            ['Source',    esc(j.source_table_name  || '–')],
            ['Target',    esc(j.target_table_name  || '–')],
            ['Layer',     j.source_layer_name ? `${esc(j.source_layer_name)} → ${esc(j.target_layer_name || '?')}` : '–'],
            ['Template',  esc(j.template_name || '–')],
            ['Steps',     this._steps.length],
            ['Erstellt',  esc(j.created_at || j.create_timestamp || '–')],
            ['Geändert',  esc(j.updated_at  || j.last_alter_timestamp || '–')],
        ];
        body.innerHTML = `<div class="jd-body-scroll"><table class="jd-meta-table">${
            rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')
        }</table></div>`;
    }

    // ── Tab: Steps – Master-Detail ───────────────────────────────────

    _renderStepsMasterDetail(body) {
        body.innerHTML = `
            <div class="jd-steps-layout" id="jd-steps-layout">
                <div class="jd-step-list-panel" id="jd-step-list-panel">
                    <div id="jd-step-items"></div>
                    <div class="jd-step-list-footer">
                        <button class="jd-step-add-btn" id="jd-step-add">＋ Step hinzufügen</button>
                    </div>
                </div>
                <div class="jd-step-detail-panel" id="jd-step-detail-panel">
                    <div class="jd-sd-empty">← Step auswählen</div>
                </div>
            </div>`;

        const layout      = this._q('#jd-steps-layout');
        const listPanel   = this._q('#jd-step-list-panel');
        const detailPanel = this._q('#jd-step-detail-panel');
        const itemsEl     = this._q('#jd-step-items');

        this._steps.forEach(step => {
            const isActive = (step.is_active || 'Y').trim() === 'Y';
            const item = document.createElement('div');
            item.className = 'jd-step-item' + (isActive ? '' : ' jd-step-inactive');
            item.dataset.stepId = step.etl_job_step_id;
            item.innerHTML = `
                <div class="jd-si-num">${step.step_order}</div>
                <div class="jd-si-info">
                    <div class="jd-si-name">${esc(step.step_name)}</div>
                    <div class="jd-si-cat">${catBadge(step.step_category)}</div>
                </div>
                <button class="jd-si-toggle" title="Aktiv/Inaktiv umschalten" data-step-id="${step.etl_job_step_id}">${isActive ? '🟢' : '⭕'}</button>`;

            // Toggle-Button: sofort IS_ACTIVE umschalten, ohne den Step-Detail zu öffnen
            const toggleBtn = item.querySelector('.jd-si-toggle');
            toggleBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const newActive = (step.is_active || 'Y').trim() === 'Y' ? 'N' : 'Y';
                toggleBtn.textContent = '⏳';
                try {
                    await window.api.jobs.updateStep(this._jobId, step.etl_job_step_id, { is_active: newActive });
                    step.is_active = newActive;
                    toggleBtn.textContent = newActive === 'Y' ? '🟢' : '⭕';
                    item.classList.toggle('jd-step-inactive', newActive !== 'Y');
                    // Falls Step-Detail gerade offen → Checkbox synchronisieren
                    const chk = detailPanel.querySelector('#jd-chk-active');
                    if (chk) chk.checked = newActive === 'Y';
                } catch (err) {
                    toggleBtn.textContent = (step.is_active || 'Y').trim() === 'Y' ? '🟢' : '⭕';
                    alert('Fehler: ' + err.message);
                }
            });

            item.addEventListener('click', () => {
                itemsEl.querySelectorAll('.jd-step-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                if (layout.classList.contains('narrow')) {
                    listPanel.classList.add('hidden');
                    detailPanel.classList.add('visible');
                }
                this._renderStepDetail(detailPanel, step);
            });
            itemsEl.appendChild(item);
        });

        // Ersten Step automatisch selektieren
        if (this._steps.length) itemsEl.querySelector('.jd-step-item')?.click();

        this._q('#jd-step-add').addEventListener('click', () => this._addStepDialog());

        // Responsive: narrow wenn Container < 480px
        const ro = new ResizeObserver(entries => {
            layout.classList.toggle('narrow', entries[0].contentRect.width < 480);
        });
        ro.observe(body);
    }

    // ── Step-Detail rendern ─────────────────────────────────────────

    _renderStepDetail(panel, step) {
        panel.innerHTML = `<div class="jd-sd-root">
            <button class="jd-sd-back" id="jd-sd-back">← Zurück</button>
            ${this._secInfo(step)}
            ${this._secRun(step)}
            ${this._secSettings(step)}
            ${this._secParams(step)}
        </div>`;

        // Zurück (narrow)
        panel.querySelector('#jd-sd-back')?.addEventListener('click', () => {
            panel.classList.remove('visible');
            this._q('#jd-step-list-panel')?.classList.remove('hidden');
        });

        // Accordion-Toggle
        panel.querySelectorAll('.jd-sd-hdr').forEach(hdr => {
            hdr.addEventListener('click', () => {
                const b = hdr.nextElementSibling;
                b.classList.toggle('hidden');
                hdr.querySelector('.jd-chevron').textContent = b.classList.contains('hidden') ? '▸' : '▾';
            });
        });

        this._initSecRun(panel, step);
        this._initSecSettings(panel, step);
        this._initSecParams(panel, step);
    }

    _section(icon, title, bodyHtml) {
        return `<div class="jd-sd-section">
            <div class="jd-sd-hdr"><span>${icon} ${title}</span><span class="jd-chevron">▾</span></div>
            <div class="jd-sd-body">${bodyHtml}</div>
        </div>`;
    }

    // Sektion: Step Informationen
    _secInfo(step) {
        return this._section('🔧', 'Step Informationen', `
            <div class="jd-sd-row"><span class="jd-sd-key">Step ID</span>     <span class="jd-sd-val">${esc(step.etl_job_step_id)}</span></div>
            <div class="jd-sd-row"><span class="jd-sd-key">Name</span>        <span class="jd-sd-val">${esc(step.step_name)}</span></div>
            <div class="jd-sd-row"><span class="jd-sd-key">Reihenfolge</span> <span class="jd-sd-val">${esc(step.step_order)}</span></div>
            <div class="jd-sd-row"><span class="jd-sd-key">Kategorie</span>   <span class="jd-sd-val">${catBadge(step.step_category)}</span></div>
            <div class="jd-sd-row"><span class="jd-sd-key">Gehört zu</span>   <span class="jd-sd-val">${esc(this._job?.job_name || `Job #${this._jobId}`)}</span></div>`);
    }

    // Sektion: Ausführung
    _secRun(step) {
        const hasTemplate = !!step.sql_template_path;
        const hasInline   = !!step.sql_inline;
        const typ = hasTemplate ? '📄 SQL Template' : (hasInline ? '✏ SQL Inline' : '—');
        return this._section('⚙', 'Ausführung', `
            <div class="jd-sd-row"><span class="jd-sd-key">Ausführung</span> <span class="jd-sd-val">${typ}</span></div>
            ${hasTemplate ? `<div class="jd-sd-row"><span class="jd-sd-key">Template Pfad</span><span class="jd-sd-val jd-sd-mono">${esc(step.sql_template_path)}</span></div>` : ''}
            <div class="jd-sd-actions">
                ${hasTemplate ? `<button class="jd-sd-btn" id="jd-btn-tpl-edit">✏ Template bearbeiten</button>` : ''}
                <button class="jd-sd-btn jd-sd-btn-primary" id="jd-btn-param-preview">▶ Mit Parametern anzeigen</button>
            </div>
            <div id="jd-sql-preview-wrap"></div>`);
    }

    _initSecRun(panel, step) {
        panel.querySelector('#jd-btn-tpl-edit')?.addEventListener('click', () => {
            this._openTemplateEditor(step.sql_template_path);
        });
        panel.querySelector('#jd-btn-param-preview')?.addEventListener('click', async () => {
            const wrap = panel.querySelector('#jd-sql-preview-wrap');
            if (wrap.innerHTML) { wrap.innerHTML = ''; return; }

            // sql_inline direkt rendern (client-seitig reicht)
            if (step.sql_inline) {
                const params = parseParams(step);
                let sql = step.sql_inline;
                for (const [k, v] of Object.entries(params)) {
                    const val = Array.isArray(v) ? v.join(', ') : String(v ?? '');
                    sql = sql.replace(new RegExp(`\\$\\{${k}\\}|\\{\\{${k}\\}\\}`, 'g'), val);
                }
                wrap.innerHTML = `<div class="jd-sql-pre">${esc(sql)}</div>`;
                return;
            }

            // Template vom Server laden und server-seitig rendern
            if (!step.sql_template_path) {
                wrap.innerHTML = `<div class="jd-sql-pre" style="color:#888">-- Kein SQL hinterlegt</div>`;
                return;
            }

            wrap.innerHTML = `<div class="jd-sql-pre" style="color:#888">⏳ Lade…</div>`;
            try {
                const params = parseParams(step);
                const result = await window.api.etl.sqlTemplates.render(step.sql_template_path, params);
                if (!result.success && result.error) {
                    wrap.innerHTML = `<div class="jd-sql-pre" style="color:#e57373">-- Fehler: ${esc(result.error)}</div>`;
                    return;
                }
                let html = `<div class="jd-sql-pre">${esc(result.rendered_sql)}</div>`;
                if (result.missing_parameters?.length) {
                    html += `<div style="margin-top:6px;padding:6px 10px;background:#fff3e0;color:#e65100;font-size:11px;border-radius:4px;">
                        ⚠ Fehlende Parameter: ${result.missing_parameters.join(', ')}
                    </div>`;
                }
                wrap.innerHTML = html;
            } catch (e) {
                wrap.innerHTML = `<div class="jd-sql-pre" style="color:#e57373">-- Fehler: ${esc(e.message)}</div>`;
            }
        });
    }

    // Template-Editor Modal
    async _openTemplateEditor(path) {
        const overlay = document.createElement('div');
        overlay.className = 'jd-tpl-overlay';
        overlay.innerHTML = `
            <div class="jd-tpl-modal">
                <div class="jd-tpl-header">
                    <span>📄</span>
                    <span class="jd-tpl-path">${esc(path)}</span>
                    <button class="jd-tpl-close" id="jd-tpl-close">✕</button>
                </div>
                <div class="jd-tpl-content">
                    <textarea class="jd-tpl-textarea" id="jd-tpl-ta" spellcheck="false" placeholder="Lade…"></textarea>
                </div>
                <div class="jd-tpl-footer">
                    <span class="jd-tpl-status" id="jd-tpl-status"></span>
                    <button class="jd-sd-btn" id="jd-tpl-cancel">Abbrechen</button>
                    <button class="jd-sd-btn jd-sd-btn-primary" id="jd-tpl-save">💾 Speichern</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        const ta     = overlay.querySelector('#jd-tpl-ta');
        const status = overlay.querySelector('#jd-tpl-status');
        const close  = () => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); };

        overlay.querySelector('#jd-tpl-close').addEventListener('click', close);
        overlay.querySelector('#jd-tpl-cancel').addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

        // Template laden
        try {
            ta.value = 'Lade…';
            ta.disabled = true;
            const result = await api.etl.sqlTemplates.get(path);
            ta.disabled = false;
            if (result && result.exists) {
                ta.value = result.content;
            } else {
                ta.value = '';
                status.textContent = 'Template-Datei nicht gefunden – wird beim Speichern angelegt.';
                status.style.color = '#e65100';
            }
            ta.focus();
        } catch (e) {
            ta.disabled = false;
            ta.value = '';
            status.textContent = `Fehler beim Laden: ${e.message}`;
            status.style.color = '#c62828';
        }

        // Speichern
        overlay.querySelector('#jd-tpl-save').addEventListener('click', async () => {
            const saveBtn = overlay.querySelector('#jd-tpl-save');
            saveBtn.disabled = true;
            status.textContent = 'Speichert…';
            status.style.color = '#888';
            try {
                await api.etl.sqlTemplates.update(path, ta.value);
                status.textContent = '✓ Gespeichert';
                status.style.color = '#43a047';
            } catch (e) {
                status.textContent = `Fehler: ${e.message}`;
                status.style.color = '#c62828';
            } finally {
                saveBtn.disabled = false;
            }
        });
    }

    // Sektion: Einstellungen
    _secSettings(step) {
        const tog = (val, id, lbl, hint, warn=false) => `
            <div class="jd-toggle-row ${warn ? 'jd-toggle-warn' : ''}">
                <span class="jd-toggle-lbl">${lbl}</span>
                <label class="jd-toggle-wrap">
                    <input type="checkbox" id="${id}" ${yesNo(val) ? 'checked' : ''}>
                    <span class="jd-toggle-sl"></span>
                </label>
                <span class="jd-toggle-hint">${hint}</span>
            </div>`;
        return this._section('🔒', 'Einstellungen', `
            ${tog(step.is_active,         'jd-chk-active',   'Aktiv',               'Step wird ausgeführt')}
            ${tog(step.is_critical,       'jd-chk-critical', 'Kritisch (Abbruch)',   'Job bricht bei Fehler ab', true)}
            ${tog(step.skip_on_empty,     'jd-chk-skip',     'Skip wenn leer',       'Überspringen wenn Quelltabelle leer')}
            ${tog(step.rollback_on_error, 'jd-chk-rollback', 'Rollback bei Fehler',  'Transaktion zurückrollen')}
            <div class="jd-save-row">
                <button class="jd-sd-btn jd-sd-btn-green" id="jd-settings-save">💾 Speichern</button>
                <span class="jd-save-msg" id="jd-settings-msg"></span>
            </div>`);
    }

    _initSecSettings(panel, step) {
        const btn = panel.querySelector('#jd-settings-save');
        const msg = panel.querySelector('#jd-settings-msg');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            const yn = id => panel.querySelector(`#${id}`)?.checked ? 'Y' : 'N';
            btn.disabled = true;
            msg.textContent = 'Speichert…'; msg.className = 'jd-save-msg';
            try {
                await window.api.jobs.updateStep(this._jobId, step.etl_job_step_id, {
                    is_active:         yn('jd-chk-active'),
                    is_critical:       yn('jd-chk-critical'),
                    skip_on_empty:     yn('jd-chk-skip'),
                    rollback_on_error: yn('jd-chk-rollback'),
                });
                step.is_active = yn('jd-chk-active');
                step.is_critical = yn('jd-chk-critical');
                step.skip_on_empty = yn('jd-chk-skip');
                step.rollback_on_error = yn('jd-chk-rollback');
                // Toggle-Button in der Liste synchronisieren
                const listItem = this._el.querySelector(`[data-step-id="${step.etl_job_step_id}"]`);
                if (listItem) {
                    const tb = listItem.querySelector('.jd-si-toggle');
                    if (tb) tb.textContent = step.is_active === 'Y' ? '🟢' : '⭕';
                    listItem.classList.toggle('jd-step-inactive', step.is_active !== 'Y');
                }
                msg.textContent = '✅ Gespeichert'; msg.className = 'jd-save-msg ok';
            } catch (e) {
                msg.textContent = `❌ ${e.message}`; msg.className = 'jd-save-msg err';
            } finally {
                btn.disabled = false;
                setTimeout(() => { msg.textContent = ''; }, 4000);
            }
        });
    }

    // Sektion: Parameter
    _secParams(step) {
        const params = parseParams(step);
        const rows = Object.entries(params);
        const tbody = rows.length
            ? rows.map(([k, v]) => {
                const val = Array.isArray(v) ? v.join(', ') : String(v ?? '');
                return `<tr>
                    <td class="jd-p-key">${esc(k)}</td>
                    <td class="jd-p-val"><input class="jd-p-inp" data-key="${esc(k)}" value="${esc(val)}"></td>
                    <td class="jd-p-del"><button class="jd-p-del-btn" data-key="${esc(k)}">✕</button></td>
                </tr>`;
            }).join('')
            : `<tr><td colspan="3" style="text-align:center;color:#bbb;padding:8px;font-size:0.85em">Keine Parameter</td></tr>`;
        return this._section('📊', 'Parameter', `
            <table class="jd-params-tbl">
                <thead><tr><th>Key</th><th>Wert</th><th></th></tr></thead>
                <tbody id="jd-params-tbody">${tbody}</tbody>
            </table>
            <div class="jd-params-footer">
                <button class="jd-sd-btn" id="jd-param-add">＋ Neu</button>
                <button class="jd-sd-btn jd-sd-btn-green" id="jd-param-save">💾 Speichern</button>
                <span class="jd-save-msg" id="jd-param-msg"></span>
            </div>`);
    }

    _initSecParams(panel, step) {
        const tbody = panel.querySelector('#jd-params-tbody');
        if (!tbody) return;

        tbody.addEventListener('click', e => {
            const btn = e.target.closest('.jd-p-del-btn');
            if (btn) btn.closest('tr').remove();
        });

        panel.querySelector('#jd-param-add')?.addEventListener('click', () => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="jd-p-key"><input class="jd-p-inp" placeholder="KEY" style="font-weight:600"></td>
                <td class="jd-p-val"><input class="jd-p-inp" placeholder="Wert"></td>
                <td class="jd-p-del"><button class="jd-p-del-btn">✕</button></td>`;
            tbody.appendChild(tr);
            tr.querySelector('input').focus();
        });

        const saveBtn = panel.querySelector('#jd-param-save');
        const msg     = panel.querySelector('#jd-param-msg');
        saveBtn?.addEventListener('click', async () => {
            const params = {};
            tbody.querySelectorAll('tr').forEach(tr => {
                const inputs = tr.querySelectorAll('input');
                if (inputs.length === 2) {
                    // Neu-Zeile (keine data-key)
                    const k = inputs[0].value.trim();
                    if (k) params[k] = inputs[1].value;
                } else {
                    const keyEl = tr.querySelector('[data-key]');
                    const valEl = tr.querySelector('.jd-p-inp');
                    if (keyEl) params[keyEl.dataset.key] = valEl?.value ?? '';
                }
            });
            saveBtn.disabled = true;
            msg.textContent = 'Speichert…'; msg.className = 'jd-save-msg';
            try {
                await window.api.jobs.updateStep(this._jobId, step.etl_job_step_id, { parameters: params });
                step.parameters = params;
                msg.textContent = '✅ Gespeichert'; msg.className = 'jd-save-msg ok';
            } catch (e) {
                msg.textContent = `❌ ${e.message}`; msg.className = 'jd-save-msg err';
            } finally {
                saveBtn.disabled = false;
                setTimeout(() => { msg.textContent = ''; }, 4000);
            }
        });
    }

    // ── Step hinzufügen ─────────────────────────────────────────────

    _addStepDialog() {
        const name  = prompt('Step-Name:', '');
        if (!name) return;
        const order = prompt('Reihenfolge (Zahl):', String((this._steps.length + 1) * 10));
        if (!order) return;
        const cat   = prompt('Kategorie (z.B. STAGING, SCD_TYPE2_INSERT, STATISTICS):', '');
        window.api.jobs.addStep(this._jobId, {
            step_name:     name,
            step_order:    parseInt(order) || 10,
            step_category: cat || 'CUSTOM',
        }).then(() => this.load(this._jobId))
          .catch(e => alert(`Fehler: ${e.message}`));
    }

    // ── Toolbar-Aktionen ────────────────────────────────────────────

    async _sqlExport() {
        try {
            const result = await window.api.etl.jobs.sqlExport(this._jobId);
            const blob = new Blob([typeof result === 'string' ? result : JSON.stringify(result, null, 2)], { type: 'text/plain' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${this._job?.job_name || 'job'}_export.sql`;
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            alert(`SQL Export fehlgeschlagen: ${e.message}`);
        }
    }

    async _saveAsTemplate() {
        const name = prompt('Template-Name:', this._job?.job_name || '');
        if (!name) return;
        const overwrite = false;
        try {
            const params = new URLSearchParams({ template_name: name });
            const base = (window.METADAITA_CONFIG?.backend_url || '') + '/api';
            const r = await fetch(`${base}/templates/save-job/${this._jobId}?${params}`, { method: 'POST' });
            const json = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(json.detail || `HTTP ${r.status}`);
            if (json.exists) {
                const ow = confirm(`Template "${name}" existiert bereits. Überschreiben?`);
                if (!ow) return;
                const p2 = new URLSearchParams({ template_name: name, overwrite: 'true' });
                const r2 = await fetch(`${base}/templates/save-job/${this._jobId}?${p2}`, { method: 'POST' });
                const j2 = await r2.json().catch(() => ({}));
                if (!r2.ok) throw new Error(j2.detail || `HTTP ${r2.status}`);
            }
            alert(`✅ Als Template "${name}" gespeichert.`);
        } catch (e) {
            alert(`Fehler: ${e.message}`);
        }
    }

    // ── Tab: Ausführen ───────────────────────────────────────────────

    _renderRun(body) {
        body.innerHTML = `<div class="jd-run-body">
            <div class="jd-init-load">
                <label>
                    <input type="checkbox" id="jd-init-chk" style="width:15px;height:15px">
                    ⚠️ Initial Load Mode – Zieltabelle vorher leeren
                </label>
                <div class="jd-init-load-warn" id="jd-init-warn">
                    <strong>🔥 Destruktive Operation!</strong> Alle Daten werden gelöscht.
                </div>
            </div>
            <div id="jd-progress-wrap" style="display:none">
                <div class="jd-progress-bar"><div class="jd-progress-fill" id="jd-progress-fill" style="width:0%"></div></div>
                <div class="jd-progress-text" id="jd-progress-text"></div>
            </div>
            <div style="display:flex;gap:8px;margin:10px 0">
                <button class="jd-btn jd-btn-primary" id="jd-start-btn" style="flex:1;justify-content:center;padding:9px">▶ Job starten</button>
                <button class="jd-btn jd-btn-secondary" id="jd-cancel-btn" style="display:none">■ Abbrechen</button>
            </div>
            <div class="jd-step-list" id="jd-run-steps"></div>
        </div>`;

        const chk = body.querySelector('#jd-init-chk');
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

        const stepsEl = body.querySelector('#jd-run-steps');
        this._steps.forEach(s => stepsEl.appendChild(this._buildStepEl(s, null)));

        btn.addEventListener('click', () => this._executeJob(body));
    }

    async _executeJob(body) {
        const btn       = body.querySelector('#jd-start-btn');
        const cancelBtn = body.querySelector('#jd-cancel-btn');
        const progWrap  = body.querySelector('#jd-progress-wrap');
        const progFill  = body.querySelector('#jd-progress-fill');
        const progText  = body.querySelector('#jd-progress-text');

        if (!confirm(`Job "${this._job?.job_name || this._jobId}" starten?${this._initialLoad ? '\n\n⚠️ Initial Load: Alle Daten werden gelöscht!' : ''}`)) return;

        btn.disabled = true;
        btn.innerHTML = `<span class="jd-spinner"></span> Starte…`;
        progWrap.style.display = '';
        progText.textContent = 'Job wird gestartet…';

        try {
            const result = await window.api.etl.jobs.execute(this._jobId, { initial_load_mode: !!this._initialLoad });
            const runId  = result?.etl_job_run_id || result?.run_id;
            document.dispatchEvent(new CustomEvent('studio:job-started', { detail: { job_id: this._jobId, run_id: runId } }));
            cancelBtn.style.display = '';
        } catch (e) {
            btn.disabled = false;
            btn.innerHTML = '▶ Job starten';
            progText.textContent = `❌ Fehler: ${e.message}`;
            return;
        }

        let polls = 0;
        this._pollTimer = setInterval(async () => {
            polls++;
            if (polls > 360) {
                this._stopPoll();
                progText.textContent = 'Timeout – bitte manuell prüfen';
                btn.disabled = false; btn.innerHTML = '▶ Neu starten';
                return;
            }
            try {
                const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 1 });
                if (!runs?.length) { progText.textContent = `Warte… (${polls * 2}s)`; return; }
                const run   = await window.api.etl.runs.get(runs[0].etl_job_run_id);
                const stEl  = body.querySelector('#jd-run-steps');
                if (stEl) { stEl.innerHTML = ''; this._steps.forEach(s => stEl.appendChild(this._buildStepEl(s, run))); }
                const done  = (run.step_runs || []).filter(s => s.status !== 'RUNNING').length;
                const total = this._steps.length;
                const pct   = total ? Math.round((done / total) * 100) : 0;
                progFill.style.width = pct + '%';
                progText.textContent = `${pct}% (${done}/${total} Steps) – ${formatDur(run.duration_seconds || polls * 2)}`;
                if (run.status === 'SUCCESS' || run.status === 'FAILED') {
                    this._stopPoll();
                    cancelBtn.style.display = 'none';
                    btn.disabled = false; btn.innerHTML = '▶ Erneut starten';
                    progFill.style.background = run.status === 'SUCCESS' ? '#4caf50' : '#f44336';
                    progFill.style.width = '100%';
                    progText.textContent = run.status === 'SUCCESS'
                        ? `✅ Erfolgreich in ${formatDur(run.duration_seconds)}`
                        : `❌ Fehlgeschlagen nach ${formatDur(run.duration_seconds)}`;
                    document.dispatchEvent(new CustomEvent('studio:job-finished', {
                        detail: { job_id: this._jobId, run_id: run.etl_job_run_id, status: run.status }
                    }));
                }
            } catch (e) { console.warn('[JobDetail] Polling:', e.message); }
        }, 2000);

        cancelBtn.addEventListener('click', async () => {
            this._stopPoll();
            const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 1 }).catch(() => []);
            if (runs?.length) await window.api.etl.runs.cancel(runs[0].etl_job_run_id).catch(() => {});
            cancelBtn.style.display = 'none';
            btn.disabled = false; btn.innerHTML = '▶ Job starten';
            progText.textContent = 'Abgebrochen.';
        }, { once: true });
    }

    // ── Run-Step-Element (für Polling-Tab) ──────────────────────────

    _buildStepEl(step, runDetails) {
        let stepRun = null;
        if (runDetails?.step_runs) {
            stepRun = runDetails.step_runs.find(sr => sr.etl_job_step_id === step.etl_job_step_id);
        }
        let cls = '', statusHtml = statusBadge('PENDING'), metricsHtml = '', expanded = false;
        if (stepRun) {
            if (stepRun.was_skipped === 'Y') {
                cls = 'skipped'; statusHtml = statusBadge('SKIPPED');
            } else if (stepRun.status === 'RUNNING') {
                cls = 'running';
                statusHtml = `<span class="jd-badge jd-badge-blue"><span class="jd-spinner"></span> Läuft</span>`;
                expanded = true;
            } else if (stepRun.status === 'SUCCESS') {
                cls = 'success'; statusHtml = statusBadge('SUCCESS');
                metricsHtml = `<div class="jd-step-metrics">
                    <div class="jd-step-metric"><span>Gelesen</span><span>${stepRun.rows_read ?? '–'}</span></div>
                    <div class="jd-step-metric"><span>Eingefügt</span><span>${stepRun.rows_inserted ?? '–'}</span></div>
                    <div class="jd-step-metric"><span>Aktualisiert</span><span>${stepRun.rows_updated ?? '–'}</span></div>
                    <div class="jd-step-metric"><span>Dauer</span><span>${formatDur(stepRun.duration_seconds)}</span></div>
                </div>`;
            } else if (stepRun.status === 'FAILED') {
                cls = 'failed'; statusHtml = statusBadge('FAILED'); expanded = true;
                metricsHtml = `<div class="jd-step-error">${esc(stepRun.error_message || 'Unbekannter Fehler')}</div>`;
            }
        }
        const div = document.createElement('div');
        div.className = `jd-step ${cls}`;
        // Inaktive Steps im Ausführen-Tab als deaktiviert anzeigen
        const stepIsActive = (step.is_active || 'Y').trim() === 'Y';
        if (!stepIsActive && !stepRun) {
            cls = 'skipped';
            statusHtml = `<span class="jd-badge jd-badge-grey" title="Step ist deaktiviert">⏩ Deaktiviert</span>`;
        }
        div.className = `jd-step ${cls}`;
        div.innerHTML = `
            <div class="jd-step-header">
                <span class="jd-step-num">${step.step_order}</span>
                <span class="jd-step-name">${esc(step.step_name)}</span>
                <span class="jd-step-cat">${esc(step.step_category || '')}</span>
                ${statusHtml}
            </div>
            <div class="jd-step-body" style="${expanded ? '' : 'display:none'}">
                ${step.sql_template_path ? `<div style="margin-bottom:3px;color:#888;font-size:0.85em">${esc(step.sql_template_path)}</div>` : ''}
                ${metricsHtml}
            </div>`;
        div.querySelector('.jd-step-header').addEventListener('click', () => {
            const b = div.querySelector('.jd-step-body');
            b.style.display = b.style.display === 'none' ? '' : 'none';
        });
        return div;
    }

    // ── Tab: History ────────────────────────────────────────────────

    async _renderHistory(body) {
        body.innerHTML = `<div class="jd-run-body"><div class="jd-empty" style="height:auto;padding:16px">Lade History…</div></div>`;
        const runs = await window.api.etl.runs.list({ job_id: this._jobId, limit: 20 }).catch(() => []);
        const wrap = body.querySelector('.jd-run-body');
        if (!runs?.length) {
            wrap.innerHTML = `<div class="jd-empty" style="height:auto;padding:16px">Noch keine Runs.</div>`;
            return;
        }
        const dotColor = { SUCCESS: '#4caf50', FAILED: '#f44336', RUNNING: '#667eea' };
        wrap.innerHTML = `<div class="jd-run-list">${
            runs.map(r => `<div class="jd-run-item" data-run="${r.etl_job_run_id}">
                <div class="jd-run-dot" style="background:${dotColor[r.status] || '#bbb'}"></div>
                <div class="jd-run-info">
                    <div class="jd-run-id">Run #${r.etl_job_run_id}</div>
                    <div class="jd-run-time">${esc(r.started_at || r.create_timestamp || '–')}</div>
                </div>
                ${statusBadge(r.status)}
                <div class="jd-run-dur">${formatDur(r.duration_seconds)}</div>
            </div>`).join('')
        }</div>`;
        wrap.querySelectorAll('.jd-run-item').forEach(item => {
            item.addEventListener('click', async () => {
                const run = await window.api.etl.runs.get(parseInt(item.dataset.run)).catch(() => null);
                if (!run) return;
                this._switchTab('run');
            });
        });
    }

    // ── Job löschen – Panel ─────────────────────────────────────────

    async _deleteJob() {
        // Preview laden
        let preview;
        try {
            preview = await window.api.jobs.deletePreview(this._jobId);
        } catch (e) {
            alert(`Fehler beim Laden der Delete-Preview: ${e.message}`);
            return;
        }

        // Overlay bauen
        const overlay = document.createElement('div');
        overlay.id = 'jd-delete-overlay';
        overlay.style.cssText = `
            position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9000;
            display:flex;align-items:center;justify-content:center;
        `;

        const modal = document.createElement('div');
        modal.style.cssText = `
            background:#1e1e2e;border:1px solid #e53e3e;border-radius:8px;
            width:560px;max-width:95vw;max-height:85vh;display:flex;
            flex-direction:column;font-family:var(--font-mono,'monospace');
        `;

        // Checklist-HTML aufbauen
        const rows = preview.objects.map(obj => {
            const disabled = obj.required ? 'disabled' : '';
            const checked  = obj.default_selected ? 'checked' : '';
            const badge    = obj.required
                ? '<span style="background:#e53e3e;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;">erforderlich</span>'
                : '<span style="background:#555;color:#ccc;border-radius:3px;padding:1px 5px;font-size:10px;">optional</span>';
            const sqlBtn   = obj.sql_preview
                ? `<button data-key="${obj.key}-sql" style="background:none;border:1px solid #555;color:#90caf9;font-size:10px;padding:1px 6px;border-radius:3px;cursor:pointer;">SQL ▾</button>`
                : '';
            return `
                <label style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid #333;cursor:${obj.required ? 'default' : 'pointer'}">
                    <input type="checkbox" data-key="${obj.key}" ${checked} ${disabled}
                        style="margin-top:3px;accent-color:#e53e3e;">
                    <div style="flex:1">
                        <div style="display:flex;gap:8px;align-items:center">
                            <span style="color:#eee;font-weight:600;">${obj.label}</span>
                            ${badge}
                            ${sqlBtn}
                        </div>
                        <div style="color:#888;font-size:11px;margin-top:2px;">${obj.value}</div>
                        ${obj.sql_preview
                            ? `<pre id="sql-${obj.key}" style="display:none;margin:6px 0 0;background:#0d1117;color:#79c0ff;font-size:11px;padding:8px;border-radius:4px;overflow:auto;max-height:150px;">${obj.sql_preview}</pre>`
                            : ''}
                    </div>
                </label>`;
        }).join('');

        modal.innerHTML = `
            <div style="padding:16px 20px;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#e53e3e;font-size:15px;font-weight:700;">⚠ Job löschen: ${preview.job_name}</span>
                <button id="jd-del-close" style="background:none;border:none;color:#aaa;font-size:18px;cursor:pointer;">✕</button>
            </div>
            <div style="padding:16px 20px;overflow-y:auto;flex:1;">
                <p style="color:#ccc;font-size:12px;margin:0 0 12px;">
                    Wähle welche Objekte gelöscht werden sollen. Erforderliche Objekte werden immer gelöscht.
                </p>
                ${rows}
            </div>
            <div style="padding:12px 20px;border-top:1px solid #333;display:flex;gap:10px;justify-content:flex-end;">
                <button id="jd-del-cancel" style="padding:7px 18px;background:#333;border:1px solid #555;color:#ccc;border-radius:5px;cursor:pointer;">Abbrechen</button>
                <button id="jd-del-confirm" style="padding:7px 18px;background:#e53e3e;border:none;color:#fff;border-radius:5px;cursor:pointer;font-weight:600;">Unwiderruflich löschen</button>
            </div>
        `;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // SQL-Toggle
        modal.querySelectorAll('button[data-key$="-sql"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const key = btn.dataset.key.replace('-sql', '');
                const pre = modal.querySelector(`#sql-${key}`);
                if (pre) {
                    pre.style.display = pre.style.display === 'none' ? 'block' : 'none';
                    btn.textContent = pre.style.display === 'none' ? 'SQL ▾' : 'SQL ▴';
                }
            });
        });

        const close = () => overlay.remove();
        overlay.querySelector('#jd-del-close').addEventListener('click', close);
        overlay.querySelector('#jd-del-cancel').addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

        overlay.querySelector('#jd-del-confirm').addEventListener('click', async () => {
            const body = {};
            modal.querySelectorAll('input[type=checkbox][data-key]').forEach(cb => {
                if (!cb.disabled) body[cb.dataset.key] = cb.checked;
            });

            try {
                await window.api.jobs.delete(this._jobId, body);
                overlay.remove();
                document.dispatchEvent(new CustomEvent('studio:job-deleted', { detail: { job_id: this._jobId } }));
                this.clear();
            } catch (e) {
                alert(`Fehler beim Löschen: ${e.message}`);
            }
        });
    }

    _stopPoll() {
        if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom Element <studio-job-detail>
// ─────────────────────────────────────────────────────────────────────────────

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

if (!customElements.get('studio-job-detail')) {
    customElements.define('studio-job-detail', StudioJobDetail);
}
window.JobDetail = JobDetail;

})();
