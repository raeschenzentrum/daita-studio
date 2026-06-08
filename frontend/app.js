// metadaita Frontend JavaScript
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';

// API URL für metadaita Backend (konfigurierbar via config.js)
const API_BASE = (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api';

let currentResult = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    mermaid.initialize({ startOnLoad: true, securityLevel: 'loose', theme: 'default' });
    loadConnections();
    loadConversionConfig();
    setupEventListeners();
    setupModeToggle();
});

// Event Listeners
function setupEventListeners() {
    document.getElementById('analyzeBtn').addEventListener('click', analyzeSql);
    document.getElementById('convertBtn').addEventListener('click', convertSql);
    document.getElementById('manageConnectionsBtn').addEventListener('click', openConnectionModal);
    
    // Optional buttons - only if they exist
    const viewMermaidBtn = document.getElementById('viewMermaidBtn');
    if (viewMermaidBtn) {
        viewMermaidBtn.addEventListener('click', showMermaidDiagram);
    }
    
    const downloadHtmlBtn = document.getElementById('downloadHtmlBtn');
    if (downloadHtmlBtn) {
        downloadHtmlBtn.addEventListener('click', downloadHtmlReport);
    }

    const copyConvertedBtn = document.getElementById('copyConvertedBtn');
    if (copyConvertedBtn) {
        copyConvertedBtn.addEventListener('click', copyConvertedSql);
    }
    
    document.getElementById('newConnectionForm').addEventListener('submit', addConnection);
    
    // Modal close buttons
    document.querySelectorAll('.close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').style.display = 'none';
        });
    });
    
    const closeConnModal = document.getElementById('closeConnModal');
    if (closeConnModal) {
        closeConnModal.addEventListener('click', () => {
            document.getElementById('connectionModal').style.display = 'none';
        });
    }
}

// Mode Toggle
function setupModeToggle() {
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    modeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            const mode = e.target.value;
            toggleMode(mode);
        });
    });
}

function toggleMode(mode) {
    const analyzeBtn = document.getElementById('analyzeBtn');
    const convertBtn = document.getElementById('convertBtn');
    const llmGroup = document.getElementById('llmGroup');
    const llmReviewGroup = document.getElementById('llmReviewGroup');
    const targetDialectGroup = document.getElementById('targetDialectGroup');
    const results = document.getElementById('results');
    const conversionResults = document.getElementById('conversionResults');
    
    if (mode === 'lineage') {
        // Lineage Mode
        analyzeBtn.style.display = 'inline-block';
        convertBtn.style.display = 'none';
        llmGroup.style.display = 'block';
        llmReviewGroup.style.display = 'none';
        targetDialectGroup.style.display = 'none';
        results.style.display = 'none';
        conversionResults.style.display = 'none';
    } else {
        // Conversion Mode
        analyzeBtn.style.display = 'none';
        convertBtn.style.display = 'inline-block';
        llmGroup.style.display = 'none';
        llmReviewGroup.style.display = 'block';
        targetDialectGroup.style.display = 'block';
        results.style.display = 'none';
        conversionResults.style.display = 'none';
    }
}

// Load Connections
async function loadConnections() {
    try {
        const response = await fetch(`${API_BASE}/connections`);
        const connections = await response.json();
        
        // Lineage LLM Select
        const select = document.getElementById('llmSelect');
        select.innerHTML = '<option value="">Ohne LLM</option>';
        
        // Conversion Review Select (multiple)
        const reviewSelect = document.getElementById('llmReviewSelect');
        reviewSelect.innerHTML = '';
        
        connections.forEach(conn => {
            // Lineage select
            const option = document.createElement('option');
            option.value = conn.id;
            option.textContent = conn.name;
            select.appendChild(option);
            
            // Review select
            const reviewOption = document.createElement('option');
            reviewOption.value = conn.id;
            reviewOption.textContent = conn.name;
            reviewSelect.appendChild(reviewOption);
        });
    } catch (error) {
        console.error('Fehler beim Laden der Connections:', error);
        showError('Konnte Connections nicht laden');
    }
}

// Load Conversion Config
async function loadConversionConfig() {
    try {
        const response = await fetch(`${API_BASE}/conversion/config`);
        const config = await response.json();
        
        const targetSelect = document.getElementById('targetDialectSelect');
        targetSelect.innerHTML = '';
        
        config.allowed_target_dialects.forEach(dialect => {
            const option = document.createElement('option');
            option.value = dialect;
            option.textContent = dialect.toUpperCase();
            if (dialect === config.default_target_dialect) {
                option.selected = true;
            }
            targetSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Fehler beim Laden der Conversion Config:', error);
    }
}

// Analyze SQL
async function analyzeSql() {
    const sql = document.getElementById('sqlInput').value.trim();
    const dialect = document.getElementById('dialectSelect').value;
    const llmConnectionId = document.getElementById('llmSelect').value || null;
    
    if (!sql) {
        showError('Bitte SQL Statement eingeben');
        return;
    }
    
    // Show loading
    const loadingDiv = document.getElementById('loading');
    loadingDiv.style.display = 'block';
    loadingDiv.innerHTML = '<div class="spinner"></div><p>Analysiere SQL... (Dies kann bei komplexen Queries mit LLM bis zu 5 Minuten dauern)</p>';
    document.getElementById('results').style.display = 'none';
    
    try {
        console.log('Sending request to:', `${API_BASE}/lineage/parse`);
        console.log('Request payload:', { sql, dialect, llm_connection_id: llmConnectionId, generate_html: true });
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 Minuten Timeout für LLM-Anfragen
        
        const response = await fetch(`${API_BASE}/lineage/parse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sql,
                dialect,
                llm_connection_id: llmConnectionId,
                generate_html: true
            }),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response:', errorText);
            try {
                const error = JSON.parse(errorText);
                throw new Error(error.detail || 'Analyse fehlgeschlagen');
            } catch (e) {
                throw new Error(`HTTP ${response.status}: ${errorText || 'Analyse fehlgeschlagen'}`);
            }
        }
        
        currentResult = await response.json();
        console.log('Result received:', currentResult);
        displayResults(currentResult);
        
    } catch (error) {
        console.error('Analyse Error:', error);
        if (error.name === 'AbortError') {
            showError('Timeout: Die Analyse dauert zu lange. Bitte vereinfachen Sie das SQL Statement oder versuchen Sie es ohne LLM-Beschreibungen.');
        } else if (error.message.includes('Failed to fetch')) {
            showError('Verbindungsfehler: Backend ist nicht erreichbar. Prüfen Sie ob der Server läuft (Port 8010).');
        } else {
            showError(error.message || 'Unbekannter Fehler bei der Analyse');
        }
    } finally {
        loadingDiv.innerHTML = '<div class="spinner"></div><p>Lädt...</p>';
        loadingDiv.style.display = 'none';
    }
}

// Display Results
function displayResults(result) {
    const resultsSection = document.getElementById('results');
    if (!resultsSection) {
        console.error('Results section not found');
        return;
    }
    resultsSection.style.display = 'block';
    
    // Stats
    const statsDiv = document.getElementById('stats');
    if (statsDiv) {
        statsDiv.innerHTML = `
            <div class="stat-card">
                <div class="value">${result.stats.total_columns}</div>
                <div class="label">Spalten</div>
            </div>
            <div class="stat-card">
                <div class="value">${result.stats.llm_enriched || 0}</div>
                <div class="label">LLM-Beschreibungen</div>
            </div>
            <div class="stat-card">
                <div class="value">${result.source_tables.length}</div>
                <div class="label">Source Tables</div>
            </div>
            <div class="stat-card">
                <div class="value">${result.stats.llm_backend || 'N/A'}</div>
                <div class="label">LLM Backend</div>
            </div>
        `;
    }
    
    // Columns Table
    const tableDiv = document.getElementById('columnsTable');
    if (!tableDiv) {
        console.error('Columns table div not found');
        return;
    }
    
    let tableHtml = `
        <h3>Column Mappings</h3>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Target Column</th>
                    <th>Transform Type</th>
                    <th>LLM Beschreibung</th>
                    <th>Source Columns</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    result.columns.slice(0, 20).forEach((col, idx) => {
        const hasDescription = col.llm_description ? 'badge-success' : 'badge-warning';
        tableHtml += `
            <tr>
                <td>${idx + 1}</td>
                <td><strong>${col.target_column}</strong></td>
                <td>${col.transform_icon}</td>
                <td>
                    ${col.llm_description 
                        ? `<span class="badge ${hasDescription}">✓</span> ${col.llm_description.substring(0, 100)}...`
                        : '<span class="badge badge-warning">-</span>'}
                </td>
                <td>${col.source_columns_d.join(', ') || '-'}</td>
            </tr>
        `;
    });
    
    tableHtml += '</tbody></table>';
    tableDiv.innerHTML = tableHtml;
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Show Mermaid Diagram
function showMermaidDiagram() {
    if (!currentResult) return;
    
    const modal = document.getElementById('mermaidModal');
    const container = document.getElementById('mermaidContainer');
    
    container.innerHTML = `<div class="mermaid">${currentResult.mermaid_code}</div>`;
    mermaid.run({ nodes: container.querySelectorAll('.mermaid') });
    
    modal.style.display = 'flex';
}

// Download HTML Report
function downloadHtmlReport() {
    if (!currentResult || !currentResult.html_file) return;
    
    const filename = currentResult.html_file.split('/').pop();
    window.open(`${API_BASE}/lineage/report/${filename}`, '_blank');
}

// Copy Converted SQL
function copyConvertedSql() {
    const code = document.querySelector('#convertedSql code');
    if (!code) return;
    
    navigator.clipboard.writeText(code.textContent).then(() => {
        const btn = document.getElementById('copyConvertedBtn');
        const originalText = btn.textContent;
        btn.textContent = '✅ Kopiert!';
        setTimeout(() => {
            btn.textContent = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Fehler beim Kopieren:', err);
        showError('Fehler beim Kopieren in die Zwischenablage');
    });
}

// SQL Conversion
async function convertSql() {
    const sql = document.getElementById('sqlInput').value.trim();
    const sourceDialect = document.getElementById('dialectSelect').value;
    const targetDialect = document.getElementById('targetDialectSelect').value;
    const llmReviewSelect = document.getElementById('llmReviewSelect');
    const selectedLlms = Array.from(llmReviewSelect.selectedOptions).map(opt => opt.value);
    
    if (!sql) {
        showError('Bitte SQL Statement eingeben');
        return;
    }
    
    // Show loading
    const loading = document.getElementById('loading');
    const loadingText = document.getElementById('loadingText');
    if (loading) {
        loading.style.display = 'block';
        if (loadingText) {
            loadingText.textContent = `Konvertiere SQL von ${sourceDialect.toUpperCase()} zu ${targetDialect.toUpperCase()}...`;
        }
    }
    
    // Hide previous results
    const results = document.getElementById('results');
    const conversionResults = document.getElementById('conversionResults');
    if (results) results.style.display = 'none';
    if (conversionResults) conversionResults.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/conversion/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sql: sql,
                source_dialect: sourceDialect,
                target_dialect: targetDialect,
                llm_connection_ids: selectedLlms.length > 0 ? selectedLlms : null
            })
        });
        
        const result = await response.json();
        
        if (loading) loading.style.display = 'none';
        
        if (!result.success) {
            showError(result.error || 'Konvertierung fehlgeschlagen');
            return;
        }
        
        displayConversionResults(result);
    } catch (error) {
        if (loading) loading.style.display = 'none';
        console.error('Fehler bei SQL Konvertierung:', error);
        showError('Fehler bei der SQL Konvertierung: ' + error.message);
    }
}

// Display Conversion Results
function displayConversionResults(result) {
    const conversionResults = document.getElementById('conversionResults');
    if (!conversionResults) {
        console.error('Conversion results section not found');
        return;
    }
    
    // Show results section
    conversionResults.style.display = 'block';
    
    // Stats
    const statsDiv = document.getElementById('conversionStats');
    if (statsDiv) {
        statsDiv.innerHTML = `
            <div class="stat-card">
                <span class="stat-label">Quell-Dialect</span>
                <span class="stat-value">${result.source_dialect.toUpperCase()}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Ziel-Dialect</span>
                <span class="stat-value">${result.target_dialect.toUpperCase()}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Original Zeilen</span>
                <span class="stat-value">${result.stats.original_lines}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Konvertierte Zeilen</span>
                <span class="stat-value">${result.stats.converted_lines}</span>
            </div>
            <div class="stat-card">
                <span class="stat-label">Konvertierungszeit</span>
                <span class="stat-value">${result.stats.conversion_time_ms}ms</span>
            </div>
        `;
    }
    
    // Converted SQL
    const convertedSqlCode = document.querySelector('#convertedSql code');
    if (convertedSqlCode) {
        convertedSqlCode.textContent = result.converted_sql;
    }
    
    // LLM Reviews
    if (result.llm_reviews && result.llm_reviews.length > 0) {
        const reviewsSection = document.getElementById('llmReviewsSection');
        const reviewsDiv = document.getElementById('llmReviews');
        
        if (reviewsSection && reviewsDiv) {
            reviewsSection.style.display = 'block';
            reviewsDiv.innerHTML = '';
            
            result.llm_reviews.forEach((review, index) => {
                const reviewCard = document.createElement('div');
                reviewCard.className = 'review-card';
                
                if (review.success) {
                    reviewCard.innerHTML = `
                        <div class="review-header">
                            <h4>🤖 ${review.llm_name} (${review.llm_model})</h4>
                            <span class="badge badge-success">✓ Erfolgreich</span>
                        </div>
                        <div class="review-content">
                            ${formatReview(review.review)}
                        </div>
                    `;
                } else {
                    reviewCard.innerHTML = `
                        <div class="review-header">
                            <h4>🤖 ${review.llm_name}</h4>
                            <span class="badge badge-error">✗ Fehler</span>
                        </div>
                        <div class="review-error">
                            ${review.error}
                        </div>
                    `;
                }
                
                reviewsDiv.appendChild(reviewCard);
            });
        }
    }
    
    // Scroll to results
    conversionResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Format LLM Review (convert markdown-style to HTML)
function formatReview(text) {
    if (!text) return '<p>Kein Review verfügbar</p>';
    
    // Simple markdown-like formatting
    let formatted = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold
        .replace(/\*(.*?)\*/g, '<em>$1</em>')              // Italic
        .replace(/`(.*?)`/g, '<code>$1</code>')            // Code
        .replace(/\n\n/g, '</p><p>')                       // Paragraphs
        .replace(/\n/g, '<br>');                           // Line breaks
    
    // Wrap in paragraphs
    if (!formatted.startsWith('<p>')) {
        formatted = '<p>' + formatted + '</p>';
    }
    
    return formatted;
}

// Connection Management
function openConnectionModal() {
    loadConnectionsList();
    document.getElementById('connectionModal').style.display = 'flex';
}

async function loadConnectionsList() {
    try {
        const response = await fetch(`${API_BASE}/connections`);
        const connections = await response.json();
        
        const listDiv = document.getElementById('connectionsList');
        listDiv.innerHTML = '';
        
        connections.forEach(conn => {
            const item = document.createElement('div');
            item.className = 'connection-item';
            item.innerHTML = `
                <div class="connection-info">
                    <h4>${conn.name}</h4>
                    <p><strong>ID:</strong> ${conn.id}</p>
                    <p><strong>Type:</strong> ${conn.backend_type}</p>
                    <p><strong>URL:</strong> ${conn.url}</p>
                    <p><strong>Model:</strong> ${conn.model}</p>
                </div>
                <button class="btn btn-danger" onclick="deleteConnection('${conn.id}')">🗑️ Löschen</button>
            `;
            listDiv.appendChild(item);
        });
    } catch (error) {
        console.error('Fehler beim Laden der Connections:', error);
    }
}

async function addConnection(e) {
    e.preventDefault();
    
    const connection = {
        id: document.getElementById('newConnId').value,
        name: document.getElementById('newConnName').value,
        backend_type: document.getElementById('newConnType').value,
        url: document.getElementById('newConnUrl').value,
        model: document.getElementById('newConnModel').value,
        api_key: document.getElementById('newConnApiKey').value || null,
        timeout: parseInt(document.getElementById('newConnTimeout').value)
    };
    
    try {
        const response = await fetch(`${API_BASE}/connections`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(connection)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail);
        }
        
        showSuccess('Connection erfolgreich hinzugefügt');
        document.getElementById('newConnectionForm').reset();
        loadConnections();
        loadConnectionsList();
        
    } catch (error) {
        showError(error.message);
    }
}

window.deleteConnection = async function(connectionId) {
    if (!confirm('Connection wirklich löschen?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/connections/${connectionId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Löschen fehlgeschlagen');
        
        showSuccess('Connection gelöscht');
        loadConnections();
        loadConnectionsList();
        
    } catch (error) {
        showError(error.message);
    }
};

// Helper Functions
function showError(message) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `<div class="error-message">❌ ${message}</div>`;
}

function showSuccess(message) {
    const resultsDiv = document.getElementById('results');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `<div class="success-message">✅ ${message}</div>`;
    setTimeout(() => {
        resultsDiv.style.display = 'none';
    }, 3000);
}
