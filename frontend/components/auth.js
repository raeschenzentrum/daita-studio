/**
 * daita-studio – Auth-Client (RBAC)
 * =================================
 *
 * Eine einzige Einbindung pro Seite genügt:
 *   <script src="config.js"></script>
 *   <script src="components/auth.js"></script>
 *
 * Aufgaben:
 *  1) window.fetch wird gepatcht: an jeden Request ans Backend wird der
 *     Authorization: Bearer <token>-Header angehängt (deckt api.js UND alle
 *     rohen fetch()-Aufrufe ab).
 *  2) Bei HTTP 401 wird der Token verworfen und auf login.html umgeleitet.
 *  3) Seiten-Guard: ohne Token -> Weiterleitung auf login.html.
 *  4) window.studioAuth: setSession / logout / getUser / getToken / hasRole.
 *
 * Der Token liegt in localStorage (nicht in Cookies) -> nur same-origin
 * lesbar, kein CSRF-Vektor.
 */
(() => {
    'use strict';

    const TOKEN_KEY = 'studio_token';
    const USER_KEY = 'studio_user';
    const ROLE_RANK = { Viewer: 0, Editor: 1, Admin: 2 };

    // ----------------------------------------------------------------
    // Backend-Basis (Host+Port, ohne /api) – aus config.js oder Fallback
    // ----------------------------------------------------------------
    function backendBase() {
        const cfg = window.METADAITA_CONFIG;
        return (cfg && cfg.backend_url) || `http://${window.location.hostname}:9021`;
    }

    function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }

    function getUser() {
        try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
        catch (_) { return null; }
    }

    function setSession(token, user) {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
    }

    function clearSession() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    }

    function hasRole(required) {
        const u = getUser();
        if (!u || !(u.role in ROLE_RANK) || !(required in ROLE_RANK)) return false;
        return ROLE_RANK[u.role] >= ROLE_RANK[required];
    }

    function isLoginPage() {
        return window.location.pathname.replace(/\/+$/, '').endsWith('login.html');
    }

    function redirectToLogin() {
        if (isLoginPage()) return;
        const next = encodeURIComponent(
            window.location.pathname.split('/').pop() + window.location.search
        );
        window.location.replace(`login.html?next=${next}`);
    }

    // ----------------------------------------------------------------
    // Soll an diese URL der Auth-Header angehängt werden?
    // Nur Requests ans Backend – nicht an CDNs o.ä.
    // ----------------------------------------------------------------
    function isBackendRequest(url) {
        if (!url) return false;
        if (url.startsWith('/')) return true; // relativ zum eigenen Host
        try {
            const u = new URL(url, window.location.href);
            const base = new URL(backendBase());
            if (url.startsWith(backendBase())) return true;
            // gleiche Portnummer wie das Backend -> als Backend-Request werten
            return !!base.port && u.port === base.port;
        } catch (_) {
            return false;
        }
    }

    // ----------------------------------------------------------------
    // fetch-Patch
    // ----------------------------------------------------------------
    const _origFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        init = init || {};
        const url = (typeof input === 'string') ? input : (input && input.url) || '';

        if (isBackendRequest(url)) {
            const token = getToken();
            if (token) {
                const headers = new Headers(
                    init.headers || (typeof input !== 'string' && input && input.headers) || {}
                );
                if (!headers.has('Authorization')) {
                    headers.set('Authorization', 'Bearer ' + token);
                }
                init = { ...init, headers };
            }
        }

        const resp = await _origFetch(input, init);

        if (resp.status === 401 && isBackendRequest(url) && !isLoginPage()) {
            clearSession();
            redirectToLogin();
        }
        return resp;
    };

    // ----------------------------------------------------------------
    // Seiten-Guard: ohne Token direkt weiterleiten
    // ----------------------------------------------------------------
    if (!isLoginPage() && !getToken()) {
        redirectToLogin();
    }

    // ----------------------------------------------------------------
    // Benutzer-Badge + Logout in den Nav-Header einhängen
    // ----------------------------------------------------------------
    function injectUserBadge() {
        if (isLoginPage()) return;
        const user = getUser();
        if (!user) return;

        const header = document.querySelector('.studio-header');
        if (!header || header.querySelector('.studio-user-badge')) return;

        const badge = document.createElement('div');
        badge.className = 'studio-user-badge';
        badge.style.cssText =
            'display:flex;align-items:center;gap:10px;color:#fff;font-size:0.85em;margin-left:auto;';
        badge.innerHTML =
            `<span title="Rolle: ${user.role}">👤 ${user.username} ` +
            `<em style="opacity:.8;font-style:normal;">(${user.role})</em></span>` +
            `<button type="button" class="studio-logout" ` +
            `style="background:rgba(255,255,255,.18);border:none;color:#fff;` +
            `padding:4px 10px;border-radius:6px;cursor:pointer;font-size:0.9em;">Abmelden</button>`;
        header.appendChild(badge);
        badge.querySelector('.studio-logout').addEventListener('click', logout);
    }

    function logout() {
        clearSession();
        window.location.replace('login.html');
    }

    document.addEventListener('studio:nav-ready', injectUserBadge);
    document.addEventListener('DOMContentLoaded', injectUserBadge);

    // ----------------------------------------------------------------
    // Öffentliche API
    // ----------------------------------------------------------------
    window.studioAuth = {
        backendBase,
        getToken,
        getUser,
        setSession,
        clearSession,
        hasRole,
        logout,
    };
})();
