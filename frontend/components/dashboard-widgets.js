/**
 * daita-studio – Widget-Registry für Dashboards
 *
 * Die Dashboard-Shell kennt keine Widget-Typen; jeder Typ meldet sich hier an.
 *
 * Verwendung:
 *   <script src="components/dashboard-widgets.js"></script>
 *   <script src="components/widgets/widget-kpi.js"></script>
 *
 *   studioWidgets.register('kpi', {
 *       render(el, daten, optionen, ctx) { ...; return { dispose() {} }; },
 *       tabelle: false,   // optional: keine Umschaltung auf Tabellenansicht
 *   });
 *
 * daten = { columns: [...], rows: [[...], ...], meta: {...} } (aus /api/dashboards/.../data)
 *
 * Zusätzlich gemeinsame Helfer unter studioWidgets.fmt (Zahlen, Datum, Dauer)
 * und studioWidgets.col(daten, name) (Spaltenindex, wirft bei unbekannter Spalte).
 *
 * Abhängigkeiten: keine
 */

(() => {
    'use strict';

    const TYPES = {};

    function register(typ, impl) {
        if (!impl || typeof impl.render !== 'function') {
            throw new Error(`Widget-Typ '${typ}': render() fehlt`);
        }
        TYPES[typ] = impl;
    }

    function get(typ) {
        return TYPES[typ] || null;
    }

    function types() {
        return Object.keys(TYPES);
    }

    // ----------------------------------------------------------------
    // Formatierung
    // ----------------------------------------------------------------

    function locale() {
        return window.METADAITA_CONFIG?.locale || document.documentElement.lang || 'de';
    }

    const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
    const ISO_TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

    const fmt = {
        zahl(v, stellen) {
            if (v === null || v === undefined || v === '') return '–';
            if (typeof v !== 'number') return String(v);
            const opts = stellen !== undefined
                ? { minimumFractionDigits: stellen, maximumFractionDigits: stellen }
                : { maximumFractionDigits: Math.abs(v) < 10 ? 2 : 1 };
            return new Intl.NumberFormat(locale(), opts).format(v);
        },
        prozent(v) {
            if (v === null || v === undefined) return '–';
            return fmt.zahl(v, 1) + ' %';
        },
        dauer_s(v) {
            if (v === null || v === undefined) return '–';
            const s = Math.round(v);
            if (s < 60) return `${s} s`;
            const m = Math.floor(s / 60), r = s % 60;
            if (m < 60) return r ? `${m} min ${r} s` : `${m} min`;
            const h = Math.floor(m / 60);
            return `${h} h ${m % 60} min`;
        },
        datum(v) {
            if (typeof v !== 'string') return fmt.wert(v);
            if (ISO_DATE.test(v)) {
                const [y, m, d] = v.split('-').map(Number);
                return new Date(y, m - 1, d).toLocaleDateString(locale());
            }
            if (ISO_TS.test(v)) {
                return new Date(v).toLocaleString(locale(), { dateStyle: 'short', timeStyle: 'short' });
            }
            return v;
        },
        /** Formatiert nach Format-Name (zahl | prozent | dauer_s | datum) oder automatisch */
        nach(format, v) {
            if (format && fmt[format]) return fmt[format](v);
            return fmt.wert(v);
        },
        wert(v) {
            if (v === null || v === undefined) return '–';
            if (typeof v === 'number') return fmt.zahl(v);
            if (typeof v === 'string' && (ISO_DATE.test(v) || ISO_TS.test(v))) return fmt.datum(v);
            return String(v);
        },
    };

    function col(daten, name) {
        const i = daten.columns.indexOf(name);
        if (i < 0) throw new Error(`Spalte '${name}' fehlt im Ergebnis (vorhanden: ${daten.columns.join(', ')})`);
        return i;
    }

    function esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    window.studioWidgets = { register, get, types, fmt, col, esc };
})();
