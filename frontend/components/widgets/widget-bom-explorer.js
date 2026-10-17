/**
 * daita-studio – Widget „bom-explorer“: ein normalisiertes Modell (3NF mit Historie)
 * interaktiv abfragen. Gegenstück zum Star-Explorer, gleiche Bedienung.
 *
 * Oben: Ausgangsentität (eine Zeile je …) und Zeitbezug (aktuell / Stichtag).
 * Darunter das Modell als Baum in Ebenen relativ zur Ausgangsentität:
 *   oben    Vorfahren (n:1)  – JOIN: gruppieren, filtern, verschiedene zählen
 *   Basis                    – gruppieren, filtern, zählen
 *   unten   Nachfahren (1:n) – Bedingung (EXISTS) und Anzahl (vorab gezählt)
 *   daneben über einen Vorfahren erreichbar – nur Bedingung (EXISTS)
 * Darunter SQL (live), R-Gerüst und Ergebnis mit Nachladen.
 *
 * Daten: Widget-Daten enthalten `bom` (Definition aus bom.yml, ohne Ausdrücke).
 * Abfragen über /api/dashboards/<id>/widgets/<wid>/bom/abfrage (nur Auswahl, nie SQL).
 * optionen: basis (Ausgangsentität), seite (Zeilen je Nachladen, Default 100)
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-star-explorer.js (window.studioExplorer),
 *                 api.js (window.api.dashboards.bom*)
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const X = () => window.studioExplorer;
    const esc = s => W.esc(s);

    const STYLE = `
    .bx-kopf { display: flex; flex-wrap: wrap; gap: 14px 22px; align-items: center; }
    .bx-kopf label { display: inline-flex; gap: 6px; align-items: center; font-size: .9em; }
    .bx-basis { display: flex; flex-wrap: wrap; gap: 6px; }
    .bx-baum { position: relative; display: flex; flex-direction: column; gap: 34px; padding: 6px 0; }
    .bx-ebene { display: flex; flex-wrap: wrap; justify-content: center; gap: 18px; position: relative; z-index: 1; }
    .bx-ebene__titel { position: absolute; left: 0; top: -20px; font-size: .74em; color: var(--viz-text-secondary, #6b6a66);
                       text-transform: uppercase; letter-spacing: .03em; }
    .bx-box { min-width: 230px; max-width: 300px; }
    .bx-box.oben { border-color: #8fb3e8; }
    .bx-box.basis { border-width: 2px; border-color: #b9a7e8; box-shadow: 0 0 0 3px rgba(118,75,162,.08); }
    .bx-box.unten { border-color: #9ccfa9; }
    .bx-box.daneben { border-style: dashed; }
    .bx-art { font-size: .72em; border-radius: 8px; padding: 1px 7px; font-weight: 600; white-space: nowrap; }
    .bx-art.oben { background: #e7f0fc; color: #1d4f91; } .bx-art.basis { background: #f0eef8; color: #4a3aa7; }
    .bx-art.unten { background: #e6f5ea; color: #2e6b3c; } .bx-art.daneben { background: #f1f1f1; color: #555; }
    .bx-zaehlen { display: flex; gap: 6px; align-items: center; font-size: .84em; padding: 4px 8px 0; }
    .sx-ico:disabled { opacity: .25; cursor: not-allowed; }
    .bx-lines { position: absolute; inset: 0; pointer-events: none; z-index: 0; overflow: visible; }
    @media (max-width: 1100px) { .bx-lines { display: none; } }`;

    function injectStyle() {
        X().injectStyle();
        if (document.getElementById('bx-style')) return;
        const s = document.createElement('style');
        s.id = 'bx-style'; s.textContent = STYLE;
        document.head.appendChild(s);
    }

    const ART = {
        oben: ['n:1 · JOIN', 'Vorfahre: wird gejoint – gruppieren, filtern, verschiedene zählen'],
        basis: ['Basis', 'Ausgangsentität: eine Ergebniszeile je Satz'],
        unten: ['1:n · zählen / Bedingung', 'Nachfahre: würde Zeilen vervielfachen – nur als Anzahl (vorab gezählt) oder Bedingung (EXISTS)'],
        daneben: ['über Vorfahre · Bedingung', 'über einen Vorfahren erreichbar – nur als Bedingung (EXISTS)'],
    };

    W.register('bom-explorer', {
        tabelle: false,
        render(el, daten, opt = {}, ctx = {}) {
            injectStyle();
            const def = daten.bom;
            if (!def || !def.entitaeten?.length) { el.innerHTML = '<div class="dsh-msg">Kein Modell definiert</div>'; return null; }
            const dashId = ctx.dashboard?.id, widgetId = ctx.widget?.id;
            const seite = Number(opt.seite) || 100;
            const api = window.api.dashboards;
            const ents = Object.fromEntries(def.entitaeten.map(e => [e.id, e]));
            const werteCache = {};
            let basis = def.basis, zeit = { art: 'aktuell', datum: new Date().toISOString().slice(0, 10) };
            let auswahl, ergebnis = null, ladeNr = 0, sqlTimer = null, pop = null, resizeObs = null;

            const stru = () => def.basen[basis];
            const key = (e, a) => `${e}|${a}`;
            const neueAuswahl = () => ({ gruppen: [], filter: {}, kennzahlen: [{ entitaet: basis }] });
            function auswahlApi() {
                return {
                    zeit: zeit.art === 'aktuell' ? { art: 'aktuell' } : { art: 'stichtag', datum: zeit.datum },
                    gruppen: auswahl.gruppen,
                    filter: Object.entries(auswahl.filter).map(([k, f]) => {
                        const [entitaet, attr] = k.split('|');
                        return { entitaet, attr, op: f.op, werte: f.werte };
                    }),
                    kennzahlen: auswahl.kennzahlen,
                };
            }
            const istGruppe = (e, a) => auswahl.gruppen.some(g => g.entitaet === e && g.attr === a);
            const zaehlt = e => auswahl.kennzahlen.some(k => k.entitaet === e);

            /** Entitäten, die im SQL vorkommen (direkt gewählt oder auf dem Weg dorthin). */
            function genutzt() {
                const s = stru(), n = new Set([basis]);
                const direkt = new Set([...auswahl.gruppen.map(g => g.entitaet), ...Object.keys(auswahl.filter).map(k => k.split('|')[0]),
                    ...auswahl.kennzahlen.map(k => k.entitaet)]);
                const hoch = id => { let x = id; while (x && x !== basis) { n.add(x); x = ents[x].eltern; if (s[x]?.art !== 'oben' && x !== basis) break; } };
                for (const id of direkt) {
                    n.add(id);
                    const st = s[id];
                    if (st.art === 'oben') hoch(id);
                    if (st.art === 'unten' || st.art === 'daneben') {
                        (st.abwaerts || []).forEach(x => n.add(x));
                        if (st.anker) { n.add(st.anker); if (s[st.anker].art === 'oben') hoch(st.anker); }
                    }
                }
                // Vorfahren zwischen Basis und genutztem Vorfahren
                for (const id of [...n]) if (s[id]?.art === 'oben') {
                    let x = ents[basis].eltern;
                    while (x && x !== id) { n.add(x); x = ents[x].eltern; }
                }
                return n;
            }

            // ---------------- Aufbau ----------------
            function attrZeilen(e, art) {
                const darfGruppe = art === 'basis' || art === 'oben';
                return e.attribute.map(a => {
                    const f = auswahl.filter[key(e.id, a.id)];
                    const g = istGruppe(e.id, a.id);
                    return `<div class="sx-attr">
                        <button class="sx-ico ${g ? 'an' : ''}" data-gruppe="${esc(e.id)}|${esc(a.id)}" ${darfGruppe ? '' : 'disabled'}
                            title="${darfGruppe ? (g ? 'Gruppierung entfernen' : 'Nach diesem Attribut gruppieren (GROUP BY)')
                                : 'Gruppieren nicht möglich: 1:n würde Zeilen vervielfachen'}">▦</button>
                        <span title="${esc(a.code ? a.id + ' → Text über Codetabelle' : a.id)}">${esc(a.titel)}${a.code ? ' <span class="sx-hint">(Text)</span>' : ''}</span>
                        <button class="sx-chip ${f ? 'an' : ''}" data-filter="${esc(e.id)}|${esc(a.id)}"
                            title="${f ? esc(X().filterText(f)) : (art === 'basis' || art === 'oben' ? 'Filter setzen (WHERE)' : 'Bedingung setzen (EXISTS: mindestens einer erfüllt sie)')}">${esc(X().filterText(f))}</button>
                    </div>`;
                }).join('');
            }

            function box(e, nutz) {
                const st = stru()[e.id], art = st.art;
                const [kurz, lang] = ART[art] || ['', ''];
                const zaehl = art === 'daneben' ? '' : `<label class="bx-zaehlen"><input type="checkbox" data-zaehlen="${esc(e.id)}" ${zaehlt(e.id) ? 'checked' : ''}>
                    ${art === 'basis' ? `Anzahl ${esc(e.titel)}` : art === 'oben' ? `Anzahl verschiedene ${esc(e.titel)}` : `Anzahl ${esc(e.titel)} je ${esc(ents[basis].titel)}`}</label>`;
                const fk = e.eltern ? `<div class="sx-box__meta">${esc(e.fk)} → ${esc(ents[e.eltern].titel)}</div>` : '';
                return `<div class="sx-box bx-box ${art} ${nutz.has(e.id) ? 'aktiv' : ''}" data-ent="${esc(e.id)}" data-eltern="${esc(e.eltern || '')}">
                    <div class="sx-box__kopf">
                        <div class="sx-box__titel"><span>${esc(e.titel)}</span><span class="sx-alias" title="Alias im SQL">${esc(e.alias)}</span></div>
                        <div style="margin:3px 0"><span class="bx-art ${art}" title="${esc(lang)}">${esc(kurz)}</span></div>
                        <div class="sx-box__meta">${esc(e.tabelle)}</div>${fk}
                    </div>
                    ${zaehl}
                    <div class="sx-box__liste">${attrZeilen(e, art)}</div>
                </div>`;
            }

            function baumHtml() {
                const s = stru(), nutz = genutzt();
                const ebenen = {};
                for (const e of def.entitaeten) if (s[e.id].art !== 'getrennt') (ebenen[s[e.id].ebene] ||= []).push(e);
                return Object.keys(ebenen).map(Number).sort((a, b) => a - b).map(n =>
                    `<div class="bx-ebene">${ebenen[n].map(e => box(e, nutz)).join('')}</div>`).join('');
            }

            function aufbauen() {
                const b = ents[basis];
                el.innerHTML = `<div class="sx">
                    <div class="bx-kopf">
                        <div><div class="sx-hint" style="margin-bottom:4px">Ausgangsentität – eine Ergebniszeile je …</div>
                            <div class="bx-basis" role="tablist">${def.entitaeten.map(e =>
                                `<button class="sx-tab" role="tab" data-basis="${esc(e.id)}" aria-selected="${e.id === basis}">${esc(e.titel)}</button>`).join('')}</div></div>
                        <div><div class="sx-hint" style="margin-bottom:4px">Zeitbezug in jeder Tabelle</div>
                            <label><input type="radio" name="bx-zeit" value="aktuell" ${zeit.art === 'aktuell' ? 'checked' : ''}> aktueller Stand</label>
                            <label><input type="radio" name="bx-zeit" value="stichtag" ${zeit.art === 'stichtag' ? 'checked' : ''}> Stand am
                                <input type="date" data-stichtag value="${esc(zeit.datum)}" ${zeit.art === 'stichtag' ? '' : 'disabled'}></label></div>
                    </div>
                    <div class="sx-hint">${esc(b.beschreibung || '')} Oben die Vorfahren (n:1, werden gejoint), unten die Nachfahren (1:n: nur Anzahl
                        oder Bedingung, sonst vervielfachen sich die Zeilen), gestrichelt was nur über einen Vorfahren erreichbar ist.
                        ▦ = gruppieren, Chip = filtern bzw. Bedingung. Gruppen unter ${esc(def.min_zelle ?? '–')} Zeilen werden maskiert.</div>
                    <div class="bx-baum"><svg class="bx-lines"></svg>${baumHtml()}</div>
                    <div class="sx-bar">
                        <button class="sx-btn sx-btn--p" data-act="run">▶ Abfrage ausführen</button>
                        <button class="sx-btn sx-btn--s" data-act="reset">Auswahl leeren</button>
                        <span class="sx-msg" data-info></span>
                    </div>
                    <div class="sx-sql"><pre data-sql></pre><div class="sx-copy">
                        <button class="sx-btn sx-btn--s" data-act="copy">SQL kopieren</button>
                        <button class="sx-btn sx-btn--s" data-act="r" title="R-Skript zu dieser Abfrage: DEF-Block mit Umgebungen, Excel-Export wie QL1">R-Gerüst</button></div></div>
                    <div class="sx-r" data-r hidden>
                        <div class="sx-bar"><b>R-Gerüst zur aktuellen Abfrage</b>
                            <span class="sx-hint">Zugangsdaten im DEF-Block statt „TODO“ eintragen; Filterwerte und Stichtag stehen in DEF$filter.</span>
                            <span style="flex:1"></span>
                            <button class="sx-btn sx-btn--s" data-act="r-copy">Kopieren</button>
                            <button class="sx-btn sx-btn--s" data-act="r-save">Als .R speichern</button>
                            <button class="sx-btn sx-btn--s" data-act="r-zu">Schließen</button></div>
                        <pre data-r-code></pre>
                    </div>
                    <div class="sx-res" data-res><div class="sx-hint" style="padding:10px">Noch keine Abfrage ausgeführt.</div></div>
                </div>`;
                linien();
                sqlVorschau(0);
            }

            function neuZeichnen() {
                const baum = el.querySelector('.bx-baum');
                baum.innerHTML = '<svg class="bx-lines"></svg>' + baumHtml();
                linien();
                sqlVorschau();
                const rBox = el.querySelector('[data-r]');
                if (rBox && !rBox.hidden) rGeruest();
            }

            function linien() {
                const baum = el.querySelector('.bx-baum'), svg = el.querySelector('.bx-lines');
                if (!baum || !svg || getComputedStyle(svg).display === 'none') return;
                const br = baum.getBoundingClientRect(), pfade = [];
                baum.querySelectorAll('.bx-box[data-eltern]').forEach(k => {
                    const p = k.dataset.eltern && baum.querySelector(`.bx-box[data-ent="${CSS.escape(k.dataset.eltern)}"]`);
                    if (!p) return;
                    const kr = k.getBoundingClientRect(), pr = p.getBoundingClientRect();
                    const x1 = pr.left + pr.width / 2 - br.left, y1 = pr.bottom - br.top;
                    const x2 = kr.left + kr.width / 2 - br.left, y2 = kr.top - br.top;
                    const an = k.classList.contains('aktiv') && p.classList.contains('aktiv');
                    const my = (y1 + y2) / 2;
                    pfade.push(`<path d="M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}" fill="none"
                        stroke="${an ? 'var(--primary-color, #667eea)' : '#c9c9d6'}" stroke-width="${an ? 2.5 : 1.2}" ${an ? '' : 'stroke-dasharray="4 4"'}/>`
                        + `<text x="${(x1 + x2) / 2 + 6}" y="${my - 3}" font-size="10" fill="#8a8984">1 : n</text>`);
                });
                svg.setAttribute('width', br.width); svg.setAttribute('height', br.height);
                svg.innerHTML = pfade.join('');
            }

            // ---------------- SQL / Ausführen ----------------
            const parameter = extra => ({ basis, q: JSON.stringify(auswahlApi()), ...extra });

            function sqlVorschau(verz = 250) {
                clearTimeout(sqlTimer);
                sqlTimer = setTimeout(async () => {
                    const nr = ++ladeNr;
                    try {
                        const r = await api.bomAbfrage(dashId, widgetId, parameter({ ausfuehren: false }));
                        if (nr !== ladeNr) return;
                        el.querySelector('[data-sql]').innerHTML = X().sqlHtml(r.sql_mit_werten);
                        el.querySelector('[data-sql]')._sql = r.sql_mit_werten;
                    } catch (e) {
                        el.querySelector('[data-sql]').textContent = `-- ${e.message}`;
                    }
                }, verz);
            }

            async function ausfuehren() {
                const res = el.querySelector('[data-res]'), info = el.querySelector('[data-info]');
                const btn = el.querySelector('[data-act="run"]');
                btn.disabled = true;
                info.className = 'sx-msg'; info.textContent = 'Abfrage läuft …';
                const p = parameter({ offset: 0, limit: seite });
                try {
                    const r = await api.bomAbfrage(dashId, widgetId, p);
                    ergebnis = { ...r, p, zeilen: r.zeilen.slice(), laedt: false };
                    zeigeErgebnis();
                } catch (e) {
                    info.className = 'sx-msg err'; info.textContent = e.message;
                    res.innerHTML = '';
                } finally { btn.disabled = false; }
            }

            function zelle(v, sp) {
                if (v === null && sp.art !== 'gruppe') return `<td class="mask" title="maskiert: weniger als ${esc(def.min_zelle)} Zeilen">&lt;${esc(def.min_zelle)}</td>`;
                if (sp.art === 'gruppe' && typeof v === 'number') return `<td>${esc(String(v))}</td>`;
                if (sp.typ === 'zahl' && typeof v === 'number') return `<td class="num">${esc(W.fmt.zahl(v))}</td>`;
                return `<td>${esc(v === null ? '(leer)' : W.fmt.wert(v))}</td>`;
            }

            function zeigeErgebnis() {
                const r = ergebnis, res = el.querySelector('[data-res]'), info = el.querySelector('[data-info]');
                const teile = [`${W.fmt.zahl(r.gesamt)} Gruppen`];
                if (r.abgeschnitten) teile.push(`auf ${W.fmt.zahl(def.max_gruppen)} begrenzt`);
                if (r.maskiert) teile.push(`${W.fmt.zahl(r.maskiert)} Werte maskiert (bisher geladen)`);
                teile.push(r.cache ? 'aus Cache' : `${W.fmt.zahl((r.laufzeit_ms || 0) / 1000, 1)} s`);
                info.className = 'sx-msg'; info.textContent = teile.join(' · ');
                const kopf = r.spalten.map(s => `<th class="${s.art !== 'gruppe' ? 'num' : ''}">${esc(s.titel)}<small>${esc(s.art === 'gruppe' ? (s.rolle || '') : s.name)}</small></th>`).join('');
                const koerper = r.zeilen.map(z => `<tr>${z.map((v, i) => zelle(v, r.spalten[i])).join('')}</tr>`).join('');
                const mehr = r.zeilen.length < r.gesamt
                    ? `<tr class="sx-mehr"><td colspan="${r.spalten.length}">${W.fmt.zahl(r.zeilen.length)} von ${W.fmt.zahl(r.gesamt)} – weiterscrollen lädt mehr</td></tr>` : '';
                const top = res.scrollTop;
                res.innerHTML = r.gesamt ? `<table><thead><tr>${kopf}</tr></thead><tbody>${koerper}${mehr}</tbody></table>`
                    : '<div class="sx-hint" style="padding:10px">Keine Zeilen.</div>';
                res.scrollTop = top;
            }

            async function nachladen() {
                const r = ergebnis;
                if (!r || r.laedt || r.zeilen.length >= r.gesamt) return;
                r.laedt = true;
                try {
                    const n = await api.bomAbfrage(dashId, widgetId, { ...r.p, offset: r.zeilen.length, limit: seite });
                    if (ergebnis !== r) return;
                    r.zeilen.push(...n.zeilen);
                    r.maskiert += n.maskiert;
                    zeigeErgebnis();
                } catch (e) {
                    el.querySelector('[data-info]').textContent = e.message;
                } finally { r.laedt = false; }
            }

            async function rGeruest() {
                const boxR = el.querySelector('[data-r]'), pre = el.querySelector('[data-r-code]');
                boxR.hidden = false;
                pre.textContent = 'Erzeuge R-Gerüst …';
                try {
                    const r = await api.bomR(dashId, widgetId, parameter({}));
                    pre.textContent = r.r_code;
                    boxR._datei = r.dateiname;
                    boxR.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                } catch (e) { pre.textContent = `# ${e.message}`; }
            }

            // ---------------- Filter-Popover ----------------
            function schliessePop() { pop?.remove(); pop = null; }

            async function oeffneFilter(knopf, eid, attr) {
                schliessePop();
                const e = ents[eid], a = e.attribute.find(x => x.id === attr), k = key(eid, attr);
                const f = auswahl.filter[k], art = stru()[eid].art;
                pop = document.createElement('div');
                pop.className = 'sx-pop';
                const wurzel = el.querySelector('.sx');
                const br = wurzel.getBoundingClientRect(), kr = knopf.getBoundingClientRect();
                pop.style.left = Math.max(0, Math.min(kr.left - br.left - 120, br.width - 290)) + 'px';
                pop.style.top = (kr.bottom - br.top + 4) + 'px';
                wurzel.style.position = 'relative';
                wurzel.appendChild(pop);
                const hinweis = art === 'unten' || art === 'daneben'
                    ? `<div class="sx-hint">Bedingung: ${esc(ents[basis].titel)} mit mindestens einem ${esc(e.titel)}, der sie erfüllt (EXISTS).</div>` : '';
                const titel = `<h4>${esc(e.titel)}: ${esc(a.titel)} <span class="sx-hint">(${esc(a.id)})</span></h4>${hinweis}`;
                const knoepfe = `<div class="knoepfe"><button class="sx-btn sx-btn--s" data-pop="weg">Entfernen</button>
                    <button class="sx-btn sx-btn--p" data-pop="ok">Übernehmen</button></div>`;
                if (a.auswahl) {
                    pop.innerHTML = `${titel}<input type="text" placeholder="Suchen …" data-such><div class="liste">Lade Werte …</div>${knoepfe}`;
                    let werte = werteCache[k];
                    if (!werte) {
                        try {
                            werte = (await api.bomWerte(dashId, widgetId, { entitaet: eid, attr })).werte;
                            werteCache[k] = werte;
                        } catch (ex) { pop.querySelector('.liste').textContent = ex.message; return; }
                    }
                    if (!pop) return;
                    const gesetzt = new Set((f?.op === 'in' ? f.werte : []).map(String));
                    const liste = pop.querySelector('.liste');
                    liste.innerHTML = werte.map(v => `<label><input type="checkbox" value="${esc(v)}" ${gesetzt.has(String(v)) ? 'checked' : ''}> ${esc(W.fmt.wert(v))}</label>`).join('');
                    pop.querySelector('[data-such]').addEventListener('input', ev => {
                        const t = ev.target.value.toLowerCase();
                        liste.querySelectorAll('label').forEach(l => { l.style.display = l.textContent.toLowerCase().includes(t) ? '' : 'none'; });
                    });
                    pop.querySelector('[data-such]').focus();
                } else {
                    const ops = a.typ === 'text' || !a.typ ? X().OPS_TEXT : X().OPS_ZAHL;
                    const typ = a.typ === 'zahl' ? 'number' : a.typ === 'datum' ? 'date' : 'text';
                    pop.innerHTML = `${titel}<select data-op>${ops.map(([o, t]) => `<option value="${o}" ${f?.op === o ? 'selected' : ''}>${t}</option>`).join('')}</select>
                        <input type="${typ}" data-w1 value="${esc(f?.werte?.[0] ?? '')}"><input type="${typ}" data-w2 value="${esc(f?.werte?.[1] ?? '')}" placeholder="bis">${knoepfe}`;
                    const sync = () => {
                        const op = pop.querySelector('[data-op]').value;
                        pop.querySelector('[data-w1]').style.display = ['null', 'notnull'].includes(op) ? 'none' : '';
                        pop.querySelector('[data-w2]').style.display = op === 'between' ? '' : 'none';
                    };
                    pop.querySelector('[data-op]').addEventListener('change', sync); sync();
                    pop.querySelector('[data-w1]').focus();
                }
                pop.addEventListener('click', ev => {
                    const b = ev.target.closest('[data-pop]');
                    if (!b) return;
                    if (b.dataset.pop === 'weg') delete auswahl.filter[k];
                    else {
                        let neu = null;
                        if (a.auswahl) {
                            const w = [...pop.querySelectorAll('.liste input:checked')].map(i => i.value);
                            if (w.length) neu = { op: 'in', werte: w };
                        } else {
                            const op = pop.querySelector('[data-op]').value;
                            const w1 = pop.querySelector('[data-w1]').value, w2 = pop.querySelector('[data-w2]').value;
                            if (['null', 'notnull'].includes(op)) neu = { op, werte: [] };
                            else if (op === 'between' ? (w1 !== '' && w2 !== '') : w1 !== '') neu = { op, werte: op === 'between' ? [w1, w2] : [w1] };
                        }
                        if (neu) auswahl.filter[k] = neu; else delete auswahl.filter[k];
                    }
                    schliessePop();
                    neuZeichnen();
                });
            }

            // ---------------- Ereignisse ----------------
            function onClick(e) {
                const t = e.target;
                if (pop && !pop.contains(t) && !t.closest('[data-filter]')) schliessePop();
                const bs = t.closest('[data-basis]');
                if (bs) { basis = bs.dataset.basis; auswahl = neueAuswahl(); ergebnis = null; aufbauen(); return; }
                const g = t.closest('[data-gruppe]');
                if (g && !g.disabled) {
                    const [entitaet, attr] = g.dataset.gruppe.split('|');
                    const i = auswahl.gruppen.findIndex(x => x.entitaet === entitaet && x.attr === attr);
                    if (i >= 0) auswahl.gruppen.splice(i, 1); else auswahl.gruppen.push({ entitaet, attr });
                    neuZeichnen();
                    return;
                }
                const fl = t.closest('[data-filter]');
                if (fl) { const [eid, attr] = fl.dataset.filter.split('|'); oeffneFilter(fl, eid, attr); return; }
                const act = t.closest('[data-act]')?.dataset.act;
                if (act === 'run') ausfuehren();
                if (act === 'reset') { auswahl = neueAuswahl(); ergebnis = null; aufbauen(); }
                if (act === 'r') rGeruest();
                if (act === 'r-zu') el.querySelector('[data-r]').hidden = true;
                if (act === 'r-copy') {
                    navigator.clipboard?.writeText(el.querySelector('[data-r-code]').textContent)
                        .then(() => { t.textContent = 'Kopiert'; setTimeout(() => { t.textContent = 'Kopieren'; }, 1500); });
                }
                if (act === 'r-save') {
                    const boxR = el.querySelector('[data-r]');
                    const blob = new Blob([el.querySelector('[data-r-code]').textContent], { type: 'text/plain;charset=utf-8' });
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob); a.download = boxR._datei || 'bom_explorer.R';
                    document.body.appendChild(a); a.click(); a.remove();
                    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
                }
                if (act === 'copy') {
                    const sql = el.querySelector('[data-sql]')._sql || '';
                    navigator.clipboard?.writeText(sql).then(() => { t.textContent = 'Kopiert'; setTimeout(() => { t.textContent = 'SQL kopieren'; }, 1500); });
                }
            }
            function onChange(e) {
                const t = e.target;
                if (t.dataset.zaehlen !== undefined) {
                    const id = t.dataset.zaehlen;
                    if (t.checked) { if (!zaehlt(id)) auswahl.kennzahlen.push({ entitaet: id }); }
                    else auswahl.kennzahlen = auswahl.kennzahlen.filter(k => k.entitaet !== id);
                    neuZeichnen();
                } else if (t.name === 'bx-zeit') {
                    zeit.art = t.value;
                    el.querySelector('[data-stichtag]').disabled = zeit.art !== 'stichtag';
                    sqlVorschau();
                } else if (t.dataset.stichtag !== undefined) {
                    zeit.datum = t.value || zeit.datum;
                    sqlVorschau();
                }
            }
            function onScroll(e) {
                const res = e.target;
                if (res.matches?.('[data-res]') && res.scrollTop + res.clientHeight > res.scrollHeight - 80) nachladen();
            }
            el.addEventListener('click', onClick);
            el.addEventListener('change', onChange);
            el.addEventListener('scroll', onScroll, true);
            if (window.ResizeObserver) { resizeObs = new ResizeObserver(() => linien()); resizeObs.observe(el); }

            auswahl = neueAuswahl();
            aufbauen();
            return {
                dispose() {
                    clearTimeout(sqlTimer); schliessePop(); resizeObs?.disconnect();
                    el.removeEventListener('click', onClick); el.removeEventListener('change', onChange);
                    el.removeEventListener('scroll', onScroll, true);
                },
            };
        },
    });
})();
