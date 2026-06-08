/**
 * Source Systems Dashboard - Frontend Logic
 * ==========================================
 * 
 * Features:
 * - Source Systems anzeigen
 * - Tabellen Discovery aus externen DBs
 * - Spalten-Preview
 * - TPT Job Erstellung
 * 
 * Autor: DWH MVP Team
 * Datum: 2026-03-18
 */

// Configuration (konfigurierbar via config.js)
const API_BASE_URL = (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api/sources';

// State
let sourceSystems = [];
let selectedSource = null;
let discoveredTables = [];
let selectedTables = new Set();

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Source Systems Dashboard initialized');
    loadSourceSystems();
});

// =============================================================================
// Source System Functions
// =============================================================================

async function loadSourceSystems() {
    const container = document.getElementById('sourceSystemsRow');
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            Lade Source Systems...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE_URL}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        sourceSystems = await response.json();
        renderSourceSystems();
    } catch (error) {
        console.error('Error loading source systems:', error);
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Fehler: ${error.message}</p>
                <button class="btn btn-sm" onclick="loadSourceSystems()">Erneut versuchen</button>
            </div>
        `;
    }
}

function renderSourceSystems() {
    const container = document.getElementById('sourceSystemsRow');
    
    if (sourceSystems.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">📭</div>
                <p>Keine Source Systems konfiguriert</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = sourceSystems.map(source => `
        <div class="source-card ${selectedSource?.source_system_id === source.source_system_id ? 'selected' : ''}" 
             onclick="selectSource(${source.source_system_id}, this)">
            <div class="source-code">${escapeHtml(source.source_system_code)}</div>
            <div>
                <span class="source-type-badge">${escapeHtml(source.source_type)}</span>
                <span class="status-badge ${source.is_active === 'Y' ? 'active' : 'inactive'}">
                    ${source.is_active === 'Y' ? 'Aktiv' : 'Inaktiv'}
                </span>
            </div>
            <div class="source-host">${escapeHtml(source.source_system_name || '')}</div>
        </div>
    `).join('');
}

function selectSource(sourceId, element) {
    selectedSource = sourceSystems.find(s => s.source_system_id === sourceId);
    selectedTables.clear();
    discoveredTables = [];
    
    // Update card selection
    document.querySelectorAll('.source-card').forEach(card => {
        card.classList.remove('selected');
    });
    if (element) {
        element.classList.add('selected');
    }
    
    // Show detail section below
    const detailSection = document.getElementById('sourceDetailSection');
    detailSection.classList.add('visible');
    
    // Update header
    document.getElementById('selectedSourceTitle').textContent = 
        `${selectedSource.source_system_code} - ${selectedSource.source_system_name || ''}`;
    document.getElementById('selectedSourceInfo').textContent = 
        `${selectedSource.source_type} | ${selectedSource.host_name || 'N/A'} | DSN: ${selectedSource.odbc_dsn_name || 'N/A'}`;
    
    // Set default schema
    document.getElementById('schemaFilter').value = selectedSource.default_schema || 'dbo';
    
    // Reset table list
    document.getElementById('tableList').innerHTML = `
        <div class="empty-state">
            <p>Klicken Sie auf "Tabellen laden" um Tabellen zu entdecken</p>
        </div>
    `;
    document.getElementById('tableCount').textContent = '';
    document.getElementById('columnPreview').style.display = 'none';
    document.getElementById('jobCreationPanel').style.display = 'none';
    
    // Scroll to detail section
    detailSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeDetailSection() {
    document.getElementById('sourceDetailSection').classList.remove('visible');
    document.querySelectorAll('.source-card').forEach(card => {
        card.classList.remove('selected');
    });
    selectedSource = null;
}

// =============================================================================
// Table Discovery Functions
// =============================================================================

async function discoverTables() {
    if (!selectedSource) {
        showToast('Bitte erst Source System auswählen', 'error');
        return;
    }
    
    const schema = document.getElementById('schemaFilter').value || 'dbo';
    const container = document.getElementById('tableList');
    
    container.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            Verbinde zu ${selectedSource.source_system_code}...
        </div>
    `;
    
    try {
        const url = new URL(`${API_BASE_URL}/${selectedSource.source_system_id}/tables`);
        url.searchParams.set('schema', schema);
        
        const response = await fetch(url);
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        discoveredTables = result.tables || [];
        
        document.getElementById('tableCount').textContent = `(${discoveredTables.length})`;
        renderTables();
        
        showToast(`${discoveredTables.length} Tabellen gefunden`, 'success');
    } catch (error) {
        console.error('Discovery error:', error);
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Discovery fehlgeschlagen: ${error.message}</p>
            </div>
        `;
        showToast(`Fehler: ${error.message}`, 'error');
    }
}

function renderTables() {
    const container = document.getElementById('tableList');
    const searchTerm = document.getElementById('tableSearch').value.toLowerCase();
    
    const filteredTables = discoveredTables.filter(t => 
        t.table_name.toLowerCase().includes(searchTerm)
    );
    
    if (filteredTables.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>Keine Tabellen gefunden</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filteredTables.map(table => `
        <div class="table-item ${table.has_job ? 'has-job' : ''}" onclick="previewColumns('${escapeHtml(table.table_name)}')">
            <input type="checkbox" 
                   ${selectedTables.has(table.table_name) ? 'checked' : ''} 
                   onclick="toggleTableSelection(event, '${escapeHtml(table.table_name)}')">
            <span class="table-name">${escapeHtml(table.table_name)}</span>
            <span class="table-type">${table.table_type === 'BASE TABLE' ? 'Table' : 'View'}</span>
            ${table.has_job ? '<span class="job-indicator">✓ Job existiert</span>' : ''}
        </div>
    `).join('');
    
    updateJobCreationPanel();
}

function filterTables() {
    renderTables();
}

function toggleTableSelection(event, tableName) {
    event.stopPropagation();
    
    if (selectedTables.has(tableName)) {
        selectedTables.delete(tableName);
    } else {
        selectedTables.add(tableName);
    }
    
    updateJobCreationPanel();
}

function selectAllTables() {
    const searchTerm = document.getElementById('tableSearch').value.toLowerCase();
    const filteredTables = discoveredTables.filter(t => 
        t.table_name.toLowerCase().includes(searchTerm)
    );
    
    // Toggle: If all selected, deselect all; otherwise select all
    const allSelected = filteredTables.every(t => selectedTables.has(t.table_name));
    
    if (allSelected) {
        filteredTables.forEach(t => selectedTables.delete(t.table_name));
    } else {
        filteredTables.forEach(t => selectedTables.add(t.table_name));
    }
    
    renderTables();
}

function updateJobCreationPanel() {
    const panel = document.getElementById('jobCreationPanel');
    const countSpan = document.getElementById('selectedTableCount');
    
    if (selectedTables.size > 0) {
        panel.style.display = 'block';
        countSpan.textContent = selectedTables.size;
    } else {
        panel.style.display = 'none';
    }
}

// =============================================================================
// Column Preview Functions (Editierbar)
// =============================================================================

// Column Mappings speichern pro Tabelle (für editierte Werte)
let allColumnMappings = {};  // { "schema.tableName": [...mappings] }
let currentPreviewTable = null;  // Aktuell angezeigte Tabelle

async function previewColumns(tableName) {
    const preview = document.getElementById('columnPreview');
    const grid = document.getElementById('columnGrid');
    const schema = document.getElementById('schemaFilter').value || 'dbo';
    const fullTableName = `${schema}.${tableName}`;
    
    currentPreviewTable = fullTableName;
    
    document.getElementById('previewTableName').textContent = tableName;
    preview.style.display = 'block';
    
    // Prüfen ob wir schon Mappings für diese Tabelle haben
    if (allColumnMappings[fullTableName]) {
        renderColumnGrid(allColumnMappings[fullTableName], fullTableName);
        return;
    }
    
    grid.innerHTML = `
        <div class="loading" style="grid-column: span 4;">
            <div class="spinner"></div>
            Lade Spalten...
        </div>
    `;
    
    try {
        const url = new URL(`${API_BASE_URL}/${selectedSource.source_system_id}/tables/${tableName}/columns`);
        url.searchParams.set('schema', schema);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const columns = await response.json();
        
        // Column Mappings initialisieren und speichern
        // Inklusive TPT-spezifischer Felder aus META_DATATYPE_MAPPING
        allColumnMappings[fullTableName] = columns.map(col => ({
            source_column: col.column_name,
            target_column: col.column_name,
            source_type: col.data_type + (col.max_length ? `(${col.max_length})` : 
                         (col.precision ? `(${col.precision}${col.scale ? ',' + col.scale : ''})` : '')),
            target_type: col.td_data_type,
            tpt_schema_multiplier: col.tpt_schema_multiplier || 1,
            convert_template: col.convert_template || null
        }));
        
        renderColumnGrid(allColumnMappings[fullTableName], fullTableName);
    } catch (error) {
        console.error('Column preview error:', error);
        grid.innerHTML = `<div style="grid-column: span 4; color: red;">Fehler: ${error.message}</div>`;
    }
}

// Column Grid rendern (4 Spalten: Source Name, Target Name, Source Type, Target Type)
function renderColumnGrid(mappings, tableName) {
    const grid = document.getElementById('columnGrid');
    
    let html = `
        <div class="column-header">Source Column</div>
        <div class="column-header">Target Column</div>
        <div class="column-header">Source Type</div>
        <div class="column-header">Target Type</div>
    `;
    
    mappings.forEach((mapping, idx) => {
        html += `
            <div class="column-cell source">${escapeHtml(mapping.source_column)}</div>
            <div class="column-cell target">
                <input type="text" value="${escapeHtml(mapping.target_column)}" 
                       onchange="updateColumnMapping('${tableName}', ${idx}, 'target_column', this.value)"
                       style="width: 100%; padding: 4px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
            <div class="column-cell source">${escapeHtml(mapping.source_type)}</div>
            <div class="column-cell target">
                <input type="text" value="${escapeHtml(mapping.target_type)}" 
                       onchange="updateColumnMapping('${tableName}', ${idx}, 'target_type', this.value)"
                       style="width: 100%; padding: 4px; border: 1px solid #ddd; border-radius: 4px;">
            </div>
        `;
    });
    
    grid.innerHTML = html;
}

// Column Mapping Update
function updateColumnMapping(tableName, index, field, value) {
    if (allColumnMappings[tableName] && allColumnMappings[tableName][index]) {
        allColumnMappings[tableName][index][field] = value;
        console.log(`Updated mapping for ${tableName}[${index}]:`, allColumnMappings[tableName][index]);
    }
}

// =============================================================================
// TPT Job Creation (getrennte Funktionen)
// =============================================================================

// Tabellen + Job anlegen (ohne TPT Script zu generieren)
async function createTablesAndJob() {
    if (selectedTables.size === 0) {
        showToast('Bitte mindestens eine Tabelle auswählen', 'error');
        return;
    }
    
    const targetDatabase = document.getElementById('targetDatabase').value;
    const tptOperator = document.getElementById('tptOperator').value;
    const registerInMeta = document.getElementById('registerInMeta').checked;
    const schema = document.getElementById('schemaFilter').value || 'dbo';
    
    // Tabellen mit Column Mappings vorbereiten
    const tablesWithMappings = Array.from(selectedTables).map(tableName => {
        const fullName = `${schema}.${tableName}`;
        const mappings = allColumnMappings[fullName];
        
        // Column Mappings konvertieren zu API-Format
        let columnMappings = null;
        if (mappings) {
            columnMappings = mappings.map(m => ({
                source_column: m.source_column,
                target_column: m.target_column,
                source_type: m.source_type,
                target_type: m.target_type,
                tpt_schema_multiplier: m.tpt_schema_multiplier || 1,
                convert_expression: m.convert_template ? 
                    m.convert_template.replace('[{col}]', `[${m.source_column}]`) : null
            }));
        }
        
        return {
            table_name: fullName,
            column_mappings: columnMappings
        };
    });
    
    // Request mit tables_with_mappings (statt einfacher source_tables Liste)
    const request = {
        source_system_id: selectedSource.source_system_id,
        source_tables: [],  // Leer - wir verwenden tables_with_mappings
        tables_with_mappings: tablesWithMappings,
        target_database: targetDatabase,
        tpt_operator_type: tptOperator,
        register_in_meta_table: registerInMeta
    };
    
    // Disable button during creation
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Erstelle...`;
    
    try {
        const response = await fetch(`${API_BASE_URL}/tpt-jobs/bulk`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(request)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        showToast(
            `${result.successful} von ${result.total_requested} Jobs erstellt`,
            result.failed > 0 ? 'warning' : 'success'
        );
        
        console.log('Job creation results:', result);
        
        if (result.failed > 0) {
            result.results.filter(r => !r.success).forEach(r => {
                console.error('Failed:', r.message);
            });
        }
        
        // Speichere Job IDs für TPT Preview
        const createdJobIds = result.results
            .filter(r => r.success && r.etl_job_id)
            .map(r => r.etl_job_id);
        
        if (createdJobIds.length > 0) {
            // Zeige TPT Preview Button an
            document.getElementById('tptPreviewBtn').style.display = 'inline-block';
            document.getElementById('tptPreviewBtn').dataset.jobIds = JSON.stringify(createdJobIds);
        }
        
    } catch (error) {
        console.error('Job creation error:', error);
        showToast(`Fehler: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '📋 Tabellen + Job anlegen';
    }
}

// TPT Script anzeigen (für erstellten Job)
async function showTPTPreview() {
    const btn = document.getElementById('tptPreviewBtn');
    const jobIds = JSON.parse(btn.dataset.jobIds || '[]');
    
    if (jobIds.length === 0) {
        showToast('Zuerst einen Job erstellen', 'error');
        return;
    }
    
    // Für den ersten Job die Preview anzeigen
    const jobId = jobIds[0];
    
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Lade...`;
    
    try {
        const response = await fetch(`${window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`}/api/etl/jobs/${jobId}/tpt-preview`);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        // TPT Script in Modal oder collapsible section anzeigen
        showTPTScriptModal(result.tpt_script, result.job_name);
        
    } catch (error) {
        console.error('TPT Preview error:', error);
        showToast(`Fehler: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '📜 TPT Script anzeigen';
    }
}

// TPT Script Modal anzeigen
function showTPTScriptModal(script, jobName) {
    // Entferne bestehendes Modal falls vorhanden
    const existing = document.getElementById('tptScriptModal');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.id = 'tptScriptModal';
    modal.innerHTML = `
        <div class="modal-overlay" onclick="closeTPTScriptModal()">
            <div class="modal-content" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>📜 TPT Script: ${escapeHtml(jobName)}</h3>
                    <button class="btn btn-sm" onclick="closeTPTScriptModal()">✕</button>
                </div>
                <div class="modal-body">
                    <pre class="tpt-script-code">${escapeHtml(script)}</pre>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-sm" onclick="copyTPTScript()">📋 Kopieren</button>
                    <button class="btn btn-sm btn-outline" onclick="closeTPTScriptModal()">Schließen</button>
                </div>
            </div>
        </div>
    `;
    
    // Inline Styles für Modal
    const style = document.createElement('style');
    style.textContent = `
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.6);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal-content {
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 900px;
            max-height: 80vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        .modal-header {
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h3 {
            margin: 0;
        }
        .modal-body {
            flex: 1;
            overflow: auto;
            padding: 20px;
        }
        .tpt-script-code {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin: 0;
        }
        .modal-footer {
            padding: 15px 20px;
            border-top: 1px solid #eee;
            display: flex;
            gap: 10px;
            justify-content: flex-end;
        }
    `;
    
    document.head.appendChild(style);
    document.body.appendChild(modal);
    
    // Speichere Script global für Copy-Funktion
    window._currentTPTScript = script;
}

function closeTPTScriptModal() {
    const modal = document.getElementById('tptScriptModal');
    if (modal) modal.remove();
}

function copyTPTScript() {
    if (window._currentTPTScript) {
        navigator.clipboard.writeText(window._currentTPTScript).then(() => {
            showToast('TPT Script kopiert!', 'success');
        }).catch(() => {
            showToast('Kopieren fehlgeschlagen', 'error');
        });
    }
}

// =============================================================================
// Utility Functions
// =============================================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'success') {
    // Remove existing toasts
    document.querySelectorAll('.toast').forEach(t => t.remove());
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 5000);
}
