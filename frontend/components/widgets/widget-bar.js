/**
 * daita-studio – Widget „bar“: Balken (gruppiert oder gestapelt), ECharts.
 *
 * optionen:
 *   x:          Kategorie-Spalte (Pflicht)
 *   y:          Werte-Spalte oder Liste von Spalten (Pflicht)
 *   serie:      Spalte, deren Werte die Serien bilden (optional; dann genau ein y)
 *   gestapelt:  true → Serien stapeln
 *   horizontal: true → Balken waagrecht (lange Beschriftungen)
 *   format:     zahl | prozent | dauer_s – für Tooltip
 *   serien:     [{wert, titel, farbe}] – Reihenfolge, Beschriftung, Farbe je Serienwert
 *               (farbe: 'status-critical', 'viz-series-2' oder Hex)
 *   renderer:   'canvas' bei sehr vielen Punkten (Default: svg)
 *   echarts:    Objekt, wird in die ECharts-Option gemischt
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-echarts.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const C = () => window.studioCharts;

    W.register('bar', {
        render(el, daten, opt = {}) {
            if (!daten.rows.length) { el.innerHTML = '<div class="dsh-msg">Keine Daten</div>'; return null; }
            const { kategorien, serien: roh } = C().pivot(daten, opt.x, opt.y, opt.serie);
            const serien = C().capSerien(C().applySerien(roh, opt.serien));
            const mehrere = serien.length > 1;
            const horizontal = !!opt.horizontal;
            const surface = C().tokens().surface;
            const radius = horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0];

            const option = C().baseOption(mehrere);
            const katAxis = {
                type: 'category',
                // Beschriftung schon formatiert, damit Achse und Tooltip gleich lesen
                data: (horizontal ? [...kategorien].reverse() : kategorien).map(C().kategorieLabel),
                axisLabel: { hideOverlap: true, width: horizontal ? 220 : undefined, overflow: 'truncate' },
            };
            const valAxis = { type: 'value', axisLabel: { formatter: v => W.fmt.zahl(v) } };
            option.xAxis = horizontal ? valAxis : katAxis;
            option.yAxis = horizontal ? katAxis : valAxis;
            option.tooltip = {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                valueFormatter: v => W.fmt.nach(opt.format || 'zahl', v),
            };
            option.series = serien.map((s, i) => ({
                type: 'bar',
                name: s.name,
                data: horizontal ? [...s.werte].reverse() : s.werte,
                stack: opt.gestapelt ? 'summe' : undefined,
                barMaxWidth: 28,
                barGap: '10%',
                itemStyle: {
                    color: s.farbe,
                    // gestapelt: nur das oberste Segment rund, 1px Fläche als Trennfuge
                    borderRadius: !opt.gestapelt || i === serien.length - 1 ? radius : 0,
                    borderColor: surface,
                    borderWidth: opt.gestapelt ? 1 : 0,
                },
                emphasis: { focus: 'series' },
            }));
            if (opt.renderer === 'canvas') option.__renderer = 'canvas';   // viele Punkte
            C().merge(option, opt.echarts);
            return C().mount(el, option);
        },
    });
})();
