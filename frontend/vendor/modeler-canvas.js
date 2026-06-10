/**
 * canvas.js – JointJS ERD Canvas (DM2)
 */
'use strict';

const ERD = (() => {

    let _graph, _paper;
    const _shapes       = {};   // tableId → joint.dia.Element
    const _links        = {};   // "fromId:toId" → joint.shapes.standard.Link
    const _columnsCache = {};   // tableId → columns[]
    const _nodeView     = {};   // tableId → 'columns'|'keys'|'info'
    let   _selected  = null;
    let   _fkMode    = false;
    let   _fkSource  = null;

    // -------------------------------------------------------------------------
    // Theme-Helper: CSS-Variablen lesen
    // -------------------------------------------------------------------------
    function _cssVar(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function _colors() {
        return {
            bg:      _cssVar('--bg-base')    || '#1e1e2e',
            surface: _cssVar('--bg-surface') || '#252535',
            border:  _cssVar('--border')     || '#3a3a5a',
            text:    _cssVar('--text')        || '#cdd6f4',
            accent:  _cssVar('--accent')      || '#89b4fa',
            danger:  _cssVar('--danger')      || '#f38ba8',
            muted:   _cssVar('--text-muted')  || '#6c7086',
        };
    }

    // -------------------------------------------------------------------------
    // Init
    // -------------------------------------------------------------------------
    function init() {
        const el = document.getElementById('erd-canvas');
        if (!el) { console.error('[ERD] #erd-canvas nicht gefunden'); return; }

        _graph = new joint.dia.Graph({}, { cellNamespace: joint.shapes });

        const parent = el.parentElement || el;
        _paper = new joint.dia.Paper({
            el,
            model:             _graph,
            width:             parent.offsetWidth  || 800,
            height:            parent.offsetHeight || 600,
            gridSize:          10,
            drawGrid:          { name: 'dot', args: { color: _colors().border, thickness: 1 } },
            background:        { color: _colors().bg },
            cellViewNamespace: joint.shapes,
        });

        _initPan();
        _initZoom();
        _initSelection();
        _initButtons();
        _initDropTarget();
        _initResize(el);

        console.log('[ERD] initialisiert –', el.offsetWidth, 'x', el.offsetHeight);
    }

    // -------------------------------------------------------------------------
    // Icon-Helper für Spalten-Flags
    // -------------------------------------------------------------------------
    // 🔑 = PK (U+1F511)   🔗 = FK (U+1F517)   ⊕ = PI (U+2295)
    function _colIcon(col) {
        const isPK = col.is_pk === 'Y' || col.pk_flag === 'Y';
        const isFK = col.is_fk === 'Y';
        const isPI = col.is_pi === 'Y';
        if (isPK) return '\uD83D\uDD11 ';   // 🔑 + space
        if (isFK) return '\uD83D\uDD17 ';   // 🔗 + space
        if (isPI) return '\u2295  ';         // ⊕  + 2 spaces (single-width char)
        return '   ';                         // 3 spaces
    }

    // -------------------------------------------------------------------------
    // Label-Inhalt je View-Modus
    // -------------------------------------------------------------------------
    function _makeLines(tableData, columns, view) {
        const c    = columns || [];
        const MAX  = 30;
        const sep  = '\u2500'.repeat(24);

        if (view === 'keys') {
            const keyCols = c.filter(col =>
                col.pk_flag === 'Y' || col.is_pk === 'Y' ||
                col.is_fk   === 'Y' || col.is_pi === 'Y'
            ).slice(0, MAX);
            const lines = [tableData.table_name, sep];
            keyCols.forEach(col => {
                const isPK = col.is_pk === 'Y' || col.pk_flag === 'Y';
                const isFK = col.is_fk === 'Y';
                const isPI = col.is_pi === 'Y';
                const tag  = [isPK?'PK':'', isFK?'FK':'', isPI?'PI':''].filter(Boolean).join('+');
                lines.push(_colIcon(col) + (col.column_name || '') + '  (' + tag + ')');
            });
            if (!keyCols.length) lines.push('(keine Keys)');
            return lines;
        }

        if (view === 'info') {
            const lines = [tableData.table_name, sep];
            lines.push('DB:    ' + (tableData.db_name || '\u2014'));
            lines.push('Layer: ' + (tableData.layer_name || tableData.layer || '\u2014'));
            lines.push('Typ:   ' + (tableData.table_type || '\u2014'));
            if (tableData.table_desc) {
                const desc = String(tableData.table_desc);
                for (let i = 0; i < Math.min(desc.length, 78); i += 26)
                    lines.push(desc.substring(i, i + 26));
            }
            return lines;
        }

        // default: columns  –  PK=🔑  FK=🔗  PI=⊕  sonst Leerzeichen
        const cols  = c.slice(0, MAX);
        const lines = [tableData.table_name, sep];
        cols.forEach(col => {
            const type = col.data_type ? '  ' + String(col.data_type).substring(0, 14) : '';
            lines.push(_colIcon(col) + (col.column_name || '') + type);
        });
        if (!cols.length) lines.push('(keine Spalten)');
        return lines;
    }

    // -------------------------------------------------------------------------
    // Shape bauen  (joint.shapes.standard.Rectangle – garantiert verfügbar)
    // -------------------------------------------------------------------------
    function _makeShape(tableData, columns, position, view) {
        const MAX_COLS = 30;
        const cols     = (columns || []).slice(0, MAX_COLS);
        const c        = _colors();

        const lines  = _makeLines(tableData, columns, view || 'columns');
        const ROW_H  = 14;
        const height = Math.max(36, 18 + lines.length * ROW_H + 8);

        const shape = new joint.shapes.standard.Rectangle({
            position: position || {
                x: 60 + Math.round(Math.random() * 300),
                y: 60 + Math.round(Math.random() * 200),
            },
            size: { width: 230, height },
            attrs: {
                body: {
                    fill:        c.surface,
                    stroke:      c.accent,
                    strokeWidth: 1,
                    rx:          4,
                    ry:          4,
                },
                label: {
                    text:               lines.join('\n'),
                    fill:               c.text,
                    fontSize:           11,
                    fontFamily:         'Consolas, "Courier New", monospace',
                    textAnchor:         'start',
                    textVerticalAnchor: 'top',
                    refX:               8,
                    refY:               6,
                    lineHeight:         ROW_H,
                },
            },
        });

        shape.set('tableData', tableData);
        shape.set('tableId',   tableData.table_id);
        return shape;
    }

    // -------------------------------------------------------------------------
    // Public: Tabelle hinzufügen
    // -------------------------------------------------------------------------
    async function addTable(tableData, position) {
        const tid = tableData.table_id;
        if (_shapes[tid]) {
            console.log('[ERD] bereits auf Canvas:', tableData.table_name);
            return _shapes[tid];
        }

        let columns = [];
        try {
            const r = await fetch(window._MODELER_API + '/api/modeler/tables/' + tid + '/columns/full');
            if (r.ok) {
                const data = await r.json();
                if (Array.isArray(data) && !data[0]?.error) columns = data;
            }
        } catch (e) {
            console.warn('[ERD] Spalten laden fehlgeschlagen:', e.message);
        }

        _columnsCache[tid] = columns;
        if (!_nodeView[tid]) _nodeView[tid] = 'columns';

        const shape = _makeShape(tableData, columns, position, _nodeView[tid]);
        _graph.addCell(shape);
        _shapes[tid] = shape;
        console.log('[ERD] hinzugefügt:', tableData.table_name,
                    '@ x=' + shape.get('position').x, 'y=' + shape.get('position').y,
                    '| Spalten:', columns.length);

        document.querySelector('.table-item[data-table-id="' + tid + '"]')
                ?.classList.add('on-canvas');
        document.getElementById('canvas-hint')?.classList.add('hidden');

        return shape;
    }

    // -------------------------------------------------------------------------
    // Public: Ausgewählte Tabelle entfernen
    // -------------------------------------------------------------------------
    function removeSelected() {
        if (!_selected) return;
        const tid = _selected.get('tableId');
        if (tid !== undefined) {
            delete _shapes[tid];
            document.querySelector('.table-item[data-table-id="' + tid + '"]')
                    ?.classList.remove('on-canvas');
        }
        _selected.remove();
        _selected = null;
    }

    function removeTable(tableId) {
        const shape = _shapes[tableId];
        if (!shape) return;
        delete _shapes[tableId];
        document.querySelector('.table-item[data-table-id="' + tableId + '"]')
                ?.classList.remove('on-canvas');
        if (_selected === shape) _selected = null;
        shape.remove();
    }

    // -------------------------------------------------------------------------
    // Public: Layout lesen / schreiben
    // -------------------------------------------------------------------------
    function getLayout() {
        return _graph.getElements().map(el => ({
            table_id:   el.get('tableId'),
            table_name: el.get('tableData')?.table_name,
            position:   el.get('position'),
        })).filter(c => c.table_id !== undefined);
    }

    async function loadLayout(cells, tableMap) {
        _graph.clear();
        Object.keys(_shapes).forEach(k => delete _shapes[k]);
        Object.keys(_links).forEach(k  => delete _links[k]);
        document.querySelectorAll('.table-item.on-canvas')
                .forEach(i => i.classList.remove('on-canvas'));
        for (const cell of cells) {
            const td = tableMap[cell.table_id];
            if (td) await addTable(td, cell.position);
        }
        if (cells.length) {
            setTimeout(() => _paper.scaleContentToFit({ padding: 40 }), 200);
        }
    }

    // -------------------------------------------------------------------------
    // DM3: FK-Links zeichnen
    // -------------------------------------------------------------------------
    // fkList = Array von { from_table_id, to_table_id, fk_name }
    function refreshLinks(fkList) {
        if (!fkList || !fkList.length) return;
        const c = _colors();

        fkList.forEach(fk => {
            const fromId = String(fk.from_table_id);
            const toId   = String(fk.to_table_id);
            const key    = fromId + ':' + toId;

            const src = _shapes[fromId];
            const tgt = _shapes[toId];

            if (src && tgt) {
                const labelDef = fk.fk_name ? [{
                    attrs: {
                        text: { text: fk.fk_name, fontSize: 9, fill: c.muted },
                        rect: { fill: c.bg, stroke: 'none' },
                    },
                    position: { distance: 0.5 },
                }] : [];

                if (!_links[key]) {
                    // Neu erstellen
                    const link = new joint.shapes.standard.Link({
                        source: { id: src.id },
                        target: { id: tgt.id },
                        attrs: {
                            line: {
                                stroke:           c.danger,
                                strokeWidth:      1.5,
                                targetMarker: {
                                    type:   'path',
                                    d:      'M 10 -5 0 0 10 5 Z',
                                    fill:   c.danger,
                                    stroke: 'none',
                                },
                            },
                        },
                        labels: labelDef,
                    });
                    link.prop('fkId',        fk.fk_id);
                    link.prop('fromTableId', fromId);
                    link.prop('toTableId',   toId);
                    _graph.addCell(link);
                    _links[key] = link;
                    console.log('[ERD] FK-Link:', fk.fk_name || key);
                } else {
                    // Existierend aktualisieren (Label + fkId)
                    _links[key].labels(labelDef);
                    _links[key].prop('fkId', fk.fk_id);
                }
            } else {
                // Einer der beiden Knoten nicht auf Canvas → Link entfernen falls vorhanden
                if (_links[key]) {
                    _links[key].remove();
                    delete _links[key];
                }
            }
        });
    }

    // -------------------------------------------------------------------------
    // Pan, Zoom, Selection, Buttons, Drop, Resize
    // -------------------------------------------------------------------------
    function _initPan() {
        let _o = null;
        _paper.on('blank:pointerdown', evt => {
            _o = { cx: evt.clientX, cy: evt.clientY,
                   tx: _paper.translate().tx, ty: _paper.translate().ty };
        });
        _paper.el.addEventListener('mousemove', e => {
            if (!_o) return;
            _paper.translate(_o.tx + e.clientX - _o.cx, _o.ty + e.clientY - _o.cy);
        });
        const stop = () => { _o = null; };
        _paper.el.addEventListener('mouseup',    stop);
        _paper.el.addEventListener('mouseleave', stop);
    }

    function _initZoom() {
        _paper.el.addEventListener('wheel', e => {
            e.preventDefault();
            _hideNodeToolbar();
            const s = _paper.scale().sx;
            _paper.scale(Math.max(0.15, Math.min(3, s * (e.deltaY < 0 ? 1.1 : 0.9))));
        }, { passive: false });
    }

    function _initSelection() {
        _paper.on('cell:pointerclick', (view, evt) => {
            evt.stopPropagation();
            if (_fkMode) {
                _handleFKClick(view.model);
                return;
            }
            _selected = view.model;
            const td = view.model.get('tableData');
            if (td) {
                window.dispatchEvent(new CustomEvent('erd:select', { detail: td }));
                _showNodeToolbar(view, td.table_id);
            }
        });
        _paper.on('blank:pointerclick', () => {
            if (_fkMode) { _cancelFKMode(); return; }
            _selected = null;
            _hideNodeToolbar();
        });
        // Toolbar verstecken beim Drag
        _paper.on('element:pointermove', () => _hideNodeToolbar());
        // Doppelklick auf FK-Linie → erd:fkEdit
        _paper.on('link:pointerdblclick', (linkView, evt) => {
            evt.stopPropagation();
            const fkId     = linkView.model.prop('fkId');
            const fromId   = linkView.model.prop('fromTableId');
            const toId     = linkView.model.prop('toTableId');
            if (fkId == null) return;
            window.dispatchEvent(new CustomEvent('erd:fkEdit', {
                detail: { fkId, fromId, toId }
            }));
        });
    }

    // -------------------------------------------------------------------------
    // Node-Toolbar: anzeigen / verstecken / View wechseln
    // -------------------------------------------------------------------------
    function _showNodeToolbar(view, tableId) {
        const toolbar = document.getElementById('erd-node-toolbar');
        if (!toolbar) return;
        const rect = view.el.getBoundingClientRect();
        toolbar.style.left    = Math.round(rect.left) + 'px';
        toolbar.style.top     = Math.max(0, Math.round(rect.top) - 32) + 'px';
        toolbar.style.display = 'flex';

        const cur = _nodeView[tableId] || 'columns';
        toolbar.querySelectorAll('.ent-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === cur);
        });

        // Handler: nur einmal binden (delegated via closure)
        toolbar._tid = tableId;
        toolbar.onclick = e => {
            const btn = e.target.closest('.ent-btn');
            if (!btn) return;
            const newView = btn.dataset.view;
            const tid     = toolbar._tid;
            _nodeView[tid] = newView;
            toolbar.querySelectorAll('.ent-btn').forEach(b =>
                b.classList.toggle('active', b.dataset.view === newView));
            _refreshNodeLabel(tid);
        };
    }

    function _hideNodeToolbar() {
        const t = document.getElementById('erd-node-toolbar');
        if (t) t.style.display = 'none';
    }

    function _refreshNodeLabel(tid) {
        const shape = _shapes[tid];
        if (!shape) return;
        const tableData = shape.get('tableData');
        const columns   = _columnsCache[tid] || [];
        const view      = _nodeView[tid] || 'columns';
        const c         = _colors();
        const lines     = _makeLines(tableData, columns, view);
        const ROW_H     = 14;
        const height    = Math.max(36, 18 + lines.length * ROW_H + 8);
        shape.attr('label/text', lines.join('\n'));
        shape.resize(shape.get('size').width, height);
    }

    // -------------------------------------------------------------------------
    // DM3: FK-Modus intern
    // -------------------------------------------------------------------------
    function _handleFKClick(model) {
        const tid = model.get('tableId');
        if (tid === undefined) return;  // Link-Element ignorieren

        if (!_fkSource) {
            // Erster Klick: Quelle merken + grün hervorheben
            _fkSource = model;
            model.attr('body/stroke', '#a6e3a1');
            model.attr('body/strokeWidth', 2);
            console.log('[FK] Quelle gewählt:', model.get('tableData')?.table_name);
        } else if (_fkSource === model) {
            // Gleiche Tabelle nochmal: abbrechen
            _cancelFKMode();
        } else {
            // Zweiter Klick: Ziel → Event auslösen
            const from = _fkSource;
            const to   = model;
            _cancelFKMode();  // setzt _fkMode = false, _fkSource = null, Farben zurück
            window.dispatchEvent(new CustomEvent('erd:fkConnect', {
                detail: {
                    fromId:   from.get('tableId'),
                    toId:     to.get('tableId'),
                    fromName: from.get('tableData')?.table_name,
                    toName:   to.get('tableData')?.table_name,
                }
            }));
        }
    }

    function _cancelFKMode() {
        if (_fkSource) {
            _fkSource.attr('body/stroke', _colors().accent);
            _fkSource.attr('body/strokeWidth', 1);
            _fkSource = null;
        }
        _fkMode = false;
        document.getElementById('erd-canvas').style.cursor = '';
        document.getElementById('btn-fk-mode')?.classList.remove('active');
    }

    // -------------------------------------------------------------------------
    // Public: FK-Modus umschalten
    // -------------------------------------------------------------------------
    function toggleFKMode() {
        if (_fkMode) {
            _cancelFKMode();
        } else {
            _fkMode = true;
            document.getElementById('erd-canvas').style.cursor = 'crosshair';
            document.getElementById('btn-fk-mode')?.classList.add('active');
            console.log('[FK] Modus aktiv – Quelle anklicken…');
        }
        return _fkMode;
    }

    function _initButtons() {
        document.getElementById('btn-zoom-in')?.addEventListener('click', () =>
            _paper.scale(Math.min(_paper.scale().sx * 1.2, 3)));
        document.getElementById('btn-zoom-out')?.addEventListener('click', () =>
            _paper.scale(Math.max(_paper.scale().sx / 1.2, 0.15)));
        document.getElementById('btn-zoom-fit')?.addEventListener('click', () =>
            _paper.scaleContentToFit({ padding: 40, minScaleX: 0.1, maxScaleX: 2 }));
        document.getElementById('btn-delete-sel')?.addEventListener('click', removeSelected);
    }

    function _initDropTarget() {
        const el = document.getElementById('erd-canvas');
        el.addEventListener('dragover', e => e.preventDefault());
        el.addEventListener('drop', e => {
            e.preventDefault();
            const json = e.dataTransfer?.getData('table_data');
            if (!json) return;
            try {
                const td   = JSON.parse(json);
                const rect = el.getBoundingClientRect();
                const s    = _paper.scale().sx;
                const t    = _paper.translate();
                addTable(td, {
                    x: Math.round((e.clientX - rect.left - t.tx) / s),
                    y: Math.round((e.clientY - rect.top  - t.ty) / s),
                }).then(() => {
                    window.dispatchEvent(new CustomEvent('erd:tableAdded'));
                });
            } catch (err) { console.error('[ERD] drop:', err); }
        });
    }

    function _initResize(el) {
        if (!window.ResizeObserver) return;
        const parent = el.parentElement || el;
        new ResizeObserver(() =>
            _paper.setDimensions(parent.offsetWidth, parent.offsetHeight)
        ).observe(parent);
    }

    // -------------------------------------------------------------------------
    // Public: Theme aktualisieren (alle bestehenden Shapes neu einfärben)
    // -------------------------------------------------------------------------
    function refreshTheme() {
        if (!_paper) return;
        const c = _colors();
        _paper.drawBackground({ color: c.bg });
        _paper.drawGrid({ name: 'dot', args: { color: c.border, thickness: 1 } });
        _graph.getElements().forEach(el => {
            el.attr('body/fill',   c.surface);
            el.attr('body/stroke', c.accent);
            el.attr('label/fill',  c.text);
        });
        _graph.getLinks().forEach(link => {
            link.attr('line/stroke', c.danger);
            link.attr('line/targetMarker/fill', c.danger);
            const labels = link.labels();
            labels.forEach((lbl, i) => {
                link.label(i, {
                    attrs: {
                        text: { ...(lbl.attrs?.text || {}), fill: c.muted },
                        rect: { fill: c.bg, stroke: 'none' },
                    },
                    position: lbl.position,
                });
            });
        });
    }

    return { init, addTable, removeSelected, removeTable, getLayout, loadLayout, refreshLinks, toggleFKMode, refreshTheme };

})();
