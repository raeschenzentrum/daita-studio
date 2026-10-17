/**
 * daita-studio – Widget „star-explorer“: ein Sternschema interaktiv abfragen.
 *
 * Oben der Stern: Fakt in der Mitte (Kennzahlen, eigene Attribute), Dimensionen
 * links und rechts, Linien vom Fakt zu jeder Dimension (genutzte Dimensionen
 * hervorgehoben). Je Attribut: gruppieren (▦) und filtern (Filter-Chip).
 * Darunter das erzeugte SQL (live, nur die gebrauchten JOINs) und das Ergebnis
 * als Tabelle; beim Scrollen werden weitere Zeilen nachgeladen.
 *
 * „R-Gerüst“: R-Skript zur aktuellen Auswahl (Vorlage widget.R, Excel-Export).
 *
 * Daten: Widget-Daten enthalten `stern` (Definition aus sterne.yml, ohne Ausdrücke);
 * Abfragen über /api/dashboards/<id>/widgets/<wid>/stern/abfrage (nur Auswahl, nie SQL).
 * optionen: fakten (im Backend ausgewertet), seite (Zeilen je Nachladen, Default 100)
 *
 * Abhängigkeiten: dashboard-widgets.js, api.js (window.api.dashboards.stern*)
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const esc = s => W.esc(s);

    const STYLE = `
    .sx { display: flex; flex-direction: column; gap: 14px; }
    .sx-tabs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .sx-tab { border: 1px solid var(--border-color, #e0e0e0); background: var(--card-bg, #fff); border-radius: 16px;
              padding: 4px 12px; cursor: pointer; font: inherit; color: inherit; }
    .sx-tab[aria-selected="true"] { background: #f0eef8; border-color: var(--primary-color, #667eea); font-weight: 600; }
    .sx-hint { color: var(--viz-text-secondary, #52514e); font-size: .88em; line-height: 1.45; }
    .sx-star { position: relative; display: grid; grid-template-columns: minmax(220px, 1fr) minmax(250px, 1.1fr) minmax(220px, 1fr);
               gap: 18px 56px; align-items: center; }
    .sx-col { display: flex; flex-direction: column; gap: 14px; z-index: 1; }
    .sx-lines { position: absolute; inset: 0; pointer-events: none; z-index: 0; overflow: visible; }
    .sx-box { background: var(--card-bg, #fff); border: 1.5px solid var(--border-color, #d9d9e3); border-radius: 10px; }
    .sx-box.aktiv { border-color: var(--primary-color, #667eea); box-shadow: 0 0 0 2px rgba(102,126,234,.15); }
    .sx-box--fakt { border-width: 2px; border-color: #b9a7e8; }
    .sx-box__kopf { padding: 7px 10px 6px; border-bottom: 1px solid var(--border-color, #eceef3); }
    .sx-box__titel { font-weight: 600; display: flex; gap: 6px; align-items: baseline; justify-content: space-between; }
    .sx-alias { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .8em; background: #eef0f6; border-radius: 4px; padding: 0 5px; }
    .sx-box__meta { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .72em; color: var(--viz-text-secondary, #6b6a66); word-break: break-all; }
    .sx-box__liste { padding: 4px 4px 6px; }
    .sx-attr { display: grid; grid-template-columns: 24px 1fr auto; gap: 4px; align-items: center; padding: 2px 4px; border-radius: 6px; font-size: .9em; }
    .sx-attr:hover { background: #f6f7fb; }
    .sx-ico { border: 1px solid transparent; background: none; cursor: pointer; border-radius: 5px; width: 22px; height: 22px; padding: 0;
              color: var(--viz-text-secondary, #8a8984); font-size: 13px; line-height: 1; }
    .sx-ico:hover { border-color: var(--border-color, #d9d9e3); }
    .sx-ico.an { background: var(--primary-color, #667eea); color: #fff; }
    .sx-chip { border: 1px dashed var(--border-color, #c9c9d6); background: none; border-radius: 10px; padding: 0 7px; font-size: .8em; cursor: pointer;
               color: var(--viz-text-secondary, #6b6a66); max-width: 150px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sx-chip.an { border-style: solid; border-color: #e0a100; background: #fff6dc; color: #6b4e00; }
    .sx-kz { display: grid; grid-template-columns: 20px 1fr auto; gap: 6px; align-items: center; padding: 2px 4px; font-size: .9em; }
    .sx-kz select { font-size: .85em; padding: 1px 2px; }
    .sx-unter { font-size: .78em; font-weight: 600; color: var(--viz-text-secondary, #6b6a66); padding: 6px 6px 2px; text-transform: uppercase; letter-spacing: .03em; }
    .sx-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .sx-btn { border: none; border-radius: 6px; padding: 7px 14px; cursor: pointer; font-weight: 600; font-size: .9em; }
    .sx-btn--p { background: linear-gradient(135deg,#667eea,#764ba2); color: #fff; }
    .sx-btn--s { background: #eef0f4; color: #333; }
    .sx-btn:disabled { opacity: .5; cursor: default; }
    .sx-sql { position: relative; }
    .sx-sql pre { margin: 0; background: #1e1f29; color: #e6e6f0; border-radius: 8px; padding: 12px 14px; font-size: .82em; line-height: 1.5;
                  overflow-x: auto; max-height: 360px; }
    .sx-sql .k { color: #8fb4ff; font-weight: 600; } .sx-sql .c { color: #8a8fa3; font-style: italic; } .sx-sql .s { color: #ffd38a; }
    .sx-sql .j { background: rgba(143,180,255,.12); display: inline-block; width: 100%; }
    .sx-copy { position: absolute; top: 8px; right: 8px; display: flex; gap: 6px; }
    .sx-copy .sx-btn { font-size: .8em; padding: 5px 10px; }
    .sx-r pre { margin: 8px 0 0; background: #f7f8fb; border: 1px solid var(--border-color, #e3e4ea); border-radius: 8px; padding: 12px 14px;
                font-size: .8em; line-height: 1.45; overflow: auto; max-height: 420px; }
    .sx-res { border: 1px solid var(--border-color, #e3e4ea); border-radius: 8px; max-height: 480px; overflow: auto; }
    .sx-res table { border-collapse: collapse; width: 100%; font-size: .86em; }
    .sx-res th, .sx-res td { padding: 5px 10px; border-bottom: 1px solid #f0f1f5; white-space: nowrap; text-align: left; }
    .sx-res th { position: sticky; top: 0; background: #f7f8fb; z-index: 1; }
    .sx-res th small { display: block; font-weight: 400; color: var(--viz-text-secondary, #6b6a66); }
    .sx-res td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .sx-res td.mask { color: #9a9a9a; text-align: right; }
    .sx-res .sx-mehr td { text-align: center; color: var(--viz-text-secondary, #6b6a66); }
    .sx-msg { font-size: .88em; } .sx-msg.err { color: #c62828; }
    .sx-pop { position: absolute; z-index: 50; background: var(--card-bg, #fff); border: 1px solid var(--border-color, #d9d9e3); border-radius: 10px;
              box-shadow: 0 8px 28px rgba(0,0,0,.16); padding: 10px; width: 280px; font-size: .9em; }
    .sx-pop h4 { margin: 0 0 6px; font-size: 1em; }
    .sx-pop .liste { max-height: 220px; overflow: auto; border: 1px solid #eee; border-radius: 6px; padding: 4px; margin: 6px 0; }
    .sx-pop .liste label { display: flex; gap: 6px; align-items: center; padding: 1px 2px; }
    .sx-pop input[type=text], .sx-pop input[type=number], .sx-pop input[type=date], .sx-pop select { width: 100%; box-sizing: border-box; padding: 4px 6px; margin: 3px 0; }
    .sx-pop .knoepfe { display: flex; gap: 6px; justify-content: flex-end; margin-top: 8px; }
    @media (max-width: 1100px) {
        .sx-star { grid-template-columns: 1fr; gap: 12px; }
        .sx-lines { display: none; }
    }`;

    function injectStyle() {
        if (document.getElementById('sx-style')) return;
        const s = document.createElement('style');
        s.id = 'sx-style'; s.textContent = STYLE;
        document.head.appendChild(s);
    }

    const OPS_TEXT = [['eq', '='], ['ne', '≠'], ['like', 'enthält'], ['null', 'leer'], ['notnull', 'nicht leer']];
    const OPS_ZAHL = [['eq', '='], ['ne', '≠'], ['ge', '≥'], ['le', '≤'], ['between', 'von – bis'], ['null', 'leer'], ['notnull', 'nicht leer']];

    function filterText(f) {
        if (!f) return 'Filter';
        const w = f.werte || [];
        switch (f.op) {
            case 'in': return w.length === 1 ? `= ${w[0]}` : `${w.length} Werte`;
            case 'between': return `${w[0]} – ${w[1]}`;
            case 'like': return `enthält ${w[0]}`;
            case 'null': return 'leer';
            case 'notnull': return 'nicht leer';
            default: return `${({ eq: '=', ne: '≠', ge: '≥', le: '≤' })[f.op] || f.op} ${w[0]}`;
        }
    }

    /** SQL einfärben: Schlüsselwörter, Kommentare, Zeichenketten; JOIN-Blöcke hinterlegt. */
    function sqlHtml(sql) {
        const KW = /\b(SELECT|FROM|LEFT JOIN|JOIN|ON|WHERE|AND|GROUP BY|ORDER BY|AS|IN|BETWEEN|IS|NOT|NULL|LIKE|UPPER|COUNT|SUM|AVG|MIN|MAX|DISTINCT|CAST|EXTRACT|YEAR|DECIMAL|DATE)\b/g;
        return sql.split('\n').map(z => {
            const m = z.match(/^(.*?)(--.*)?$/);
            let code = esc(m[1] || '').replace(/'[^']*'/g, s => `<span class="s">${s}</span>`).replace(KW, '<span class="k">$1</span>');
            const kom = m[2] ? `<span class="c">${esc(m[2])}</span>` : '';
            const join = /^\s*(LEFT JOIN|ON)\b/.test(z) || /^-- (Dimension|.*n:1|.*1:n)/.test(z);
            return join ? `<span class="j">${code}${kom}</span>` : code + kom;
        }).join('\n');
    }

    // Gemeinsame Bausteine für weitere Explorer (widget-bom-explorer.js)
    window.studioExplorer = { injectStyle, esc, filterText, sqlHtml, OPS_TEXT, OPS_ZAHL };

    W.register('star-explorer', {
        tabelle: false,
        render(el, daten, opt = {}, ctx = {}) {
            injectStyle();
            const def = daten.stern;
            if (!def || !def.fakten?.length) { el.innerHTML = '<div class="dsh-msg">Kein Stern definiert</div>'; return null; }
            const dashId = ctx.dashboard?.id, widgetId = ctx.widget?.id;
            const seite = Number(opt.seite) || 100;
            const api = window.api.dashboards;
            const werteCache = {};
            let fakt, auswahl, ergebnis = null, ladeNr = 0, sqlTimer = null, pop = null, resizeObs = null;

            function neueAuswahl(f) {
                return {
                    gruppen: [],
                    filter: {},
                    kennzahlen: f.kennzahlen.filter(k => k.standard).map(k => ({ id: k.id, agg: k.agg[0]?.id })),
                };
            }
            function auswahlApi() {
                return {
                    gruppen: auswahl.gruppen,
                    filter: Object.entries(auswahl.filter).map(([k, f]) => {
                        const [rolle, attr] = k.split('|');
                        return { rolle, attr, op: f.op, werte: f.werte };
                    }),
                    kennzahlen: auswahl.kennzahlen,
                };
            }
            const key = (rolle, attr) => `${rolle}|${attr}`;
            const istGruppe = (rolle, attr) => auswahl.gruppen.some(g => g.rolle === rolle && g.attr === attr);
            const genutzt = rolle => auswahl.gruppen.some(g => g.rolle === rolle)
                || Object.keys(auswahl.filter).some(k => k.startsWith(rolle + '|'));

            function waehleFakt(i) {
                fakt = def.fakten[i];
                auswahl = neueAuswahl(fakt);
                ergebnis = null;
                aufbauen();
            }

            // ---------------- Aufbau ----------------
            function attrZeilen(rolle, attribute) {
                return attribute.map(a => {
                    const f = auswahl.filter[key(rolle, a.id)];
                    return `<div class="sx-attr">
                        <button class="sx-ico ${istGruppe(rolle, a.id) ? 'an' : ''}" data-gruppe="${esc(rolle)}|${esc(a.id)}"
                            title="${istGruppe(rolle, a.id) ? 'Gruppierung entfernen' : 'Nach diesem Attribut gruppieren (GROUP BY)'}">▦</button>
                        <span title="${esc(a.id)}">${esc(a.titel)}</span>
                        <button class="sx-chip ${f ? 'an' : ''}" data-filter="${esc(rolle)}|${esc(a.id)}" title="${f ? esc(filterText(f)) : 'Filter setzen (WHERE)'}">${esc(filterText(f))}</button>
                    </div>`;
                }).join('');
            }

            function dimBox(r) {
                return `<div class="sx-box ${genutzt(r.rolle) ? 'aktiv' : ''}" data-rolle="${esc(r.rolle)}">
                    <div class="sx-box__kopf">
                        <div class="sx-box__titel"><span>${esc(r.titel)}</span><span class="sx-alias" title="Alias im SQL">${esc(r.alias)}</span></div>
                        <div class="sx-box__meta">${esc(r.view)}</div>
                        <div class="sx-box__meta">ON ${esc(r.alias)}.${esc(r.schluessel)} = f.${esc(r.spalte)}</div>
                    </div>
                    <div class="sx-box__liste">${attrZeilen(r.rolle, r.attribute)}</div>
                </div>`;
            }

            function faktBox() {
                const kz = fakt.kennzahlen.map(k => {
                    const gew = auswahl.kennzahlen.find(x => x.id === k.id);
                    const aggs = k.agg.length > 1
                        ? `<select data-agg="${esc(k.id)}">${k.agg.map(a => `<option value="${esc(a.id)}" ${gew?.agg === a.id ? 'selected' : ''}>${esc(a.titel)}</option>`).join('')}</select>`
                        : `<span class="sx-hint">${esc(k.agg[0]?.titel || '')}</span>`;
                    return `<label class="sx-kz"><input type="checkbox" data-kz="${esc(k.id)}" ${gew ? 'checked' : ''}>
                        <span title="${esc(k.spalte || 'COUNT(*)')}">${esc(k.titel)}</span>${aggs}</label>`;
                }).join('');
                return `<div class="sx-box sx-box--fakt aktiv" data-rolle="fakt">
                    <div class="sx-box__kopf">
                        <div class="sx-box__titel"><span>Fakt: ${esc(fakt.titel)}</span><span class="sx-alias">f</span></div>
                        <div class="sx-box__meta">${esc(fakt.view)}</div>
                    </div>
                    <div class="sx-unter">Kennzahlen (SELECT … COUNT/SUM/AVG)</div>
                    <div class="sx-box__liste">${kz}</div>
                    ${fakt.attribute.length ? `<div class="sx-unter">Attribute im Fakt</div><div class="sx-box__liste">${attrZeilen('fakt', fakt.attribute)}</div>` : ''}
                </div>`;
            }

            function aufbauen() {
                const dims = fakt.dimensionen;
                const links = dims.filter((_, i) => i % 2 === 0), rechts = dims.filter((_, i) => i % 2 === 1);
                el.innerHTML = `<div class="sx">
                    <div class="sx-tabs" role="tablist">${def.fakten.length > 1 ? def.fakten.map((f, i) =>
                        `<button class="sx-tab" role="tab" data-fakt="${i}" aria-selected="${f === fakt}">${esc(f.titel)}</button>`).join('') : ''}
                        <span class="sx-hint">${esc(fakt.beschreibung || '')}</span></div>
                    <div class="sx-hint">▦ = gruppieren (GROUP BY), Filter-Chip = einschränken (WHERE). Nur gebrauchte Dimensionen werden gejoint;
                        sie sind hervorgehoben. Gruppen mit weniger als ${esc(def.min_zelle ?? '–')} Zeilen werden maskiert.</div>
                    <div class="sx-star">
                        <svg class="sx-lines"></svg>
                        <div class="sx-col">${links.map(dimBox).join('')}</div>
                        <div class="sx-col">${faktBox()}</div>
                        <div class="sx-col">${rechts.map(dimBox).join('')}</div>
                    </div>
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
                            <span class="sx-hint">Zugangsdaten im DEF-Block statt „TODO“ eintragen; Filterwerte stehen in DEF$filter.</span>
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
                // Stern-Teil und SQL aktualisieren, Ergebnis bleibt bis zur nächsten Ausführung stehen
                const star = el.querySelector('.sx-star');
                const dims = fakt.dimensionen;
                const cols = star.querySelectorAll('.sx-col');
                cols[0].innerHTML = dims.filter((_, i) => i % 2 === 0).map(dimBox).join('');
                cols[1].innerHTML = faktBox();
                cols[2].innerHTML = dims.filter((_, i) => i % 2 === 1).map(dimBox).join('');
                linien();
                sqlVorschau();
                const rBox = el.querySelector('[data-r]');
                if (rBox && !rBox.hidden) rGeruest();   // offenes R-Gerüst folgt der Auswahl
            }

            function linien() {
                const star = el.querySelector('.sx-star'), svg = el.querySelector('.sx-lines');
                if (!star || !svg) return;
                const sr = star.getBoundingClientRect();
                const fb = star.querySelector('.sx-box--fakt')?.getBoundingClientRect();
                if (!fb || getComputedStyle(svg).display === 'none') { svg.innerHTML = ''; return; }
                const pfade = [];
                star.querySelectorAll('.sx-box[data-rolle]:not(.sx-box--fakt)').forEach(b => {
                    const r = b.getBoundingClientRect();
                    const rechts = r.left > fb.right;
                    const x1 = (rechts ? fb.right : fb.left) - sr.left, y1 = fb.top + fb.height / 2 - sr.top;
                    const x2 = (rechts ? r.left : r.right) - sr.left, y2 = r.top + Math.min(r.height / 2, 40) - sr.top;
                    const an = b.classList.contains('aktiv');
                    const mx = (x1 + x2) / 2;
                    pfade.push(`<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none"
                        stroke="${an ? 'var(--primary-color, #667eea)' : '#c9c9d6'}" stroke-width="${an ? 2.5 : 1.2}" ${an ? '' : 'stroke-dasharray="4 4"'}/>`);
                });
                svg.setAttribute('width', sr.width); svg.setAttribute('height', sr.height);
                svg.innerHTML = pfade.join('');
            }

            // ---------------- SQL / Ausführen ----------------
            function sqlVorschau(verz = 250) {
                clearTimeout(sqlTimer);
                sqlTimer = setTimeout(async () => {
                    const nr = ++ladeNr;
                    try {
                        const r = await api.sternAbfrage(dashId, widgetId, { fakt: fakt.id, q: JSON.stringify(auswahlApi()), ausfuehren: false });
                        if (nr !== ladeNr) return;
                        el.querySelector('[data-sql]').innerHTML = sqlHtml(r.sql_mit_werten);
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
                const q = JSON.stringify(auswahlApi());
                try {
                    const r = await api.sternAbfrage(dashId, widgetId, { fakt: fakt.id, q, offset: 0, limit: seite });
                    ergebnis = { ...r, q, zeilen: r.zeilen.slice(), laedt: false };
                    zeigeErgebnis();
                } catch (e) {
                    info.className = 'sx-msg err'; info.textContent = e.message;
                    res.innerHTML = '';
                } finally { btn.disabled = false; }
            }

            function zelle(v, sp) {
                if (v === null && sp.art !== 'gruppe') return `<td class="mask" title="maskiert: weniger als ${esc(def.min_zelle)} Zeilen">&lt;${esc(def.min_zelle)}</td>`;
                if (sp.art === 'gruppe' && typeof v === 'number') return `<td>${esc(String(v))}</td>`;
                if (sp.typ === 'zahl' && typeof v === 'number') return `<td class="num">${esc(W.fmt.zahl(v, sp.agg === 'avg' ? 1 : undefined))}</td>`;
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
                    const n = await api.sternAbfrage(dashId, widgetId, { fakt: fakt.id, q: r.q, offset: r.zeilen.length, limit: seite });
                    if (ergebnis !== r) return;
                    r.zeilen.push(...n.zeilen);
                    r.maskiert += n.maskiert;
                    zeigeErgebnis();
                } catch (e) {
                    el.querySelector('[data-info]').textContent = e.message;
                } finally { r.laedt = false; }
            }

            async function rGeruest() {
                const box = el.querySelector('[data-r]'), pre = el.querySelector('[data-r-code]');
                box.hidden = false;
                pre.textContent = 'Erzeuge R-Gerüst …';
                try {
                    const r = await api.sternR(dashId, widgetId, { fakt: fakt.id, q: JSON.stringify(auswahlApi()) });
                    pre.textContent = r.r_code;
                    box._datei = r.dateiname;
                    box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                } catch (e) { pre.textContent = `# ${e.message}`; }
            }

            // ---------------- Filter-Popover ----------------
            function attrDef(rolle, attr) {
                const liste = rolle === 'fakt' ? fakt.attribute : (fakt.dimensionen.find(r => r.rolle === rolle)?.attribute || []);
                return liste.find(a => a.id === attr);
            }

            function schliessePop() { pop?.remove(); pop = null; }

            async function oeffneFilter(knopf, rolle, attr) {
                schliessePop();
                const a = attrDef(rolle, attr);
                const k = key(rolle, attr);
                const f = auswahl.filter[k];
                pop = document.createElement('div');
                pop.className = 'sx-pop';
                const box = el.querySelector('.sx');
                const br = box.getBoundingClientRect(), kr = knopf.getBoundingClientRect();
                pop.style.left = Math.max(0, Math.min(kr.left - br.left - 120, br.width - 290)) + 'px';
                pop.style.top = (kr.bottom - br.top + 4) + 'px';
                box.style.position = 'relative';
                box.appendChild(pop);
                const titel = `<h4>${esc(a.titel)} <span class="sx-hint">(${esc(a.id)})</span></h4>`;
                const knoepfe = `<div class="knoepfe"><button class="sx-btn sx-btn--s" data-pop="weg">Entfernen</button>
                    <button class="sx-btn sx-btn--p" data-pop="ok">Übernehmen</button></div>`;
                if (a.auswahl) {
                    pop.innerHTML = `${titel}<input type="text" placeholder="Suchen …" data-such><div class="liste">Lade Werte …</div>${knoepfe}`;
                    let werte = werteCache[`${fakt.id}|${k}`];
                    if (!werte) {
                        try {
                            werte = (await api.sternWerte(dashId, widgetId, { fakt: fakt.id, rolle, attr })).werte;
                            werteCache[`${fakt.id}|${k}`] = werte;
                        } catch (e) { pop.querySelector('.liste').textContent = e.message; return; }
                    }
                    if (!pop) return;
                    const gesetzt = new Set((f?.op === 'in' ? f.werte : []).map(String));
                    const liste = pop.querySelector('.liste');
                    liste.innerHTML = werte.map(w => `<label><input type="checkbox" value="${esc(w)}" ${gesetzt.has(String(w)) ? 'checked' : ''}> ${esc(W.fmt.wert(w))}</label>`).join('');
                    pop.querySelector('[data-such]').addEventListener('input', e => {
                        const t = e.target.value.toLowerCase();
                        liste.querySelectorAll('label').forEach(l => { l.style.display = l.textContent.toLowerCase().includes(t) ? '' : 'none'; });
                    });
                    pop.querySelector('[data-such]').focus();
                } else {
                    const ops = a.typ === 'text' || !a.typ ? OPS_TEXT : OPS_ZAHL;
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
                pop.addEventListener('click', e => {
                    const b = e.target.closest('[data-pop]');
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
                const tab = t.closest('[data-fakt]');
                if (tab) { waehleFakt(Number(tab.dataset.fakt)); return; }
                const g = t.closest('[data-gruppe]');
                if (g) {
                    const [rolle, attr] = g.dataset.gruppe.split('|');
                    const i = auswahl.gruppen.findIndex(x => x.rolle === rolle && x.attr === attr);
                    if (i >= 0) auswahl.gruppen.splice(i, 1); else auswahl.gruppen.push({ rolle, attr });
                    neuZeichnen();
                    return;
                }
                const fl = t.closest('[data-filter]');
                if (fl) { const [rolle, attr] = fl.dataset.filter.split('|'); oeffneFilter(fl, rolle, attr); return; }
                const act = t.closest('[data-act]')?.dataset.act;
                if (act === 'run') ausfuehren();
                if (act === 'reset') { auswahl = neueAuswahl(fakt); ergebnis = null; aufbauen(); }
                if (act === 'r') rGeruest();
                if (act === 'r-zu') el.querySelector('[data-r]').hidden = true;
                if (act === 'r-copy') {
                    navigator.clipboard?.writeText(el.querySelector('[data-r-code]').textContent)
                        .then(() => { t.textContent = 'Kopiert'; setTimeout(() => { t.textContent = 'Kopieren'; }, 1500); });
                }
                if (act === 'r-save') {
                    const box = el.querySelector('[data-r]');
                    const blob = new Blob([el.querySelector('[data-r-code]').textContent], { type: 'text/plain;charset=utf-8' });
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob); a.download = box._datei || 'star_explorer.R';
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
                if (t.dataset.kz !== undefined) {
                    const id = t.dataset.kz;
                    const k = fakt.kennzahlen.find(x => x.id === id);
                    if (t.checked) auswahl.kennzahlen.push({ id, agg: el.querySelector(`[data-agg="${CSS.escape(id)}"]`)?.value || k.agg[0]?.id });
                    else auswahl.kennzahlen = auswahl.kennzahlen.filter(x => x.id !== id);
                    neuZeichnen();
                } else if (t.dataset.agg !== undefined) {
                    const x = auswahl.kennzahlen.find(k => k.id === t.dataset.agg);
                    if (x) { x.agg = t.value; sqlVorschau(); }
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

            waehleFakt(0);
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
