/**
 * daita-studio – ECharts-Basis für Diagramm-Widgets
 *
 * Kapselt alles, was nur die Diagramm-Widgets brauchen: Theme aus den
 * CSS-Variablen (style.css, --viz-*), Instanz mit Resize, Grundoptionen
 * (Tooltip, Legende, Achsen, PNG-Export) und das Pivotieren von Ergebnis-
 * zeilen in Serien. Shell und Definitionen hängen nicht von ECharts ab.
 *
 * Verwendung (in einem Widget):
 *   const chart = studioCharts.mount(el, option);   // → { dispose() }
 *   const { kategorien, serien } = studioCharts.pivot(daten, 'TAG', 'LAEUFE', 'STATUS');
 *
 * Abhängigkeiten: vendor/echarts/echarts.min.js (global echarts), dashboard-widgets.js
 */

(() => {
    'use strict';

    const THEME = 'studio';
    let themeRegistered = false;

    function cssVar(name, fallback) {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    }

    // Ersatzwerte = Palette aus style.css (falls das Stylesheet veraltet im Cache liegt,
    // bleiben die Serien trotzdem unterscheidbar)
    const PALETTE_ERSATZ = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];

    function palette() {
        return PALETTE_ERSATZ.map((f, i) => cssVar(`--viz-series-${i + 1}`, f));
    }

    function tokens() {
        return {
            text: cssVar('--viz-text-primary', '#0b0b0b'),
            text2: cssVar('--viz-text-secondary', '#52514e'),
            muted: cssVar('--viz-muted', '#898781'),
            grid: cssVar('--viz-grid', '#e1e0d9'),
            axis: cssVar('--viz-axis', '#c3c2b7'),
            surface: cssVar('--card-bg', '#ffffff'),
            font: getComputedStyle(document.body).fontFamily,
        };
    }

    function ensureTheme() {
        if (themeRegistered || !window.echarts) return;
        const t = tokens();
        const axis = {
            axisLine: { lineStyle: { color: t.axis } },
            axisTick: { show: false },
            axisLabel: { color: t.muted, fontSize: 11 },
            splitLine: { lineStyle: { color: t.grid, width: 1 } },
            nameTextStyle: { color: t.muted },
        };
        echarts.registerTheme(THEME, {
            color: palette(),
            backgroundColor: 'transparent',
            textStyle: { fontFamily: t.font, color: t.text },
            legend: { textStyle: { color: t.text2, fontSize: 12 }, icon: 'roundRect', itemWidth: 10, itemHeight: 10 },
            tooltip: {
                backgroundColor: t.surface,
                borderColor: t.grid,
                textStyle: { color: t.text, fontSize: 12 },
                extraCssText: 'box-shadow: 0 2px 8px rgba(0,0,0,0.12); border-radius: 6px;',
            },
            categoryAxis: { ...axis, splitLine: { show: false } },
            valueAxis: { ...axis, axisLine: { show: false } },
            timeAxis: axis,
        });
        themeRegistered = true;
    }

    /**
     * Zeilen → Kategorien × Serien. Ohne serieSpalte: eine Serie je y-Spalte.
     * Reihenfolge der Serien = erstes Auftreten (stabil, nicht nach Rang).
     */
    function pivot(daten, xSpalte, ySpalten, serieSpalte) {
        const W = window.studioWidgets;
        const xi = W.col(daten, xSpalte);
        const yList = Array.isArray(ySpalten) ? ySpalten : [ySpalten];
        const kategorien = [];
        const kIndex = new Map();
        for (const r of daten.rows) {
            if (!kIndex.has(r[xi])) { kIndex.set(r[xi], kategorien.length); kategorien.push(r[xi]); }
        }
        const serien = [];
        if (serieSpalte) {
            const si = W.col(daten, serieSpalte);
            const yi = W.col(daten, yList[0]);
            const sIndex = new Map();
            for (const r of daten.rows) {
                const name = r[si] === null || r[si] === undefined ? '–' : String(r[si]);
                if (!sIndex.has(name)) {
                    sIndex.set(name, serien.length);
                    serien.push({ name, werte: new Array(kategorien.length).fill(null) });
                }
                serien[sIndex.get(name)].werte[kIndex.get(r[xi])] = r[yi];
            }
        } else {
            for (const y of yList) {
                const yi = W.col(daten, y);
                const werte = new Array(kategorien.length).fill(null);
                for (const r of daten.rows) werte[kIndex.get(r[xi])] = r[yi];
                serien.push({ name: y, werte });
            }
        }
        return { kategorien, serien };
    }

    /** Ab 9 Serien: die kleinsten zu „Übrige“ zusammenfassen (Farben nie zyklisch). */
    function capSerien(serien, max = 8) {
        if (serien.length <= max) return serien;
        const summe = s => s.werte.reduce((a, v) => a + (Number(v) || 0), 0);
        const sortiert = [...serien].sort((a, b) => summe(b) - summe(a));
        const behalten = new Set(sortiert.slice(0, max - 1).map(s => s.name));
        const rest = serien.filter(s => !behalten.has(s.name));
        const uebrige = {
            name: 'Übrige',
            werte: rest[0].werte.map((_, i) => rest.reduce((a, s) => a + (Number(s.werte[i]) || 0), 0)),
        };
        return [...serien.filter(s => behalten.has(s.name)), uebrige];
    }

    /**
     * optionen.serien: [{ wert, titel?, farbe? }] – feste Reihenfolge, Beschriftung
     * und Farbe je Serienwert. farbe: CSS-Variable ohne '--' (z. B. 'status-critical',
     * 'viz-series-3') oder Hex-Wert. Nicht aufgeführte Serien folgen danach.
     */
    function applySerien(serien, def) {
        if (!Array.isArray(def) || !def.length) return serien;
        const nachName = new Map(serien.map(s => [s.name, s]));
        const out = [];
        for (const d of def) {
            const s = nachName.get(String(d.wert));
            if (!s) continue;
            nachName.delete(String(d.wert));
            out.push({ ...s, name: d.titel ?? s.name, farbe: farbe(d.farbe) });
        }
        return [...out, ...nachName.values()];
    }

    const FARB_ERSATZ = {
        'viz-muted': '#898781', 'viz-axis': '#c3c2b7',
        'status-good': '#0ca30c', 'status-warning': '#fab219', 'status-serious': '#ec835a', 'status-critical': '#d03b3b',
    };

    function farbe(f) {
        if (!f) return undefined;
        if (f.startsWith('#')) return f;
        const m = /^viz-series-(\d)$/.exec(f);
        return cssVar(`--${f}`, m ? PALETTE_ERSATZ[Number(m[1]) - 1] : FARB_ERSATZ[f]);
    }

    function baseOption(mehrereSerien) {
        return {
            animationDuration: 300,
            // oben Platz für Legende bzw. Export-Symbol, damit nichts überlappt
            grid: { left: 8, right: 24, top: mehrereSerien ? 40 : 28, bottom: 8, containLabel: true },
            legend: mehrereSerien ? { top: 0, left: 0, type: 'scroll' } : { show: false },
            toolbox: {
                right: 0, top: 0, itemSize: 13,
                feature: { saveAsImage: { title: 'Als PNG speichern', pixelRatio: 2, backgroundColor: tokens().surface } },
                iconStyle: { borderColor: tokens().muted },
            },
        };
    }

    /** Kategoriebeschriftung: ISO-Datum lokal formatieren; Zahlen sind hier Kennungen
     *  (Jahr, Code), also ohne Tausendertrennung */
    function kategorieLabel(v) {
        if (typeof v === 'number') return String(v);
        return window.studioWidgets.fmt.wert(v);
    }

    /** Farbe einer Serie: aus optionen.serien, „Übrige“ neutral grau, sonst Palette */
    function serienFarbe(s) {
        if (s.farbe) return s.farbe;
        if (s.name === 'Übrige') return cssVar('--viz-muted', '#898781');
        return undefined;
    }

    function mount(el, option) {
        if (!window.echarts) {
            el.innerHTML = '<div class="dsh-msg dsh-msg--error">ECharts nicht geladen (vendor/echarts/echarts.min.js)</div>';
            return { dispose() {} };
        }
        ensureTheme();
        const chart = echarts.init(el, THEME, { renderer: option.__renderer || 'svg' });
        delete option.__renderer;
        chart.setOption(option);
        const ro = new ResizeObserver(() => chart.resize());
        ro.observe(el);
        return {
            chart,
            dispose() { ro.disconnect(); chart.dispose(); },
        };
    }

    /** Tiefes Zusammenführen für optionen.echarts (nur Daten, keine Funktionen) */
    function merge(ziel, quelle) {
        if (!quelle || typeof quelle !== 'object') return ziel;
        for (const [k, v] of Object.entries(quelle)) {
            if (v && typeof v === 'object' && !Array.isArray(v) && ziel[k] && typeof ziel[k] === 'object' && !Array.isArray(ziel[k])) {
                merge(ziel[k], v);
            } else {
                ziel[k] = v;
            }
        }
        return ziel;
    }

    window.studioCharts = { mount, pivot, capSerien, applySerien, serienFarbe, baseOption, kategorieLabel, merge, tokens, palette };
})();
