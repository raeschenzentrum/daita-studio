/**
 * daita-studio – Widget „kpi“: eine Kennzahl aus der ersten Ergebniszeile.
 *
 * optionen:
 *   wert:      Spalte mit der Kennzahl (Pflicht)
 *   format:    zahl | prozent | dauer_s (Default: zahl)
 *   vergleich: Spalte mit Vergleichswert (optional, z. B. Vorjahr)
 *   vergleich_titel: Beschriftung des Vergleichs (Default: "Vergleich")
 *   status:    Schwellen {warning: n, serious: n, critical: n} – ab Wert ≥ Schwelle
 *              wird ein Status mit Symbol und Text angezeigt (nie Farbe allein)
 *
 * Abhängigkeiten: dashboard-widgets.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;

    const STATUS = [
        ['critical', 'kritisch', '▲'],
        ['serious', 'erhöht', '▲'],
        ['warning', 'Hinweis', '●'],
    ];

    W.register('kpi', {
        tabelle: false,
        render(el, daten, opt = {}) {
            const row = daten.rows[0] || [];
            const wert = opt.wert ? row[W.col(daten, opt.wert)] : row[0];
            let html = `<div class="dsh-kpi"><div class="dsh-kpi__wert">${W.esc(W.fmt.nach(opt.format || 'zahl', wert))}</div>`;

            if (opt.vergleich) {
                const v = row[W.col(daten, opt.vergleich)];
                let delta = '';
                if (typeof wert === 'number' && typeof v === 'number' && v !== 0) {
                    const d = (wert - v) / Math.abs(v) * 100;
                    delta = ` (${d >= 0 ? '+' : '−'}${W.fmt.zahl(Math.abs(d), 1)} %)`;
                }
                html += `<div class="dsh-kpi__vergleich">${W.esc(opt.vergleich_titel || 'Vergleich')}: ${W.esc(W.fmt.nach(opt.format || 'zahl', v))}${W.esc(delta)}</div>`;
            }

            if (opt.status && typeof wert === 'number') {
                const hit = STATUS.find(([k]) => opt.status[k] !== undefined && wert >= opt.status[k]);
                if (hit) {
                    html += `<div class="dsh-kpi__status"><span class="dsh-status-dot" style="color:var(--status-${hit[0]})">${hit[2]}</span>${W.esc(hit[1])}</div>`;
                }
            }
            el.innerHTML = html + '</div>';
            return null;
        },
    });
})();
