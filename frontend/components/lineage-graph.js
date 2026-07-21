/**
 * daita-studio – LineageGraph (Dataflow-Ansicht, Phase 1)
 *
 * Zeichnet den Herkunftsgraphen eines Objekts als Layer-Swimlanes.
 * Layout: RAW links → CONS rechts (nach META_LAYER.layer_sequence).
 * Knoten = Objekt-Boxen (Tabelle/View), Kanten = ETL-Strecken (durchgezogen).
 *
 * Reines Vanilla-JS (kein npm/Build). SVG für Kanten, HTML für Knoten.
 *
 * Verwendung:
 *   const g = new LineageGraph(containerEl, {
 *       onNodeClick: (node) => {...},
 *       onEdgeClick: (edge) => {...},
 *   });
 *   await g.load(tableId, depth);
 */

(() => {
    'use strict';

    const LAYER_ICONS = { SRC: '🗄️', RAW: '📦', DISC: '🔍', REUS: '♻️', CONS: '📊', META: '🏷️' };

    // Layout-Konstanten
    const COL_W     = 200;   // Breite einer Knoten-Box / Layer-Spalte
    const COL_GAP   = 96;    // horizontaler Abstand zwischen Layer-Spalten
    const NODE_H    = 70;    // Höhe einer Knoten-Box
    const NODE_VGAP = 22;    // vertikaler Abstand zwischen Boxen
    const HEAD_TOP  = 12;    // Y-Position der Layer-Kopf-Boxen
    const HEAD_H    = 58;    // Höhe der Layer-Kopf-Boxen
    const PAD_TOP   = HEAD_TOP + HEAD_H + 26;  // Startlinie für Knoten
    const PAD_LEFT  = 16;

    const STYLE = `
        .lg-root { position: relative; width: 100%; overflow: auto; }
        .lg-canvas { position: relative; }
        .lg-svg { position: absolute; top: 0; left: 0; pointer-events: none; overflow: visible; z-index: 1; }
        .lg-lane {
            position: absolute; top: ${HEAD_TOP}px; z-index: 0;
            background: #fafbff; border: 1px solid #eef0f7; border-radius: 10px;
        }
        .lg-lane:nth-child(even) { background: #f6f7fc; }
        .lg-colhead {
            position: absolute; top: ${HEAD_TOP}px; height: ${HEAD_H}px; z-index: 3;
            box-sizing: border-box;
            background: #fff; border: 2px solid #e5e0f8; border-radius: 10px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.06);
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 1px;
        }
        .lg-colhead .lg-ch-icon { font-size: 1.25em; line-height: 1; }
        .lg-colhead .lg-ch-code { font-weight: 800; font-size: 0.82em; color: #667eea; letter-spacing: 0.04em; }
        .lg-colhead .lg-ch-name { font-size: 0.64em; color: #999; }
        .lg-node {
            position: absolute; box-sizing: border-box; z-index: 2;
            background: #fff; border: 2px solid #d9dbe4; border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            padding: 8px 10px; cursor: pointer; overflow: hidden;
            transition: border-color 0.15s, box-shadow 0.15s;
        }
        .lg-node:hover { box-shadow: 0 4px 16px rgba(102,126,234,0.28); border-color: #a9b0e6; }
        .lg-node.is-root { border-color: #667eea; box-shadow: 0 4px 16px rgba(102,126,234,0.35); }
        .lg-node.is-external { border-style: dashed; opacity: 0.8; }
        .lg-node-top { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
        .lg-badge {
            font-size: 0.62em; font-weight: 700; padding: 1px 6px; border-radius: 8px;
            background: #eef0fb; color: #667eea; white-space: nowrap;
        }
        .lg-badge.type-V { background: #e8f5e9; color: #2e9e57; }
        .lg-badge.type-T { background: #fdf3e7; color: #c9832b; }
        .lg-node-name {
            font-weight: 700; font-size: 0.86em; color: #2b2b2b;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .lg-node-db {
            font-size: 0.7em; color: #999;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .lg-edge { fill: none; stroke: #667eea; stroke-width: 2; }
        .lg-edge.view { stroke: #b08cff; stroke-width: 2; stroke-dasharray: 6 5; }
        .lg-edge-hit { fill: none; stroke: transparent; stroke-width: 14; pointer-events: stroke; cursor: pointer; }
        .lg-edge-label {
            position: absolute; transform: translate(-50%, -50%); z-index: 3;
            font-size: 0.66em; background: #fff; border: 1px solid #e0e0e0;
            border-radius: 8px; padding: 1px 6px; color: #667eea; cursor: pointer;
            white-space: nowrap; max-width: 160px; overflow: hidden; text-overflow: ellipsis;
        }
        .lg-edge-label:hover { background: #667eea; color: #fff; }
        .lg-empty { padding: 30px; text-align: center; color: #999; font-size: 0.9em; }
        .lg-legend { font-size: 0.72em; color: #999; margin: 4px 0 12px; }
        .lg-legend b { color: #667eea; }
    `;

    function injectStyles() {
        if (document.getElementById('lg-style')) return;
        const s = document.createElement('style');
        s.id = 'lg-style';
        s.textContent = STYLE;
        document.head.appendChild(s);
    }

    function esc(v) {
        return String(v ?? '').replace(/[&<>"']/g, c =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    class LineageGraph {
        constructor(container, opts = {}) {
            this._el = container;
            this._opts = opts;
            this._layers = null;   // gecacht
            injectStyles();
        }

        /** Layer einmalig laden (für Spalten-Reihenfolge). */
        async _ensureLayers() {
            if (this._layers) return this._layers;
            const raw = await api.etl.layers();
            this._layers = (Array.isArray(raw) ? raw : [])
                .filter(l => l && l.layer_id != null)
                .sort((a, b) => (a.layer_sequence ?? 0) - (b.layer_sequence ?? 0));
            return this._layers;
        }

        /** Herkunftsgraph für ein Objekt laden und rendern. */
        async load(tableId, depth) {
            this._el.innerHTML = `<div class="lg-empty">⏳ Lade Herkunft …</div>`;
            let data;
            try {
                await this._ensureLayers();
                data = await api.lineageFlow.dataflow(tableId, depth);
            } catch (e) {
                this._el.innerHTML = `<div class="lg-empty">Fehler: ${esc(e.message)}</div>`;
                return;
            }
            this._render(data);
        }

        _render(data) {
            const rawNodes = data.nodes || [];
            const rawEdges = data.edges || [];

            if (!rawNodes.length) {
                this._el.innerHTML = `<div class="lg-empty">Kein Objekt gefunden.</div>`;
                return;
            }

            const SUB_GAP = 72;   // Abstand zwischen Sub-Spalten innerhalb einer Lane

            // Layer-Infos; META-Layer wird nicht dargestellt
            const layerById = {};
            this._layers.forEach(l => { layerById[l.layer_id] = l; });
            const isHiddenLayer = (id) => ((layerById[id]?.layer_code || '').toUpperCase() === 'META');

            // META-Knoten (und deren Kanten) herausfiltern
            const nodes = rawNodes.filter(n => !isHiddenLayer(n.layer_id));
            const nodeIdSet = new Set(nodes.map(n => n.table_id));
            const edges = rawEdges.filter(e => nodeIdSet.has(e.from_table_id) && nodeIdSet.has(e.to_table_id));

            if (!nodes.length) {
                this._el.innerHTML = `<div class="lg-empty">Kein Objekt gefunden.</div>`;
                return;
            }

            // ── Lanes in Layer-Reihenfolge (RAW links → CONS rechts), META ausgeblendet ──
            const colKeys = [];
            const hasExternal = nodes.some(n => n.layer_id == null);
            if (hasExternal) colKeys.push('__ext__');
            this._layers.forEach(l => {
                if ((l.layer_code || '').toUpperCase() === 'META') return;
                colKeys.push(l.layer_id);
            });
            nodes.forEach(n => {
                if (n.layer_id != null && !colKeys.includes(n.layer_id)) colKeys.push(n.layer_id);
            });

            const laneKeyOf = (n) => (n.layer_id == null ? '__ext__' : n.layer_id);

            // Knoten je Lane
            const byLane = {};
            colKeys.forEach(k => { byLane[k] = []; });
            nodes.forEach(n => { if (byLane[laneKeyOf(n)]) byLane[laneKeyOf(n)].push(n); });

            // ── Intra-Lane Sub-Spalten (Quelle links, abhängiges Objekt rechts) ──
            // subCol via Longest-Path über Kanten, deren beide Enden dieselbe Lane haben.
            const laneOf = {};
            nodes.forEach(n => { laneOf[n.table_id] = laneKeyOf(n); });
            const intraChildren = {};
            const intraIndeg = {};
            nodes.forEach(n => { intraChildren[n.table_id] = []; intraIndeg[n.table_id] = 0; });
            edges.forEach(e => {
                if (laneOf[e.from_table_id] !== undefined &&
                    laneOf[e.from_table_id] === laneOf[e.to_table_id] &&
                    e.from_table_id !== e.to_table_id) {
                    intraChildren[e.from_table_id].push(e.to_table_id);
                    intraIndeg[e.to_table_id] = (intraIndeg[e.to_table_id] || 0) + 1;
                }
            });
            const subCol = {};
            nodes.forEach(n => { subCol[n.table_id] = 0; });
            const indegWork = Object.assign({}, intraIndeg);
            const q = nodes.filter(n => (intraIndeg[n.table_id] || 0) === 0).map(n => n.table_id);
            let guard = 0; const guardMax = nodes.length * (nodes.length + 1) + 1;
            while (q.length && guard++ < guardMax) {
                const u = q.shift();
                (intraChildren[u] || []).forEach(v => {
                    if (subCol[v] < subCol[u] + 1) subCol[v] = subCol[u] + 1;
                    indegWork[v] -= 1;
                    if (indegWork[v] === 0) q.push(v);
                });
            }

            // maxSub je Lane → Lane-Breiten + kumulative X-Offsets
            const maxSub = {};
            colKeys.forEach(k => { maxSub[k] = 0; });
            nodes.forEach(n => {
                const k = laneOf[n.table_id];
                if (subCol[n.table_id] > maxSub[k]) maxSub[k] = subCol[n.table_id];
            });
            const laneWidth = {}, laneX = {};
            colKeys.forEach(k => { laneWidth[k] = (maxSub[k] + 1) * COL_W + maxSub[k] * SUB_GAP; });
            let cursor = PAD_LEFT;
            colKeys.forEach(k => { laneX[k] = cursor; cursor += laneWidth[k] + COL_GAP; });

            // ── Positionen: Sub-Spalte = x, Zeile je Sub-Spalte = y ──
            const pos = {};
            const rowInSub = {};
            colKeys.forEach(k => {
                byLane[k].sort((a, b) =>
                    (subCol[a.table_id] - subCol[b.table_id]) ||
                    String(a.table_name).localeCompare(String(b.table_name)));
                byLane[k].forEach(n => {
                    const sc = subCol[n.table_id];
                    const rk = k + '|' + sc;
                    const ri = rowInSub[rk] || 0;
                    rowInSub[rk] = ri + 1;
                    const x = laneX[k] + sc * (COL_W + SUB_GAP);
                    const y = PAD_TOP + ri * (NODE_H + NODE_VGAP);
                    pos[n.table_id] = { x, y, w: COL_W, h: NODE_H };
                });
            });

            let maxRows = 0;
            Object.values(rowInSub).forEach(c => { if (c > maxRows) maxRows = c; });

            const totalW = cursor + PAD_LEFT;
            const totalH = PAD_TOP + maxRows * (NODE_H + NODE_VGAP) + 20;

            // ── DOM aufbauen ──
            const root = document.createElement('div');
            root.className = 'lg-root';

            const legend = document.createElement('div');
            legend.className = 'lg-legend';
            legend.innerHTML = `Fluss <b>RAW → CONS</b> · <span style="border-bottom:2px solid #667eea">ETL-Job</span> ` +
                `· <span style="border-bottom:2px dashed #b08cff">View-Abhängigkeit</span> ` +
                `· Klick auf Box = dorthin springen · Klick auf ETL-Kante = Job · Klick auf View-Kante = DDL`;
            root.appendChild(legend);

            const canvas = document.createElement('div');
            canvas.className = 'lg-canvas';
            canvas.style.width = totalW + 'px';
            canvas.style.height = totalH + 'px';

            // SVG-Ebene (Kanten)
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'lg-svg');
            svg.setAttribute('width', totalW);
            svg.setAttribute('height', totalH);
            svg.innerHTML = `<defs>
                <marker id="lg-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4"
                        orient="auto" markerUnits="userSpaceOnUse">
                    <path d="M0,0 L8,4 L0,8 Z" fill="#667eea"></path>
                </marker>
            </defs>`;
            canvas.appendChild(svg);

            // Lanes (Hintergrund je Layer) + Layer-Kopf-Boxen (die Layer-Leiste)
            colKeys.forEach(k => {
                const x = laneX[k];
                const w = laneWidth[k];

                const lane = document.createElement('div');
                lane.className = 'lg-lane';
                lane.style.left = (x - 8) + 'px';
                lane.style.width = (w + 16) + 'px';
                lane.style.height = (totalH - HEAD_TOP - 6) + 'px';
                canvas.appendChild(lane);

                const head = document.createElement('div');
                head.className = 'lg-colhead';
                head.style.left = x + 'px';
                head.style.width = w + 'px';
                if (k === '__ext__') {
                    head.innerHTML = `<span class="lg-ch-icon">❓</span>` +
                        `<span class="lg-ch-code">EXTERN</span>` +
                        `<span class="lg-ch-name">nicht in META</span>`;
                } else {
                    const l = layerById[k] || {};
                    head.innerHTML = `<span class="lg-ch-icon">${LAYER_ICONS[l.layer_code] || '📁'}</span>` +
                        `<span class="lg-ch-code">${esc(l.layer_code || l.layer_name || k)}</span>` +
                        `<span class="lg-ch-name">${esc(l.layer_name || '')}</span>`;
                }
                canvas.appendChild(head);
            });

            // Knoten-Boxen
            nodes.forEach(n => {
                const p = pos[n.table_id];
                if (!p) return;
                const box = document.createElement('div');
                box.className = 'lg-node'
                    + (n.is_root ? ' is-root' : '')
                    + (n.is_external ? ' is-external' : '');
                box.style.left = p.x + 'px';
                box.style.top = p.y + 'px';
                box.style.width = p.w + 'px';
                box.style.height = p.h + 'px';

                const typeCode = (n.object_type === 'V') ? 'V' : (n.object_type === 'T' ? 'T' : '');
                const typeLabel = typeCode === 'V' ? 'View' : (typeCode === 'T' ? 'Tabelle' : '');
                const layerCode = n.layer_code || (n.is_external ? 'extern' : '');
                box.innerHTML = `
                    <div class="lg-node-top">
                        ${layerCode ? `<span class="lg-badge">${LAYER_ICONS[n.layer_code] || ''} ${esc(layerCode)}</span>` : ''}
                        ${typeLabel ? `<span class="lg-badge type-${typeCode}">${typeLabel}</span>` : ''}
                    </div>
                    <div class="lg-node-name" title="${esc(n.table_name)}">${esc(n.table_name)}</div>
                    <div class="lg-node-db" title="${esc(n.db_name || '')}">${esc(n.db_name || '')}</div>`;

                box.addEventListener('click', () => {
                    if (typeof this._opts.onNodeClick === 'function') this._opts.onNodeClick(n);
                });
                canvas.appendChild(box);
            });

            // Kanten (source = links, target = rechts)
            edges.forEach(edge => {
                const s = pos[edge.from_table_id];
                const t = pos[edge.to_table_id];
                if (!s || !t) return;

                const x1 = s.x + s.w, y1 = s.y + s.h / 2;   // rechter Rand Quelle
                const x2 = t.x,       y2 = t.y + t.h / 2;   // linker Rand Ziel
                const mx = (x1 + x2) / 2;
                const dPath = `M ${x1},${y1} C ${mx},${y1} ${mx},${y2} ${x2},${y2}`;

                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('class', 'lg-edge' + (edge.edge_type === 'VIEW' ? ' view' : ''));
                path.setAttribute('d', dPath);
                path.setAttribute('marker-end', 'url(#lg-arrow)');
                svg.appendChild(path);

                // breiter, unsichtbarer Klick-Pfad
                const hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                hit.setAttribute('class', 'lg-edge-hit');
                hit.setAttribute('d', dPath);
                hit.addEventListener('click', () => {
                    if (typeof this._opts.onEdgeClick === 'function') this._opts.onEdgeClick(edge);
                });
                svg.appendChild(hit);

                // Label nur für ETL-Kanten (Job-Name)
                if (edge.edge_type === 'ETL' && edge.job_name) {
                    const lbl = document.createElement('div');
                    lbl.className = 'lg-edge-label';
                    lbl.style.left = mx + 'px';
                    lbl.style.top = ((y1 + y2) / 2) + 'px';
                    lbl.title = edge.job_name;
                    lbl.textContent = edge.job_name;
                    lbl.addEventListener('click', () => {
                        if (typeof this._opts.onEdgeClick === 'function') this._opts.onEdgeClick(edge);
                    });
                    canvas.appendChild(lbl);
                }
            });

            root.appendChild(canvas);
            this._el.innerHTML = '';
            this._el.appendChild(root);
        }
    }

    window.LineageGraph = LineageGraph;
})();
