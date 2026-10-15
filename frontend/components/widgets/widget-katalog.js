/**
 * daita-studio – Gemeinsame Basis der Übersichts-Widgets (area-map, star-map, subject-map)
 *
 * Die Widgets zeigen den Katalog (katalog.yml der Dashboard-Ablage) und den
 * Ist-Stand der referenzierten DB-Objekte. Daten kommen aus einem Widget mit
 * `daten: katalog`: { katalog, status, dashboards }.
 *
 * Status eines Elements = Plan (status im YAML) kombiniert mit dem Ist-Stand
 * seiner `quelle` (existiert, Zeilenzahl). Status wird immer mit Form und Text
 * gezeigt, nie nur über Farbe.
 *
 * Bereitgestellt als window.studioKatalog:
 *   status(el, ctx)       → { key, label, symbol, ist, hinweis }
 *   abdeckung(elemente)   → { key, label, symbol, erfuellt, gesamt }
 *   badge(st)             → HTML (Symbol + Text)
 *   legende()             → HTML
 *   linien(root, svg, paare) – zeichnet Verbindungslinien als SVG-Overlay
 *   panel(root, inhalt)   – Detail-Panel (Side-Panel im Widget)
 *   ctx(daten)            → Kontext für status() (Objektstatus nach Name)
 *
 * Abhängigkeiten: dashboard-widgets.js
 */

(() => {
    'use strict';
    const W = window.studioWidgets;

    // Symbole als SVG (schriftunabhängig); Form unterscheidet den Status auch ohne Farbe
    const SVG = {
        voll:  '<circle cx="6" cy="6" r="5" fill="currentColor"/>',
        ring:  '<circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="6" cy="6" r="1.8" fill="currentColor"/>',
        halb:  '<circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6 1.4 A4.6 4.6 0 0 1 6 10.6 Z" fill="currentColor"/>',
        leer:  '<circle cx="6" cy="6" r="4.4" fill="none" stroke="currentColor" stroke-width="1.6"/>',
        kreuz: '<path d="M2 2 L10 10 M10 2 L2 10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    };
    const STATUS = {
        vorhanden: { label: 'vorhanden', symbol: SVG.voll,  farbe: 'var(--status-good, #0ca30c)', wert: 1 },
        ableitbar: { label: 'ableitbar', symbol: SVG.ring,  farbe: 'var(--status-good, #0ca30c)', wert: 1 },
        teilweise: { label: 'teilweise', symbol: SVG.halb,  farbe: 'var(--status-warning, #fab219)', wert: 0.5 },
        leer:      { label: 'leer',      symbol: SVG.leer,  farbe: 'var(--status-serious, #ec835a)', wert: 0.25 },
        fehlt:     { label: 'fehlt',     symbol: SVG.kreuz, farbe: 'var(--status-critical, #d03b3b)', wert: 0 },
    };

    const STYLE = `
        .kat { position: relative; font-size: 0.85em; color: var(--viz-text-primary, #0b0b0b); }
        .kat h3 { font-size: 1.05em; margin: 0 0 8px; color: var(--viz-text-primary, #0b0b0b); }
        .kat-legende { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; color: var(--viz-text-secondary, #52514e);
                       font-size: 0.9em; margin-bottom: 12px; }
        .kat-legende__box { display: inline-block; width: 22px; height: 12px; border-radius: 3px; vertical-align: -1px; margin-right: 4px; }
        .kat-st { white-space: nowrap; }
        .kat-st__sym { display: inline-block; width: 11px; height: 11px; margin-right: 4px; vertical-align: -1px; }
        .kat-st__sym svg { width: 11px; height: 11px; display: block; }
        .kat-st--klein .kat-st__txt { font-size: 0.85em; color: var(--viz-text-secondary, #52514e); }

        .kat-box { border: 1px solid var(--border-color, #e0e0e0); border-radius: 8px; background: var(--card-bg, #fff);
                   padding: 8px 10px; cursor: pointer; position: relative; }
        .kat-box:hover { box-shadow: 0 0 0 2px rgba(102,126,234,0.35); }
        .kat-box__titel { font-weight: 600; display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
        .kat-box__sub { color: var(--viz-text-secondary, #52514e); font-size: 0.88em; }
        .kat-box ul { margin: 4px 0 0; padding: 0; list-style: none; }
        .kat-box li { line-height: 1.45; }
        .kat-box--fakt { background: #fdf1ec; border-color: #f2b9a1; }
        .kat-box--conf { background: #f0eef8; border-color: #b9b2e3; }
        .kat-box--dim  { background: #eef4fc; border-color: #a9c8f0; }
        .kat-box--fehlt { border-style: dashed; }
        .kat-box[aria-selected="true"] { box-shadow: 0 0 0 2px var(--primary-color, #667eea); }

        .kat-lines { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
        .kat-lines path { fill: none; stroke: var(--viz-axis, #c3c2b7); stroke-width: 1.5; }
        .kat-lines path.kat-line--fehlt { stroke-dasharray: 5 4; }
        .kat-lines text { font-size: 10px; fill: var(--viz-muted, #898781); }

        .kat-panel { position: fixed; top: 64px; right: 16px; width: 360px; max-height: calc(100vh - 90px); overflow: auto; z-index: 900;
                     background: var(--card-bg, #fff); border-radius: 10px; box-shadow: 0 4px 24px rgba(0,0,0,0.18); padding: 14px 16px; }
        .kat-panel[hidden] { display: none; }
        .kat-panel__zu { position: absolute; top: 8px; right: 10px; border: none; background: none; font-size: 1.2em; cursor: pointer;
                         color: var(--viz-muted, #898781); }
        .kat-panel dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 10px; margin: 8px 0 0; }
        .kat-panel dt { color: var(--viz-text-secondary, #52514e); }
        .kat-panel dd { margin: 0; word-break: break-word; }
    `;

    function injectStyle() {
        if (document.getElementById('kat-style')) return;
        const s = document.createElement('style');
        s.id = 'kat-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function ctx(daten) {
        const nachObjekt = {};
        for (const st of Object.values(daten.status || {})) {
            if (st && st.objekt) nachObjekt[st.objekt.toUpperCase()] = st;
        }
        return { nachObjekt, dashboards: new Set(daten.dashboards || []) };
    }

    /** Status eines Katalog-Elements aus Plan und Ist-Stand */
    function status(el, c) {
        const plan = STATUS[el.status] ? el.status : null;
        let key, ist = null, hinweis = null;
        if (el.quelle) {
            ist = c.nachObjekt[String(el.quelle).toUpperCase()] || null;
            if (!ist || ist.fehler) {
                key = plan || 'vorhanden';
                hinweis = ist?.fehler ? `Ist-Stand nicht prüfbar: ${ist.fehler}` : 'Ist-Stand nicht prüfbar';
            } else if (!ist.existiert) {
                key = 'fehlt';
                hinweis = 'Objekt existiert nicht in der Datenbank';
            } else if (ist.zugriff === false) {
                key = plan || 'vorhanden';
                hinweis = 'Objekt vorhanden; kein Lesezugriff für den Studio-User (Zeilenzahl unbekannt)';
            } else if (!ist.zeilen) {
                key = 'leer';
                hinweis = 'Objekt vorhanden, aber leer';
            } else {
                key = plan && plan !== 'fehlt' ? plan : 'vorhanden';
            }
        } else {
            key = plan || 'fehlt';
        }
        return { key, ...STATUS[key], ist, hinweis };
    }

    function abdeckung(liste) {
        const gesamt = liste.length;
        if (!gesamt) return { key: 'fehlt', ...STATUS.fehlt, erfuellt: 0, gesamt: 0 };
        const summe = liste.reduce((a, st) => a + st.wert, 0);
        const erfuellt = liste.filter(st => st.wert >= 1).length;
        const key = summe >= gesamt ? 'vorhanden' : summe === 0 ? 'fehlt' : 'teilweise';
        return { key, ...STATUS[key], erfuellt, gesamt };
    }

    function badge(st, klein) {
        return `<span class="kat-st ${klein ? 'kat-st--klein' : ''}" title="${W.esc(st.label + (st.hinweis ? ' – ' + st.hinweis : ''))}">`
            + `<span class="kat-st__sym" style="color:${st.farbe}" aria-hidden="true"><svg viewBox="0 0 12 12">${st.symbol}</svg></span>`
            + `<span class="kat-st__txt">${W.esc(st.label)}</span></span>`;
    }

    function legende(boxen = true) {
        const st = Object.keys(STATUS).map(k => badge({ ...STATUS[k] })).join('');
        const bx = boxen ? `
            <span><span class="kat-legende__box kat-box--fakt" style="border:1px solid #f2b9a1"></span>Fakt (Kennzahlen)</span>
            <span><span class="kat-legende__box kat-box--conf" style="border:1px solid #b9b2e3"></span>Conformed Dimension</span>
            <span><span class="kat-legende__box kat-box--dim" style="border:1px solid #a9c8f0"></span>Bereichs-Dimension</span>
            <span>┄ geplant, fehlt</span>` : '';
        return `<div class="kat-legende">${bx}${st}</div>`;
    }

    function zeilenText(st) {
        if (!st.ist) return '';
        if (st.ist.zugriff === false) return 'kein Lesezugriff';
        if (st.ist.zeilen !== undefined) return `${W.fmt.zahl(st.ist.zeilen)} Zeilen`;
        return '';
    }

    function kurzName(quelle) {
        return quelle ? String(quelle).split('.').pop() : '';
    }

    /**
     * Linien zwischen Elementen. paare: [{von: el, nach: el, seiteVon, seiteNach, fehlt, label}]
     * seite: 'rechts' | 'links' | 'unten' | 'oben' | 'auto'
     */
    function linien(root, svg, paare) {
        const r0 = root.getBoundingClientRect();
        svg.setAttribute('width', r0.width);
        svg.setAttribute('height', r0.height);
        const punkt = (b, seite) => {
            const x = b.left - r0.left, y = b.top - r0.top;
            switch (seite) {
                case 'rechts': return [x + b.width, y + b.height / 2];
                case 'links': return [x, y + b.height / 2];
                case 'unten': return [x + b.width / 2, y + b.height];
                default: return [x + b.width / 2, y];
            }
        };
        let html = '';
        for (const p of paare) {
            if (!p.von || !p.nach) continue;
            const a = p.von.getBoundingClientRect(), b = p.nach.getBoundingClientRect();
            if (!a.width || !b.width) continue;
            let sv = p.seiteVon, sn = p.seiteNach;
            if (!sv || sv === 'auto') {
                if (a.right <= b.left) { sv = 'rechts'; sn = 'links'; }
                else if (b.right <= a.left) { sv = 'links'; sn = 'rechts'; }
                else if (a.bottom <= b.top) { sv = 'unten'; sn = 'oben'; }
                else { sv = 'oben'; sn = 'unten'; }
            }
            const [x1, y1] = punkt(a, sv), [x2, y2] = punkt(b, sn);
            const horiz = sv === 'rechts' || sv === 'links';
            const d = horiz
                ? `M${x1},${y1} H${(x1 + x2) / 2} V${y2} H${x2}`
                : `M${x1},${y1} V${(y1 + y2) / 2} H${x2} V${y2}`;
            html += `<path d="${d}" class="${p.fehlt ? 'kat-line--fehlt' : ''}"/>`;
            html += `<circle cx="${x2}" cy="${y2}" r="3" fill="var(--viz-axis, #c3c2b7)"/>`;
            if (p.label) html += `<text x="${(x1 + x2) / 2 + 3}" y="${(y1 + y2) / 2 - 3}">${W.esc(p.label)}</text>`;
        }
        svg.innerHTML = html;
    }

    function panel(root, inhalt) {
        let p = root.querySelector('.kat-panel');
        if (!p) {
            p = document.createElement('aside');
            p.className = 'kat-panel';
            p.setAttribute('role', 'dialog');
            root.appendChild(p);
        }
        if (!inhalt) { p.hidden = true; return; }
        p.hidden = false;
        p.innerHTML = `<button class="kat-panel__zu" title="Schließen" aria-label="Schließen">×</button>${inhalt}`;
        p.querySelector('.kat-panel__zu').addEventListener('click', () => { p.hidden = true; });
    }

    /** Detailinhalt eines Elements für das Panel */
    function details(typ, el, st) {
        const zeilen = [];
        zeilen.push(['Art', typ]);
        zeilen.push(['Status', badge(st)]);
        if (el.status && el.status !== st.key) zeilen.push(['Plan', W.esc(el.status)]);
        if (el.quelle) zeilen.push(['Quelle', W.esc(el.quelle)]);
        if (st.ist?.art) zeilen.push(['Objekt', W.esc(st.ist.art)]);
        const z = zeilenText(st);
        if (z) zeilen.push(['Ist-Stand', W.esc(z)]);
        if (st.hinweis) zeilen.push(['Hinweis', W.esc(st.hinweis)]);
        if (el.luecke) zeilen.push(['Lücke / Notiz', W.esc(el.luecke)]);
        if (el.attribute?.length) zeilen.push(['Attribute', W.esc(el.attribute.join(', '))]);
        if (el.schluessel?.length) zeilen.push(['Schlüssel', W.esc(el.schluessel.join(', '))]);
        return `<h3>${W.esc(el.titel || el.id)}</h3><dl>${zeilen.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
    }

    /** Linien neu zeichnen, sobald sich die Größe ändert; liefert dispose() */
    function beobachte(root, zeichne) {
        let raf = 0;
        const ro = new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(zeichne); });
        ro.observe(root);
        requestAnimationFrame(zeichne);
        return () => { ro.disconnect(); cancelAnimationFrame(raf); };
    }

    window.studioKatalog = {
        STATUS, injectStyle, ctx, status, abdeckung, badge, legende, linien, panel, details,
        zeilenText, kurzName, beobachte,
    };
})();
