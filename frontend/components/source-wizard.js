/**
 * Source Wizard - TPT Job Erstellung
 * ===================================
 * 
 * 5-Step Wizard: Source → Schema/Tabelle → Spalten → Job-Steps → Erstellen
 * 
 * Verwendung:
 *   const wizard = new SourceWizard({
 *       container: '#wizardContainer',
 *       mode: 'fullscreen' | 'embedded',
 *       onJobCreated: (result) => { ... },
 *       onClose: () => { ... }
 *   });
 *   wizard.init();
 */

class SourceWizard {
    constructor(options) {
        this.container = document.querySelector(options.container);
        this.mode = options.mode || 'fullscreen';
        this.apiBaseUrl = options.apiBaseUrl || (window.METADAITA_CONFIG?.backend_url || `http://${window.location.hostname}:8010`) + '/api';
        this.onJobCreated = options.onJobCreated || (() => {});
        this.onClose = options.onClose || (() => {});
        
        // State
        this.currentStep = 1;
        this.totalSteps = 5;
        this.sourceSystems = [];
        this.selectedSource = null;
        this.schemas = [];
        this.selectedSchema = null;
        this.discoveredTables = [];
        this.selectedTable = null;
        this.columnMappings = [];
        this.jobStepConfig = {
            cleanup: true,
            dropTables: false,
            createTables: true,
            generateTpt: true,
            executeTpt: true
        };
        this.tptConfig = {
            operator: 'STREAM',
            maxSessions: 4,
            targetDatabase: ''  // Pflichtfeld - User muss auswählen
        };
    }
    
    async init() {
        this.render();
        await this.loadSourceSystems();
    }
    
    // =========================================================================
    // RENDERING
    // =========================================================================
    
    render() {
        this.container.innerHTML = `
            <div class="sw-wizard ${this.mode === 'embedded' ? 'sw-embedded' : 'sw-fullscreen'}">
                <div class="sw-header">
                    <h3>🧙 TPT Job Wizard</h3>
                    <button class="sw-btn-close" id="swBtnClose">✕ Abbrechen</button>
                </div>
                ${this.renderStepIndicator()}
                <div class="sw-content" id="swContent">
                    <div class="sw-loading"><div class="sw-spinner"></div><p>Lade...</p></div>
                </div>
                <div class="sw-footer">
                    <button class="sw-btn sw-btn-outline" id="swBtnPrev" disabled>← Zurück</button>
                    <button class="sw-btn sw-btn-primary" id="swBtnNext">Weiter →</button>
                </div>
            </div>
        `;
        this.bindGlobalEvents();
    }
    
    renderStepIndicator() {
        const steps = ['Source', 'Tabelle', 'Spalten', 'Job-Steps', 'Erstellen'];
        return `
            <div class="sw-steps">
                ${steps.map((label, i) => `
                    <div class="sw-step ${i + 1 === this.currentStep ? 'active' : ''} ${i + 1 < this.currentStep ? 'completed' : ''}">
                        <span class="sw-step-num">${i + 1 < this.currentStep ? '✓' : i + 1}</span>
                        <span class="sw-step-label">${label}</span>
                    </div>
                    ${i < steps.length - 1 ? '<div class="sw-step-connector"></div>' : ''}
                `).join('')}
            </div>
        `;
    }
    
    updateContent() {
        const content = document.getElementById('swContent');
        switch (this.currentStep) {
            case 1: content.innerHTML = this.renderStep1(); break;
            case 2: content.innerHTML = this.renderStep2(); break;
            case 3: content.innerHTML = this.renderStep3(); this.loadColumns(); break;
            case 4: content.innerHTML = this.renderStep4(); break;
            case 5: content.innerHTML = this.renderStep5(); break;
        }
        // Update step indicator
        document.querySelector('.sw-steps').outerHTML = this.renderStepIndicator();
        // Update buttons
        document.getElementById('swBtnPrev').disabled = this.currentStep === 1;
        document.getElementById('swBtnNext').textContent = this.currentStep === 5 ? '✓ Job erstellen' : 'Weiter →';
        // Bind step-specific events
        this.bindStepEvents();
    }
    
    // =========================================================================
    // STEP 1: Source System
    // =========================================================================
    
    renderStep1() {
        if (this.sourceSystems.length === 0) {
            return '<div class="sw-empty">Keine Source Systems konfiguriert</div>';
        }
        return `
            <div class="sw-step-content">
                <h4>Source System auswählen</h4>
                <div class="sw-source-cards">
                    ${this.sourceSystems.map(s => `
                        <div class="sw-source-card ${this.selectedSource?.source_system_id === s.source_system_id ? 'selected' : ''}"
                             data-id="${s.source_system_id}">
                            <div class="sw-source-code">${this.esc(s.source_system_code)}</div>
                            <span class="sw-source-type">${this.esc(s.source_type)}</span>
                            <div class="sw-source-name">${this.esc(s.source_system_name || '')}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    async loadSourceSystems() {
        try {
            const res = await fetch(`${this.apiBaseUrl}/sources`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.sourceSystems = await res.json();
            this.updateContent();
        } catch (err) {
            document.getElementById('swContent').innerHTML = `<div class="sw-error">❌ ${err.message}</div>`;
        }
    }
    
    selectSource(id) {
        this.selectedSource = this.sourceSystems.find(s => s.source_system_id === parseInt(id));
        this.schemas = [];
        this.selectedSchema = null;
        this.discoveredTables = [];
        this.selectedTable = null;
        this.columnMappings = [];
        // Update UI
        document.querySelectorAll('.sw-source-card').forEach(card => {
            card.classList.toggle('selected', parseInt(card.dataset.id) === this.selectedSource?.source_system_id);
        });
    }
    
    // =========================================================================
    // STEP 2: Schema + Tabelle
    // =========================================================================
    
    renderStep2() {
        if (!this.selectedSource) {
            return '<div class="sw-error">Bitte zuerst Source System auswählen</div>';
        }
        return `
            <div class="sw-step-content">
                <h4>Schema & Tabelle auswählen</h4>
                
                <div class="sw-form-row">
                    <label>Schema:</label>
                    <select id="swSchema" class="sw-select">
                        <option value="">-- Schema laden --</option>
                    </select>
                    <button class="sw-btn sw-btn-sm" id="swBtnLoadSchemas">🔄 Schemas laden</button>
                </div>
                
                <div class="sw-form-row">
                    <input type="text" id="swTableSearch" placeholder="Tabelle suchen..." class="sw-input sw-search">
                </div>
                
                <div class="sw-table-list" id="swTableList">
                    <div class="sw-hint">Wähle ein Schema und lade die Tabellen</div>
                </div>
            </div>
        `;
    }
    
    async loadSchemas() {
        const select = document.getElementById('swSchema');
        select.innerHTML = '<option value="">Lade...</option>';
        
        try {
            const res = await fetch(`${this.apiBaseUrl}/sources/${this.selectedSource.source_system_id}/schemas`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.schemas = await res.json();
            
            select.innerHTML = this.schemas.map(s => 
                `<option value="${this.esc(s)}" ${s === this.selectedSource.default_schema ? 'selected' : ''}>${this.esc(s)}</option>`
            ).join('');
            
            // Auto-select default schema and load tables
            if (this.selectedSource.default_schema && this.schemas.includes(this.selectedSource.default_schema)) {
                this.selectedSchema = this.selectedSource.default_schema;
                this.loadTables();
            } else if (this.schemas.length > 0) {
                this.selectedSchema = this.schemas[0];
                this.loadTables();
            }
            
            this.showToast(`${this.schemas.length} Schemas gefunden`, 'success');
        } catch (err) {
            select.innerHTML = '<option value="">Fehler beim Laden</option>';
            this.showToast(`Fehler: ${err.message}`, 'error');
        }
    }
    
    async loadTables() {
        const schema = document.getElementById('swSchema')?.value;
        if (!schema) return;
        
        this.selectedSchema = schema;
        const listEl = document.getElementById('swTableList');
        listEl.innerHTML = '<div class="sw-loading"><div class="sw-spinner"></div></div>';
        
        try {
            const url = new URL(`${this.apiBaseUrl}/sources/${this.selectedSource.source_system_id}/tables`);
            url.searchParams.set('schema', schema);
            
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            
            const result = await res.json();
            this.discoveredTables = result.tables || [];
            this.renderTableList();
            this.showToast(`${this.discoveredTables.length} Tabellen gefunden`, 'success');
        } catch (err) {
            listEl.innerHTML = `<div class="sw-error">❌ ${err.message}</div>`;
        }
    }
    
    renderTableList() {
        const listEl = document.getElementById('swTableList');
        const search = document.getElementById('swTableSearch')?.value?.toLowerCase() || '';
        const filtered = this.discoveredTables.filter(t => t.table_name.toLowerCase().includes(search));
        
        if (filtered.length === 0) {
            listEl.innerHTML = '<div class="sw-hint">Keine Tabellen gefunden</div>';
            return;
        }
        
        listEl.innerHTML = filtered.map(t => `
            <div class="sw-table-item ${this.selectedTable?.table_name === t.table_name ? 'selected' : ''}"
                 data-name="${this.esc(t.table_name)}">
                <span class="sw-table-name">${this.esc(t.table_name)}</span>
                <span class="sw-table-type">${t.table_type === 'BASE TABLE' ? 'Table' : 'View'}</span>
            </div>
        `).join('');
        
        // Bind click events
        listEl.querySelectorAll('.sw-table-item').forEach(item => {
            item.addEventListener('click', () => this.selectTable(item.dataset.name));
        });
    }
    
    selectTable(name) {
        this.selectedTable = this.discoveredTables.find(t => t.table_name === name);
        this.columnMappings = [];
        
        document.querySelectorAll('.sw-table-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.name === name);
        });
    }
    
    // =========================================================================
    // STEP 3: Spalten-Mapping
    // =========================================================================
    
    renderStep3() {
        if (!this.selectedTable) {
            return '<div class="sw-error">Bitte zuerst Tabelle auswählen</div>';
        }
        return `
            <div class="sw-step-content">
                <h4>Spalten-Mapping: ${this.esc(this.selectedTable.table_name)}</h4>
                
                <div class="sw-form-row">
                    <label>Target Database:</label>
                    <input type="text" id="swTargetDb" value="${this.esc(this.tptConfig.targetDatabase)}" class="sw-input">
                </div>
                
                <div class="sw-form-row">
                    <label>Target Table:</label>
                    <input type="text" id="swTargetTable" value="${this.esc(this.selectedTable.table_name)}" class="sw-input">
                </div>
                
                <div class="sw-column-grid" id="swColumnGrid">
                    <div class="sw-loading"><div class="sw-spinner"></div><p>Lade Spalten...</p></div>
                </div>
            </div>
        `;
    }
    
    async loadColumns() {
        const gridEl = document.getElementById('swColumnGrid');
        if (!gridEl) return;
        
        try {
            const url = new URL(`${this.apiBaseUrl}/sources/${this.selectedSource.source_system_id}/tables/${this.selectedTable.table_name}/columns`);
            url.searchParams.set('schema', this.selectedSchema);
            
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            
            const columns = await res.json();
            this.columnMappings = columns.map(col => ({
                source_column: col.column_name,
                target_column: col.column_name,
                source_type: col.data_type + (col.max_length ? `(${col.max_length})` : 
                             (col.precision ? `(${col.precision}${col.scale ? ',' + col.scale : ''})` : '')),
                target_type: col.td_data_type,
                tpt_schema_multiplier: col.tpt_schema_multiplier || 1,
                convert_template: col.convert_template || null
            }));
            
            gridEl.innerHTML = this.renderColumnGrid();
            this.bindColumnGridEvents();  // FIX: Events nach Grid-Render binden!
        } catch (err) {
            gridEl.innerHTML = `<div class="sw-error">❌ ${err.message}</div>`;
        }
    }
    
    bindColumnGridEvents() {
        // Event-Listener für Column-Mapping Inputs
        document.querySelectorAll('.sw-column-grid input').forEach(input => {
            input.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.idx);
                const field = e.target.dataset.field;
                if (this.columnMappings[idx]) {
                    this.columnMappings[idx][field] = e.target.value;
                    console.log(`Column ${idx} ${field} = ${e.target.value}`);
                }
            });
        });
    }
    
    renderColumnGrid() {
        if (this.columnMappings.length === 0) return '<div class="sw-hint">Keine Spalten</div>';
        
        return `
            <div class="sw-grid-header">
                <div>Source</div><div>Target</div><div>Source Type</div><div>Target Type</div>
            </div>
            ${this.columnMappings.map((m, i) => `
                <div class="sw-grid-row">
                    <div class="sw-cell-ro">${this.esc(m.source_column)}</div>
                    <div><input type="text" class="sw-input sw-input-sm" value="${this.esc(m.target_column)}" data-idx="${i}" data-field="target_column"></div>
                    <div class="sw-cell-ro">${this.esc(m.source_type)}</div>
                    <div><input type="text" class="sw-input sw-input-sm" value="${this.esc(m.target_type)}" data-idx="${i}" data-field="target_type"></div>
                </div>
            `).join('')}
        `;
    }
    
    // =========================================================================
    // STEP 4: Job-Steps
    // =========================================================================
    
    renderStep4() {
        return `
            <div class="sw-step-content">
                <h4>Job-Steps konfigurieren</h4>
                <p class="sw-hint">Alle Steps werden erzeugt und können einzeln ausgeführt werden.</p>
                
                <div class="sw-jobsteps">
                    <label class="sw-checkbox">
                        <input type="checkbox" id="swStepCleanup" ${this.jobStepConfig.cleanup ? 'checked' : ''}>
                        <span class="sw-step-order">10</span>
                        <strong>TPT Cleanup</strong> - Drop _ET, _UV, _WT, _LG; Release MLOAD
                    </label>
                    <label class="sw-checkbox">
                        <input type="checkbox" id="swStepDrop" ${this.jobStepConfig.dropTables ? 'checked' : ''}>
                        <span class="sw-step-order">20</span>
                        <strong>Drop Tables</strong> - Drop Target + Load Tabellen (optional)
                    </label>
                    <label class="sw-checkbox">
                        <input type="checkbox" id="swStepCreate" ${this.jobStepConfig.createTables ? 'checked' : ''}>
                        <span class="sw-step-order">30</span>
                        <strong>Create Tables</strong> - Create Target + Load Tabellen
                    </label>
                    <label class="sw-checkbox">
                        <input type="checkbox" id="swStepGenerate" ${this.jobStepConfig.generateTpt ? 'checked' : ''}>
                        <span class="sw-step-order">40</span>
                        <strong>Generate TPT</strong> - TPT Script aus Parameter-Set
                    </label>
                    <label class="sw-checkbox">
                        <input type="checkbox" id="swStepExecute" ${this.jobStepConfig.executeTpt ? 'checked' : ''}>
                        <span class="sw-step-order">50</span>
                        <strong>Execute TPT</strong> - tbuild ausführen
                    </label>
                </div>
                
                <div class="sw-options">
                    <h5>TPT Optionen</h5>
                    <div class="sw-form-row">
                        <label>Operator:</label>
                        <select id="swTptOperator" class="sw-select">
                            <option value="STREAM" ${this.tptConfig.operator === 'STREAM' ? 'selected' : ''}>Stream (INSERT)</option>
                            <option value="LOAD" ${this.tptConfig.operator === 'LOAD' ? 'selected' : ''}>Load (FastLoad)</option>
                            <option value="UPDATE" ${this.tptConfig.operator === 'UPDATE' ? 'selected' : ''}>Update (MultiLoad)</option>
                        </select>
                    </div>
                    <div class="sw-form-row">
                        <label>Max Sessions:</label>
                        <input type="number" id="swMaxSessions" value="${this.tptConfig.maxSessions}" class="sw-input sw-input-sm">
                    </div>
                </div>
            </div>
        `;
    }
    
    saveJobStepConfig() {
        this.jobStepConfig = {
            cleanup: document.getElementById('swStepCleanup')?.checked ?? true,
            dropTables: document.getElementById('swStepDrop')?.checked ?? false,
            createTables: document.getElementById('swStepCreate')?.checked ?? true,
            generateTpt: document.getElementById('swStepGenerate')?.checked ?? true,
            executeTpt: document.getElementById('swStepExecute')?.checked ?? true
        };
        this.tptConfig.operator = document.getElementById('swTptOperator')?.value || 'STREAM';
        this.tptConfig.maxSessions = parseInt(document.getElementById('swMaxSessions')?.value) || 4;
        // targetDatabase wird in Step 3 gespeichert (nextStep), hier NICHT überschreiben!
    }
    
    // =========================================================================
    // STEP 5: Preview + Erstellen
    // =========================================================================
    
    renderStep5() {
        const targetTable = document.getElementById('swTargetTable')?.value || this.selectedTable?.table_name;
        return `
            <div class="sw-step-content">
                <h4>Zusammenfassung</h4>
                
                <div class="sw-summary">
                    <div class="sw-summary-row"><strong>Source:</strong> ${this.esc(this.selectedSource?.source_system_code)}</div>
                    <div class="sw-summary-row"><strong>Schema:</strong> ${this.esc(this.selectedSchema)}</div>
                    <div class="sw-summary-row"><strong>Tabelle:</strong> ${this.esc(this.selectedTable?.table_name)}</div>
                    <div class="sw-summary-row"><strong>Target:</strong> ${this.esc(this.tptConfig.targetDatabase)}.${this.esc(targetTable)}</div>
                    <div class="sw-summary-row"><strong>Spalten:</strong> ${this.columnMappings.length}</div>
                    <div class="sw-summary-row"><strong>Operator:</strong> ${this.tptConfig.operator}</div>
                </div>
                
                <div class="sw-tabs">
                    <button class="sw-tab active" data-tab="params">Parameter-Set</button>
                    <button class="sw-tab" data-tab="ddl">DDL Preview</button>
                    <button class="sw-tab" data-tab="tpt">TPT Preview</button>
                </div>
                
                <div class="sw-tab-content" id="swTabContent">
                    <pre>${this.esc(JSON.stringify(this.buildParameterSet(), null, 2))}</pre>
                </div>
            </div>
        `;
    }
    
    buildParameterSet() {
        const targetTable = document.getElementById('swTargetTable')?.value || this.selectedTable?.table_name;
        return {
            source_system_id: this.selectedSource.source_system_id,
            source_table: `${this.selectedSchema}.${this.selectedTable.table_name}`,
            target_database: this.tptConfig.targetDatabase,
            target_table: targetTable,
            tpt_operator_type: this.tptConfig.operator,
            tpt_max_sessions: this.tptConfig.maxSessions,
            column_mappings: this.columnMappings.map(m => ({
                source_column: m.source_column,
                target_column: m.target_column,
                source_type: m.source_type,
                target_type: m.target_type
            })),
            job_steps: this.jobStepConfig
        };
    }
    
    showPreviewTab(tab) {
        document.querySelectorAll('.sw-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        const content = document.getElementById('swTabContent');
        
        switch (tab) {
            case 'params':
                content.innerHTML = `<pre>${this.esc(JSON.stringify(this.buildParameterSet(), null, 2))}</pre>`;
                break;
            case 'ddl':
                content.innerHTML = `<pre>-- DDL wird vom Backend generiert\n-- Target: ${this.tptConfig.targetDatabase}.${this.selectedTable?.table_name}\n\nCREATE TABLE ... (wird beim Job-Erstellen generiert)</pre>`;
                break;
            case 'tpt':
                content.innerHTML = `<pre>-- TPT Script wird vom Backend generiert\n-- Operator: ${this.tptConfig.operator}\n\nDEFINE JOB ... (wird beim Job-Erstellen generiert)</pre>`;
                break;
        }
    }
    
    // =========================================================================
    // JOB ERSTELLEN
    // =========================================================================
    
    async createJob() {
        const btn = document.getElementById('swBtnNext');
        btn.disabled = true;
        btn.textContent = 'Erstelle Job...';
        
        try {
            const params = this.buildParameterSet();
            
            const res = await fetch(`${this.apiBaseUrl}/sources/tpt-jobs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_system_id: params.source_system_id,
                    source_table: params.source_table,
                    target_database: params.target_database,
                    target_table: params.target_table,
                    tpt_operator_type: params.tpt_operator_type,
                    tpt_max_sessions: params.tpt_max_sessions,
                    column_mappings: params.column_mappings,  // FIX: Column Mappings mitsenden!
                    register_in_meta_table: true
                })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            
            const result = await res.json();
            this.showToast(`Job "${result.job_name}" erstellt!`, 'success');
            this.onJobCreated(result);
            
        } catch (err) {
            this.showToast(`Fehler: ${err.message}`, 'error');
            btn.disabled = false;
            btn.textContent = '✓ Job erstellen';
        }
    }
    
    // =========================================================================
    // NAVIGATION
    // =========================================================================
    
    nextStep() {
        // Validate current step
        if (this.currentStep === 1 && !this.selectedSource) {
            this.showToast('Bitte Source System auswählen', 'error');
            return;
        }
        if (this.currentStep === 2 && !this.selectedTable) {
            this.showToast('Bitte Tabelle auswählen', 'error');
            return;
        }
        
        // Save config before leaving step
        if (this.currentStep === 3) {
            this.tptConfig.targetDatabase = document.getElementById('swTargetDb')?.value || '';
        }
        if (this.currentStep === 4) {
            this.saveJobStepConfig();
        }
        
        // Create job on last step
        if (this.currentStep === 5) {
            this.createJob();
            return;
        }
        
        this.currentStep++;
        this.updateContent();
    }
    
    prevStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.updateContent();
        }
    }
    
    close() {
        this.onClose();
    }
    
    // =========================================================================
    // EVENTS
    // =========================================================================
    
    bindGlobalEvents() {
        document.getElementById('swBtnNext')?.addEventListener('click', () => this.nextStep());
        document.getElementById('swBtnPrev')?.addEventListener('click', () => this.prevStep());
        document.getElementById('swBtnClose')?.addEventListener('click', () => this.close());
    }
    
    bindStepEvents() {
        // Step 1: Source cards
        document.querySelectorAll('.sw-source-card').forEach(card => {
            card.addEventListener('click', () => this.selectSource(card.dataset.id));
        });
        
        // Step 2: Schema + Tables
        document.getElementById('swBtnLoadSchemas')?.addEventListener('click', () => this.loadSchemas());
        document.getElementById('swSchema')?.addEventListener('change', () => this.loadTables());
        document.getElementById('swTableSearch')?.addEventListener('input', () => this.renderTableList());
        
        // Step 5: Tabs
        document.querySelectorAll('.sw-tab').forEach(tab => {
            tab.addEventListener('click', () => this.showPreviewTab(tab.dataset.tab));
        });
        
        // Column mapping inputs - werden in bindColumnGridEvents() gebunden (nach Grid-Render)
    }
    
    // =========================================================================
    // UTILITIES
    // =========================================================================
    
    esc(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    
    showToast(msg, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `sw-toast sw-toast-${type}`;
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
    }
}

// Export for use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SourceWizard;
}
