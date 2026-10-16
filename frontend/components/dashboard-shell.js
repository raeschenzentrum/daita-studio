/**
 * daita-studio – Dashboard-Shell
 *
 * Auswahl der Dashboards, Filterleiste, Raster der Widgets, Datenstand.
 * Kennt keine Widget-Typen – rendert über studioWidgets (dashboard-widgets.js).
 * Zustand (Dashboard + Filter) steht im URL-Hash: #d=<id>&<filter>=<wert>
 *
 * Verwendung:
 *   <script src="components/api.js"></script>
 *   <script src="components/dashboard-widgets.js"></script>
 *   <script src="components/widgets/widget-*.js"></script>
 *   <script src="components/dashboard-shell.js"></script>
 *   <studio-dashboard-shell></studio-dashboard-shell>
 *
 * Custom Events (auf document):
 *   studio:dashboard-loaded          { detail: { dashboard } }
 *   studio:dashboard-filter-changed  { detail: { dashboard, filter } }
 *   studio:dashboard-refresh         { detail: { dashboard } }   – auch von außen auslösbar
 *
 * Abhängigkeiten: api.js (window.api), dashboard-widgets.js, auth.js (optional, Rollen)
 */

(() => {
    'use strict';

    const ROW_HEIGHT = 112;

    const STYLE = `
        studio-dashboard-shell { display: block; }
        .dsh-root { max-width: 1600px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }

        .dsh-tabs { display: flex; gap: 4px; flex-wrap: wrap; background: var(--card-bg, #fff);
                    border-radius: 10px; padding: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.07); }
        .dsh-tab { border: none; background: transparent; padding: 7px 14px; border-radius: 7px; cursor: pointer;
                   font-size: 0.9em; color: var(--text-secondary, #666); }
        .dsh-tab:hover { background: var(--bg-color, #f5f5f5); }
        .dsh-tab[aria-selected="true"] { background: var(--primary-color, #667eea); color: #fff; }
        .dsh-tab__gruppe { font-size: 0.75em; opacity: 0.75; margin-right: 6px; }

        .dsh-head { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
        .dsh-head__titel { flex: 1; min-width: 220px; }
        .dsh-head__titel h1 { font-size: 1.3em; margin: 0; color: var(--text-primary, #333); }
        .dsh-head__titel p { margin: 2px 0 0; color: var(--text-secondary, #666); font-size: 0.88em; }
        .dsh-filter { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
        .dsh-filter label { display: flex; flex-direction: column; font-size: 0.75em; color: var(--text-secondary, #666); gap: 2px; }
        .dsh-filter input, .dsh-filter select { padding: 5px 8px; border: 1px solid var(--border-color, #ddd); border-radius: 6px;
                    font-size: 1.1em; background: var(--card-bg, #fff); color: var(--text-primary, #333); }
        .dsh-filter input[type=number] { width: 90px; }
        .dsh-meta { font-size: 0.8em; color: var(--text-secondary, #666); display: flex; gap: 10px; align-items: center; }
        .dsh-btn { padding: 5px 12px; border: 1px solid var(--primary-color, #667eea); border-radius: 6px;
                   background: transparent; color: var(--primary-color, #667eea); cursor: pointer; font-size: 0.95em; }
        .dsh-btn:hover { background: rgba(102,126,234,0.08); }

        .dsh-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr));
                    grid-auto-rows: minmax(${ROW_HEIGHT}px, auto); gap: 14px; }
        .dsh-card { background: var(--card-bg, #fff); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.07);
                    display: flex; flex-direction: column; min-width: 0; min-height: 0; padding: 12px 14px 8px; }
        .dsh-card__head { display: flex; align-items: baseline; gap: 8px; }
        .dsh-card__head[hidden] { display: none; }
        .dsh-card__titel { font-size: 0.88em; font-weight: 600; color: var(--viz-text-secondary, #52514e); flex: 1;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .dsh-card__untertitel { font-size: 0.75em; color: var(--viz-muted, #898781); }
        .dsh-card__ansicht { border: none; background: none; cursor: pointer; font-size: 0.75em;
                    color: var(--viz-muted, #898781); padding: 0 2px; }
        .dsh-card__ansicht:hover { color: var(--primary-color, #667eea); }
        .dsh-card__info { border: 1px solid var(--viz-axis, #c3c2b7); background: none; cursor: pointer; border-radius: 50%;
                    width: 18px; height: 18px; line-height: 15px; padding: 0; font-size: 0.72em; font-weight: 600;
                    color: var(--viz-muted, #898781); font-family: Georgia, serif; flex: none; }
        .dsh-card__info:hover { color: var(--primary-color, #667eea); border-color: var(--primary-color, #667eea); }
        .dsh-card { position: relative; }
        .dsh-card__info--frei { position: absolute; top: 12px; right: 14px; z-index: 2; background: var(--card-bg, #fff); }
        .dsh-card__body { flex: 1; min-height: 0; position: relative; margin-top: 4px; }
        .dsh-card[data-auto] .dsh-card__body { position: static; }
        .dsh-card__foot { font-size: 0.72em; color: var(--viz-muted, #898781); min-height: 1.2em; }

        .dsh-msg { color: var(--viz-muted, #898781); font-size: 0.85em; padding: 8px 0; }
        .dsh-msg--error { color: var(--status-critical, #d03b3b); }
        .dsh-loading { color: var(--viz-muted, #898781); font-size: 0.85em; padding: 8px 0; }

        .dsh-kpi { display: flex; flex-direction: column; justify-content: center; height: 100%; }
        .dsh-kpi__wert { font-size: 2em; font-weight: 600; color: var(--viz-text-primary, #0b0b0b); line-height: 1.1; }
        .dsh-kpi__vergleich { font-size: 0.8em; color: var(--viz-text-secondary, #52514e); }
        .dsh-kpi__status { font-size: 0.8em; color: var(--viz-text-secondary, #52514e); display: flex; gap: 4px; align-items: center; }

        .dsh-table { height: 100%; overflow: auto; font-size: 0.8em; }
        .dsh-table table { border-collapse: collapse; width: 100%; margin: 0; }
        .dsh-table tr:hover { background: var(--bg-color, #f5f5f5); }
        .dsh-table th { position: sticky; top: 0; background: var(--card-bg, #fff); text-align: left; cursor: pointer;
                    color: var(--viz-text-secondary, #52514e); font-weight: 600; border-bottom: 1px solid var(--viz-axis, #c3c2b7);
                    padding: 4px 8px; white-space: nowrap; user-select: none; }
        .dsh-table td { padding: 3px 8px; border-bottom: 1px solid var(--viz-grid, #e1e0d9); color: var(--viz-text-primary, #0b0b0b);
                    vertical-align: top; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.4; }
        .dsh-table .num { text-align: right; font-variant-numeric: tabular-nums; }
        .dsh-table__mehr { color: var(--viz-muted, #898781); padding: 4px 8px; }

        @media (max-width: 900px) {
            .dsh-grid { grid-template-columns: 1fr; grid-auto-rows: auto; }
            .dsh-card { grid-column: 1 / -1 !important; grid-row: auto !important; height: var(--dsh-h); }
            .dsh-card[data-auto] { height: auto; }
        }
    `;

    function injectStyle() {
        if (document.getElementById('dsh-style')) return;
        const s = document.createElement('style');
        s.id = 'dsh-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    const W = () => window.studioWidgets;

    function fire(name, detail) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }

    function readHash() {
        const p = new URLSearchParams(location.hash.slice(1));
        const out = { id: p.get('d'), filter: {} };
        for (const [k, v] of p) if (k !== 'd') out.filter[k] = v;
        return out;
    }

    function writeHash(id, filter) {
        // weitere Parameter (z. B. bereich= eines Widgets) bleiben erhalten, solange das Dashboard gleich ist
        const alt = new URLSearchParams(location.hash.slice(1));
        const p = alt.get('d') === id ? alt : new URLSearchParams();
        p.set('d', id);
        for (const [k, v] of Object.entries(filter)) p.set(k, v);
        history.replaceState(null, '', '#' + p.toString());
    }

    class DashboardShell {
        constructor(root) {
            this.root = root;
            this.liste = [];
            this.def = null;
            this.filter = {};
            this.instanzen = [];
            this.ladeNr = 0;
            document.addEventListener('studio:dashboard-refresh', e => {
                if (!e.detail?.dashboard || e.detail.dashboard === this.def?.id) this.ladeWidgets();
            });
            window.addEventListener('hashchange', () => {
                const h = readHash();
                if (h.id && h.id !== this.def?.id) this.oeffne(h.id, h.filter);
            });
        }

        async start() {
            this.root.innerHTML = '<div class="dsh-root"><div class="dsh-loading">Lade Dashboards …</div></div>';
            try {
                this.liste = await window.api.dashboards.list();
            } catch (e) {
                this.root.innerHTML = `<div class="dsh-root"><div class="dsh-msg dsh-msg--error">${W().esc(e.message)}</div></div>`;
                return;
            }
            if (!this.liste.length) {
                this.root.innerHTML = '<div class="dsh-root"><div class="dsh-msg">Keine Dashboards definiert (cfg/config.yml → paths.dashboards).</div></div>';
                return;
            }
            const h = readHash();
            const id = this.liste.some(d => d.id === h.id) ? h.id : this.liste[0].id;
            await this.oeffne(id, h.filter);
        }

        async oeffne(id, filter = {}) {
            this.dispose();
            window.studioDashboardInfo?.close();
            try {
                this.def = await window.api.dashboards.get(id);
            } catch (e) {
                this.root.innerHTML = `<div class="dsh-root"><div class="dsh-msg dsh-msg--error">${W().esc(e.message)}</div></div>`;
                return;
            }
            this.filter = {};
            for (const f of this.def.filter) {
                this.filter[f.id] = filter[f.id] ?? (f.default !== undefined ? String(f.default) : '');
            }
            writeHash(id, this.filter);
            this.renderRahmen();
            fire('studio:dashboard-loaded', { dashboard: this.def });
            await this.ladeWidgets();
        }

        renderRahmen() {
            const esc = W().esc;
            const d = this.def;
            const tabs = this.liste.map(x => `
                <button class="dsh-tab" role="tab" data-id="${esc(x.id)}" aria-selected="${x.id === d.id}" title="${esc(x.beschreibung || '')}">
                    ${x.gruppe ? `<span class="dsh-tab__gruppe">${esc(x.gruppe)}</span>` : ''}${esc(x.titel)}
                </button>`).join('');
            const filter = d.filter.map(f => `<label>${esc(f.titel || f.id)}${this.filterControl(f)}</label>`).join('');
            const darfRefresh = !window.studioAuth || window.studioAuth.hasRole('Editor');
            const cards = d.widgets.map(w => {
                const p = w.pos || {};
                const auto = p.h === 'auto';   // Höhe nach Inhalt (z. B. Übersichtsseiten)
                const h = auto ? 1 : (p.h || 2);
                return `
                <section class="dsh-card" data-w="${esc(w.id)}" ${auto ? 'data-auto="1"' : ''}
                    style="grid-column:${(p.x || 0) + 1} / span ${p.b || 6};grid-row:${(p.y || 0) + 1} / span ${h};--dsh-h:${h * ROW_HEIGHT}px">
                    <div class="dsh-card__head" ${w.titel === '' ? 'hidden' : ''}>
                        <span class="dsh-card__titel" title="${esc(w.titel || w.id)}">${esc(w.titel || w.id)}</span>
                        ${w.untertitel ? `<span class="dsh-card__untertitel">${esc(w.untertitel)}</span>` : ''}
                        ${W().get(w.typ)?.tabelle !== false ? '<button class="dsh-card__ansicht" title="Zwischen Diagramm und Tabelle wechseln">Tabelle</button>' : ''}
                        ${window.studioDashboardInfo ? '<button class="dsh-card__info" title="Erläuterung, Datenmodell und SQL" aria-label="Informationen zum Widget">i</button>' : ''}
                    </div>
                    ${w.titel === '' && window.studioDashboardInfo ? '<button class="dsh-card__info dsh-card__info--frei" title="Erläuterung, Objekte und Prüf-SQL" aria-label="Informationen zur Übersicht">i</button>' : ''}
                    <div class="dsh-card__body"><div class="dsh-loading">Lade …</div></div>
                    <div class="dsh-card__foot"></div>
                </section>`;
            }).join('');

            this.root.innerHTML = `
                <div class="dsh-root">
                    <nav class="dsh-tabs" role="tablist">${tabs}</nav>
                    <div class="dsh-head">
                        <div class="dsh-head__titel"><h1>${esc(d.titel)}</h1>${d.beschreibung ? `<p>${esc(d.beschreibung)}</p>` : ''}</div>
                        <div class="dsh-filter">${filter}</div>
                        <div class="dsh-meta">
                            <span class="dsh-datenstand"></span>
                            ${darfRefresh ? '<button class="dsh-btn dsh-refresh" title="Cache leeren und neu laden">Aktualisieren</button>' : ''}
                        </div>
                    </div>
                    <div class="dsh-grid">${cards}</div>
                </div>`;

            this.root.querySelectorAll('.dsh-tab').forEach(b =>
                b.addEventListener('click', () => this.oeffne(b.dataset.id)));
            this.root.querySelectorAll('[data-filter]').forEach(inp =>
                inp.addEventListener('change', () => {
                    this.filter[inp.dataset.filter] = inp.value;
                    writeHash(this.def.id, this.filter);
                    fire('studio:dashboard-filter-changed', { dashboard: this.def.id, filter: { ...this.filter } });
                    this.ladeWidgets();
                }));
            this.root.querySelector('.dsh-refresh')?.addEventListener('click', async () => {
                try { await window.api.dashboards.refresh(this.def.id); } catch (_) { /* studio:api-error */ }
                fire('studio:dashboard-refresh', { dashboard: this.def.id });
            });
            this.root.querySelectorAll('.dsh-card__info').forEach(b =>
                b.addEventListener('click', () => {
                    const card = b.closest('.dsh-card');
                    const w = this.def.widgets.find(x => x.id === card.dataset.w);
                    const filter = {};
                    for (const fid of w.filter || []) filter[fid] = this.filter[fid];
                    window.studioDashboardInfo.open({ dashboard: this.def.id, widget: w.id, titel: w.titel || this.def.titel,
                        typ: w.typ, filter, meta: card._daten?.meta });
                }));
            this.root.querySelectorAll('.dsh-card__ansicht').forEach(b =>
                b.addEventListener('click', () => {
                    const card = b.closest('.dsh-card');
                    card.dataset.tabelle = card.dataset.tabelle === '1' ? '' : '1';
                    b.textContent = card.dataset.tabelle ? 'Diagramm' : 'Tabelle';
                    this.zeichne(card);
                }));
        }

        filterControl(f) {
            const esc = W().esc;
            const v = this.filter[f.id] ?? '';
            if (f.typ === 'auswahl') {
                const opts = (f.werte || []).map(w => {
                    const wert = typeof w === 'object' ? w.wert : w;
                    const titel = typeof w === 'object' ? (w.titel ?? w.wert) : w;
                    return `<option value="${esc(wert)}" ${String(wert) === String(v) ? 'selected' : ''}>${esc(titel)}</option>`;
                }).join('');
                return `<select data-filter="${esc(f.id)}">${opts}</select>`;
            }
            const typ = { jahr: 'number', zahl: 'number', datum: 'date' }[f.typ] || 'text';
            let wert = v;
            if (f.typ === 'jahr' && /^aktuell/.test(wert)) wert = String(new Date().getFullYear() + Number(wert.slice(7) || 0));
            if (f.typ === 'datum' && wert === 'heute') wert = new Date().toISOString().slice(0, 10);
            const grenzen = f.typ === 'jahr' ? 'min="1900" max="2100"'
                : `${f.min !== undefined ? `min="${esc(f.min)}"` : ''} ${f.max !== undefined ? `max="${esc(f.max)}"` : ''}`;
            return `<input type="${typ}" data-filter="${esc(f.id)}" value="${esc(wert)}" ${grenzen}>`;
        }

        async ladeWidgets() {
            const nr = ++this.ladeNr;
            this.disposeWidgets();
            const def = this.def;
            this.root.querySelector('.dsh-datenstand').textContent = '';
            await Promise.allSettled(def.widgets.map(async w => {
                const card = this.root.querySelector(`.dsh-card[data-w="${CSS.escape(w.id)}"]`);
                card.querySelector('.dsh-card__body').innerHTML = '<div class="dsh-loading">Lade …</div>';
                card.querySelector('.dsh-card__foot').textContent = '';
                const filter = {};
                for (const fid of w.filter || []) filter[fid] = this.filter[fid];
                try {
                    const daten = await window.api.dashboards.data(def.id, w.id, filter);
                    if (nr !== this.ladeNr) return;
                    card._daten = daten;
                    card._widget = w;
                    this.zeichne(card);
                    this.fuss(card, daten.meta);
                    if (daten.meta?.datenstand) {
                        this.root.querySelector('.dsh-datenstand').textContent = 'Datenstand ' + W().fmt.datum(daten.meta.datenstand);
                    }
                } catch (e) {
                    if (nr !== this.ladeNr) return;
                    card.querySelector('.dsh-card__body').innerHTML = `<div class="dsh-msg dsh-msg--error">${W().esc(e.message)}</div>`;
                }
            }));
        }

        zeichne(card) {
            const w = card._widget, daten = card._daten;
            if (!w || !daten) return;
            card._instanz?.dispose?.();
            card._instanz = null;
            const body = card.querySelector('.dsh-card__body');
            body.innerHTML = '';
            const typ = card.dataset.tabelle ? 'table' : w.typ;
            const impl = W().get(typ);
            if (!impl) {
                body.innerHTML = `<div class="dsh-msg dsh-msg--error">Unbekannter Widget-Typ '${W().esc(w.typ)}'</div>`;
                return;
            }
            const host = document.createElement('div');
            host.style.cssText = card.dataset.auto ? '' : 'position:absolute;inset:0;';
            body.appendChild(host);
            try {
                card._instanz = impl.render(host, daten, typ === 'table' && card.dataset.tabelle ? {} : (w.optionen || {}), { widget: w, dashboard: this.def });
                if (card._instanz) this.instanzen.push(card._instanz);
            } catch (e) {
                host.innerHTML = `<div class="dsh-msg dsh-msg--error">${W().esc(e.message)}</div>`;
            }
        }

        fuss(card, meta = {}) {
            const teile = [];
            if (card._widget.typ === 'star-explorer') { card.querySelector('.dsh-card__foot').textContent = ''; return; }
            if (meta.zeilen !== undefined && card._widget.typ !== 'kpi' && card._widget.daten !== 'katalog') teile.push(`${W().fmt.zahl(meta.zeilen)} Zeilen`);
            if (meta.abgeschnitten) teile.push('gekürzt');
            if (meta.unterdrueckt) teile.push(`${W().fmt.zahl(meta.unterdrueckt)} kleine Werte ausgeblendet`);
            if (meta.cache && card._widget.typ !== 'kpi') teile.push('aus Cache');
            else if (meta.laufzeit_ms !== undefined && meta.laufzeit_ms !== null && card._widget.typ !== 'kpi')
                teile.push(W().fmt.zahl(meta.laufzeit_ms / 1000, 1) + ' s');
            card.querySelector('.dsh-card__foot').textContent = teile.join(' · ');
        }

        disposeWidgets() {
            this.instanzen.forEach(i => { try { i.dispose?.(); } catch (_) { /* ignore */ } });
            this.instanzen = [];
            this.root.querySelectorAll('.dsh-card').forEach(c => { c._instanz = null; });
        }

        dispose() {
            this.ladeNr++;
            this.disposeWidgets();
        }
    }

    class StudioDashboardShell extends HTMLElement {
        connectedCallback() {
            if (this._shell) return;
            injectStyle();
            this._shell = new DashboardShell(this);
            this._shell.start();
        }
        disconnectedCallback() {
            this._shell?.dispose();
        }
    }

    window.DashboardShell = DashboardShell;
    if (!customElements.get('studio-dashboard-shell')) {
        customElements.define('studio-dashboard-shell', StudioDashboardShell);
    }
})();
