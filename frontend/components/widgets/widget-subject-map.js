/**
 * daita-studio – Widget „subject-map“ (Übersicht Reusable / Business-Objekt-Modell)
 *
 * Ein Kasten je Bereich `art: subject_area` mit seinen Entitäten (Status, umgesetzte
 * Tabelle, Zeilenzahl); Beziehungen aus `beziehungen: [{von, nach, kard}]` als Linien.
 * Entitäten mit `kern: true` sind hervorgehoben, `zusatz: true` markiert Entitäten,
 * die umgesetzt, aber in der Vorlage nicht benannt sind.
 *
 * Daten: Widget mit `daten: katalog` → { katalog, status, dashboards }
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-katalog.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const K = () => window.studioKatalog;

    const STYLE = `
        .kat-sa-summe { color: var(--viz-text-secondary, #52514e); margin-bottom: 10px; }
        .kat-sa-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 28px 40px; }
        .kat-sa { border: 1px dashed var(--viz-axis, #c3c2b7); border-radius: 14px; padding: 12px 14px; background: #fafaf8; }
        .kat-sa__titel { font-weight: 600; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 8px; }
        .kat-sa__ents { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
        .kat-ent--kern { box-shadow: inset 0 0 0 2px var(--status-good, #0ca30c); }
        .kat-ent__tag { font-size: 0.78em; border-radius: 8px; padding: 0 6px; background: #eef4fc; color: var(--viz-series-1, #2a78d6); }
        @media (max-width: 900px) { .kat-lines { display: none; } }
    `;

    function injectStyle() {
        K().injectStyle();
        if (document.getElementById('kat-sa-style')) return;
        const s = document.createElement('style');
        s.id = 'kat-sa-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    W.register('subject-map', {
        tabelle: false,
        render(el, daten) {
            injectStyle();
            const kat = daten.katalog || {};
            const c = K().ctx(daten);
            const areas = (kat.bereiche || []).filter(b => b.art === 'subject_area');
            if (!areas.length) {
                el.innerHTML = '<div class="dsh-msg">Kein Katalog mit Subject Areas (art: subject_area) gefunden.</div>';
                return null;
            }
            const reg = new Map();
            let vorlage = 0, umgesetzt = 0, fehlend = 0;
            for (const a of areas) {
                for (const e of a.entitaeten || []) {
                    const st = K().status(e, c);
                    reg.set(e.id, { el: e, st, area: a });
                    if (!e.zusatz) {
                        vorlage++;
                        if (st.key === 'fehlt') fehlend++; else umgesetzt++;
                    }
                }
            }

            const areaHtml = areas.map(a => {
                const liste = (a.entitaeten || []).filter(e => !e.zusatz).map(e => reg.get(e.id).st);
                const ab = K().abdeckung(liste);
                const ents = (a.entitaeten || []).map(e => {
                    const { st } = reg.get(e.id);
                    const z = K().zeilenText(st);
                    return `<div class="kat-box kat-box--dim${st.key === 'fehlt' ? ' kat-box--fehlt' : ''}${e.kern ? ' kat-ent--kern' : ''}" data-ent="${W.esc(e.id)}">
                        <div class="kat-box__titel"><span>${e.kern ? '★ ' : ''}${W.esc(e.titel || e.id)}</span></div>
                        <div>${K().badge(st, true)} ${e.zusatz ? '<span class="kat-ent__tag">zusätzlich</span>' : ''}</div>
                        ${e.quelle ? `<div class="kat-box__sub">${W.esc(K().kurzName(e.quelle))}</div>` : ''}
                        ${z ? `<div class="kat-box__sub">${W.esc(z)}</div>` : ''}
                    </div>`;
                }).join('');
                return `<section class="kat-sa">
                    <div class="kat-sa__titel"><span>${W.esc(a.titel || a.id)}</span>${K().badge(ab, true)}</div>
                    <div class="kat-sa__ents">${ents}</div>
                </section>`;
            }).join('');

            el.innerHTML = `
                <div class="kat">
                    <h3>${W.esc(kat.titel_reusable || 'Business-Objekt-Modell')}</h3>
                    ${K().legende(false)}
                    <div class="kat-sa-summe">Entitäten laut Vorlage: ${vorlage} · umgesetzt oder ableitbar: ${umgesetzt} · fehlen: ${fehlend}
                        · ★ Kern-Entität · Linien: Beziehungen</div>
                    <div class="kat-sa-grid">${areaHtml}</div>
                    <svg class="kat-lines" aria-hidden="true"></svg>
                </div>`;
            const root = el.querySelector('.kat');

            root.querySelectorAll('[data-ent]').forEach(n => n.addEventListener('click', ev => {
                ev.stopPropagation();
                const r = reg.get(n.dataset.ent);
                if (r) K().panel(root, K().details(`Entität (${r.area.titel || r.area.id})`, r.el, r.st));
            }));

            const zeichne = () => {
                const paare = (kat.beziehungen || []).map(b => ({
                    von: root.querySelector(`[data-ent="${CSS.escape(b.von)}"]`),
                    nach: root.querySelector(`[data-ent="${CSS.escape(b.nach)}"]`),
                    seiteVon: 'auto',
                    label: b.kard,
                    fehlt: [b.von, b.nach].some(id => reg.get(id)?.st.key === 'fehlt'),
                }));
                K().linien(root, root.querySelector('.kat-lines'), paare);
            };
            const stopp = K().beobachte(root, zeichne);
            return { dispose: stopp };
        },
    });
})();
