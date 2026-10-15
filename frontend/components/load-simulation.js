/**
 * daita-studio – Tagessimulation: lädt die Kette der Delta-Jobs Tag für Tag
 * bis zu einer Lade-ID (ein „Tag" = ein Ladelauf der Quelle).
 *
 * Backend: GET /api/etl/simulation, GET /api/etl/simulation/status,
 *          POST /api/etl/simulation/start, POST /api/etl/simulation/stop
 *
 * Verwendung: const sim = new LoadSimulation(container); sim.load();
 * Abhängigkeiten: api.js (window.api.etl.simulation)
 */
(() => {
    'use strict';

    const CSS = `
    .ls-root { display: flex; flex-direction: column; gap: 12px; flex: 1; min-width: 0; }
    .ls-card { background: var(--card-bg, #fff); border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.07); padding: 14px 16px; }
    .ls-card h3 { margin: 0 0 8px; font-size: 1em; }
    .ls-hint { color: #555; font-size: .85em; line-height: 1.45; margin: 0; }
    .ls-kpis { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 4px; }
    .ls-kpi { background: #f5f7fb; border-radius: 8px; padding: 8px 12px; min-width: 140px; }
    .ls-kpi b { display: block; font-size: 1.25em; }
    .ls-kpi span { color: #666; font-size: .8em; }
    .ls-form { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 10px; font-size: .9em; }
    .ls-form select { padding: 5px 6px; min-width: 260px; max-width: 100%; }
    .ls-btn { border: none; border-radius: 6px; padding: 7px 14px; cursor: pointer; font-weight: 600; font-size: .9em; }
    .ls-btn-primary { background: linear-gradient(135deg,#667eea,#764ba2); color: #fff; }
    .ls-btn-secondary { background: #eef0f4; color: #333; }
    .ls-btn:disabled { opacity: .5; cursor: default; }
    .ls-progress { height: 8px; background: #eef0f4; border-radius: 4px; overflow: hidden; margin: 8px 0 4px; }
    .ls-progress div { height: 100%; background: #667eea; width: 0; transition: width .4s; }
    .ls-msg { font-size: .88em; margin-top: 6px; }
    .ls-msg.fehler { color: #c62828; } .ls-msg.fertig { color: #2e7d32; }
    .ls-table-wrap { overflow-x: auto; max-height: 520px; overflow-y: auto; }
    .ls-table { border-collapse: collapse; width: 100%; font-size: .82em; }
    .ls-table th, .ls-table td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #eef0f4; white-space: nowrap; }
    .ls-table th { position: sticky; top: 0; background: #f8f9fb; }
    .ls-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .ls-table tr.aktiv td { background: #eef3fb; }
    .ls-badge { display: inline-block; border-radius: 4px; padding: 1px 6px; font-size: .9em; }
    .ls-badge.o { background: #e3f2fd; color: #1d4f91; } .ls-badge.f { background: #f3e5f5; color: #6a1b9a; }
    .ls-st-SUCCESS { color: #2e7d32; } .ls-st-FAILED { color: #c62828; }
    `;

    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const datum = v => v ? new Date(v).toLocaleString('de-CH', { dateStyle: 'medium', timeStyle: 'short' }) : '–';
    const zahl = v => v == null ? '–' : Number(v).toLocaleString('de-CH');

    class LoadSimulation {
        constructor(container) {
            this._el = container;
            this._timer = null;
            this._daten = null;
            if (!document.getElementById('ls-style')) {
                const st = document.createElement('style');
                st.id = 'ls-style'; st.textContent = CSS;
                document.head.appendChild(st);
            }
        }

        async load() {
            this._el.innerHTML = '<div class="ls-card">Lade …</div>';
            try {
                this._daten = await window.api.etl.simulation.get();
            } catch (e) {
                this._el.innerHTML = `<div class="ls-card ls-msg fehler">Fehler: ${esc(e.message)}</div>`;
                return;
            }
            this._render();
            if (this._daten.status?.zustand === 'laeuft') this._poll();
        }

        _render() {
            const d = this._daten;
            const st = d.status || {};
            const laeuft = st.zustand === 'laeuft';
            const ids = d.lade_ids || [];
            const optionen = ids.filter(l => d.ladestand == null || l.lade_id > d.ladestand).reverse()
                .map(l => `<option value="${l.lade_id}" ${l.lade_id === d.naechster_tag ? 'selected' : ''}>`
                    + `${l.lade_id} – ${esc(datum(l.snapshot))} (${l.tabellen} Tab., ${zahl(l.zeilen)} Z.)</option>`).join('');
            const tagInfo = d.naechster_tag
                ? `Nächster Tag: Lade-ID ${d.naechster_tag} (${esc(datum((ids.find(l => l.lade_id === d.naechster_tag) || {}).snapshot))})`
                : 'Alle verfügbaren Lade-IDs sind geladen.';
            const n = d.jobs.length;
            const nO = d.jobs.filter(j => j.obergrenze).length;

            this._el.innerHTML = `<div class="ls-root">
                <div class="ls-card">
                    <h3>Tagessimulation</h3>
                    <p class="ls-hint">Lädt die Kette Tag für Tag: Je Lade-ID laufen alle ${n} Jobs einmal in Abhängigkeitsreihenfolge.
                    Jobs mit Obergrenze (${nO}, aus RAW) laden bis zur Lade-ID des Tages, die Folge-Jobs (${n - nO})
                    bis zum kleinsten Ladestand ihrer Vorgänger. Beim ersten Fehler bricht die Simulation ab.</p>
                    <div class="ls-kpis">
                        <div class="ls-kpi"><b>${d.ladestand ?? '–'}</b><span>Ladestand der Kette (kleinster der Jobs mit Obergrenze)</span></div>
                        <div class="ls-kpi"><b>${ids.length ? `${ids[0].lade_id}–${ids[ids.length - 1].lade_id}` : '–'}</b><span>verfügbare Lade-IDs über ${d.quellen} Quelltabellen</span></div>
                        <div class="ls-kpi"><b>${n}</b><span>Jobs je Tag</span></div>
                    </div>
                    <p class="ls-hint">${tagInfo}</p>
                    <div class="ls-form">
                        <button class="ls-btn ls-btn-primary" id="ls-next" ${!d.naechster_tag || laeuft ? 'disabled' : ''}>▶ Nächster Tag</button>
                        <label>bis Lade-ID <select id="ls-bis" ${!optionen || laeuft ? 'disabled' : ''}>${optionen}</select></label>
                        <label><input type="checkbox" id="ls-tft" checked ${laeuft ? 'disabled' : ''}> Tag für Tag</label>
                        <button class="ls-btn ls-btn-primary" id="ls-start" ${!optionen || laeuft ? 'disabled' : ''}>▶ Starten</button>
                        <button class="ls-btn ls-btn-secondary" id="ls-stop" ${laeuft ? '' : 'disabled'}>■ Anhalten</button>
                        <button class="ls-btn ls-btn-secondary" id="ls-reload" ${laeuft ? 'disabled' : ''}>↺</button>
                    </div>
                    <div id="ls-status">${this._statusHtml(st)}</div>
                </div>
                <div class="ls-card">
                    <h3>Jobs in Ausführungsreihenfolge</h3>
                    <div class="ls-table-wrap"><table class="ls-table">
                        <thead><tr><th>#</th><th>Job</th><th>Name</th><th>Art</th><th>Vorgänger</th><th>Ladestand</th><th>Letzter Lauf (Simulation)</th></tr></thead>
                        <tbody id="ls-jobs">${this._jobsHtml(st)}</tbody>
                    </table></div>
                </div>
            </div>`;

            const q = s => this._el.querySelector(s);
            q('#ls-next')?.addEventListener('click', () => this._start(d.naechster_tag, true));
            q('#ls-start')?.addEventListener('click', () => this._start(Number(q('#ls-bis').value), q('#ls-tft').checked));
            q('#ls-stop')?.addEventListener('click', async () => {
                try { await window.api.etl.simulation.stop(); this._pollOnce(); } catch (e) { alert(e.message); }
            });
            q('#ls-reload')?.addEventListener('click', () => this.load());
        }

        _jobsHtml(st) {
            const letzte = {};
            (st.laeufe || []).forEach(l => { letzte[l.job_id] = l; });
            return this._daten.jobs.map((j, i) => {
                const l = letzte[j.job_id];
                const lauf = l ? `<span class="ls-st-${esc(l.status)}">${esc(l.status)}</span> · Tag ${esc(l.tag)} · ${esc(l.dauer_s)} s${l.run_id ? ` · Run ${esc(l.run_id)}` : ''}` : '';
                return `<tr class="${st.zustand === 'laeuft' && st.job === j.job_id ? 'aktiv' : ''}">
                    <td class="num">${i + 1}</td><td class="num">${j.job_id}</td><td>${esc(j.job_name)}</td>
                    <td>${j.obergrenze ? '<span class="ls-badge o">bis Lade-ID</span>' : '<span class="ls-badge f">Folge-Job</span>'}</td>
                    <td>${esc((j.vorgaenger || []).join(', '))}</td><td class="num">${j.ladestand ?? '–'}</td><td>${lauf}</td></tr>`;
            }).join('');
        }

        _statusHtml(st) {
            if (!st || st.zustand === 'bereit') return '';
            const tage = st.tage || [];
            const gesamt = tage.length * (st.jobs_je_tag || 1);
            const fertig = st.anzahl_laeufe || 0;
            const pct = gesamt ? Math.round(fertig / gesamt * 100) : 0;
            const text = {
                laeuft: `Läuft: Tag ${st.tag_nr} von ${tage.length} (Lade-ID ${st.tag}), Job ${st.job_nr} von ${st.jobs_je_tag} (${st.job})`,
                fertig: 'Fertig', fehler: 'Fehler', angehalten: 'Angehalten',
            }[st.zustand] || st.zustand;
            const cls = st.zustand === 'fehler' ? 'fehler' : st.zustand === 'fertig' ? 'fertig' : '';
            return `<div class="ls-progress"><div style="width:${pct}%"></div></div>
                <div class="ls-msg ${cls}"><b>${esc(text)}</b> · ${fertig} von ${gesamt} Jobläufen
                · Tage ${esc(tage[0])}${tage.length > 1 ? `–${esc(tage[tage.length - 1])}` : ''}
                · gestartet ${esc(datum(st.gestartet))}${st.beendet ? `, beendet ${esc(datum(st.beendet))}` : ''}
                ${st.meldung ? `<br>${esc(st.meldung)}` : ''}</div>`;
        }

        async _start(bis, tagFuerTag) {
            if (!bis) return;
            const d = this._daten;
            const tage = tagFuerTag ? (d.lade_ids || []).filter(l => (d.ladestand == null || l.lade_id > d.ladestand) && l.lade_id <= bis).length : 1;
            if (!confirm(`Kette laden bis Lade-ID ${bis}?\n\n${tage} Tag(e) × ${d.jobs.length} Jobs = ${tage * d.jobs.length} Jobläufe.`)) return;
            try {
                await window.api.etl.simulation.start({ bis_lade_id: bis, tag_fuer_tag: tagFuerTag });
            } catch (e) {
                alert(`Start nicht möglich: ${e.message}`);
                return;
            }
            await this.load();
        }

        _poll() {
            clearInterval(this._timer);
            this._timer = setInterval(() => this._pollOnce(), 3000);
        }

        async _pollOnce() {
            if (!this._el.isConnected) { clearInterval(this._timer); return; }
            let st;
            try { st = await window.api.etl.simulation.status(); } catch (e) { return; }
            if (st.zustand !== 'laeuft') {
                clearInterval(this._timer);
                await this.load();          // Ladestände und Knöpfe neu
                return;
            }
            this._daten.status = st;
            const s = this._el.querySelector('#ls-status');
            if (s) s.innerHTML = this._statusHtml(st);
            const t = this._el.querySelector('#ls-jobs');
            if (t) t.innerHTML = this._jobsHtml(st);
        }
    }

    window.LoadSimulation = LoadSimulation;
})();
