/**
 * daita-studio – Widget „line“: Zeitreihe/Verlauf, ECharts.
 *
 * optionen:
 *   x:       Spalte der x-Achse (Pflicht; ISO-Datum wird lokal formatiert)
 *   y:       Werte-Spalte oder Liste von Spalten (Pflicht)
 *   serie:   Spalte, deren Werte die Serien bilden (optional; dann genau ein y)
 *   flaeche: true → Fläche unter der Linie (nur bei einer Serie sinnvoll)
 *   zoom:    true → Zoom-Leiste über die x-Achse (Default: ab 60 Punkten)
 *   format:  zahl | prozent | dauer_s – für Tooltip
 *   serien:     [{wert, titel, farbe}] – Reihenfolge, Beschriftung, Farbe je Serienwert
 *               (farbe: 'status-critical', 'viz-series-2' oder Hex)
 *   renderer:   'canvas' bei sehr vielen Punkten (Default: svg)
 *   echarts: Objekt, wird in die ECharts-Option gemischt
 *
 * Abhängigkeiten: dashboard-widgets.js, widget-echarts.js
 */
(() => {
    'use strict';
    const W = window.studioWidgets;
    const C = () => window.studioCharts;

    W.register('line', {
        render(el, daten, opt = {}) {
            if (!daten.rows.length) { el.innerHTML = '<div class="dsh-msg">Keine Daten</div>'; return null; }
            const { kategorien, serien: roh } = C().pivot(daten, opt.x, opt.y, opt.serie);
            const serien = C().capSerien(C().applySerien(roh, opt.serien));
            const mehrere = serien.length > 1;
            const zoom = opt.zoom ?? kategorien.length >= 60;

            const option = C().baseOption(mehrere);
            option.xAxis = {
                type: 'category',
                data: kategorien.map(C().kategorieLabel),
                boundaryGap: false,
                axisLabel: { hideOverlap: true, alignMinLabel: 'left', alignMaxLabel: 'right' },
            };
            option.yAxis = { type: 'value', axisLabel: { formatter: v => W.fmt.zahl(v) } };
            option.tooltip = {
                trigger: 'axis',
                axisPointer: { type: 'line', lineStyle: { color: C().tokens().axis } },
                valueFormatter: v => W.fmt.nach(opt.format || 'zahl', v),
            };
            if (zoom) {
                option.dataZoom = [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 0 }];
                option.grid.bottom = 32;
            }
            option.series = serien.map(s => ({
                type: 'line',
                name: s.name,
                data: s.werte,
                showSymbol: kategorien.length <= 31,
                symbol: 'circle',
                symbolSize: 8,
                lineStyle: { width: 2 },
                color: s.farbe,
                itemStyle: { borderColor: C().tokens().surface, borderWidth: 2 },
                areaStyle: opt.flaeche && !mehrere ? { opacity: 0.12 } : undefined,
                connectNulls: false,
                emphasis: { focus: 'series' },
            }));
            if (opt.renderer === 'canvas') option.__renderer = 'canvas';   // viele Punkte
            C().merge(option, opt.echarts);
            return C().mount(el, option);
        },
    });
})();
