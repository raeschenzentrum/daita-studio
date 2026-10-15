/**
 * daita-studio – Widget „boxplot“: Verteilungen je Kategorie, ECharts.
 *
 * Die Kennwerte rechnet das SQL (z. B. mit PERCENTILE_CONT); das Widget zeichnet nur.
 *
 * optionen:
 *   x:        Kategorie-Spalte (Pflicht)
 *   werte:    [unten, q1, median, q3, oben] – fünf Spalten (Pflicht), z. B.
 *             [P05, P25, MEDIAN, P75, P95]
 *   anzahl:   Spalte mit der Fallzahl (optional, erscheint im Tooltip)
 *   format:   zahl | prozent | dauer_s – für Tooltip und Achse
 *   einheit:  Text hinter den Werten im Tooltip (z. B. "Tage")
 *   beschriftung: [Text unten, Q1, Median, Q3, Text oben] – Tooltip-Beschriftung
 *   echarts:  Objekt, wird in die ECharts-Option gemischt
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-echarts.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const C = () => window.studioCharts;

    W.register('boxplot', {
        render(el, daten, opt = {}) {
            if (!daten.rows.length) { el.innerHTML = '<div class="dsh-msg">Keine Daten</div>'; return null; }
            const xi = W.col(daten, opt.x);
            const wi = (opt.werte || []).map(c => W.col(daten, c));
            if (wi.length !== 5) throw new Error("boxplot: optionen.werte braucht genau fünf Spalten");
            const ni = opt.anzahl ? W.col(daten, opt.anzahl) : -1;
            const label = opt.beschriftung || ['unten', '25 %', 'Median', '75 %', 'oben'];
            const einheit = opt.einheit ? ` ${opt.einheit}` : '';
            const f = v => W.fmt.nach(opt.format || 'zahl', v) + einheit;

            const kategorien = daten.rows.map(r => C().kategorieLabel(r[xi]));
            const boxen = daten.rows.map(r => wi.map(i => r[i]));
            const anzahl = daten.rows.map(r => (ni >= 0 ? r[ni] : null));

            const option = C().baseOption(false);
            option.xAxis = { type: 'category', data: kategorien, axisLabel: { hideOverlap: true } };
            option.yAxis = { type: 'value', axisLabel: { formatter: v => W.fmt.zahl(v) } };
            option.tooltip = {
                trigger: 'item',
                formatter: p => {
                    const v = boxen[p.dataIndex];
                    const n = anzahl[p.dataIndex];
                    return `<b>${W.esc(kategorien[p.dataIndex])}</b><br>`
                        + [4, 3, 2, 1, 0].map(i => `${W.esc(label[i])}: <b>${W.esc(f(v[i]))}</b>`).join('<br>')
                        + (n !== null ? `<br>Fälle: <b>${W.esc(W.fmt.zahl(n))}</b>` : '');
                },
            };
            option.series = [{
                type: 'boxplot',
                data: boxen,
                boxWidth: ['20%', '45%'],
                itemStyle: { color: 'rgba(42,120,214,0.15)', borderColor: C().palette()[0], borderWidth: 1.5 },
                emphasis: { itemStyle: { borderWidth: 2 } },
            }];
            if (opt.renderer === 'canvas') option.__renderer = 'canvas';
            C().merge(option, opt.echarts);
            return C().mount(el, option);
        },
    });
})();
