/**
 * daita-studio – Gemeinsamer Navigation-Header (C2)
 *
 * Verwendung:
 *   <script src="/components/nav-header.js"></script>
 *   <studio-nav active="flow"></studio-nav>
 *
 * Attribute:
 *   active  – Key des aktiven Menüpunkts (flow | modeler | jobs | lineage | sources)
 *
 * Custom Events (gefeuert auf document):
 *   studio:nav-ready  – nach dem ersten Render
 *
 * Abhängigkeiten: keine (kann standalone ohne api.js verwendet werden)
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Menüdefinition – Reihenfolge entspricht Seitenleiste
    // ----------------------------------------------------------------
    const NAV_ITEMS = [
        { key: 'flow',    label: 'Flow',    icon: '⟳', href: 'flow.html' },
        { key: 'modeler', label: 'Modeler', icon: '⬡', href: 'modeler.html' },
        { key: 'jobs',    label: 'Jobs',    icon: '⚙', href: 'jobs.html' },
        { key: 'lineage', label: 'Lineage', icon: '↗', href: 'lineage.html' },
        { key: 'dataflow',label: 'Dataflow',icon: '⤳', href: 'lineage-flow.html' },
        { key: 'sources', label: 'Sources', icon: '⇄', href: 'sources.html' },
    ];

    const BRAND_HREF = 'index.html';

    // ----------------------------------------------------------------
    // Styles (inline, kein externes CSS erforderlich)
    // ----------------------------------------------------------------
    const STYLE = `
        studio-nav {
            display: block;
        }
        .studio-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 0 24px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            position: sticky;
            top: 0;
            z-index: 1000;
            user-select: none;
        }
        .studio-header__brand {
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: #fff;
            font-weight: 700;
            font-size: 1.15em;
            letter-spacing: 0.02em;
            flex-shrink: 0;
        }
        .studio-header__brand-logo {
            width: 28px;
            height: 28px;
            background: rgba(255,255,255,0.25);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1em;
        }
        .studio-header__nav {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .studio-header__nav a {
            color: rgba(255,255,255,0.85);
            text-decoration: none;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 0.9em;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: background 0.15s, color 0.15s;
            white-space: nowrap;
        }
        .studio-header__nav a:hover {
            background: rgba(255,255,255,0.18);
            color: #fff;
        }
        .studio-header__nav a.active {
            background: rgba(255,255,255,0.28);
            color: #fff;
            font-weight: 600;
        }
        .studio-header__nav a .nav-icon {
            font-size: 1em;
            opacity: 0.9;
        }
        .studio-header__right {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
        }
        .studio-header__status {
            font-size: 0.78em;
            padding: 3px 10px;
            border-radius: 10px;
            background: rgba(255,255,255,0.15);
            color: rgba(255,255,255,0.9);
            cursor: default;
        }
        .studio-header__status.ok   { background: rgba(76,175,80,0.4); }
        .studio-header__status.err  { background: rgba(244,67,54,0.4); }
    `;

    // ----------------------------------------------------------------
    // Hilfsfunktionen
    // ----------------------------------------------------------------

    function injectStyles() {
        if (document.getElementById('studio-nav-style')) return;
        const s = document.createElement('style');
        s.id = 'studio-nav-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function buildNav(activeKey) {
        return NAV_ITEMS.map(item => {
            const cls = item.key === activeKey ? 'active' : '';
            return `<a href="${item.href}" class="${cls}">
                <span class="nav-icon">${item.icon}</span>${item.label}
            </a>`;
        }).join('');
    }

    function render(el, activeKey) {
        injectStyles();
        el.innerHTML = `
            <nav class="studio-header" role="navigation" aria-label="Hauptnavigation">
                <a class="studio-header__brand" href="${BRAND_HREF}">
                    <span class="studio-header__brand-logo">⬡</span>
                    daita-studio
                </a>
                <div class="studio-header__nav">
                    ${buildNav(activeKey)}
                </div>
                <div class="studio-header__right">
                    <span class="studio-header__status" id="studio-nav-status" title="Backend-Status">●</span>
                </div>
            </nav>`;
    }

    // ----------------------------------------------------------------
    // Backend Health-Check (leises Polling alle 30s)
    // ----------------------------------------------------------------

    async function checkHealth(statusEl) {
        const cfg  = window.METADAITA_CONFIG;
        const base = (cfg?.backend_url || `http://${window.location.hostname}:9021`);
        try {
            const res = await fetch(base + '/', { method: 'GET', cache: 'no-store' });
            if (res.ok) {
                statusEl.textContent = '● online';
                statusEl.className   = 'studio-header__status ok';
                statusEl.title       = `Backend ${base} – online`;
            } else {
                throw new Error(`HTTP ${res.status}`);
            }
        } catch (e) {
            statusEl.textContent = '● offline';
            statusEl.className   = 'studio-header__status err';
            statusEl.title       = `Backend ${base} – ${e.message}`;
        }
    }

    // ----------------------------------------------------------------
    // Custom Element
    // ----------------------------------------------------------------

    class StudioNav extends HTMLElement {
        connectedCallback() {
            const active = this.getAttribute('active') || '';
            render(this, active);

            const statusEl = this.querySelector('#studio-nav-status');
            if (statusEl) {
                checkHealth(statusEl);
                setInterval(() => checkHealth(statusEl), 30_000);
            }

            document.dispatchEvent(new CustomEvent('studio:nav-ready'));
        }

        static get observedAttributes() { return ['active']; }

        attributeChangedCallback(name, oldVal, newVal) {
            if (name === 'active' && oldVal !== newVal && this.isConnected) {
                const statusEl = this.querySelector('#studio-nav-status');
                render(this, newVal || '');
                // status nach Re-Render neu starten
                const newStatus = this.querySelector('#studio-nav-status');
                if (newStatus) checkHealth(newStatus);
            }
        }
    }

    customElements.define('studio-nav', StudioNav);

})();
