/**
 * daita-studio – Widgets „area-map“ und „star-map“ (Übersicht Consumable)
 *
 * area-map: Kachelreihe aller Bereiche (art: mart) mit Produktzahl, Priorität,
 *   Schutzniveau und Abdeckung; links die Conformed Dimensions; in der Mitte der
 *   Stern des gewählten Bereichs (Fakt, Kennzahlen, Dimensionen, Linien);
 *   darunter heutige Umsetzung und Datenprodukte; unten die übrigen Bereiche kurz.
 * star-map: nur der Stern eines Bereichs (optionen.bereich), ohne Kacheln.
 *
 * Daten: Widget mit `daten: katalog` → { katalog, status, dashboards }
 * optionen:
 *   bereich: ID des zuerst gewählten Bereichs (Default: erster)
 *
 * Klick auf ein Element öffnet ein Detail-Panel (Status, Quelle, Ist-Stand, Lücke).
 * Gewählter Bereich steht im URL-Hash als `bereich=<id>`.
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-katalog.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const K = () => window.studioKatalog;

    const STYLE = `
        .kat-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 16px; }
        .kat-tile { border: 2px solid var(--border-color, #e0e0e0); border-radius: 10px; padding: 8px 10px; cursor: pointer;
                    background: var(--card-bg, #fff); text-align: left; font: inherit; color: inherit; }
        .kat-tile:hover { background: var(--bg-color, #f5f5f5); }
        .kat-tile[aria-selected="true"] { background: #f0eef8; box-shadow: 0 0 0 2px var(--primary-color, #667eea); }
        .kat-tile__titel { font-weight: 600; line-height: 1.25; }
        .kat-tile__meta { color: var(--viz-text-secondary, #52514e); font-size: 0.88em; line-height: 1.4; margin-top: 2px; }

        .kat-main { display: grid; grid-template-columns: minmax(200px, 260px) 1fr; gap: 56px; align-items: start; }
        .kat-conf { display: flex; flex-direction: column; gap: 12px; }
        .kat-conf__titel { font-weight: 600; color: var(--viz-text-secondary, #52514e); }
        .kat-star { border: 1px dashed var(--viz-axis, #c3c2b7); border-radius: 14px; padding: 14px 16px; }
        .kat-star__grid { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(200px, 1fr); gap: 48px; align-items: center; margin: 8px 0 14px; }
        .kat-star__dims { display: flex; flex-direction: column; gap: 10px; }
        .kat-star__fakten { display: flex; flex-direction: column; gap: 12px; }
        .kat-kz { display: flex; justify-content: space-between; gap: 8px; }
        .kat-abschnitt { margin-top: 12px; }
        .kat-abschnitt__titel { font-weight: 600; margin-bottom: 4px; color: var(--viz-text-secondary, #52514e); }
        .kat-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .kat-chip { border: 1px solid var(--border-color, #e0e0e0); border-radius: 14px; padding: 2px 10px; cursor: pointer; background: var(--card-bg, #fff); }
        .kat-chip:hover { border-color: var(--primary-color, #667eea); }
        .kat-produkte { list-style: none; margin: 0; padding: 0; }
        .kat-produkte li { padding: 2px 0; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
        .kat-produkte a { color: var(--primary-color, #667eea); }
        .kat-pilot { font-size: 0.8em; border-radius: 8px; padding: 0 6px; background: #f0eef8; color: var(--viz-series-7, #4a3aa7); }
        .kat-notiz { color: var(--viz-text-secondary, #52514e); font-style: italic; margin-top: 8px; }

        .kat-weitere { margin-top: 22px; }
        .kat-weitere__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }

        @media (max-width: 1100px) {
            .kat-main, .kat-star__grid { grid-template-columns: 1fr; gap: 16px; }
            .kat-lines { display: none; }
        }
    `;

    function injectStyle() {
        K().injectStyle();
        if (document.getElementById('kat-area-style')) return;
        const s = document.createElement('style');
        s.id = 'kat-area-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function hashBereich() {
        return new URLSearchParams(location.hash.slice(1)).get('bereich');
    }

    function setHashBereich(id) {
        const p = new URLSearchParams(location.hash.slice(1));
        p.set('bereich', id);
        history.replaceState(null, '', '#' + p.toString());
    }

    function render(el, daten, opt, nurStern) {
        injectStyle();
        const kat = daten.katalog || {};
        const c = K().ctx(daten);
        const conf = kat.conformed_dimensionen || [];
        const confNach = Object.fromEntries(conf.map(d => [d.id, d]));
        const marts = (kat.bereiche || []).filter(b => b.art === 'mart').sort((a, b) => (a.nr ?? 99) - (b.nr ?? 99));
        if (!marts.length) {
            el.innerHTML = '<div class="dsh-msg">Kein Katalog mit Bereichen (art: mart) gefunden.</div>';
            return null;
        }

        // Elemente registrieren: key → {typ, el, st}
        const reg = new Map();
        const merke = (key, typ, e) => { const st = K().status(e, c); reg.set(key, { typ, el: e, st }); return st; };
        conf.forEach(d => merke(`conf:${d.id}`, 'Conformed Dimension', d));

        // Abdeckung eines Bereichs = seine Kennzahlen (die Statistiken selbst); ohne Kennzahlen
        // die bereichseigenen Dimensionen. Conformed Dimensions zählen nicht, sie gelten für alle.
        const abdeckung = new Map();
        for (const m of marts) {
            const kzListe = [], dimListe = [];
            for (const f of m.fakten || []) {
                for (const kz of f.kennzahlen || []) kzListe.push(merke(`kz:${m.id}:${f.id}:${kz.id}`, 'Kennzahl', kz));
            }
            for (const d of m.dimensionen || []) dimListe.push(merke(`dim:${m.id}:${d.id}`, 'Bereichs-Dimension', d));
            const liste = kzListe.length ? kzListe : dimListe;
            for (const u of m.umsetzung || []) merke(`ums:${m.id}:${u.quelle || u.titel}`, 'Umsetzung heute', u);
            for (const p of m.produkte || []) merke(`prod:${m.id}:${p.id}`, 'Datenprodukt', p);
            abdeckung.set(m.id, K().abdeckung(liste));
        }

        let gewaehlt = nurStern ? (opt.bereich || marts[0].id)
            : (marts.some(m => m.id === hashBereich()) ? hashBereich() : (opt.bereich || marts[0].id));

        const box = (key, klasse, inner) => {
            const r = reg.get(key);
            const fehlt = r && r.st.key === 'fehlt' ? ' kat-box--fehlt' : '';
            return `<div class="kat-box ${klasse}${fehlt}" data-key="${W.esc(key)}">${inner}</div>`;
        };
        const kopf = (titel, st) => `<div class="kat-box__titel"><span>${W.esc(titel)}</span>${K().badge(st, true)}</div>`;

        function confHtml() {
            return conf.map(d => {
                const st = reg.get(`conf:${d.id}`).st;
                const ums = d.quelle ? `<div class="kat-box__sub">${W.esc(K().kurzName(d.quelle))}${K().zeilenText(st) ? ' · ' + W.esc(K().zeilenText(st)) : ''}</div>` : '';
                return box(`conf:${d.id}`, 'kat-box--conf', kopf(d.titel || d.id, st) + ums
                    + (d.attribute?.length ? `<ul>${d.attribute.map(a => `<li>${W.esc(a)}</li>`).join('')}</ul>` : ''));
            }).join('');
        }

        function sternHtml(m) {
            const fakten = (m.fakten || []).map(f => {
                const kz = (f.kennzahlen || []).map(k => {
                    const st = reg.get(`kz:${m.id}:${f.id}:${k.id}`).st;
                    return `<li class="kat-kz" data-key="${W.esc(`kz:${m.id}:${f.id}:${k.id}`)}"><span>${W.esc(k.titel || k.id)}</span>${K().badge(st, true)}</li>`;
                }).join('');
                const sl = (f.schluessel || []).map(s => `<li>${W.esc(s)} (FK)</li>`).join('');
                return `<div class="kat-box kat-box--fakt" data-fakt="${W.esc(f.id)}">
                    <div class="kat-box__titel"><span>${W.esc(f.titel || f.id)}</span></div>
                    ${sl ? `<ul>${sl}</ul>` : ''}
                    ${kz ? `<div class="kat-box__sub" style="margin-top:6px">Kennzahlen</div><ul>${kz}</ul>` : ''}
                </div>`;
            }).join('');
            const dims = (m.dimensionen || []).map(d => {
                const st = reg.get(`dim:${m.id}:${d.id}`).st;
                const ums = d.quelle ? `<div class="kat-box__sub">${W.esc(K().kurzName(d.quelle))}${K().zeilenText(st) ? ' · ' + W.esc(K().zeilenText(st)) : ''}</div>` : '';
                return box(`dim:${m.id}:${d.id}`, 'kat-box--dim', kopf(d.titel || d.id, st) + ums
                    + (d.attribute?.length ? `<ul>${d.attribute.map(a => `<li>${W.esc(a)}</li>`).join('')}</ul>` : ''));
            }).join('');
            const ums = (m.umsetzung || []).map(u => {
                const key = `ums:${m.id}:${u.quelle || u.titel}`;
                const st = reg.get(key).st;
                const z = K().zeilenText(st);
                return `<span class="kat-chip" data-key="${W.esc(key)}">${K().badge(st, true).replace(/<span class="kat-st__txt">.*?<\/span>/, '')} ${W.esc(u.titel || K().kurzName(u.quelle))}${z ? ' · ' + W.esc(z) : ''}</span>`;
            }).join('');
            const prod = (m.produkte || []).map(p => {
                const key = `prod:${m.id}:${p.id}`;
                const st = reg.get(key).st;
                const titel = `${W.esc(p.id)} ${W.esc(p.titel)}`;
                const link = p.dashboard && c.dashboards.has(p.dashboard)
                    ? `<a href="#d=${encodeURIComponent(p.dashboard)}">${titel}</a>` : `<span>${titel}</span>`;
                return `<li data-key="${W.esc(key)}" style="cursor:pointer">${K().badge(st, true)} ${link}${p.pilot ? '<span class="kat-pilot">Pilot</span>' : ''}</li>`;
            }).join('');
            const anz = m.produkte_anzahl && m.produkte_anzahl > (m.produkte || []).length
                ? `<div class="kat-box__sub">${(m.produkte || []).length} von ${m.produkte_anzahl} Produkten im Katalog benannt</div>` : '';
            const ab = abdeckung.get(m.id);
            return `
                <div class="kat-star">
                    <h3>Data Mart ${W.esc(m.nr ?? '')}: ${W.esc(m.titel)} <span class="kat-box__sub">(Star Schema)</span></h3>
                    <div class="kat-box__sub">Abdeckung ${K().badge(ab)} – ${ab.erfuellt} von ${ab.gesamt} Kennzahlen vorhanden oder ableitbar</div>
                    <div class="kat-star__grid">
                        <div class="kat-star__fakten">${fakten || '<div class="dsh-msg">Kein Fakt definiert</div>'}</div>
                        <div class="kat-star__dims">${dims || '<div class="kat-box__sub">Keine bereichseigenen Dimensionen</div>'}</div>
                    </div>
                    ${ums ? `<div class="kat-abschnitt"><div class="kat-abschnitt__titel">Umsetzung heute</div><div class="kat-chips">${ums}</div></div>` : ''}
                    ${prod || anz ? `<div class="kat-abschnitt"><div class="kat-abschnitt__titel">Datenprodukte</div><ul class="kat-produkte">${prod}</ul>${anz}</div>` : ''}
                    ${m.luecke ? `<div class="kat-notiz">${W.esc(m.luecke)}</div>` : ''}
                </div>`;
        }

        function tilesHtml() {
            return marts.map(m => {
                const ab = abdeckung.get(m.id);
                return `<button class="kat-tile" data-bereich="${W.esc(m.id)}" aria-selected="${m.id === gewaehlt}"
                        style="border-color:${ab.farbe}" title="Abdeckung: ${ab.label} (${ab.erfuellt}/${ab.gesamt})">
                    <div class="kat-tile__titel">${W.esc(m.nr ?? '')}. ${W.esc(m.titel)}</div>
                    <div class="kat-tile__meta">${m.produkte_anzahl ? `${W.esc(m.produkte_anzahl)} Produkte<br>` : ''}
                        ${m.prioritaet ? `Priorität: ${W.esc(m.prioritaet)}<br>` : ''}
                        ${m.schutzniveau ? `Schutz: ${W.esc(m.schutzniveau)}<br>` : ''}
                        ${K().badge(ab, true)}</div>
                </button>`;
            }).join('');
        }

        function weitereHtml() {
            return marts.filter(m => m.id !== gewaehlt).map(m => {
                const ab = abdeckung.get(m.id);
                const f = (m.fakten || [])[0] || {};
                const dims = (f.dimensionen || []).map(d => confNach[d] ? `${confNach[d].titel} (conformed)` :
                    ((m.dimensionen || []).find(x => x.id === d)?.titel || d));
                const kz = (f.kennzahlen || []).map(k => k.titel || k.id);
                return `<div class="kat-box" data-bereich="${W.esc(m.id)}">
                    <div class="kat-box__titel"><span>${W.esc(m.nr ?? '')}: ${W.esc(m.titel)}</span>${K().badge(ab, true)}</div>
                    ${f.titel ? `<div><b>${W.esc(f.titel)}</b></div>` : ''}
                    ${dims.length ? `<div class="kat-box__sub">+ ${dims.map(W.esc).join('<br>+ ')}</div>` : ''}
                    ${kz.length ? `<div class="kat-box__sub" style="margin-top:4px">Kennzahlen: ${kz.map(W.esc).join(', ')}</div>` : ''}
                    <div class="kat-box__sub" style="margin-top:4px">${m.produkte_anzahl ? `${W.esc(m.produkte_anzahl)} Produkte` : ''}${m.schutzniveau ? ` · Schutz: ${W.esc(m.schutzniveau)}` : ''}</div>
                </div>`;
            }).join('');
        }

        let stopp = () => {};
        function zeichne() {
            const m = marts.find(x => x.id === gewaehlt) || marts[0];
            el.innerHTML = `
                <div class="kat">
                    ${nurStern ? '' : `<h3>${W.esc(kat.titel_consumable || 'Data-Mart-Bereiche')}</h3>`}
                    ${K().legende(true)}
                    ${nurStern ? '' : `<div class="kat-tiles" role="tablist">${tilesHtml()}</div>`}
                    <div class="kat-main" style="${nurStern || !conf.length ? 'grid-template-columns:1fr' : ''}">
                        ${nurStern || !conf.length ? '' : `<div class="kat-conf"><div class="kat-conf__titel">Conformed Dimensions</div>${confHtml()}</div>`}
                        ${sternHtml(m)}
                    </div>
                    ${nurStern ? '' : `<div class="kat-weitere"><div class="kat-abschnitt__titel">Weitere Bereiche</div><div class="kat-weitere__grid">${weitereHtml()}</div></div>`}
                    <svg class="kat-lines" aria-hidden="true"></svg>
                </div>`;
            const root = el.querySelector('.kat');

            root.querySelectorAll('[data-bereich]').forEach(b => b.addEventListener('click', () => {
                gewaehlt = b.dataset.bereich;
                setHashBereich(gewaehlt);
                K().panel(root, null);
                zeichne();
            }));
            root.querySelectorAll('[data-key]').forEach(n => n.addEventListener('click', ev => {
                if (ev.target.closest('a')) return;
                ev.stopPropagation();
                const r = reg.get(n.dataset.key);
                if (r) K().panel(root, K().details(r.typ, r.el, r.st));
            }));

            // Linien: Conformed Dims → Fakt (links), Bereichs-Dims → Fakt (rechts)
            const linienZeichnen = () => {
                const svg = root.querySelector('.kat-lines');
                if (!svg) return;
                const paare = [];
                for (const f of m.fakten || []) {
                    const fakt = root.querySelector(`[data-fakt="${CSS.escape(f.id)}"]`);
                    for (const dId of f.dimensionen || []) {
                        if (confNach[dId]) {
                            const n = root.querySelector(`[data-key="${CSS.escape('conf:' + dId)}"]`);
                            paare.push({ von: n, nach: fakt, seiteVon: 'rechts', seiteNach: 'links', fehlt: reg.get('conf:' + dId).st.key === 'fehlt' });
                        } else {
                            const n = root.querySelector(`[data-key="${CSS.escape(`dim:${m.id}:${dId}`)}"]`);
                            const r = reg.get(`dim:${m.id}:${dId}`);
                            paare.push({ von: n, nach: fakt, seiteVon: 'links', seiteNach: 'rechts', fehlt: r?.st.key === 'fehlt' });
                        }
                    }
                }
                K().linien(root, svg, paare);
            };
            stopp();
            stopp = K().beobachte(root, linienZeichnen);
        }

        zeichne();
        return { dispose() { stopp(); } };
    }

    W.register('area-map', { tabelle: false, render: (el, d, opt = {}) => render(el, d, opt, false) });
    W.register('star-map', { tabelle: false, render: (el, d, opt = {}) => render(el, d, opt, true) });
})();
