/**
 * daita-studio – Widget „table“: Ergebnis als Tabelle, sortierbar per Klick auf den Kopf.
 *
 * optionen:
 *   spalten:  Liste der anzuzeigenden Spalten (Default: alle)
 *   titel:    { SPALTE: "Überschrift" }
 *   format:   { SPALTE: zahl | prozent | dauer_s | datum }
 *   max_anzeige: angezeigte Zeilen (Default 200)
 *
 * Wird von der Shell auch als Tabellenansicht für Diagramme verwendet.
 *
 * Abhängigkeiten: dashboard-widgets.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;

    W.register('table', {
        tabelle: false,
        render(el, daten, opt = {}) {
            const spalten = opt.spalten || daten.columns;
            const idx = spalten.map(c => W.col(daten, c));
            const titel = opt.titel || {};
            const format = opt.format || {};
            const max = opt.max_anzeige || 200;
            let sortCol = null, asc = true;

            const numerisch = idx.map(i => daten.rows.some(r => typeof r[i] === 'number')
                && daten.rows.every(r => r[i] === null || typeof r[i] === 'number'));
            // Kennungen (Jahr, Code, ID, Nummer) ohne Tausendertrennung anzeigen
            const kennung = spalten.map(c => /(^|_)(JAHR|ID|CD|CODE|NR|SK)($|_)/i.test(c));
            const zelle = (k, v) => kennung[k] && typeof v === 'number' ? String(v) : W.fmt.nach(format[spalten[k]], v);

            function draw() {
                let rows = daten.rows;
                if (sortCol !== null) {
                    const i = idx[sortCol];
                    rows = [...rows].sort((a, b) => {
                        const x = a[i], y = b[i];
                        if (x === y) return 0;
                        if (x === null || x === undefined) return 1;
                        if (y === null || y === undefined) return -1;
                        return (x < y ? -1 : 1) * (asc ? 1 : -1);
                    });
                }
                const head = spalten.map((c, k) =>
                    `<th data-k="${k}" class="${numerisch[k] ? 'num' : ''}" aria-sort="${sortCol === k ? (asc ? 'ascending' : 'descending') : 'none'}">`
                    + `${W.esc(titel[c] || c)}${sortCol === k ? (asc ? ' ▲' : ' ▼') : ''}</th>`).join('');
                const body = rows.slice(0, max).map(r => '<tr>' + idx.map((i, k) =>
                    `<td class="${numerisch[k] ? 'num' : ''}">${W.esc(zelle(k, r[i]))}</td>`).join('') + '</tr>').join('');
                const mehr = rows.length > max ? `<div class="dsh-table__mehr">${W.fmt.zahl(rows.length - max)} weitere Zeilen nicht angezeigt</div>` : '';
                el.innerHTML = rows.length
                    ? `<div class="dsh-table"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${mehr}</div>`
                    : '<div class="dsh-msg">Keine Daten</div>';
                el.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
                    const k = Number(th.dataset.k);
                    asc = sortCol === k ? !asc : true;
                    sortCol = k;
                    draw();
                }));
            }
            draw();
            return null;
        },
    });
})();
