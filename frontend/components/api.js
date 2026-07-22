/**
 * daita-studio – Zentraler API-Client (C1)
 *
 * Alle fetch()-Aufrufe laufen über dieses Modul.
 * Pages und Komponenten dürfen kein direktes fetch() machen.
 *
 * Verwendung:
 *   <script src="/components/api.js"></script>
 *   const layers = await api.etl.layers();
 *   const job    = await api.jobs.get(42);
 *
 * Fehlerbehandlung:
 *   Alle Methoden werfen einen Error mit .message wenn der Server
 *   einen Nicht-2xx-Status oder ein {detail}-Feld zurückgibt.
 *
 * Events (Custom Events, Präfix studio:):
 *   studio:api-error  { detail: { status, url, message } }
 *   – wird bei jedem HTTP-Fehler gefeuert; Pages können darauf lauschen.
 */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // Basis-Konfiguration
    // ----------------------------------------------------------------

    function _baseUrl() {
        const cfg = window.METADAITA_CONFIG;
        return (cfg?.backend_url || `http://${window.location.hostname}:9021`) + '/api';
    }

    // ----------------------------------------------------------------
    // Interne Fetch-Hilfsfunktion
    // ----------------------------------------------------------------

    async function _fetch(path, options = {}) {
        const url = _baseUrl() + path;
        const defaults = {
            headers: { 'Content-Type': 'application/json' }
        };
        const req = { ...defaults, ...options };
        if (req.headers && options.headers) {
            req.headers = { ...defaults.headers, ...options.headers };
        }
        // Body-Serialisierung
        if (req.body && typeof req.body === 'object') {
            req.body = JSON.stringify(req.body);
        }

        let response;
        try {
            response = await fetch(url, req);
        } catch (networkError) {
            const msg = `Netzwerkfehler: ${networkError.message}`;
            _fireError({ status: 0, url, message: msg });
            throw new Error(msg);
        }

        if (!response.ok) {
            let message = `HTTP ${response.status}`;
            try {
                const err = await response.json();
                message = err.detail || err.message || JSON.stringify(err);
            } catch (_) { /* ignore parse error */ }
            _fireError({ status: response.status, url, message });
            throw new Error(message);
        }

        // 204 No Content
        if (response.status === 204) return null;

        const ct = response.headers.get('content-type') || '';
        if (ct.includes('application/json')) {
            return response.json();
        }
        return response.text();
    }

    function _fireError(detail) {
        document.dispatchEvent(new CustomEvent('studio:api-error', { detail }));
    }

    // Shortcut-Helfer
    const get    = (path, params)   => _fetch(path + _qs(params));
    const post   = (path, body)     => _fetch(path, { method: 'POST', body });
    const put    = (path, body)     => _fetch(path, { method: 'PUT',  body });
    const patch  = (path, body)     => _fetch(path, { method: 'PATCH', body });
    const del    = (path, body)     => _fetch(path, body
        ? { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
        : { method: 'DELETE' });

    function _qs(params) {
        if (!params) return '';
        const p = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) {
            if (v !== undefined && v !== null) p.append(k, v);
        }
        const s = p.toString();
        return s ? '?' + s : '';
    }

    // ================================================================
    // API-Namespaces
    // ================================================================

    const api = {};

    // ----------------------------------------------------------------
    // etl  – /api/etl/*
    // ----------------------------------------------------------------
    api.etl = {
        /** Layer-Liste */
        layers:     ()                  => get('/etl/layers'),
        /** Datenbanken / Schemas */
        databases:  ()                  => get('/etl/databases'),
        /** Tabellen einer Datenbank */
        dbTables:   (dbId)              => get(`/etl/databases/${dbId}/tables`),

        // ---- Jobs ----
        jobs: {
            list:       (params)            => get('/etl/jobs', params),
            get:        (id)                => get(`/etl/jobs/${id}`),
            steps:      (id)                => get(`/etl/jobs/${id}/steps`),
            mapping:    (id)                => get(`/etl/jobs/${id}/mapping`),
            sqlExport:  (id)                => get(`/etl/jobs/${id}/sql-export`),
            tptPreview: (id)                => get(`/etl/jobs/${id}/tpt-preview`),
            delete:     (id)                => del(`/etl/jobs/${id}`),
            execute:    (id, body={})        => post(`/etl/jobs/${id}/execute`, body),
            updateStepParams: (stepId, p)   => put(`/etl/steps/${stepId}/parameters`, p),
        },

        // ---- Tabellen / Spalten ----
        tables: {
            get:        (id)                => get(`/etl/tables/${id}`),
            columns:    (id)                => get(`/etl/tables/${id}/columns`),
            diff:       (id)                => get(`/etl/tables/${id}/columns/diff`),
            sync:       (id)                => post(`/etl/tables/${id}/columns/sync`),
            syncCols:   (id)                => post(`/etl/tables/${id}/sync-columns`),
            compare:    (id)                => get(`/etl/tables/${id}/compare`),
            delete:     (id)                => del(`/etl/tables/${id}`),
        },

        // ---- DBC / Import (etl-Weg) ----
        dbc: {
            tables:     (dbId)              => get(`/etl/databases/${dbId}/dbc-tables`),
            importTable:(dbId, body)        => post(`/etl/databases/${dbId}/import-table`, body),
        },

        // ---- Runs ----
        runs: {
            list:       (params)            => get('/etl/runs', params),
            get:        (runId)             => get(`/etl/runs/${runId}`),
            pause:      (runId)             => post(`/etl/runs/${runId}/pause`),
            resume:     (runId)             => post(`/etl/runs/${runId}/resume`),
            cancel:     (runId)             => post(`/etl/runs/${runId}/cancel`),
        },

        // ---- SQL Template Files ----
        sqlTemplates: {
            get:    (path)                  => get(`/etl/templates/${path}`),
            update: (path, content)         => put(`/etl/templates/${path}`, { content }),
            render: (path, parameters)      => post(`/etl/templates/${path}/render`, { parameters }),
        },

        // ---- Dashboard ----
        dashboard:  ()                      => get('/etl/dashboard/stats'),

        // ---- Layer-Bulk-Export (F10) – liefert die rohe Response (ZIP-Blob) ----
        exportLayer: (body)                 => fetch(_baseUrl() + '/etl/export/layer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }),
    };

    // ----------------------------------------------------------------
    // jobs  – /api/jobs/*   (Job-Management-Layer, separates API)
    // ----------------------------------------------------------------
    api.jobs = {
        /** Tabellen eines Layers mit Load-Status */
        layerTables:    (layerId)           => get(`/layers/${layerId}/tables`),
        /** Jobs zwischen zwei Layern */
        between:        (srcId, tgtId)      => get(`/layers/${srcId}/to/${tgtId}/jobs`),

        create:         (body)              => post('/jobs', body),
        update:         (id, body)          => put(`/jobs/${id}`, body),
        delete:         (id, body)          => del(`/jobs/${id}`, body),
        deletePreview:  (id)                => get(`/jobs/${id}/delete-preview`),

        addStep:        (jobId, body)       => post(`/jobs/${jobId}/steps`, body),
        updateStep:     (jobId, stepId, b)  => put(`/jobs/${jobId}/steps/${stepId}`, b),
        deleteStep:     (jobId, stepId)     => del(`/jobs/${jobId}/steps/${stepId}`),
        updateMapping:  (jobId, stepId, b)  => put(`/jobs/${jobId}/steps/${stepId}/mapping`, b),
    };

    // ----------------------------------------------------------------
    // templates  – /api/templates/*
    // ----------------------------------------------------------------
    api.templates = {
        listJobs:       ()                  => get('/templates/jobs'),
        getJob:         (id)                => get(`/templates/jobs/${id}`),
        createJob:      (body)              => post('/templates/jobs', body),
        deleteJob:      (id)                => del(`/templates/jobs/${id}`),
        patchJob:       (id, body)          => patch(`/templates/jobs/${id}`, body),

        listSteps:      (params)            => get('/templates/steps', params),
        createStep:     (body)              => post('/templates/steps', body),
        deleteStep:     (id)                => del(`/templates/steps/${id}`),
        patchStep:      (id, body)          => patch(`/templates/steps/${id}`, body),
        getStepParams:  (id)                => get(`/templates/steps/${id}/params`),
        saveStepParams: (id, body)          => put(`/templates/steps/${id}/params`, body),

        /** B2: Erstellt ETL-Job + Zieltabelle in einem Schritt */
        applyJob:       (templateId, body)  => post(`/templates/jobs/${templateId}/create-job`, body),
        addStepToJob:   (stepTplId, jobId)  => post(`/templates/steps/${stepTplId}/add-to-job/${jobId}`),
        saveJobAsTpl:   (jobId)             => post(`/templates/save-job/${jobId}`),

        exportJob:      (id)                => get(`/templates/export/${id}`),
        importJob:      (body)              => post('/templates/import', body),
    };

    // ----------------------------------------------------------------
    // modeler  – /api/modeler/*
    // ----------------------------------------------------------------
    api.modeler = {
        layers:         ()                  => get('/modeler/layers'),
        databases:      ()                  => get('/modeler/databases'),

        tables: {
            list:       (params)            => get('/modeler/tables', params),
            get:        (id)                => get(`/modeler/tables/${id}`),
            update:     (id, body)          => put(`/modeler/tables/${id}`, body),
            columns:    (id)                => get(`/modeler/tables/${id}/columns`),
            columnsFull:(id)                => get(`/modeler/tables/${id}/columns/full`),
            columnPanel:(id)                => get(`/modeler/tables/${id}/column-panel`),
            indexes:    (id)                => get(`/modeler/tables/${id}/indexes`),
            saveIndexes:(id, body)          => put(`/modeler/tables/${id}/indexes`, body),
            fk:         (id)                => get(`/modeler/tables/${id}/fk`),
            reverseEng: (id)                => get(`/modeler/tables/${id}/reverse-engineer`),
            syncDbc:    (id)                => post(`/modeler/tables/${id}/sync-from-dbc`),
        },

        columns: {
            update:     (colId, body)       => put(`/modeler/columns/${colId}`, body),
        },

        fk: {
            list:       ()                  => get('/modeler/fk'),
            create:     (body)              => post('/modeler/fk', body),
            update:     (id, body)          => put(`/modeler/fk/${id}`, body),
            delete:     (id)                => del(`/modeler/fk/${id}`),
        },

        areas: {
            list:       ()                  => get('/modeler/areas'),
        },

        cache: {
            clear:      ()                  => post('/modeler/cache/clear'),
        },
    };

    // ----------------------------------------------------------------
    // diagrams  – /api/diagrams/*
    // ----------------------------------------------------------------
    api.diagrams = {
        list:           ()                  => get('/diagrams'),
        load:           (name)              => get(`/diagrams/${name}`),
        save:           (name, body)        => post(`/diagrams/${name}`, body),
        delete:         (name)              => del(`/diagrams/${name}`),
    };

    // ----------------------------------------------------------------
    // import  – /api/import/*
    // ----------------------------------------------------------------
    api.importTd = {
        candidates:     (db)                => get('/import/candidates', { db }),
        table:          (body)              => post('/import/table', body),
        importTable:    (body)              => post('/import/table', body),
    };

    // ----------------------------------------------------------------
    // sources  – /api/sources/*
    // ----------------------------------------------------------------
    api.sources = {
        list:           ()                  => get('/sources'),
        get:            (id)                => get(`/sources/${id}`),
        create:         (body)              => post('/sources', body),
        update:         (id, body)          => put(`/sources/${id}`, body),
        delete:         (id)                => del(`/sources/${id}`),
        test:           (id)                => post(`/sources/${id}/test`),
        tables:         (id)                => get(`/sources/${id}/tables`),
    };

    // ----------------------------------------------------------------
    // metadata  – /api/metadata/*
    // ----------------------------------------------------------------
    api.metadata = {
        list:           ()                  => get('/metadata/list'),
        get:            (id)                => get(`/metadata/${id}`),
        create:         (body)              => post('/metadata/', body),
        update:         (id, body)          => put(`/metadata/${id}`, body),
    };

    // ----------------------------------------------------------------
    // lineage-flow  – /api/lineage/*  (Dataflow-Graph, Phase 1: ETL-Kanten)
    // ----------------------------------------------------------------
    api.lineageFlow = {
        /** Datenfluss-Graph eines Objekts: { root_table_id, direction, nodes, edges } */
        dataflow:   (tableId, depth, direction) => get(`/lineage/dataflow/${tableId}`, {
            ...(depth ? { depth } : {}),
            ...(direction ? { direction } : {}),
        }),
        /** View-DDL + Spalten-Mapping eines Objekts */
        viewDdl:    (tableId)        => get(`/lineage/view/${tableId}/ddl`),
    };

    // ----------------------------------------------------------------
    // health  – /
    // ----------------------------------------------------------------
    api.health = () => _fetch('/'.replace('/api', ''), { headers: {} });

    // ================================================================
    // Export: global als window.api verfügbar
    // ================================================================
    window.api = api;

})();
