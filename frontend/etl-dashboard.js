/**
 * ETL Orchestrator Dashboard - Frontend Logic
 * ===========================================
 * 
 * Interaktives Dashboard für ETL Job Monitoring & Execution
 * 
 * Features:
 * - Real-time Stats
 * - Job List mit Execute-Button
 * - Run History mit Details
 * - Auto-Refresh
 * 
 * Autor: DWH MVP Team
 * Datum: 2026-01-19
 */

// Configuration (konfigurierbar via config.js)
const API_BASE_URL = (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api/etl';
const AUTO_REFRESH_INTERVAL = 30000; // 30 Sekunden

// State
let autoRefreshTimer = null;
let currentJobs = [];
let currentRuns = [];
let pendingExecutionSteps = null;
let pendingExecutionJobId = null;
let pendingExecutionJobName = null;
let initialLoadMode = false;

// =============================================================================
// Helper Functions
// =============================================================================

function escapeQuotes(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

/**
 * Check URL for jobId parameter and open job detail modal
 * Usage: etl-dashboard.html?jobId=4&jobName=load_ContactType
 */
async function checkUrlForJobId() {
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get('jobId');
    const jobName = params.get('jobName') || `Job #${jobId}`;
    
    if (jobId) {
        // Wait a bit for DOM and data to load
        setTimeout(() => {
            console.log(`Opening job from URL: ${jobId} - ${jobName}`);
            showJobDetail(parseInt(jobId), decodeURIComponent(jobName));
            
            // Clear URL parameters
            window.history.replaceState({}, document.title, window.location.pathname);
        }, 500);
    }
}

// =============================================================================
// Initialization
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('ETL Dashboard initialized');
    
    // Initial Load
    loadDashboard();
    
    // Check for URL parameter to open job directly
    checkUrlForJobId();
    
    // Event Listeners
    document.getElementById('activeOnlyFilter').addEventListener('change', refreshJobs);
    
    // Auto-Refresh starten
    startAutoRefresh();
});

// =============================================================================
// Dashboard Loading
// =============================================================================

async function loadDashboard() {
    await Promise.all([
        loadStats(),
        loadJobs(),
        loadRecentRuns()
    ]);
    updateLastRefreshTime();
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/dashboard/stats`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const stats = await response.json();
        renderStats(stats);
    } catch (error) {
        console.error('Error loading stats:', error);
        document.getElementById('statsGrid').innerHTML = `
            <div class="error-message">Failed to load statistics: ${error.message}</div>
        `;
    }
}

async function loadJobs() {
    const activeOnly = document.getElementById('activeOnlyFilter').checked;
    
    try {
        const response = await fetch(`${API_BASE_URL}/jobs?active_only=${activeOnly}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        currentJobs = await response.json();
        renderJobs(currentJobs);
    } catch (error) {
        console.error('Error loading jobs:', error);
        document.getElementById('jobsTable').innerHTML = `
            <div class="error-message">Failed to load jobs: ${error.message}</div>
        `;
    }
}

async function loadRecentRuns() {
    try {
        const response = await fetch(`${API_BASE_URL}/runs?limit=20`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        currentRuns = await response.json();
        renderRuns(currentRuns);
    } catch (error) {
        console.error('Error loading runs:', error);
        document.getElementById('runsTable').innerHTML = `
            <div class="error-message">Failed to load runs: ${error.message}</div>
        `;
    }
}

// =============================================================================
// Rendering Functions
// =============================================================================

function renderStats(stats) {
    const successRate = stats.success_rate_24h !== null 
        ? stats.success_rate_24h.toFixed(1) + '%' 
        : 'N/A';
    
    const html = `
        <div class="stat-card">
            <div class="stat-label">Total Jobs</div>
            <div class="stat-value">${stats.total_jobs}</div>
        </div>
        <div class="stat-card success">
            <div class="stat-label">Active Jobs</div>
            <div class="stat-value">${stats.active_jobs}</div>
        </div>
        <div class="stat-card" style="border-left-color: #2196F3;">
            <div class="stat-label">Running Now</div>
            <div class="stat-value">${stats.running_jobs}</div>
        </div>
        <div class="stat-card error">
            <div class="stat-label">Failed (24h)</div>
            <div class="stat-value">${stats.failed_runs_24h}</div>
        </div>
        <div class="stat-card success">
            <div class="stat-label">Success Rate (24h)</div>
            <div class="stat-value" style="font-size: 2em;">${successRate}</div>
        </div>
    `;
    
    document.getElementById('statsGrid').innerHTML = html;
}

function renderJobs(jobs) {
    if (jobs.length === 0) {
        document.getElementById('jobsTable').innerHTML = '<p>No jobs found</p>';
        return;
    }
    
    const rows = jobs.map(job => {
        // Trim Leerzeichen von is_active (Teradata CHAR Felder haben trailing spaces)
        const isActiveRaw = job.is_active || '';
        const isActive = isActiveRaw.trim() === 'Y';
        const statusClass = isActive ? 'success' : 'inactive';
        const statusText = isActive ? 'Active' : 'Inactive';
        
        const lastRunBadge = job.last_run_status 
            ? `<span class="status-badge ${job.last_run_status.trim().toLowerCase()}">${job.last_run_status.trim()}</span>`
            : '<span style="color: #999;">Never run</span>';
        
        const lastRunTime = job.last_run_time 
            ? formatDateTime(job.last_run_time)
            : '-';
        
        // Check ob ein Run gerade läuft
        const isRunning = job.last_run_status && job.last_run_status.trim() === 'RUNNING';
        
        return `
            <tr>
                <td>${job.etl_job_id}</td>
                <td><strong>${job.job_name}</strong></td>
                <td>${job.job_type}</td>
                <td>${job.source_table_name || '-'}</td>
                <td>${job.target_table_name || '-'}</td>
                <td>${job.step_count}</td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${lastRunBadge}</td>
                <td style="font-size: 0.85em;">${lastRunTime}</td>
                <td style="white-space: nowrap;">
                    ${isRunning ? `
                        <button class="btn btn-sm btn-warning" 
                                onclick="pauseLatestRun(${job.etl_job_id})"
                                title="Job pausieren">
                            ⏸️ Pause
                        </button>
                        <button class="btn btn-sm btn-danger" 
                                onclick="cancelLatestRun(${job.etl_job_id})"
                                title="Job abbrechen">
                            ⏹️ Stop
                        </button>
                    ` : `
                        <button class="btn btn-sm btn-success" 
                                onclick="executeJob(${job.etl_job_id}, '${escapeQuotes(job.job_name)}')"
                                ${isActive ? '' : 'disabled'}
                                title="${isActive ? 'Job starten' : 'Job ist inaktiv'}">
                            ▶️ Start
                        </button>
                    `}
                    <button class="btn btn-sm" onclick="showJobSteps(${job.etl_job_id})" title="Steps anzeigen">
                        📋
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteJob(${job.etl_job_id}, '${escapeQuotes(job.job_name)}')" title="Job löschen">
                        🗑️
                    </button>
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('jobsTable').innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Job Name</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Target</th>
                    <th>Steps</th>
                    <th>Status</th>
                    <th>Last Run</th>
                    <th>Last Run Time</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

function renderRuns(runs) {
    if (runs.length === 0) {
        document.getElementById('runsTable').innerHTML = '<p>No runs found</p>';
        return;
    }
    
    const rows = runs.map(run => {
        const duration = run.duration_seconds 
            ? formatDuration(run.duration_seconds)
            : (run.status === 'RUNNING' ? '⏱️ Running...' : '-');
        
        return `
            <tr onclick="showRunDetails(${run.etl_job_run_id})" style="cursor: pointer;">
                <td>${run.etl_job_run_id}</td>
                <td>${run.etl_job_id}</td>
                <td><span class="status-badge ${run.status.toLowerCase()}">${run.status}</span></td>
                <td style="font-size: 0.85em;">${formatDateTime(run.start_time)}</td>
                <td style="font-size: 0.85em;">${run.end_time ? formatDateTime(run.end_time) : '-'}</td>
                <td>${duration}</td>
                <td style="font-size: 0.85em; max-width: 200px; overflow: hidden; text-overflow: ellipsis;">
                    ${run.error_message || '-'}
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('runsTable').innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Run ID</th>
                    <th>Job ID</th>
                    <th>Status</th>
                    <th>Start Time</th>
                    <th>End Time</th>
                    <th>Duration</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
}

// =============================================================================
// Job Execution with Live Tracking
// =============================================================================

let executionPollingTimer = null;
let currentExecutionJobId = null;

async function executeJob(jobId, jobName) {
    // Modal öffnen
    const modal = document.getElementById('executionModal');
    const modalBody = document.getElementById('executionModalBody');
    const modalTitle = document.getElementById('executionModalTitle');
    
    modal.style.display = 'block';
    modalTitle.textContent = `🚀 Job: ${jobName}`;
    document.getElementById('btnCloseExecution').style.display = 'inline-block';
    document.getElementById('executionProgress').textContent = '';
    
    // Initial Loading State
    modalBody.innerHTML = `
        <div class="execution-header">
            <h3>${jobName}</h3>
            <div class="execution-status">
                <span>📋 Step-Übersicht</span>
            </div>
        </div>
        <div class="loading">Lade Step-Konfiguration...</div>
    `;
    
    try {
        // Lade Steps für die Anzeige
        const stepsResponse = await fetch(`${API_BASE_URL}/jobs/${jobId}/steps`);
        if (!stepsResponse.ok) throw new Error('Steps konnten nicht geladen werden');
        const steps = await stepsResponse.json();
        
        // Zeige Steps als "pending" mit Start-Button
        renderExecutionStepsWithStartButton(steps, jobId, jobName);
        
    } catch (error) {
        console.error('Error loading steps:', error);
        modalBody.innerHTML = `
            <div class="execution-header" style="background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%);">
                <h3>${jobName}</h3>
                <div class="execution-status">
                    <span>❌ Fehler beim Laden</span>
                </div>
            </div>
            <div class="error-message" style="margin-top: 20px;">
                ${error.message}
            </div>
        `;
        document.getElementById('btnCloseExecution').style.display = 'inline-block';
        document.getElementById('executionProgress').textContent = '';
    }
}

async function startJobExecution(jobId, jobName, steps) {
    const modalBody = document.getElementById('executionModalBody');
    
    // Bestätigung - angepasst für Initial Load Mode
    let confirmMessage = `Job "${jobName}" jetzt starten?\n\nDies führt alle ${steps.length} Steps aus und kann je nach Datenmenge einige Zeit dauern.`;
    
    if (initialLoadMode) {
        confirmMessage = `⚠️ ACHTUNG: Initial Load Mode aktiviert!\n\n` +
                        `Job "${jobName}" mit DELETE starten?\n\n` +
                        `1. ALLE Daten in der Zieltabelle werden GELÖSCHT\n` +
                        `2. Danach werden ${steps.length} Steps ausgeführt\n\n` +
                        `Diese Aktion kann NICHT rückgängig gemacht werden!\n\n` +
                        `Wirklich fortfahren?`;
    }
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    // Zeige Steps als "starting"
    renderExecutionSteps(steps, null, 'STARTING', jobName);
    document.getElementById('btnCloseExecution').style.display = 'none';
    document.getElementById('executionProgress').textContent = 'Job wird gestartet...';
    
    try {
        // Job starten
        const executeResponse = await fetch(`${API_BASE_URL}/jobs/${jobId}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initial_load_mode: initialLoadMode
            })
        });
        
        if (!executeResponse.ok) {
            const error = await executeResponse.json();
            throw new Error(error.detail || `HTTP ${executeResponse.status}`);
        }
        
        const result = await executeResponse.json();
        currentExecutionJobId = jobId;
        
        // Starte Polling für Live-Updates
        startExecutionPolling(jobId, jobName, steps);
        
    } catch (error) {
        console.error('Error executing job:', error);
        modalBody.innerHTML = `
            <div class="execution-header" style="background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%);">
                <h3>${jobName}</h3>
                <div class="execution-status">
                    <span>❌ Fehler beim Starten</span>
                </div>
            </div>
            <div class="error-message" style="margin-top: 20px;">
                ${error.message}
            </div>
        `;
        document.getElementById('btnCloseExecution').style.display = 'inline-block';
        document.getElementById('executionProgress').textContent = '';
    }
}

function startExecutionPolling(jobId, jobName, steps) {
    // Poll alle 2 Sekunden für Updates
    let pollCount = 0;
    const maxPolls = 300; // Max 10 Minuten (300 * 2s)
    
    executionPollingTimer = setInterval(async () => {
        pollCount++;
        
        if (pollCount > maxPolls) {
            clearInterval(executionPollingTimer);
            document.getElementById('executionProgress').textContent = 'Timeout - bitte manuell prüfen';
            document.getElementById('btnCloseExecution').style.display = 'inline-block';
            return;
        }
        
        try {
            // Hole neueste Runs für diesen Job
            const runsResponse = await fetch(`${API_BASE_URL}/runs?job_id=${jobId}&limit=1`);
            if (!runsResponse.ok) return;
            
            const runs = await runsResponse.json();
            if (runs.length === 0) {
                document.getElementById('executionProgress').textContent = `Warte auf Start... (${pollCount * 2}s)`;
                return;
            }
            
            const latestRun = runs[0];
            
            // Hole Details mit Step Runs
            const detailsResponse = await fetch(`${API_BASE_URL}/runs/${latestRun.etl_job_run_id}`);
            if (!detailsResponse.ok) return;
            
            const runDetails = await detailsResponse.json();
            
            // Update UI
            renderExecutionSteps(steps, runDetails, runDetails.status, jobName);
            
            // Berechne Fortschritt
            const completedSteps = runDetails.step_runs ? runDetails.step_runs.filter(s => s.status !== 'RUNNING').length : 0;
            const totalSteps = steps.length;
            const progress = Math.round((completedSteps / totalSteps) * 100);
            document.getElementById('executionProgress').textContent = `Fortschritt: ${progress}% (${completedSteps}/${totalSteps} Steps) - ${formatDuration(runDetails.duration_seconds || (pollCount * 2))}`;
            
            // Job fertig?
            if (runDetails.status === 'SUCCESS' || runDetails.status === 'FAILED') {
                clearInterval(executionPollingTimer);
                document.getElementById('btnCloseExecution').style.display = 'inline-block';
                document.getElementById('executionProgress').textContent = 
                    runDetails.status === 'SUCCESS' 
                        ? `✅ Erfolgreich abgeschlossen in ${formatDuration(runDetails.duration_seconds)}`
                        : `❌ Fehlgeschlagen nach ${formatDuration(runDetails.duration_seconds)}`;
                
                // Dashboard aktualisieren
                loadDashboard();
            }
            
        } catch (error) {
            console.error('Polling error:', error);
        }
        
    }, 2000);
}

function renderExecutionStepsWithStartButton(steps, jobId, jobName) {
    const modalBody = document.getElementById('executionModalBody');
    
    // Speichere Steps in globaler Variable für onclick
    pendingExecutionSteps = steps;
    pendingExecutionJobId = jobId;
    pendingExecutionJobName = jobName;
    initialLoadMode = false; // Reset
    
    // Header mit Info-Status
    let html = `
        <div class="execution-header">
            <h3>${jobName}</h3>
            <div class="execution-status">
                <span>📋 ${steps.length} Steps konfiguriert</span>
            </div>
        </div>
        
        <div style="background: #E3F2FD; border-left: 4px solid #2196F3; padding: 15px; margin: 20px 0; border-radius: 4px;">
            <strong>ℹ️ Bereit zum Starten</strong>
            <p style="margin: 10px 0 0 0; font-size: 0.9em; color: #555;">
                Dieser Job führt ${steps.length} Steps aus. Überprüfe die Step-Konfiguration unten und klicke dann auf "Job starten" um die Ausführung zu beginnen.
            </p>
        </div>
        
        <!-- Initial Load Mode Option -->
        <div id="initialLoadSection" style="background: #FFF3E0; border-left: 4px solid #FF9800; padding: 15px; margin: 20px 0; border-radius: 4px;">
            <div style="display: flex; align-items: start; gap: 10px;">
                <input type="checkbox" id="chkInitialLoad" onchange="toggleInitialLoadMode()" 
                       style="margin-top: 3px; width: 18px; height: 18px; cursor: pointer;">
                <div style="flex: 1;">
                    <label for="chkInitialLoad" style="cursor: pointer; font-weight: 600; color: #E65100; display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 1.2em;">⚠️</span>
                        <span>Initial Load Mode - Zieltabelle leeren</span>
                    </label>
                    <p style="margin: 8px 0 0 0; font-size: 0.85em; color: #666; line-height: 1.4;">
                        <strong>Achtung:</strong> Wenn aktiviert, werden <strong>ALLE Daten</strong> aus der Zieltabelle gelöscht, 
                        bevor der ETL-Prozess startet. Verwende diese Option nur für Initial Loads oder wenn du die 
                        Tabelle komplett neu befüllen möchtest.
                    </p>
                    <div id="initialLoadWarning" style="display: none; margin-top: 10px; padding: 10px; background: #FFEBEE; border-radius: 4px; border: 1px solid #EF5350;">
                        <strong style="color: #C62828;">🔥 Destruktive Operation aktiviert!</strong>
                        <p style="margin: 5px 0 0 0; font-size: 0.85em; color: #C62828;">
                            Beim Start wird ein DELETE FROM durchgeführt. Diese Aktion kann nicht rückgängig gemacht werden.
                        </p>
                    </div>
                </div>
            </div>
        </div>
        
        <div style="text-align: center; margin: 20px 0;">
            <button id="btnStartExecution" class="btn" style="font-size: 1.1em; padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; cursor: pointer; border-radius: 6px; box-shadow: 0 4px 6px rgba(102, 126, 234, 0.3); transition: all 0.3s;" 
                    onclick="startJobExecutionFromButton()">
                ▶️ Job starten
            </button>
        </div>
    `;
    
    // Step Timeline (Preview)
    html += '<div class="execution-timeline">';
    
    steps.forEach(step => {
        html += `
            <div class="execution-step pending">
                <div class="execution-step-header">
                    <span class="execution-step-name">${step.step_order}. ${step.step_name}</span>
                    <span class="status-badge pending">Ausstehend</span>
                </div>
                <div style="font-size: 0.85em; color: #888;">
                    ${step.step_category} ${step.sql_template_path ? `• Template: ${step.sql_template_path}` : ''}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    modalBody.innerHTML = html;
}

function toggleInitialLoadMode() {
    const checkbox = document.getElementById('chkInitialLoad');
    const warning = document.getElementById('initialLoadWarning');
    const startButton = document.getElementById('btnStartExecution');
    
    initialLoadMode = checkbox.checked;
    
    if (initialLoadMode) {
        warning.style.display = 'block';
        startButton.style.background = 'linear-gradient(135deg, #FF5722 0%, #E64A19 100%)';
        startButton.innerHTML = '🔥 Initial Load starten (Daten werden gelöscht!)';
    } else {
        warning.style.display = 'none';
        startButton.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        startButton.innerHTML = '▶️ Job starten';
    }
}

function startJobExecutionFromButton() {
    if (pendingExecutionSteps && pendingExecutionJobId && pendingExecutionJobName) {
        startJobExecution(pendingExecutionJobId, pendingExecutionJobName, pendingExecutionSteps);
    } else {
        console.error('No pending execution data found');
        alert('Fehler: Keine Job-Daten gefunden. Bitte schließe das Fenster und versuche es erneut.');
    }
}

function renderExecutionSteps(steps, runDetails, status, jobName) {
    const modalBody = document.getElementById('executionModalBody');
    
    // Header
    let headerBg = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
    let statusIcon = '<div class="spinner"></div>';
    let statusText = 'Job wird ausgeführt...';
    
    if (status === 'SUCCESS') {
        headerBg = 'linear-gradient(135deg, #4CAF50 0%, #388E3C 100%)';
        statusIcon = '✅';
        statusText = 'Job erfolgreich abgeschlossen!';
    } else if (status === 'FAILED') {
        headerBg = 'linear-gradient(135deg, #f44336 0%, #d32f2f 100%)';
        statusIcon = '❌';
        statusText = 'Job fehlgeschlagen';
    } else if (status === 'STARTING') {
        statusText = 'Job wird gestartet...';
    }
    
    let html = `
        <div class="execution-header" style="background: ${headerBg};">
            <h3>${jobName}</h3>
            <div class="execution-status">
                ${typeof statusIcon === 'string' && statusIcon.length > 5 ? statusIcon : `<span style="font-size: 1.5em;">${statusIcon}</span>`}
                <span>${statusText}</span>
            </div>
        </div>
    `;
    
    // Step Timeline
    html += '<div class="execution-timeline">';
    
    steps.forEach(step => {
        // Finde passenden Step Run
        let stepRun = null;
        if (runDetails && runDetails.step_runs) {
            stepRun = runDetails.step_runs.find(sr => sr.etl_job_step_id === step.etl_job_step_id);
        }
        
        let stepClass = 'pending';
        let stepStatus = 'Ausstehend';
        let stepMetrics = '';
        
        if (stepRun) {
            if (stepRun.was_skipped === 'Y') {
                stepClass = 'skipped';
                stepStatus = 'Übersprungen';
            } else if (stepRun.status === 'RUNNING') {
                stepClass = 'running';
                stepStatus = '⏳ Läuft...';
            } else if (stepRun.status === 'SUCCESS') {
                stepClass = 'success';
                stepStatus = '✅ Erfolgreich';
                stepMetrics = `
                    <div class="execution-step-metrics">
                        <span class="metric-item"><strong>📖 Gelesen:</strong> ${stepRun.rows_read}</span>
                        <span class="metric-item success"><strong>➕ Eingefügt:</strong> ${stepRun.rows_inserted}</span>
                        <span class="metric-item"><strong>🔄 Aktualisiert:</strong> ${stepRun.rows_updated}</span>
                        <span class="metric-item"><strong>⏱️ Dauer:</strong> ${formatDuration(stepRun.duration_seconds)}</span>
                    </div>
                `;
            } else if (stepRun.status === 'FAILED') {
                stepClass = 'failed';
                stepStatus = '❌ Fehlgeschlagen';
                // Formatiere Error Message mit Code-Block für TPT-Kommando
                const errorMsg = stepRun.error_message || 'Unbekannter Fehler';
                const formattedError = errorMsg.split('\\n').map(line => {
                    if (line.startsWith('TPT-Kommando:') || line.startsWith('Script:')) {
                        const parts = line.split(': ', 2);
                        return `<strong>${parts[0]}:</strong><br><code style="display: block; background: #1a1a2e; color: #0f0; padding: 8px; border-radius: 4px; margin: 5px 0; font-family: monospace; cursor: pointer; user-select: all;" onclick="navigator.clipboard.writeText(this.textContent).then(() => alert('Kopiert!'))">${parts[1] || ''}</code>`;
                    }
                    return line;
                }).join('<br>');
                stepMetrics = `<div class="error-message" style="margin-top: 10px; white-space: pre-wrap;">${formattedError}</div>`;
            }
        }
        
        html += `
            <div class="execution-step ${stepClass}">
                <div class="execution-step-header">
                    <span class="execution-step-name">${step.step_order}. ${step.step_name}</span>
                    <span class="status-badge ${stepClass}">${stepStatus}</span>
                </div>
                <div style="font-size: 0.85em; color: #888;">
                    ${step.step_category} ${step.sql_template_path ? `• Template: ${step.sql_template_path}` : ''}
                </div>
                ${stepMetrics}
            </div>
        `;
    });
    
    html += '</div>';
    
    // Summary (nur wenn Job fertig)
    if (runDetails && (runDetails.status === 'SUCCESS' || runDetails.status === 'FAILED')) {
        // Helper: Prüfe ob Step-Kategorie für Metriken relevant ist (exkludiere STATISTICS/COLLECT_STATISTICS)
        const isMetricRelevantStep = (stepRunId) => {
            const step = steps.find(s => s.etl_job_step_id === stepRunId);
            if (!step) return true; // Wenn Step nicht gefunden, zähle mit
            const category = (step.step_category || '').toUpperCase();
            return !category.includes('STATISTIC'); // Exkludiert STATISTICS, COLLECT_STATISTICS, etc.
        };
        
        const totalRead = runDetails.step_runs ? runDetails.step_runs
            .filter(s => isMetricRelevantStep(s.etl_job_step_id))
            .reduce((sum, s) => sum + (s.rows_read || 0), 0) : 0;
        const totalInserted = runDetails.step_runs ? runDetails.step_runs
            .filter(s => isMetricRelevantStep(s.etl_job_step_id))
            .reduce((sum, s) => sum + (s.rows_inserted || 0), 0) : 0;
        const totalUpdated = runDetails.step_runs ? runDetails.step_runs
            .filter(s => isMetricRelevantStep(s.etl_job_step_id))
            .reduce((sum, s) => sum + (s.rows_updated || 0), 0) : 0;
        const totalSkipped = runDetails.step_runs ? runDetails.step_runs.filter(s => s.was_skipped === 'Y').length : 0;
        
        html += `
            <div class="execution-summary">
                <h4>📊 Zusammenfassung</h4>
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="value">${totalRead.toLocaleString()}</div>
                        <div class="label">Zeilen gelesen</div>
                    </div>
                    <div class="summary-item">
                        <div class="value" style="color: #4CAF50;">${totalInserted.toLocaleString()}</div>
                        <div class="label">Zeilen eingefügt</div>
                    </div>
                    <div class="summary-item">
                        <div class="value" style="color: #2196F3;">${totalUpdated.toLocaleString()}</div>
                        <div class="label">Zeilen aktualisiert</div>
                    </div>
                    <div class="summary-item">
                        <div class="value">${formatDuration(runDetails.duration_seconds)}</div>
                        <div class="label">Gesamtdauer</div>
                    </div>
                    <div class="summary-item">
                        <div class="value">${totalSkipped}</div>
                        <div class="label">Steps übersprungen</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    modalBody.innerHTML = html;
}

function closeExecutionModal() {
    // Polling stoppen
    if (executionPollingTimer) {
        clearInterval(executionPollingTimer);
        executionPollingTimer = null;
    }
    
    document.getElementById('executionModal').style.display = 'none';
    currentExecutionJobId = null;
    
    // Dashboard aktualisieren
    loadDashboard();
}

// =============================================================================
// Job Run Details Modal
// =============================================================================

async function showRunDetails(runId) {
    const modal = document.getElementById('runDetailsModal');
    const modalBody = document.getElementById('modalBody');
    const modalTitle = document.getElementById('modalTitle');
    
    modal.style.display = 'block';
    modalTitle.textContent = `Job Run #${runId} Details`;
    modalBody.innerHTML = '<div class="loading">Loading details...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/runs/${runId}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const run = await response.json();
        renderRunDetails(run, modalBody);
    } catch (error) {
        console.error('Error loading run details:', error);
        modalBody.innerHTML = `<div class="error-message">Failed to load details: ${error.message}</div>`;
    }
}

function renderRunDetails(run, container) {
    const duration = run.duration_seconds ? formatDuration(run.duration_seconds) : '-';
    const status = run.status.trim();
    
    let html = `
        <div style="margin-bottom: 20px;">
            <h3>${run.job_name} <span class="status-badge ${status.toLowerCase()}">${status}</span></h3>
            <p><strong>Job Run ID:</strong> ${run.etl_job_run_id}</p>
            <p><strong>Job ID:</strong> ${run.etl_job_id}</p>
            <p><strong>Start Time:</strong> ${formatDateTime(run.start_time)}</p>
            <p><strong>End Time:</strong> ${run.end_time ? formatDateTime(run.end_time) : '-'}</p>
            <p><strong>Duration:</strong> ${duration}</p>
    `;
    
    // Control Buttons basierend auf Status
    html += `<div style="margin: 15px 0; display: flex; gap: 10px;">`;
    
    if (status === 'RUNNING') {
        html += `
            <button class="btn btn-warning" onclick="pauseJobRun(${run.etl_job_run_id})">
                ⏸️ Pause
            </button>
            <button class="btn btn-danger" onclick="cancelJobRun(${run.etl_job_run_id})">
                ⏹️ Abbrechen
            </button>
        `;
    } else if (status === 'PAUSED') {
        html += `
            <button class="btn btn-success" onclick="resumeJobRun(${run.etl_job_run_id})">
                ▶️ Fortsetzen
            </button>
            <button class="btn btn-danger" onclick="cancelJobRun(${run.etl_job_run_id})">
                ⏹️ Abbrechen
            </button>
        `;
    }
    
    html += `</div>`;
    
    if (run.error_message) {
        html += `
            <div class="error-message">
                <strong>Error:</strong> ${run.error_message}
            </div>
        `;
    }
    
    html += `</div>`;
    
    // Step Runs
    if (run.step_runs && run.step_runs.length > 0) {
        html += `
            <h3>Step Execution</h3>
            <div class="step-timeline">
        `;
        
        run.step_runs.forEach(step => {
            const stepDuration = step.duration_seconds ? formatDuration(step.duration_seconds) : '-';
            const stepStatus = step.status ? step.status.trim() : 'UNKNOWN';
            const wasSkipped = step.was_skipped ? step.was_skipped.trim() : 'N';
            const stepClass = wasSkipped === 'Y' ? 'skipped' : stepStatus.toLowerCase();
            const stepId = `step-${step.etl_job_step_run_id}`;
            
            // Parse parameters for display
            let paramsPreview = '';
            if (step.parameters) {
                try {
                    const params = JSON.parse(step.parameters);
                    paramsPreview = `target_database: ${params.target_database || '(leer)'}, target_table: ${params.target_table || '?'}`;
                } catch (e) {
                    paramsPreview = 'Parameters nicht parsbar';
                }
            }
            
            html += `
                <div class="step-item ${stepClass}">
                    <div class="step-header">
                        <span>${step.step_order}. ${step.step_name}</span>
                        <span class="status-badge ${stepClass}">${wasSkipped === 'Y' ? 'SKIPPED' : stepStatus}</span>
                    </div>
                    <div style="font-size: 0.85em; color: #666;">
                        Category: ${step.step_category} | Duration: ${stepDuration}
                    </div>
                    <div class="step-metrics">
                        📊 Read: ${step.rows_read ?? '-'} | Inserted: ${step.rows_inserted ?? '-'} | 
                        Updated: ${step.rows_updated ?? '-'} | Deleted: ${step.rows_deleted ?? '-'}
                    </div>
                    ${step.skip_reason ? `<div style="font-size: 0.85em; color: #FF9800; margin-top: 5px;">Skip Reason: ${step.skip_reason}</div>` : ''}
                    ${step.error_message ? `<div class="error-message" style="margin-top: 5px;"><strong>❌ Error:</strong> ${step.error_message}</div>` : ''}
                    ${step.parameters ? `
                        <div style="margin-top: 8px;">
                            <button class="btn btn-sm" onclick="toggleParams('${stepId}')" style="font-size: 0.8em;">📋 Parameters anzeigen</button>
                            <div id="${stepId}" style="display: none; margin-top: 5px; background: #f5f5f5; padding: 10px; border-radius: 4px; font-size: 0.85em; overflow-x: auto;">
                                <pre style="margin: 0; white-space: pre-wrap;">${formatStepParams(step.parameters)}</pre>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;
        });
        
        html += `</div>`;
    }
    
    container.innerHTML = html;
}

async function showJobSteps(jobId) {
    const modal = document.getElementById('runDetailsModal');
    const modalBody = document.getElementById('modalBody');
    const modalTitle = document.getElementById('modalTitle');
    
    modal.style.display = 'block';
    modalTitle.textContent = `Job #${jobId} - Step Configuration`;
    modalBody.innerHTML = '<div class="loading">Loading steps...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/steps`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const steps = await response.json();
        renderJobSteps(steps, modalBody);
    } catch (error) {
        console.error('Error loading job steps:', error);
        modalBody.innerHTML = `<div class="error-message">Failed to load steps: ${error.message}</div>`;
    }
}

function renderJobSteps(steps, container) {
    if (steps.length === 0) {
        container.innerHTML = '<p>No steps configured</p>';
        return;
    }
    
    let html = '<div class="step-timeline">';
    
    steps.forEach(step => {
        const params = step.parameters ? JSON.stringify(JSON.parse(step.parameters), null, 2) : 'None';
        // Trim trailing spaces von CHAR-Feldern
        const isActive = (step.is_active || '').trim();
        const skipOnEmpty = (step.skip_on_empty || '').trim();
        const isCritical = (step.is_critical || '').trim();
        
        html += `
            <div class="step-item">
                <div class="step-header">
                    <span>${step.step_order}. ${step.step_name}</span>
                    <span class="status-badge ${isActive === 'Y' ? 'active' : 'inactive'}">
                        ${isActive === 'Y' ? 'Active' : 'Inactive'}
                    </span>
                </div>
                <div style="font-size: 0.85em; color: #666; margin-top: 5px;">
                    <strong>Category:</strong> ${step.step_category}<br>
                    <strong>Template:</strong> ${step.sql_template_path || 'Inline SQL'}<br>
                    <strong>Skip on Empty:</strong> ${skipOnEmpty}<br>
                    <strong>Critical:</strong> ${isCritical}
                </div>
                ${step.parameters ? `
                    <details style="margin-top: 10px;">
                        <summary style="cursor: pointer; font-weight: 600;">Parameters</summary>
                        <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 0.8em;">${params}</pre>
                    </details>
                ` : ''}
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

function closeModal() {
    document.getElementById('runDetailsModal').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('runDetailsModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
};

// =============================================================================
// Refresh Functions
// =============================================================================

async function refreshJobs() {
    await loadJobs();
    updateLastRefreshTime();
}

async function refreshRuns() {
    await loadRecentRuns();
    updateLastRefreshTime();
}

function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(() => {
        console.log('Auto-refresh triggered');
        loadDashboard();
    }, AUTO_REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

function updateLastRefreshTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = 
        `(Last update: ${now.toLocaleTimeString()})`;
}

// =============================================================================
// Job Run Control Functions (Pause/Resume/Cancel)
// =============================================================================

async function pauseLatestRun(jobId) {
    // Hole neuesten laufenden Run für diesen Job
    try {
        const response = await fetch(`${API_BASE_URL}/runs?job_id=${jobId}&limit=1`);
        if (!response.ok) throw new Error('Konnte Runs nicht laden');
        
        const runs = await response.json();
        if (runs.length === 0 || runs[0].status.trim() !== 'RUNNING') {
            alert('Kein laufender Job gefunden');
            return;
        }
        
        await pauseJobRun(runs[0].etl_job_run_id);
    } catch (error) {
        console.error('Error:', error);
        alert('Fehler: ' + error.message);
    }
}

async function cancelLatestRun(jobId) {
    // Hole neuesten laufenden Run für diesen Job
    try {
        const response = await fetch(`${API_BASE_URL}/runs?job_id=${jobId}&limit=1`);
        if (!response.ok) throw new Error('Konnte Runs nicht laden');
        
        const runs = await response.json();
        if (runs.length === 0) {
            alert('Kein laufender Job gefunden');
            return;
        }
        
        const status = runs[0].status.trim();
        if (status !== 'RUNNING' && status !== 'PAUSED') {
            alert('Job ist nicht aktiv');
            return;
        }
        
        await cancelJobRun(runs[0].etl_job_run_id);
    } catch (error) {
        console.error('Error:', error);
        alert('Fehler: ' + error.message);
    }
}

async function pauseJobRun(jobRunId) {
    if (!confirm('Job nach aktuellem Step pausieren?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/runs/${jobRunId}/pause`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Pause fehlgeschlagen');
        }
        
        const result = await response.json();
        alert(result.message);
        
        // Refresh Details
        showRunDetails(jobRunId);
        loadRuns();
        
    } catch (error) {
        console.error('Error pausing job:', error);
        alert('Fehler: ' + error.message);
    }
}

async function resumeJobRun(jobRunId) {
    if (!confirm('Pausierten Job fortsetzen?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/runs/${jobRunId}/resume`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Resume fehlgeschlagen');
        }
        
        const result = await response.json();
        alert(result.message);
        
        // Modal schließen und Dashboard aktualisieren
        document.getElementById('runDetailsModal').style.display = 'none';
        loadRuns();
        loadStats();
        
    } catch (error) {
        console.error('Error resuming job:', error);
        alert('Fehler: ' + error.message);
    }
}

async function cancelJobRun(jobRunId) {
    if (!confirm('Job wirklich abbrechen?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/runs/${jobRunId}/cancel`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Abbruch fehlgeschlagen');
        }
        
        const result = await response.json();
        alert(result.message);
        
        // Refresh Details
        showRunDetails(jobRunId);
        loadRuns();
        
    } catch (error) {
        console.error('Error cancelling job:', error);
        alert('Fehler: ' + error.message);
    }
}

// =============================================================================
// Utility Functions
// =============================================================================

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    // Teradata TIMESTAMP wird ohne Zeitzone geliefert
    // JavaScript interpretiert es als lokale Zeit, was korrekt ist
    const date = new Date(dateStr);
    return date.toLocaleString('de-DE', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}m ${secs}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }
}

// Toggle Parameters Display für Step Run Details
function toggleParams(stepId) {
    const el = document.getElementById(stepId);
    if (el) {
        el.style.display = el.style.display === 'none' ? 'block' : 'none';
    }
}

// Format Step Parameters als lesbare JSON
function formatStepParams(paramsStr) {
    if (!paramsStr) return '(keine Parameter)';
    try {
        const params = JSON.parse(paramsStr);
        // Columns kürzen für bessere Lesbarkeit
        if (params.columns && params.columns.length > 3) {
            const colCount = params.columns.length;
            params.columns = [
                params.columns[0],
                `... (${colCount - 2} weitere Spalten) ...`,
                params.columns[colCount - 1]
            ];
        }
        return JSON.stringify(params, null, 2);
    } catch (e) {
        return paramsStr;
    }
}

// =============================================================================
// Cleanup on page unload
// =============================================================================

window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// =============================================================================
// Delete Job
// =============================================================================

async function deleteJob(jobId, jobName) {
    // Einfacher Bestätigungsdialog
    const confirmed = confirm(
        `Job "${jobName}" (ID: ${jobId}) wirklich löschen?\n\n` +
        `Dies löscht:\n` +
        `• Job Definition\n` +
        `• Alle Job Steps\n` +
        `• Alle Run-Historien`
    );
    
    if (!confirmed) {
        return;
    }
    
    // Frage nach Tabellen-Löschung
    const deleteTables = confirm(
        `Auch die zugehörigen Teradata-Tabellen löschen?\n\n` +
        `• Zieltabelle\n` +
        `• Staging-Tabelle (_LOAD)\n` +
        `• Log/Error-Tabellen\n\n` +
        `OK = Tabellen auch löschen\n` +
        `Abbrechen = Nur Job-Metadaten löschen`
    );
    
    try {
        const url = `${API_BASE_URL}/jobs/${jobId}?delete_tables=${deleteTables}`;
        const response = await fetch(url, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        // Erfolgsmeldung
        let message = `Job "${jobName}" gelöscht!\n\n`;
        message += `• ${result.deleted_steps} Step(s)\n`;
        message += `• ${result.deleted_job_runs} Job-Run(s)\n`;
        message += `• ${result.deleted_step_runs} Step-Run(s)\n`;
        
        if (result.deleted_tables && result.deleted_tables.length > 0) {
            message += `\nGelöschte Tabellen:\n`;
            result.deleted_tables.forEach(t => message += `• ${t}\n`);
        }
        
        alert(message);
        
        // Dashboard neu laden
        loadJobs();
        loadRecentRuns();
        loadStats();
        
    } catch (error) {
        console.error('Error deleting job:', error);
        alert(`Fehler beim Löschen: ${error.message}`);
    }
}
