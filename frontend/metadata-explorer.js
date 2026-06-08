/**
 * Metadata Explorer JavaScript
 * ============================
 * 
 * Interaktive UI für Layer → Database → Table → Column Navigation
 * 
 * Autor: DWH MVP Team
 * Datum: 2026-03-18
 */

const API_BASE = (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api';

// Teradata Typcode → Klartext-Bezeichnung
function getTypeKlartext(dataType, length) {
    if (!dataType) return '-';
    const t = dataType.trim().toUpperCase();
    const lenStr = length ? `(${length})` : '';
    const map = {
        'I8':  'BIGINT',
        'I4':  'INTEGER',
        'I ':  'INTEGER',
        'I':   'INTEGER',
        'I2':  'SMALLINT',
        'I1':  'BYTEINT',
        'BO':  'BYTEINT',
        'F ':  'FLOAT',
        'F':   'FLOAT',
        'D ':  'DECIMAL',
        'D':   'DECIMAL',
        'N ':  'NUMBER',
        'N':   'NUMBER',
        'CF':  'CHAR',
        'CV':  'VARCHAR',
        'CO':  'CLOB',
        'BF':  'BYTE',
        'BV':  'VARBYTE',
        'DA':  'DATE',
        'AT':  'TIME',
        'AZ':  'TIME WITH TIME ZONE',
        'TS':  'TIMESTAMP',
        'TZ':  'TIMESTAMP WITH TIME ZONE',
        'SZ':  'TIMESTAMP WITH TIME ZONE',
        'JN':  'JSON',
        'XM':  'XML',
        'PS':  'PERIOD(DATE)',
        'PT':  'PERIOD(TIME)',
        'PM':  'PERIOD(TIMESTAMP)',
        'YR':  'INTERVAL YEAR',
        'YM':  'INTERVAL YEAR TO MONTH',
        'MO':  'INTERVAL MONTH',
        'DY':  'INTERVAL DAY',
        'DH':  'INTERVAL DAY TO HOUR',
        'DM':  'INTERVAL DAY TO MINUTE',
        'DS':  'INTERVAL DAY TO SECOND',
        'HR':  'INTERVAL HOUR',
        'HM':  'INTERVAL HOUR TO MINUTE',
        'HS':  'INTERVAL HOUR TO SECOND',
        'MI':  'INTERVAL MINUTE',
        'MS':  'INTERVAL MINUTE TO SECOND',
        'SC':  'INTERVAL SECOND',
        'UT':  'UDT',
    };
    const base = map[t];
    if (!base) return dataType;
    // Länge nur bei Typen anzeigen, die sie wirklich verwenden
    const withLen = ['CHAR', 'VARCHAR', 'BYTE', 'VARBYTE', 'DECIMAL', 'NUMBER', 'FLOAT', 'CLOB'];
    return withLen.includes(base) && length ? `${base}(${length})` : base;
}

// State
let currentLayerId = null;
let currentDatabaseId = null;
let currentDatabaseName = null;
let currentTableId = null;
let currentTableName = null;

// Cache
let layersCache = [];
let databasesCache = [];
let tablesCache = [];
let columnsCache = [];

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    loadLayers();
});

// ============================================================================
// Layer Functions
// ============================================================================

async function loadLayers() {
    try {
        // Lade Layers und Databases parallel
        const [layersRes, dbRes] = await Promise.all([
            fetch(`${API_BASE}/etl/layers`),
            fetch(`${API_BASE}/etl/databases`)
        ]);
        
        layersCache = await layersRes.json();
        databasesCache = await dbRes.json();
        
        renderLayerList();
    } catch (err) {
        console.error('Error loading layers:', err);
        document.getElementById('layerList').innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Fehler beim Laden</p>
            </div>
        `;
    }
}

function renderLayerList() {
    const container = document.getElementById('layerList');
    
    let html = '';
    
    for (const layer of layersCache) {
        const dbs = databasesCache.filter(d => d.layer_id === layer.layer_id);
        
        // Layer Header
        html += `
            <div class="nav-item layer-header" style="background: rgba(102,126,234,0.05); cursor: default;">
                <span class="name">
                    <span class="layer-badge layer-${layer.layer_code}">${layer.layer_code}</span>
                    ${layer.layer_name}
                </span>
                <span class="count">${dbs.length}</span>
            </div>
        `;
        
        // Databases unter diesem Layer
        for (const db of dbs) {
            html += `
                <div class="nav-item database-item ${currentDatabaseId === db.database_id ? 'active' : ''}" 
                     onclick="selectDatabase(${db.database_id}, '${db.database_name}')"
                     data-db-id="${db.database_id}">
                    <span class="name" style="padding-left: 15px;">
                        📂 ${db.database_name}
                    </span>
                    <span class="count">${db.table_count}</span>
                </div>
            `;
        }
    }
    
    container.innerHTML = html;
}

// ============================================================================
// Database/Table Functions
// ============================================================================

async function selectDatabase(databaseId, databaseName) {
    currentDatabaseId = databaseId;
    currentDatabaseName = databaseName;
    currentTableId = null;
    currentTableName = null;
    
    // Update active state in layer list
    document.querySelectorAll('.database-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.dbId) === databaseId);
    });
    
    // Show import panel
    document.getElementById('importPanel').style.display = 'block';
    
    // Load tables
    await loadTables(databaseId);
    
    // Clear column editor
    document.getElementById('columnEditor').innerHTML = `
        <div class="empty-state">
            <div class="icon">👈</div>
            <p>Wähle eine Tabelle</p>
        </div>
    `;
}

async function loadTables(databaseId) {
    const container = document.getElementById('tableList');
    container.innerHTML = `
        <div class="empty-state">
            <div class="spinner"></div>
            Lade Tabellen...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/etl/databases/${databaseId}/tables`);
        tablesCache = await response.json();
        
        renderTableList();
    } catch (err) {
        console.error('Error loading tables:', err);
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Fehler beim Laden</p>
            </div>
        `;
    }
}

function renderTableList() {
    const container = document.getElementById('tableList');
    
    if (tablesCache.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">📭</div>
                <p>Keine Tabellen vorhanden</p>
                <p style="font-size: 12px;">Nutze "Neue Tabelle importieren"</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    for (const table of tablesCache) {
        const histBadge = table.is_historized === 'Y' 
            ? `<span class="flag-badge flag-scd" title="Historisiert">${table.historization_type || 'HIST'}</span>` 
            : '';
        
        html += `
            <div class="table-item ${currentTableId === table.table_id ? 'active' : ''}"
                 onclick="selectTable(${table.table_id}, '${table.table_name}')"
                 data-table-id="${table.table_id}">
                <span class="table-name">
                    📋 ${table.table_name}
                    ${histBadge}
                </span>
                <span class="table-item-actions">
                    <span class="col-count">${table.column_count} Spalten</span>
                    <button class="btn-delete-table" title="Tabelle aus Metadaten löschen"
                            onclick="event.stopPropagation(); deleteTable(${table.table_id}, '${table.table_name}')">
                        🗑
                    </button>
                </span>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

async function deleteTable(tableId, tableName) {
    if (!confirm(`Tabelle "${tableName}" wirklich aus den Metadaten löschen?\n\nAlle Spalteninformationen werden ebenfalls gelöscht.`)) return;

    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const err = await response.json();
            alert('❌ Fehler: ' + (err.detail || 'Unbekannter Fehler'));
            return;
        }

        const result = await response.json();
        alert(`✅ Tabelle "${result.table_name}" gelöscht (${result.columns_deleted} Spalten entfernt).`);

        // Wenn die gelöschte Tabelle gerade ausgewählt war, Editor leeren
        if (currentTableId === tableId) {
            currentTableId = null;
            currentTableName = null;
            document.getElementById('columnEditor').innerHTML = `
                <div class="empty-state">
                    <div class="icon">👈</div>
                    <p>Wähle eine Tabelle</p>
                </div>
            `;
        }

        // Tabellenliste + Layer-Counts aktualisieren
        await loadTables(currentDatabaseId);
        await loadLayers();

    } catch (err) {
        console.error('Error deleting table:', err);
        alert('❌ Fehler beim Löschen: ' + err.message);
    }
}

// ============================================================================
// Table/Column Functions
// ============================================================================

async function selectTable(tableId, tableName) {
    currentTableId = tableId;
    currentTableName = tableName;
    
    // Update active state
    document.querySelectorAll('.table-item').forEach(el => {
        el.classList.toggle('active', parseInt(el.dataset.tableId) === tableId);
    });
    
    // Load columns
    await loadColumns(tableId);
}

async function loadColumns(tableId) {
    const container = document.getElementById('columnEditor');
    container.innerHTML = `
        <div class="empty-state">
            <div class="spinner"></div>
            Lade Spalten...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}/columns`);
        columnsCache = await response.json();
        
        renderColumnEditor();
    } catch (err) {
        console.error('Error loading columns:', err);
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Fehler beim Laden der Spalten</p>
            </div>
        `;
    }
}

function renderColumnEditor() {
    const container = document.getElementById('columnEditor');
    
    let html = `
        <div class="column-editor-header">
            <h3>📋 ${currentTableName} <span style="color: var(--text-secondary); font-weight: normal;">(${columnsCache.length} Spalten)</span></h3>
            <button class="btn-action btn-sync" onclick="syncTableColumns(${currentTableId})">
                🔄 Sync mit DB
            </button>
        </div>
    `;
    
    if (columnsCache.length === 0) {
        html += `
            <div class="empty-state">
                <div class="icon">📭</div>
                <p>Keine Spalten vorhanden</p>
                <p style="font-size: 12px;">Klicke "Sync mit DB" um Spalten zu importieren</p>
            </div>
        `;
    } else {
        html += `
            <div style="overflow-x: auto;">
                <table class="column-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Spaltenname</th>
                            <th>Typ</th>
                            <th>Klartext</th>
                            <th>Null</th>
                            <th>Flags</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const col of columnsCache) {
            const flags = [];
            if (col.is_business_key) flags.push('<span class="flag-badge flag-bk">BK</span>');
            if (col.is_technical_key) flags.push('<span class="flag-badge flag-tk">TK</span>');
            if (col.is_scd_column) flags.push(`<span class="flag-badge flag-scd">${col.scd_type || 'SCD'}</span>`);
            if (col.is_audit_column) flags.push('<span class="flag-badge flag-audit">Audit</span>');
            
            const typeDisplay = col.length ? `${col.data_type}(${col.length})` : col.data_type;
            const typePlain = getTypeKlartext(col.data_type, col.length);

            html += `
                <tr>
                    <td style="color: var(--text-secondary);">${col.position}</td>
                    <td><strong>${col.column_name}</strong></td>
                    <td class="column-type">${typeDisplay || '-'}</td>
                    <td class="column-type-plain">${typePlain}</td>
                    <td>${col.nullable ? '✓' : ''}</td>
                    <td class="column-flags">${flags.join('') || '-'}</td>
                </tr>
            `;
        }
        
        html += `
                    </tbody>
                </table>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// ============================================================================
// Import Table Functions
// ============================================================================

async function showImportModal() {
    if (!currentDatabaseId) {
        alert('Keine Datenbank ausgewählt');
        return;
    }
    
    document.getElementById('importModal').style.display = 'flex';
    document.getElementById('importModalTitle').textContent = `Tabelle importieren aus ${currentDatabaseName}`;
    document.getElementById('importModalBody').innerHTML = `
        <div class="empty-state">
            <div class="spinner"></div>
            Lade verfügbare Tabellen aus dbc...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/etl/databases/${currentDatabaseId}/dbc-tables`);
        const dbcTables = await response.json();
        
        // Filter: Nur Tabellen die noch nicht in META_TABLE sind
        const existingNames = tablesCache.map(t => t.table_name.toUpperCase());
        
        let html = `<ul class="import-table-list">`;
        
        for (const tbl of dbcTables) {
            const isImported = existingNames.includes(tbl.table_name.toUpperCase());
            
            html += `
                <li class="import-table-item ${isImported ? 'imported' : ''}">
                    <div>
                        <span class="tbl-name">${tbl.table_kind === 'View' ? '👁️' : '📋'} ${tbl.table_name}${tbl.table_kind === 'View' ? ' <span style="font-size:10px;color:var(--text-secondary)">(View)</span>' : ''}</span>
                        ${isImported ? '<span class="badge-imported">✓ bereits importiert</span>' : ''}
                        ${tbl.comment ? `<div style="font-size: 11px; color: var(--text-secondary);">${tbl.comment}</div>` : ''}
                    </div>
                    <button class="btn-import-single" onclick="importTable('${tbl.table_name}')">
                        ➕ Importieren
                    </button>
                </li>
            `;
        }
        
        if (dbcTables.length === 0) {
            html += `
                <div class="empty-state">
                    <div class="icon">📭</div>
                    <p>Keine Tabellen in ${currentDatabaseName} gefunden</p>
                </div>
            `;
        }
        
        html += `</ul>`;
        document.getElementById('importModalBody').innerHTML = html;
        
    } catch (err) {
        console.error('Error loading dbc tables:', err);
        document.getElementById('importModalBody').innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>Fehler beim Laden: ${err.message}</p>
            </div>
        `;
    }
}

function closeImportModal() {
    document.getElementById('importModal').style.display = 'none';
}

async function importTable(tableName) {
    if (!confirm(`Tabelle "${tableName}" mit allen Spalten importieren?`)) return;
    
    try {
        const response = await fetch(`${API_BASE}/etl/databases/${currentDatabaseId}/import-table`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ table_name: tableName })
        });
        
        const result = await response.json();
        
        if (result.error) {
            alert('❌ Fehler: ' + result.error);
            return;
        }
        
        alert(`✅ Tabelle "${result.table_name}" importiert!\n${result.columns_imported} Spalten hinzugefügt.`);
        
        closeImportModal();
        
        // Refresh table list and database counts
        await loadTables(currentDatabaseId);
        await loadLayers();  // Refresh counts
        
        // Select the new table
        selectTable(result.table_id, result.table_name);
        
    } catch (err) {
        console.error('Error importing table:', err);
        alert('❌ Fehler beim Importieren: ' + err.message);
    }
}

// ============================================================================
// Sync/Diff Functions
// ============================================================================

async function syncTableColumns(tableId) {
    document.getElementById('diffModal').style.display = 'flex';
    document.getElementById('diffModalTitle').textContent = `Spalten-Vergleich: ${currentTableName}`;
    document.getElementById('diffModalBody').innerHTML = `
        <div class="empty-state">
            <div class="spinner"></div>
            Vergleiche mit Datenbank...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}/columns/diff`);
        
        if (!response.ok) throw new Error('Fehler beim Laden des Vergleichs');
        
        const diff = await response.json();
        renderDiffModal(diff, tableId);
        
    } catch (err) {
        document.getElementById('diffModalBody').innerHTML = `
            <div class="empty-state">
                <div class="icon">❌</div>
                <p>${err.message}</p>
            </div>
        `;
    }
}

function renderDiffModal(diff, tableId) {
    let html = '';
    
    // Summary
    html += `
        <div class="diff-summary">
            <div class="diff-stat">
                <span class="diff-number">${diff.summary.total_in_dbc}</span>
                <span class="diff-label">In DB</span>
            </div>
            <div class="diff-stat">
                <span class="diff-number">${diff.summary.total_in_meta}</span>
                <span class="diff-label">In Meta</span>
            </div>
            <div class="diff-stat diff-added">
                <span class="diff-number">+${diff.summary.added_count}</span>
                <span class="diff-label">Neu</span>
            </div>
            <div class="diff-stat diff-removed">
                <span class="diff-number">-${diff.summary.removed_count}</span>
                <span class="diff-label">Gelöscht</span>
            </div>
            <div class="diff-stat diff-changed">
                <span class="diff-number">~${diff.summary.changed_count}</span>
                <span class="diff-label">Geändert</span>
            </div>
        </div>
    `;
    
    // No changes
    if (diff.summary.added_count === 0 && diff.summary.removed_count === 0 && diff.summary.changed_count === 0) {
        html += `
            <div class="success-message" style="padding: 20px; text-align: center; color: var(--success-color);">
                ✅ Metadaten sind aktuell - keine Änderungen erforderlich.
            </div>
        `;
        document.getElementById('diffModalBody').innerHTML = html;
        document.getElementById('diffModalFooter').innerHTML = `
            <button class="btn btn-secondary" onclick="closeDiffModal()">Schließen</button>
        `;
        return;
    }
    
    // Added columns
    if (diff.added.length > 0) {
        html += `<div class="diff-section"><h4>➕ Neue Spalten (${diff.added.length})</h4>`;
        html += '<table class="diff-table"><tr><th>Spalte</th><th>Typ</th><th>Länge</th></tr>';
        for (const col of diff.added) {
            html += `<tr class="diff-row-added">
                <td><strong>${col.column_name}</strong></td>
                <td>${col.column_type || '-'}</td>
                <td>${col.length || '-'}</td>
            </tr>`;
        }
        html += '</table></div>';
    }
    
    // Removed columns
    if (diff.removed.length > 0) {
        html += `<div class="diff-section"><h4>➖ Gelöschte Spalten (${diff.removed.length})</h4>`;
        html += '<table class="diff-table"><tr><th>Spalte</th><th>Typ</th></tr>';
        for (const col of diff.removed) {
            html += `<tr class="diff-row-removed">
                <td><strong>${col.column_name}</strong></td>
                <td>${col.data_type || '-'}</td>
            </tr>`;
        }
        html += '</table></div>';
    }
    
    // Changed columns
    if (diff.changed.length > 0) {
        html += `<div class="diff-section"><h4>🔄 Geänderte Spalten (${diff.changed.length})</h4>`;
        html += '<table class="diff-table"><tr><th>Spalte</th><th>Änderungen</th></tr>';
        for (const col of diff.changed) {
            html += `<tr class="diff-row-changed">
                <td><strong>${col.column_name}</strong></td>
                <td>${col.changes.join('<br>')}</td>
            </tr>`;
        }
        html += '</table></div>';
    }
    
    document.getElementById('diffModalBody').innerHTML = html;
    document.getElementById('diffModalFooter').innerHTML = `
        <button class="btn btn-secondary" onclick="closeDiffModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="doSyncColumns(${tableId})">🔄 Metadaten aktualisieren</button>
    `;
}

function closeDiffModal() {
    document.getElementById('diffModal').style.display = 'none';
}

async function doSyncColumns(tableId) {
    if (!confirm('Metadaten wirklich aktualisieren?\n\nNeue Spalten werden hinzugefügt, geänderte aktualisiert, gelöschte entfernt.')) return;
    
    document.getElementById('diffModalBody').innerHTML = `
        <div class="empty-state">
            <div class="spinner"></div>
            Aktualisiere Metadaten...
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}/columns/sync`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (result.error) {
            alert('❌ Fehler: ' + result.error);
            return;
        }
        
        let message = `✅ ${result.message}`;
        if (result.details.errors?.length > 0) {
            message += `\n\n⚠️ Fehler:\n${result.details.errors.join('\n')}`;
        }
        
        alert(message);
        closeDiffModal();
        
        // Refresh columns
        await loadColumns(tableId);
        
        // Refresh table list (column count changed)
        await loadTables(currentDatabaseId);
        
    } catch (err) {
        alert('❌ Fehler: ' + err.message);
    }
}
