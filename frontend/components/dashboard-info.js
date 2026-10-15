/**
 * daita-studio – Info-Panel zu einem Dashboard-Widget
 *
 * Seitenpanel rechts (kein Modal, docs/FLOW_UX_KONZEPT.md) mit Erläuterung,
 * Hinweisen, beteiligten Fakten/Dimensionen samt Joins, Herkunft bis zu den
 * Tabellen und dem SQL (mit eingesetzten Filterwerten oder als Vorlage).
 *
 * Verwendung:
 *   studioDashboardInfo.open({ dashboard: 'id', widget: 'wid', filter: {...}, meta: {...} });
 *   studioDashboardInfo.close();
 *
 * Daten: GET /api/dashboards/{id}/widgets/{wid}/info (api.dashboards.info)
 * Abhängigkeiten: api.js, dashboard-widgets.js (esc, fmt)
 */

(() => {
    'use strict';
    const W = () => window.studioWidgets;

    const STYLE = `
        .dsi { position: fixed; top: 64px; right: 16px; bottom: 16px; width: min(460px, calc(100vw - 32px));
               background: var(--card-bg, #fff); border-radius: 10px; box-shadow: 0 4px 24px rgba(0,0,0,0.18);
               z-index: 950; display: flex; flex-direction: column; font-size: 0.85em; color: var(--viz-text-primary, #0b0b0b); }
        .dsi[hidden] { display: none; }
        .dsi__kopf { display: flex; align-items: flex-start; gap: 8px; padding: 14px 16px 10px; border-bottom: 1px solid var(--border-color, #e0e0e0); }
        .dsi__titel { font-weight: 600; font-size: 1.1em; flex: 1; }
        .dsi__typ { color: var(--viz-muted, #898781); font-size: 0.85em; font-weight: 400; }
        .dsi__zu { border: none; background: none; font-size: 1.3em; line-height: 1; cursor: pointer; color: var(--viz-muted, #898781); }
        .dsi__body { overflow: auto; padding: 4px 16px 16px; }
        .dsi__abschnitt { margin-top: 14px; }
        .dsi__h { font-size: 0.82em; color: var(--viz-text-secondary, #52514e); font-weight: 600; margin-bottom: 4px;
                  display: flex; align-items: center; gap: 8px; }
        .dsi__h span { flex: 1; }
        .dsi__hinweis { background: #fef6e0; border: 1px solid #f5d27a; color: #6b4a00; border-radius: 6px; padding: 6px 8px; margin-top: 6px; }
        .dsi__chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .dsi__chip { border-radius: 6px; padding: 3px 8px; border: 1px solid var(--border-color, #e0e0e0); font-family: ui-monospace, monospace; font-size: 0.92em; }
        .dsi__chip--fakt { background: #fdf1ec; border-color: #f2b9a1; }
        .dsi__chip--dim { background: #eef4fc; border-color: #a9c8f0; }
        .dsi__chip small { font-family: inherit; color: var(--viz-text-secondary, #52514e); }
        .dsi__joins { margin: 6px 0 0; padding-left: 16px; font-family: ui-monospace, monospace; font-size: 0.9em; }
        .dsi__baum, .dsi__baum ul { list-style: none; margin: 0; padding-left: 14px; }
        .dsi__baum { padding-left: 0; font-family: ui-monospace, monospace; font-size: 0.9em; }
        .dsi__baum li { line-height: 1.55; }
        .dsi__baum li::before { content: '└ '; color: var(--viz-axis, #c3c2b7); }
        .dsi__baum > li::before { content: ''; }
        .dsi__art { font-family: system-ui, sans-serif; font-size: 0.85em; color: var(--viz-muted, #898781); margin-left: 4px; }
        .dsi__btn { border: 1px solid var(--border-color, #ddd); background: var(--card-bg, #fff); border-radius: 6px;
                    padding: 2px 8px; cursor: pointer; font-size: 0.85em; color: var(--text-secondary, #666); }
        .dsi__btn[aria-pressed="true"] { border-color: var(--primary-color, #667eea); color: var(--primary-color, #667eea); }
        .dsi__sql { background: var(--bg-color, #f5f5f5); border-radius: 6px; padding: 8px 10px; margin: 6px 0 0;
                    font-family: ui-monospace, monospace; font-size: 0.85em; white-space: pre-wrap; word-break: break-word; }
        .dsi__meta { color: var(--viz-muted, #898781); }
        .dsi__msg { color: var(--viz-muted, #898781); padding: 8px 0; }
        .dsi__msg--fehler { color: var(--status-critical, #d03b3b); }
    `;

    let root = null;
    let ladeNr = 0;

    function injectStyle() {
        if (document.getElementById('dsi-style')) return;
        const s = document.createElement('style');
        s.id = 'dsi-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function ensureRoot() {
        injectStyle();
        if (root) return root;
        root = document.createElement('aside');
        root.className = 'dsi';
        root.hidden = true;
        root.setAttribute('role', 'complementary');
        root.setAttribute('aria-label', 'Informationen zum Widget');
        document.body.appendChild(root);
        document.addEventListener('keydown', e => { if (e.key === 'Escape' && !root.hidden) close(); });
        return root;
    }

    function kurz(objekt) {
        return String(objekt || '').split('.').pop();
    }

    function chip(o) {
        const esc = W().esc;
        const klasse = o.art === 'Fakt' ? 'dsi__chip--fakt' : o.art === 'Dimension' ? 'dsi__chip--dim' : '';
        let zusatz = '';
        if (o.existiert === false) zusatz = 'fehlt';
        else if (o.zugriff === false) zusatz = 'kein Lesezugriff';
        else if (o.zeilen !== undefined && o.zeilen !== null) zusatz = W().fmt.zahl(o.zeilen) + ' Zeilen';
        return `<span class="dsi__chip ${klasse}" title="${esc(o.objekt)}">${esc(o.art)} ${esc(kurz(o.objekt))}`
            + `${zusatz ? ` <small>· ${esc(zusatz)}</small>` : ''}</span>`;
    }

    function baum(knoten) {
        const esc = W().esc;
        const li = k => `<li>${esc(k.objekt)}<span class="dsi__art">${esc(k.art)}`
            + `${k.verweis ? ', siehe oben' : ''}${k.abgeschnitten ? ', abgeschnitten' : ''}</span>`
            + `${k.quellen && k.quellen.length ? `<ul>${k.quellen.map(li).join('')}</ul>` : ''}</li>`;
        return `<ul class="dsi__baum">${knoten.map(li).join('')}</ul>`;
    }

    function render(info, meta) {
        const esc = W().esc;
        const teile = [];
        if (info.erlaeuterung) {
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Erläuterung</span></div><div>${esc(info.erlaeuterung)}</div></div>`);
        }
        if (info.hinweise && info.hinweise.length) {
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Hinweise</span></div>`
                + info.hinweise.map(h => `<div class="dsi__hinweis">${esc(h)}</div>`).join('') + `</div>`);
        }
        if (info.katalog) {
            const k = info.katalog;
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Im Katalog</span></div>`
                + `<div>${esc(k.titel || k.id)}${k.status ? ` <span class="dsi__meta">· Status ${esc(k.status)}</span>` : ''}</div></div>`);
        }
        if (info.objekte && info.objekte.length) {
            const joins = (info.joins || []).map(j =>
                `<li>${esc(kurz(j.links))}.${esc(j.links_spalte)} = ${esc(kurz(j.rechts))}.${esc(j.rechts_spalte)}</li>`).join('');
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Datenmodell</span></div>`
                + `<div class="dsi__chips">${info.objekte.map(chip).join('')}</div>`
                + (joins ? `<div class="dsi__meta" style="margin-top:6px">Verknüpft über</div><ul class="dsi__joins">${joins}</ul>` : '')
                + `</div>`);
        }
        if (info.herkunft && info.herkunft.length) {
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Herkunft bis zu den Tabellen</span></div>${baum(info.herkunft)}</div>`);
        } else if (info.herkunft_fehler) {
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Herkunft</span></div><div class="dsi__msg dsi__msg--fehler">${esc(info.herkunft_fehler)}</div></div>`);
        }
        if (info.sql) {
            const p = Object.entries(info.sql.parameter || {}).map(([k, v]) => `${k} = ${v}`).join(', ');
            teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>SQL</span>`
                + `<button class="dsi__btn" data-sql="mit_werten" aria-pressed="true">mit Filterwerten</button>`
                + `<button class="dsi__btn" data-sql="vorlage" aria-pressed="false">Vorlage</button>`
                + `<button class="dsi__btn dsi__kopieren" title="SQL in die Zwischenablage">Kopieren</button></div>`
                + `<pre class="dsi__sql">${esc(info.sql.mit_werten)}</pre>`
                + `<div class="dsi__meta" style="margin-top:4px">Datei ${esc(info.sql.datei)}${p ? ` · Filter ${esc(p)}` : ''}</div></div>`);
        }
        const lauf = [];
        if (meta?.datenstand) lauf.push('Datenstand ' + W().fmt.datum(meta.datenstand));
        if (meta?.zeilen !== undefined) lauf.push(W().fmt.zahl(meta.zeilen) + ' Zeilen');
        if (meta?.laufzeit_ms !== undefined && meta?.laufzeit_ms !== null) lauf.push('Abfrage ' + W().fmt.zahl(meta.laufzeit_ms / 1000, 1) + ' s');
        if (meta?.cache) lauf.push('aus Cache');
        if (lauf.length) teile.push(`<div class="dsi__abschnitt"><div class="dsi__h"><span>Letzter Lauf</span></div><div class="dsi__meta">${esc(lauf.join(' · '))}</div></div>`);

        root.querySelector('.dsi__body').innerHTML = teile.join('') || '<div class="dsi__msg">Keine Angaben zu diesem Widget.</div>';

        const pre = root.querySelector('.dsi__sql');
        root.querySelectorAll('[data-sql]').forEach(b => b.addEventListener('click', () => {
            root.querySelectorAll('[data-sql]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
            pre.textContent = info.sql[b.dataset.sql];
        }));
        root.querySelector('.dsi__kopieren')?.addEventListener('click', async e => {
            const btn = e.currentTarget;
            try {
                await navigator.clipboard.writeText(pre.textContent);
            } catch (_) {   // ohne sicheren Kontext (http): Text markieren
                const r = document.createRange(); r.selectNodeContents(pre);
                const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
                document.execCommand('copy');
            }
            btn.textContent = 'Kopiert';
            setTimeout(() => { btn.textContent = 'Kopieren'; }, 1500);
        });
    }

    async function open({ dashboard, widget, titel, typ, filter, meta }) {
        const esc = W().esc;
        ensureRoot();
        const nr = ++ladeNr;
        root.hidden = false;
        root.innerHTML = `
            <div class="dsi__kopf">
                <div class="dsi__titel">${esc(titel || widget)} <span class="dsi__typ">${esc(typ || '')}</span></div>
                <button class="dsi__zu" title="Schließen" aria-label="Schließen">×</button>
            </div>
            <div class="dsi__body"><div class="dsi__msg">Lade …</div></div>`;
        root.querySelector('.dsi__zu').addEventListener('click', close);
        try {
            // erst ohne Zeilenzahlen (schnell), dann mit Zeilenzahlen nachladen
            const info = await window.api.dashboards.info(dashboard, widget, { ...filter, _zeilen: 0 });
            if (nr !== ladeNr) return;
            render(info, meta);
            if (info.objekte && info.objekte.length) {
                const voll = await window.api.dashboards.info(dashboard, widget, filter);
                if (nr !== ladeNr) return;
                const chips = root.querySelector('.dsi__chips');
                if (chips) chips.innerHTML = voll.objekte.map(chip).join('');
            }
        } catch (e) {
            if (nr !== ladeNr) return;
            root.querySelector('.dsi__body').innerHTML = `<div class="dsi__msg dsi__msg--fehler">${esc(e.message)}</div>`;
        }
    }

    function close() {
        ladeNr++;
        if (root) root.hidden = true;
    }

    window.studioDashboardInfo = { open, close };
})();
