// metadaita Metadaten Dashboard - ETL Jobs & Steps Viewer
const API_BASE = (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api';

let allJobs = [];
let allSteps = {};  // job_id -> steps[]
let selectedObject = null;
let currentTemplatePath = null;

document.addEventListener('DOMContentLoaded', () => {
    loadAllData();
});

// URL-Parameter-Support: ?jobId=123 oder ?jobId=123&stepId=456
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        jobId: params.get('jobId') ? parseInt(params.get('jobId')) : null,
        stepId: params.get('stepId') ? parseInt(params.get('stepId')) : null
    };
}

async function loadAllData() {
    const listEl = document.getElementById('objectList');
    listEl.innerHTML = '<li class="empty-state"><div class="spinner"></div>Lade Daten...</li>';
    
    try {
        // Lade alle Jobs
        const jobsRes = await fetch(`${API_BASE}/etl/jobs`);
        if (!jobsRes.ok) throw new Error('Fehler beim Laden der Jobs');
        allJobs = await jobsRes.json();
        
        // Lade Steps für jeden Job
        for (const job of allJobs) {
            try {
                const stepsRes = await fetch(`${API_BASE}/etl/jobs/${job.etl_job_id}/steps`);
                if (stepsRes.ok) {
                    const steps = await stepsRes.json();
                    // Sortiere nach step_order
                    allSteps[job.etl_job_id] = steps.sort((a, b) => a.step_order - b.step_order);
                }
            } catch (e) {
                console.warn(`Konnte Steps für Job ${job.etl_job_id} nicht laden:`, e);
                allSteps[job.etl_job_id] = [];
            }
        }
        
        renderObjectList();
        
        // URL-Parameter auswerten und automatisch Job/Step öffnen
        const urlParams = getUrlParams();
        if (urlParams.jobId) {
            // Finde den Job
            const job = allJobs.find(j => j.etl_job_id === urlParams.jobId);
            if (job) {
                if (urlParams.stepId && allSteps[urlParams.jobId]) {
                    // Step auswählen
                    const step = allSteps[urlParams.jobId].find(s => s.etl_job_step_id === urlParams.stepId);
                    if (step) {
                        selectObject('step', step.etl_job_step_id, urlParams.jobId);
                    } else {
                        // Fallback: Job anzeigen
                        selectObject('job', urlParams.jobId);
                    }
                } else {
                    // Nur Job anzeigen
                    selectObject('job', urlParams.jobId);
                }
                
                // Zum Element scrollen
                setTimeout(() => {
                    const selectedEl = document.querySelector('.object-list li.selected');
                    if (selectedEl) {
                        selectedEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
            }
        }
    } catch (err) {
        listEl.innerHTML = `<li class="error-message">❌ ${err.message}</li>`;
    }
}

function renderObjectList() {
    const listEl = document.getElementById('objectList');
    const filter = document.getElementById('filterType').value;
    
    let html = '';
    
    for (const job of allJobs) {
        if (filter === 'all' || filter === 'job') {
            const isSelected = selectedObject?.type === 'job' && selectedObject?.id === job.etl_job_id;
            html += `
                <li class="${isSelected ? 'selected' : ''}" onclick="selectJob(${job.etl_job_id})">
                    <span class="object-name">🚀 ${job.job_name}</span>
                    <span class="object-type job">${job.job_type}</span>
                </li>
            `;
        }
        
        // Steps für diesen Job
        if (filter === 'all' || filter === 'step') {
            const steps = allSteps[job.etl_job_id] || [];
            for (const step of steps) {
                const isSelected = selectedObject?.type === 'step' && selectedObject?.id === step.etl_job_step_id;
                html += `
                    <li class="${isSelected ? 'selected' : ''}" onclick="selectStep(${job.etl_job_id}, ${step.etl_job_step_id})" style="padding-left: 30px;">
                        <span class="object-name">
                            <span style="color: #667eea; font-weight: bold;">${step.step_order}.</span> 
                            ${step.step_name}
                        </span>
                        <span class="object-type step">${step.step_category}</span>
                    </li>
                `;
            }
        }
    }
    
    if (!html) {
        html = '<li class="empty-state">Keine Objekte gefunden.</li>';
    }
    
    listEl.innerHTML = html;
}

function filterObjects() {
    renderObjectList();
}

window.selectJob = function(jobId) {
    const job = allJobs.find(j => j.etl_job_id === jobId);
    if (!job) return;
    
    selectedObject = { type: 'job', id: jobId };
    renderObjectList();
    
    const steps = allSteps[jobId] || [];
    
    document.getElementById('detailTitle').textContent = job.job_name;
    
    let html = `
        <div class="detail-section">
            <h3>📋 Job Informationen</h3>
            <div class="detail-row"><span class="detail-label">Job ID:</span><span class="detail-value">${job.etl_job_id}</span></div>
            <div class="detail-row"><span class="detail-label">Name:</span><span class="detail-value">${job.job_name}</span></div>
            <div class="detail-row"><span class="detail-label">Typ:</span><span class="detail-value">${job.job_type}</span></div>
            <div class="detail-row"><span class="detail-label">Status:</span><span class="detail-value">${job.is_active === 'Y' ? '✅ Aktiv' : '❌ Inaktiv'}</span></div>
            <div class="detail-row"><span class="detail-label">Source Table:</span><span class="detail-value">${job.source_table_name || job.source_table_id || '-'}</span></div>
            <div class="detail-row"><span class="detail-label">Target Table:</span><span class="detail-value">${job.target_table_name || job.target_table_id || '-'}</span></div>
            <div class="detail-row"><span class="detail-label">Retry Count:</span><span class="detail-value">${job.retry_count || 3}</span></div>
            <div class="detail-row"><span class="detail-label">Timeout:</span><span class="detail-value">${job.timeout_seconds || 3600}s</span></div>
            <div class="detail-row"><span class="detail-label">Letzter Run:</span><span class="detail-value">${job.last_run_status || '-'} ${job.last_run_time ? '(' + new Date(job.last_run_time).toLocaleString('de-DE') + ')' : ''}</span></div>
        </div>
        
        <div class="detail-section">
            <h3>📊 Steps (${steps.length}) - Ausführungsreihenfolge</h3>
            ${steps.length === 0 ? '<p style="color: #999;">Keine Steps definiert.</p>' : ''}
            <ul class="steps-list">
    `;
    
    for (const step of steps) {
        const execution = step.sql_template_path 
            ? `📄 Template: ${step.sql_template_path}`
            : step.sql_inline 
                ? '📝 Inline SQL'
                : step.python_module 
                    ? `🐍 Python: ${step.python_module}.${step.python_function || 'run'}`
                    : '⚠️ Keine Ausführung definiert';
        
        html += `
            <li class="step-item" onclick="selectStep(${jobId}, ${step.etl_job_step_id})" style="cursor: pointer;">
                <div class="step-header">
                    <span class="step-order">${step.step_order}</span>
                    <span class="step-name">${step.step_name}</span>
                    <span class="step-category">${step.step_category}</span>
                </div>
                <div class="step-details">
                    ${execution}
                    ${step.is_critical === 'Y' ? ' | 🔴 Kritisch' : ''}
                    ${step.skip_on_empty === 'Y' ? ' | ⏭️ Skip wenn leer' : ''}
                </div>
            </li>
        `;
    }
    
    html += '</ul></div>';
    
    // Mapping Section mit Toggle
    html += `
        <div class="detail-section">
            <h3>
                🔗 Source → Target Mapping 
                <button class="btn-small btn-toggle-section" onclick="toggleMappingPanel(${jobId})">▶ Anzeigen</button>
            </h3>
            <div id="mappingPanel-${jobId}" class="mapping-panel" style="display: none;">
                <div class="mapping-loading">Lade Spalten...</div>
            </div>
        </div>
    `;
    
    document.getElementById('detailPanel').innerHTML = html;
}

window.selectStep = function(jobId, stepId) {
    const steps = allSteps[jobId] || [];
    const step = steps.find(s => s.etl_job_step_id === stepId);
    if (!step) return;
    
    const job = allJobs.find(j => j.etl_job_id === jobId);
    
    selectedObject = { type: 'step', id: stepId };
    renderObjectList();
    
    document.getElementById('detailTitle').textContent = step.step_name;
    
    let executionHtml = '';
    if (step.sql_template_path) {
        executionHtml = `
            <div class="detail-row"><span class="detail-label">Ausführung:</span><span class="detail-value">📄 SQL Template</span></div>
            <div class="detail-row"><span class="detail-label">Template Pfad:</span><span class="detail-value"><code>${step.sql_template_path}</code></span></div>
            <div style="display: flex; gap: 8px; margin-top: 10px;">
                <button class="view-template-btn" onclick="openTemplateEditor('${step.sql_template_path}')">📝 Template bearbeiten</button>
                <button class="view-template-btn" style="background: #43a047;" onclick="openRenderedTemplate('${step.sql_template_path}', ${step.etl_job_step_id})">▶️ Mit Parametern anzeigen</button>
            </div>
        `;
    } else if (step.sql_inline) {
        executionHtml = `
            <div class="detail-row"><span class="detail-label">Ausführung:</span><span class="detail-value">📝 Inline SQL</span></div>
            <div style="margin-top: 10px;">
                <strong>SQL Code:</strong>
                <div class="step-sql">${escapeHtml(step.sql_inline)}</div>
            </div>
        `;
    } else if (step.python_module) {
        executionHtml = `
            <div class="detail-row"><span class="detail-label">Ausführung:</span><span class="detail-value">🐍 Python</span></div>
            <div class="detail-row"><span class="detail-label">Modul:</span><span class="detail-value"><code>${step.python_module}</code></span></div>
            <div class="detail-row"><span class="detail-label">Funktion:</span><span class="detail-value"><code>${step.python_function || 'run'}</code></span></div>
        `;
    }
    
    let html = `
        <div class="detail-section">
            <h3>🔧 Step Informationen</h3>
            <div class="detail-row"><span class="detail-label">Step ID:</span><span class="detail-value">${step.etl_job_step_id}</span></div>
            <div class="detail-row"><span class="detail-label">Name:</span><span class="detail-value">${step.step_name}</span></div>
            <div class="detail-row"><span class="detail-label">Reihenfolge:</span><span class="detail-value"><strong>${step.step_order}</strong></span></div>
            <div class="detail-row"><span class="detail-label">Kategorie:</span><span class="detail-value">${step.step_category}</span></div>
            <div class="detail-row"><span class="detail-label">Gehört zu Job:</span><span class="detail-value">${job?.job_name || jobId}</span></div>
        </div>
        
        <div class="detail-section">
            <h3>⚙️ Ausführung</h3>
            ${executionHtml || '<p style="color: #999;">Keine Ausführung definiert.</p>'}
        </div>
        
        <div class="detail-section">
            <h3>🔒 Einstellungen</h3>
            <div class="detail-row"><span class="detail-label">Aktiv:</span><span class="detail-value">${step.is_active === 'Y' ? '✅ Ja' : '❌ Nein'}</span></div>
            <div class="detail-row"><span class="detail-label">Kritisch:</span><span class="detail-value">${step.is_critical === 'Y' ? '🔴 Ja (Abbruch bei Fehler)' : '🟢 Nein'}</span></div>
            <div class="detail-row"><span class="detail-label">Skip wenn leer:</span><span class="detail-value">${step.skip_on_empty === 'Y' ? '⏭️ Ja' : 'Nein'}</span></div>
            <div class="detail-row"><span class="detail-label">Rollback bei Fehler:</span><span class="detail-value">${step.rollback_on_error === 'Y' ? '↩️ Ja' : 'Nein'}</span></div>
        </div>
    `;
    
    if (step.parameters) {
        try {
            const params = typeof step.parameters === 'string' ? JSON.parse(step.parameters) : step.parameters;
            html += `
                <div class="detail-section">
                    <h3>📦 Parameter <button class="btn-small btn-add" onclick="addNewParameter(${step.etl_job_step_id})">➕ Neu</button></h3>
                    <div id="parameterForm-${step.etl_job_step_id}">
                        ${renderParameterForm(params, step.etl_job_step_id)}
                    </div>
                    <div style="margin-top: 15px; text-align: right;">
                        <button class="btn btn-primary" onclick="saveStepParameters(${step.etl_job_step_id})">💾 Parameter speichern</button>
                    </div>
                </div>
            `;
        } catch (e) {
            html += `
                <div class="detail-section">
                    <h3>📦 Parameter</h3>
                    <div class="step-sql">${escapeHtml(step.parameters)}</div>
                </div>
            `;
        }
    } else {
        html += `
            <div class="detail-section">
                <h3>📦 Parameter <button class="btn-small btn-add" onclick="addNewParameter(${step.etl_job_step_id})">➕ Neu</button></h3>
                <div id="parameterForm-${step.etl_job_step_id}">
                    <p style="color: #999;">Keine Parameter definiert.</p>
                </div>
                <div style="margin-top: 15px; text-align: right;">
                    <button class="btn btn-primary" onclick="saveStepParameters(${step.etl_job_step_id})">💾 Parameter speichern</button>
                </div>
            </div>
        `;
    }
    
    if (step.condition_sql) {
        html += `
            <div class="detail-section">
                <h3>❓ Bedingung (Condition SQL)</h3>
                <div class="step-sql">${escapeHtml(step.condition_sql)}</div>
            </div>
        `;
    }
    
    document.getElementById('detailPanel').innerHTML = html;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Template Editor Functions
// =============================================================================

window.openTemplateEditor = async function(templatePath) {
    currentTemplatePath = templatePath;
    document.getElementById('templateModalTitle').textContent = templatePath.split('/').pop();
    document.getElementById('templatePath').textContent = templatePath;
    document.getElementById('templateEditor').value = 'Lade Template...';
    document.getElementById('templateModal').style.display = 'block';
    
    try {
        const response = await fetch(`${API_BASE}/etl/templates/${encodeURIComponent(templatePath)}`);
        if (!response.ok) throw new Error('Fehler beim Laden des Templates');
        const data = await response.json();
        
        if (!data.exists) {
            document.getElementById('templateEditor').value = '-- Template existiert noch nicht.\n-- Erstelle hier den SQL Code:';
        } else {
            document.getElementById('templateEditor').value = data.content;
        }
    } catch (err) {
        document.getElementById('templateEditor').value = `-- Fehler: ${err.message}`;
    }
}

window.closeTemplateModal = function() {
    document.getElementById('templateModal').style.display = 'none';
    currentTemplatePath = null;
}

window.saveTemplate = async function() {
    if (!currentTemplatePath) return;
    
    const content = document.getElementById('templateEditor').value;
    
    try {
        const response = await fetch(`${API_BASE}/etl/templates/${encodeURIComponent(currentTemplatePath)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        
        if (!response.ok) throw new Error('Fehler beim Speichern');
        
        alert('✅ Template erfolgreich gespeichert!');
        closeTemplateModal();
    } catch (err) {
        alert('❌ Fehler beim Speichern: ' + err.message);
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('templateModal');
    if (event.target === modal) {
        closeTemplateModal();
    }
}

// =============================================================================
// Rendered Template Viewer
// =============================================================================

window.openRenderedTemplate = async function(templatePath, stepId) {
    // Finde den Step um die Parameter zu bekommen
    let stepParams = {};
    for (const jobId in allSteps) {
        const step = allSteps[jobId].find(s => s.etl_job_step_id === stepId);
        if (step && step.parameters) {
            try {
                stepParams = typeof step.parameters === 'string' 
                    ? JSON.parse(step.parameters) 
                    : step.parameters;
            } catch (e) {
                console.warn('Konnte Parameter nicht parsen:', e);
            }
            break;
        }
    }
    
    currentTemplatePath = templatePath;
    document.getElementById('templateModalTitle').textContent = '▶️ ' + templatePath.split('/').pop() + ' (gerendert)';
    document.getElementById('templatePath').innerHTML = `<strong>Pfad:</strong> ${templatePath}<br><strong>Parameter:</strong> <code>${JSON.stringify(stepParams)}</code>`;
    document.getElementById('templateEditor').value = 'Rendere Template...';
    document.getElementById('templateEditor').readOnly = true;
    document.getElementById('templateModal').style.display = 'block';
    
    // Verstecke Speichern-Button bei gerendertem Template
    const saveBtn = document.querySelector('.modal-footer .btn-primary');
    if (saveBtn) saveBtn.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/etl/templates/${encodeURIComponent(templatePath)}/render`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parameters: stepParams })
        });
        
        if (!response.ok) throw new Error('Fehler beim Rendern des Templates');
        const data = await response.json();
        
        let headerInfo = '';
        if (data.missing_parameters && data.missing_parameters.length > 0) {
            headerInfo = `-- ⚠️ FEHLENDE PARAMETER: ${data.missing_parameters.join(', ')}\n`;
            headerInfo += `-- Diese Parameter werden vom Orchestrator zur Laufzeit generiert\n`;
            headerInfo += `-- (z.B. aus hash_columns, select_columns Listen)\n`;
            headerInfo += `-- ${'─'.repeat(60)}\n\n`;
        }
        
        if (!data.success) {
            document.getElementById('templateEditor').value = headerInfo + data.rendered_sql;
            document.getElementById('templatePath').innerHTML = `<strong>Pfad:</strong> ${templatePath}<br><strong>Status:</strong> <span style="color: #f39c12;">⚠️ Teilweise gerendert</span><br><strong>Parameter:</strong> <code style="font-size: 11px; word-break: break-all;">${JSON.stringify(stepParams)}</code>`;
        } else {
            document.getElementById('templateEditor').value = data.rendered_sql;
            document.getElementById('templatePath').innerHTML = `<strong>Pfad:</strong> ${templatePath}<br><strong>Status:</strong> <span style="color: #27ae60;">✅ Vollständig gerendert</span><br><strong>Parameter:</strong> <code style="font-size: 11px; word-break: break-all;">${JSON.stringify(stepParams)}</code>`;
        }
    } catch (err) {
        document.getElementById('templateEditor').value = `-- Fehler: ${err.message}`;
    }
}

// Überschreibe closeTemplateModal um Editor-State zurückzusetzen
const originalCloseTemplateModal = window.closeTemplateModal;
window.closeTemplateModal = function() {
    document.getElementById('templateModal').style.display = 'none';
    document.getElementById('templateEditor').readOnly = false;
    currentTemplatePath = null;
    
    // Zeige Speichern-Button wieder
    const saveBtn = document.querySelector('.modal-footer .btn-primary');
    if (saveBtn) saveBtn.style.display = 'inline-block';
}

// =============================================================================
// Parameter Form Functions
// =============================================================================

// Speicher für aktuelle Parameter pro Step
let stepParametersCache = {};

function renderParameterForm(params, stepId) {
    stepParametersCache[stepId] = JSON.parse(JSON.stringify(params)); // Deep copy
    
    let html = '<div class="param-form">';
    
    for (const [key, value] of Object.entries(params)) {
        html += renderParameterField(key, value, stepId, [key]);
    }
    
    html += '</div>';
    return html;
}

function renderParameterField(key, value, stepId, path) {
    const pathStr = path.join('.');
    const isArray = Array.isArray(value);
    const isObject = typeof value === 'object' && value !== null && !isArray;
    
    let typeIcon = '📝';
    if (typeof value === 'number') typeIcon = '#️⃣';
    else if (typeof value === 'boolean') typeIcon = '☑️';
    else if (isArray) typeIcon = '📋';
    else if (isObject) typeIcon = '📁';
    
    let html = `<div class="param-field" data-path="${pathStr}">`;
    html += `<div class="param-header">`;
    html += `<span class="param-type-icon">${typeIcon}</span>`;
    html += `<span class="param-key">${key}</span>`;
    
    if (isArray) {
        html += `<span class="param-count">(${value.length} Einträge)</span>`;
        html += `<button class="btn-tiny btn-toggle" onclick="toggleArrayExpand(this)">▼</button>`;
    }
    
    html += `<button class="btn-tiny btn-delete" onclick="deleteParameter(${stepId}, '${pathStr}')" title="Löschen">🗑</button>`;
    html += `</div>`;
    
    if (isArray) {
        html += `<div class="param-array-container">`;
        html += `<div class="param-array">`;
        value.forEach((item, index) => {
            const needsTextarea = typeof item === 'string' && (item.length > 50 || item.includes(',') || item.includes('('));
            html += `<div class="param-array-item">`;
            if (needsTextarea) {
                html += `<textarea class="param-input param-textarea" data-path="${pathStr}.${index}" onchange="updateParameterValue(${stepId}, '${pathStr}.${index}', this.value)">${escapeHtml(item)}</textarea>`;
            } else if (typeof item === 'object') {
                html += `<span class="param-object-preview">${JSON.stringify(item)}</span>`;
            } else {
                html += `<input type="text" class="param-input" data-path="${pathStr}.${index}" value="${escapeHtml(String(item))}" onchange="updateParameterValue(${stepId}, '${pathStr}.${index}', this.value)">`;
            }
            html += `<button class="btn-tiny btn-delete" onclick="deleteArrayItem(${stepId}, '${pathStr}', ${index})" title="Entfernen">−</button>`;
            html += `</div>`;
        });
        html += `</div>`;
        html += `<button class="btn-small btn-add-item" onclick="addArrayItem(${stepId}, '${pathStr}')">+ Eintrag hinzufügen</button>`;
        html += `</div>`;
    } else if (isObject) {
        html += `<div class="param-object">`;
        for (const [subKey, subValue] of Object.entries(value)) {
            html += renderParameterField(subKey, subValue, stepId, [...path, subKey]);
        }
        html += `</div>`;
    } else if (typeof value === 'boolean') {
        html += `<input type="checkbox" class="param-checkbox" ${value ? 'checked' : ''} onchange="updateParameterValue(${stepId}, '${pathStr}', this.checked)">`;
    } else {
        const needsTextarea = typeof value === 'string' && (value.length > 80 || value.includes('\n'));
        if (needsTextarea) {
            html += `<textarea class="param-input param-textarea" onchange="updateParameterValue(${stepId}, '${pathStr}', this.value)">${escapeHtml(String(value))}</textarea>`;
        } else {
            html += `<input type="${typeof value === 'number' ? 'number' : 'text'}" class="param-input" value="${escapeHtml(String(value))}" onchange="updateParameterValue(${stepId}, '${pathStr}', this.value, '${typeof value}')">`;
        }
    }
    
    html += `</div>`;
    return html;
}

window.toggleArrayExpand = function(btn) {
    const container = btn.closest('.param-field').querySelector('.param-array-container');
    if (container.style.display === 'none') {
        container.style.display = 'block';
        btn.textContent = '▼';
    } else {
        container.style.display = 'none';
        btn.textContent = '▶';
    }
}

window.updateParameterValue = function(stepId, pathStr, value, originalType) {
    const path = pathStr.split('.');
    let obj = stepParametersCache[stepId];
    
    for (let i = 0; i < path.length - 1; i++) {
        const key = isNaN(path[i]) ? path[i] : parseInt(path[i]);
        obj = obj[key];
    }
    
    const lastKey = isNaN(path[path.length - 1]) ? path[path.length - 1] : parseInt(path[path.length - 1]);
    
    // Typ-Konvertierung
    if (originalType === 'number') {
        obj[lastKey] = parseFloat(value) || 0;
    } else if (value === 'true') {
        obj[lastKey] = true;
    } else if (value === 'false') {
        obj[lastKey] = false;
    } else {
        obj[lastKey] = value;
    }
}

window.deleteParameter = function(stepId, pathStr) {
    if (!confirm(`Parameter "${pathStr}" wirklich löschen?`)) return;
    
    const path = pathStr.split('.');
    let obj = stepParametersCache[stepId];
    
    for (let i = 0; i < path.length - 1; i++) {
        obj = obj[path[i]];
    }
    
    delete obj[path[path.length - 1]];
    refreshParameterForm(stepId);
}

window.deleteArrayItem = function(stepId, pathStr, index) {
    const path = pathStr.split('.');
    let obj = stepParametersCache[stepId];
    
    for (const key of path) {
        obj = obj[isNaN(key) ? key : parseInt(key)];
    }
    
    obj.splice(index, 1);
    refreshParameterForm(stepId);
}

window.addArrayItem = function(stepId, pathStr) {
    const path = pathStr.split('.');
    let obj = stepParametersCache[stepId];
    
    for (const key of path) {
        obj = obj[isNaN(key) ? key : parseInt(key)];
    }
    
    obj.push('');
    refreshParameterForm(stepId);
}

window.addNewParameter = function(stepId) {
    const key = prompt('Name des neuen Parameters:');
    if (!key) return;
    
    if (!stepParametersCache[stepId]) {
        stepParametersCache[stepId] = {};
    }
    
    const typeChoice = prompt('Typ wählen:\n1 = Text\n2 = Zahl\n3 = Boolean\n4 = Array (Liste)', '1');
    
    switch (typeChoice) {
        case '2':
            stepParametersCache[stepId][key] = 0;
            break;
        case '3':
            stepParametersCache[stepId][key] = false;
            break;
        case '4':
            stepParametersCache[stepId][key] = [];
            break;
        default:
            stepParametersCache[stepId][key] = '';
    }
    
    refreshParameterForm(stepId);
}

function refreshParameterForm(stepId) {
    const formContainer = document.getElementById(`parameterForm-${stepId}`);
    if (formContainer && stepParametersCache[stepId]) {
        formContainer.innerHTML = renderParameterForm(stepParametersCache[stepId], stepId);
    }
}

window.saveStepParameters = async function(stepId) {
    const params = stepParametersCache[stepId];
    
    if (!params) {
        alert('Keine Parameter zum Speichern.');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/etl/steps/${stepId}/parameters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parameters: params })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Fehler beim Speichern');
        }
        
        // Update local cache
        for (const jobId in allSteps) {
            const step = allSteps[jobId].find(s => s.etl_job_step_id === stepId);
            if (step) {
                step.parameters = JSON.stringify(params);
                break;
            }
        }
        
        alert('✅ Parameter erfolgreich gespeichert!');
    } catch (err) {
        alert('❌ Fehler beim Speichern: ' + err.message);
    }
}

// =============================================================================
// Source/Target Mapping Functions
// =============================================================================

let mappingCache = {};  // jobId -> mapping data

window.toggleMappingPanel = async function(jobId) {
    const panel = document.getElementById(`mappingPanel-${jobId}`);
    const btn = panel.previousElementSibling?.querySelector('.btn-toggle-section');
    
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        if (btn) btn.textContent = '▼ Verbergen';
        
        // Lade Mapping wenn noch nicht im Cache
        if (!mappingCache[jobId]) {
            await loadMappingData(jobId);
        } else {
            renderMappingPanel(jobId);
        }
    } else {
        panel.style.display = 'none';
        if (btn) btn.textContent = '▶ Anzeigen';
    }
}

async function loadMappingData(jobId) {
    const panel = document.getElementById(`mappingPanel-${jobId}`);
    panel.innerHTML = '<div class="mapping-loading"><div class="spinner"></div> Lade Spalten...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/etl/jobs/${jobId}/mapping`);
        if (!response.ok) throw new Error('Mapping-Daten nicht verfügbar');
        
        mappingCache[jobId] = await response.json();
        renderMappingPanel(jobId);
    } catch (err) {
        panel.innerHTML = `<div class="error-message">❌ ${err.message}</div>`;
    }
}

function renderMappingPanel(jobId) {
    const mapping = mappingCache[jobId];
    const panel = document.getElementById(`mappingPanel-${jobId}`);
    
    if (!mapping) {
        panel.innerHTML = '<div class="error-message">Keine Mapping-Daten</div>';
        return;
    }
    
    let html = '<div class="mapping-container">';
    
    // Source Table
    html += '<div class="mapping-table source-table">';
    html += `<div class="mapping-table-header">
        <span class="table-icon">📥</span>
        <span class="table-name">${mapping.source?.full_name || 'Keine Source'}</span>
        <span class="column-count">${mapping.source?.columns?.length || 0} Spalten</span>
        ${mapping.source?.table_id ? `<button class="btn-refresh-meta" onclick="showColumnDiff(${mapping.source.table_id}, 'source')" title="Metadaten aktualisieren">🔄</button>` : ''}
    </div>`;
    
    if (mapping.source?.columns?.length) {
        html += '<div class="mapping-columns">';
        for (const col of mapping.source.columns) {
            const badges = [];
            if (col.is_business_key) badges.push('<span class="col-badge badge-bk">BK</span>');
            if (col.is_technical_key) badges.push('<span class="col-badge badge-tk">TK</span>');
            if (col.is_audit_column) badges.push('<span class="col-badge badge-audit">Audit</span>');
            
            html += `
                <div class="mapping-column" draggable="true" data-column="${col.column_name}">
                    <span class="col-name">${col.column_name}</span>
                    <span class="col-type">${col.data_type || ''}${col.length ? `(${col.length})` : ''}</span>
                    ${badges.join('')}
                </div>
            `;
        }
        html += '</div>';
    } else {
        html += '<div class="no-columns">Keine Spalten gefunden</div>';
    }
    html += '</div>';
    
    // Arrow
    html += '<div class="mapping-arrow">→</div>';
    
    // Target Table
    html += '<div class="mapping-table target-table">';
    html += `<div class="mapping-table-header">
        <span class="table-icon">📤</span>
        <span class="table-name">${mapping.target?.full_name || 'Kein Target'}</span>
        <span class="column-count">${mapping.target?.columns?.length || 0} Spalten</span>
        ${mapping.target?.table_id ? `<button class="btn-refresh-meta" onclick="showColumnDiff(${mapping.target.table_id}, 'target')" title="Metadaten aktualisieren">🔄</button>` : ''}
    </div>`;
    
    if (mapping.target?.columns?.length) {
        html += '<div class="mapping-columns">';
        for (const col of mapping.target.columns) {
            const badges = [];
            if (col.is_business_key) badges.push('<span class="col-badge badge-bk">BK</span>');
            if (col.is_technical_key) badges.push('<span class="col-badge badge-tk">TK</span>');
            if (col.is_scd_column) badges.push(`<span class="col-badge badge-scd">${col.scd_type || 'SCD'}</span>`);
            if (col.is_audit_column) badges.push('<span class="col-badge badge-audit">Audit</span>');
            
            html += `
                <div class="mapping-column" data-column="${col.column_name}">
                    <span class="col-name">${col.column_name}</span>
                    <span class="col-type">${col.data_type || ''}${col.length ? `(${col.length})` : ''}</span>
                    ${badges.join('')}
                </div>
            `;
        }
        html += '</div>';
    } else {
        html += '<div class="no-columns">Keine Spalten gefunden</div>';
    }
    html += '</div>';
    
    html += '</div>';  // mapping-container
    
    // Legende
    html += `
        <div class="mapping-legend">
            <span class="col-badge badge-bk">BK</span> Business Key
            <span class="col-badge badge-tk">TK</span> Technical Key
            <span class="col-badge badge-scd">SCD</span> SCD-Spalte
            <span class="col-badge badge-audit">Audit</span> Audit-Spalte
        </div>
    `;
    
    panel.innerHTML = html;
}

// =============================================================================
// Column Metadata Diff & Sync Functions
// =============================================================================

let currentDiffTableId = null;

window.showColumnDiff = async function(tableId, tableType) {
    currentDiffTableId = tableId;
    
    // Erstelle Modal falls noch nicht vorhanden
    if (!document.getElementById('diffModal')) {
        const modalHtml = `
            <div id="diffModal" class="modal">
                <div class="modal-content modal-large">
                    <div class="modal-header">
                        <h2 id="diffModalTitle">Spalten-Vergleich</h2>
                        <button class="modal-close" onclick="closeDiffModal()">&times;</button>
                    </div>
                    <div class="modal-body" id="diffModalBody">
                        <div class="mapping-loading"><div class="spinner"></div> Vergleiche mit Datenbank...</div>
                    </div>
                    <div class="modal-footer" id="diffModalFooter">
                        <button class="btn btn-secondary" onclick="closeDiffModal()">Schließen</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    document.getElementById('diffModal').style.display = 'block';
    document.getElementById('diffModalBody').innerHTML = '<div class="mapping-loading"><div class="spinner"></div> Vergleiche mit Datenbank...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}/columns/diff`);
        if (!response.ok) throw new Error('Fehler beim Laden des Vergleichs');
        
        const diff = await response.json();
        renderDiffModal(diff);
    } catch (err) {
        document.getElementById('diffModalBody').innerHTML = `<div class="error-message">❌ ${err.message}</div>`;
    }
}

function renderDiffModal(diff) {
    document.getElementById('diffModalTitle').textContent = `Spalten-Vergleich: ${diff.database_name}.${diff.table_name}`;
    
    let html = '';
    
    // Zusammenfassung
    html += `
        <div class="diff-summary">
            <div class="diff-stat">
                <span class="diff-number">${diff.summary.total_in_dbc}</span>
                <span class="diff-label">Spalten in DB</span>
            </div>
            <div class="diff-stat">
                <span class="diff-number">${diff.summary.total_in_meta}</span>
                <span class="diff-label">In Metadaten</span>
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
    
    // Keine Änderungen
    if (diff.summary.added_count === 0 && diff.summary.removed_count === 0 && diff.summary.changed_count === 0) {
        html += '<div class="success-message">✅ Metadaten sind aktuell - keine Änderungen erforderlich.</div>';
        document.getElementById('diffModalBody').innerHTML = html;
        document.getElementById('diffModalFooter').innerHTML = `
            <button class="btn btn-secondary" onclick="closeDiffModal()">Schließen</button>
        `;
        return;
    }
    
    // Neue Spalten
    if (diff.added.length > 0) {
        html += '<div class="diff-section"><h4>➕ Neue Spalten (in DB, nicht in Metadaten)</h4>';
        html += '<table class="diff-table"><tr><th>Spalte</th><th>Typ</th><th>Länge</th><th>Position</th></tr>';
        for (const col of diff.added) {
            html += `<tr class="diff-row-added">
                <td><strong>${col.column_name}</strong></td>
                <td>${col.column_type || '-'}</td>
                <td>${col.length || '-'}</td>
                <td>${col.position}</td>
            </tr>`;
        }
        html += '</table></div>';
    }
    
    // Gelöschte Spalten
    if (diff.removed.length > 0) {
        html += '<div class="diff-section"><h4>➖ Gelöschte Spalten (in Metadaten, nicht mehr in DB)</h4>';
        html += '<table class="diff-table"><tr><th>Spalte</th><th>Typ</th><th>Position</th></tr>';
        for (const col of diff.removed) {
            html += `<tr class="diff-row-removed">
                <td><strong>${col.column_name}</strong></td>
                <td>${col.data_type || '-'}</td>
                <td>${col.position}</td>
            </tr>`;
        }
        html += '</table></div>';
    }
    
    // Geänderte Spalten
    if (diff.changed.length > 0) {
        html += '<div class="diff-section"><h4>🔄 Geänderte Spalten</h4>';
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
    
    // Footer mit Sync-Button
    document.getElementById('diffModalFooter').innerHTML = `
        <button class="btn btn-secondary" onclick="closeDiffModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="syncColumns(${diff.table_id})">🔄 Metadaten aktualisieren</button>
    `;
}

window.closeDiffModal = function() {
    const modal = document.getElementById('diffModal');
    if (modal) modal.style.display = 'none';
    currentDiffTableId = null;
}

window.syncColumns = async function(tableId) {
    if (!confirm('Metadaten wirklich aktualisieren?\n\nNeue Spalten werden hinzugefügt, geänderte aktualisiert.')) return;
    
    document.getElementById('diffModalBody').innerHTML = '<div class="mapping-loading"><div class="spinner"></div> Aktualisiere Metadaten...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/etl/tables/${tableId}/columns/sync`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Fehler beim Synchronisieren');
        
        const result = await response.json();
        
        let message = `✅ ${result.message}`;
        if (result.details.errors?.length > 0) {
            message += `\n\n⚠️ Fehler:\n${result.details.errors.join('\n')}`;
        }
        
        alert(message);
        closeDiffModal();
        
        // Mapping-Cache leeren und neu laden
        mappingCache = {};
        
    } catch (err) {
        alert('❌ Fehler: ' + err.message);
    }
}
