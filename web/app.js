// Brand AI Readiness Audit — Three-Phase UI Application Controller
const API_BASE = 'http://127.0.0.1:8080';

let currentAuditData = null;
let activeSkillFilter = 'all';
let activeSeverityFilter = 'all';
let currentPhase = 1; // 1 = landing, 2 = verification, 3 = report
let auditStartTime = null;
let progressInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    bindExportBtn();
    initializePhase();
});

/* ==========================================================================
   PHASE MANAGEMENT
   ========================================================================== */

function initializePhase() {
    // Start in Phase 1 (landing)
    showPhase(1);
}

function showPhase(phase) {
    currentPhase = phase;
    const phase1 = document.getElementById('phase1-landing');
    const phase2 = document.getElementById('phase2-verification');
    const phase3 = document.getElementById('phase3-report');
    
    // Hide all phases first
    [phase1, phase2, phase3].forEach(el => {
        if (el) el.classList.add('hidden');
    });
    
    // Show target phase
    const targetPhase = document.getElementById(`phase${phase}-${phase === 1 ? 'landing' : phase === 2 ? 'verification' : 'report'}`);
    if (targetPhase) targetPhase.classList.remove('hidden');
    
    // Update body class for potential global styling
    document.body.className = document.body.className.replace(/phase-\d/g, '');
    document.body.classList.add(`phase-${phase}`);
}

function resetToPhase1() {
    // Clear progress interval
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    // Reset all state
    currentAuditData = null;
    activeSkillFilter = 'all';
    activeSeverityFilter = 'all';
    auditStartTime = null;
    
    // Reset form
    resetForm();
    
    // Reset pipeline stages
    resetPipelineStages();
    
    // Reset evidence pipeline nodes
    resetEvidenceNodes();
    
    // Reset dimension scores
    resetDimensionScores();
    
    // Reset scorecard
    resetScorecard();
    
    // Reset findings list
    resetFindingsList();
    
    // Reset AI reasoning banner
    resetAIBanner();
    
    // Reset filters
    activeSkillFilter = 'all';
    activeSeverityFilter = 'all';
    const tabs = document.querySelectorAll('.tab-btn, .tab-matrix-btn');
    tabs.forEach(t => t.classList.remove('active'));
    const allTab = document.querySelector('.tab-matrix-btn[onclick*="all"]');
    if (allTab) allTab.classList.add('active');
    const severityFilter = document.getElementById('severity-filter');
    if (severityFilter) severityFilter.value = 'all';
    
    // Show Phase 1
    showPhase(1);
}

function resetForm() {
    const urlInput = document.getElementById('url-input');
    const brandInput = document.getElementById('brand-input');
    const noLlmCheckbox = document.getElementById('no-llm-checkbox');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnSpinner = document.getElementById('btn-spinner');
    
    if (urlInput) urlInput.value = '';
    if (brandInput) brandInput.value = '';
    if (noLlmCheckbox) noLlmCheckbox.checked = false;
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.textContent = 'Run AI Readiness Audit';
    if (btnSpinner) btnSpinner.classList.add('hidden');
}

function resetPipelineStages() {
    const stages = ['stage-1', 'stage-2', 'stage-3', 'stage-4', 'stage-5', 'stage-6', 'stage-7', 'stage-8'];
    stages.forEach(s => {
        const el = document.getElementById(s);
        if (el) {
            el.className = 'stage-step waiting';
            const icon = el.querySelector('.stage-icon');
            if (icon) icon.textContent = '○';
        }
    });
    
    const statusLabel = document.getElementById('exec-current-status');
    if (statusLabel) {
        statusLabel.textContent = 'Initializing verification pipeline...';
    }
}

function resetEvidenceNodes() {
    const nodes = [
        { id: 'node-1', text: 'Live Website Fetched' },
        { id: 'node-2', text: 'Robots.txt Inspected' },
        { id: 'node-3', text: 'Sitemap Discovered...' },
        { id: 'node-4', text: 'Server HTML Inspected...' },
        { id: 'node-5', text: 'JS-Rendered DOM ...' },
        { id: 'node-6', text: 'Schema.org Extracted...' },
        { id: 'node-7', text: 'Wikidata Corroborated...' }
    ];
    nodes.forEach(n => {
        const el = document.getElementById(n.id);
        if (el) {
            el.className = 'pipe-node pipe-ok';
            el.innerHTML = `<span class="node-icon">✓</span> <span class="node-text">${n.text}</span>`;
        }
    });
    // Reset nodes 3 and 5 to unavail
    const unavailNodes = ['node-3', 'node-5'];
    unavailNodes.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.className = 'pipe-node pipe-unavail';
            const textEl = el.querySelector('.node-text');
            if (textEl) textEl.textContent = textEl.textContent.replace(' (Unavailable)', '');
        }
    });
}

function resetDimensionScores() {
    ['crawl', 'semantic', 'corroboration', 'engagement'].forEach(dim => {
        const scoreEl = document.getElementById(`dim-score-${dim}`);
        const barEl = document.getElementById(`bar-fill-${dim}`);
        if (scoreEl) scoreEl.textContent = '0';
        if (barEl) barEl.style.width = '0%';
    });
}

function resetScorecard() {
    const scoreValue = document.getElementById('score-value');
    const scoreRing = document.getElementById('score-ring-fill');
    const badge = document.getElementById('res-readiness-badge');
    const targetUrl = document.getElementById('res-target-url');
    const brandName = document.getElementById('res-brand-name');
    
    if (scoreValue) scoreValue.textContent = '0';
    if (scoreRing) scoreRing.style.strokeDashoffset = '326.7';
    if (badge) {
        badge.className = 'badge-readiness-status';
        badge.textContent = 'READY FOR AUDIT';
    }
    if (targetUrl) {
        targetUrl.textContent = 'run audit above';
        targetUrl.href = '#';
    }
    if (brandName) brandName.textContent = 'Brand AI Readiness Scorecard';
    
    // Reset severity counts
    ['critical', 'high', 'medium', 'low'].forEach(sev => {
        const el = document.getElementById(`count-${sev}`);
        if (el) el.textContent = '0';
    });
}

function resetFindingsList() {
    const findingsContainer = document.getElementById('findings-list-container');
    if (findingsContainer) {
        findingsContainer.innerHTML = `
            <div class="finding-glass-empty-state">
                <span class="empty-icon">🔍</span>
                <h4 class="empty-title">Ready to Inspect</h4>
                <p class="empty-desc">Enter any target website domain above and run the audit to populate real-time diagnostic findings, AI reasoning notes, and implementation guides.</p>
            </div>
        `;
    }
}

function resetAIBanner() {
    const bannerTitle = document.getElementById('banner-ai-title');
    const bannerSub = document.getElementById('banner-ai-sub');
    if (bannerTitle) bannerTitle.textContent = 'AI Multi-Skill Reasoning Active';
    if (bannerSub) bannerSub.textContent = 'gemini (gemini-3-flash-preview) reasoning engine operational. Cross-skill findings validated with calibrated confidence.';
}

/* ==========================================================================
   SYSTEM HEALTH CHECK
   ========================================================================== */

async function checkHealth() {
    const statusPill = document.getElementById('system-status-pill');
    try {
        const response = await fetch(`${API_BASE}/api/health`);
        if (response.ok) {
            const data = await response.json();
            const pwStatus = data.playwright_available ? 'Playwright Ready' : 'HTTP Only';
            const modelName = data.llm_model || 'Gemini 3.6-flash';
            const llmStatus = data.llm_key_configured ? `Gemini Live Ready (${modelName})` : 'Fallback Mode';

            if (statusPill) {
                statusPill.className = 'status-pill status-online';
                statusPill.innerHTML = `<span class="status-pulse-dot"></span> Systems Online (${pwStatus} • ${llmStatus})`;
            }
        }
    } catch (e) {
        if (statusPill) {
            statusPill.className = 'status-pill status-loading';
            statusPill.innerHTML = `<span class="status-pulse-dot"></span> Server Connecting...`;
        }
    }
}

/* ==========================================================================
   AUDIT RUNTIME EXECUTION & PROGRESS CONTROLLER
   ========================================================================== */

async function startAudit() {
    const urlInput = document.getElementById('url-input').value.trim();
    const brandInput = document.getElementById('brand-input').value.trim();
    const noLlm = document.getElementById('no-llm-checkbox').checked;
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnSpinner = document.getElementById('btn-spinner');

    if (!urlInput) {
        alert('Please enter a target website URL (e.g. facebook.com).');
        return;
    }

    submitBtn.disabled = true;
    btnText.textContent = 'Starting Audit...';
    btnSpinner.classList.remove('hidden');

    // Store audit start time
    auditStartTime = Date.now();
    
    // Update compact search bar inputs for Phase 2
    const compactUrlInput = document.getElementById('compact-url-input');
    const compactBrandInput = document.getElementById('compact-brand-input');
    const compactBadge = document.getElementById('compact-mode-badge');
    
    if (compactUrlInput) compactUrlInput.value = urlInput;
    if (compactBrandInput) compactBrandInput.value = brandInput || '(Auto-detect)';
    if (compactBadge) {
        compactBadge.textContent = 'Auditing...';
        compactBadge.className = 'mode-badge';
    }

    // Transition to Phase 2 (Verification)
    showPhase(2);
    
    // Reset and start progress animation
    resetPipelineStages();
    simulateProgressStages();

    try {
        const response = await fetch(`${API_BASE}/api/audit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: urlInput,
                brand: brandInput,
                no_llm: noLlm
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Audit execution failed');
        }

        currentAuditData = data;
        renderResults(data);

        // Update compact badge to complete
        if (compactBadge) {
            compactBadge.textContent = 'Complete';
            compactBadge.className = 'mode-badge mode-complete';
        }

        // Brief pause to show completion, then transition to Phase 3
        setTimeout(() => {
            transitionToPhase3(data);
        }, 1000);

    } catch (err) {
        alert(`Audit Error: ${err.message}`);
        // On error, show Phase 2 with error state
        if (compactBadge) {
            compactBadge.textContent = 'Error';
            compactBadge.className = 'mode-badge';
            compactBadge.style.background = 'rgba(239, 68, 68, 0.15)';
            compactBadge.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            compactBadge.style.color = '#F87171';
        }
        // Reset button
        submitBtn.disabled = false;
        btnText.textContent = 'Run AI Readiness Audit';
        btnSpinner.classList.add('hidden');
    }
}

function simulateProgressStages() {
    const stages = [
        'stage-1', 'stage-2', 'stage-3', 'stage-4', 'stage-5', 'stage-6', 'stage-7', 'stage-8'
    ];
    stages.forEach((s) => {
        const el = document.getElementById(s);
        if (el) {
            el.className = 'stage-step waiting';
            const icon = el.querySelector('.stage-icon');
            if (icon) icon.textContent = '○';
        }
    });

    let current = 0;
    progressInterval = setInterval(() => {
        if (current > 0 && current <= stages.length) {
            const prev = document.getElementById(stages[current - 1]);
            if (prev) {
                prev.className = 'stage-step complete';
                const icon = prev.querySelector('.stage-icon');
                if (icon) icon.textContent = '✓';
            }
        }

        if (current < stages.length) {
            const curr = document.getElementById(stages[current]);
            if (curr) {
                curr.className = 'stage-step running';
                const icon = curr.querySelector('.stage-icon');
                if (icon) icon.textContent = '●';
                
                const statusLabel = document.getElementById('exec-current-status');
                if (statusLabel) {
                    statusLabel.textContent = curr.textContent.trim();
                }
            }
            current++;
        } else {
            clearInterval(progressInterval);
            progressInterval = null;
        }
    }, 800);
}

function transitionToPhase3(data) {
    // Clear progress interval
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    // Update report compact bar inputs
    const reportUrlInput = document.getElementById('report-url-input');
    const reportBrandInput = document.getElementById('report-brand-input');
    const reportBadge = document.getElementById('report-mode-badge');
    
    if (reportUrlInput) reportUrlInput.value = data.site || 'example.com';
    if (reportBrandInput) reportBrandInput.value = data.brand || '(Auto-detect)';
    if (reportBadge) {
        reportBadge.textContent = 'Complete';
        reportBadge.className = 'mode-badge mode-complete';
    }

    // Show Phase 3
    showPhase(3);
    
    // Scroll to scorecard
    setTimeout(() => {
        const matrixEl = document.getElementById('matrix');
        if (matrixEl) {
            matrixEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 100);
}

/* ==========================================================================
   RESULTS RENDERER
   ========================================================================== */

function renderResults(data) {
    if (!data) return;

    // 1. Target Domain & Brand Title
    const siteUrl = data.site || 'target.com';
    const targetLink = document.getElementById('res-target-url');
    if (targetLink) {
        targetLink.textContent = siteUrl;
        targetLink.href = `https://${siteUrl}`;
    }
    
    document.getElementById('res-brand-name').textContent = `${data.brand || data.site} AI Readiness Scorecard`;

    // 2. Score Hierarchy & Gauge Circle Fill
    const score = data.readiness_score !== undefined ? data.readiness_score : 100;
    const scores = data.scores || {};
    const crawlScore = scores.crawl_render !== undefined ? scores.crawl_render : (data.ai_discoverability_score || 80);
    const semanticScore = scores.semantic_readiness !== undefined ? scores.semantic_readiness : 85;
    const corroborationScore = scores.freshness_corroboration !== undefined ? scores.freshness_corroboration : 100;
    const engagementScore = data.onsite_engagement_score !== undefined ? data.onsite_engagement_score : (scores.onsite_engagement || 75);

    document.getElementById('score-value').textContent = score;

    // SVG Ring Gauge fill calculation & dynamic color stroke
    const ringFill = document.getElementById('score-ring-fill');
    if (ringFill) {
        const offset = 326.7 - (326.7 * score / 100);
        ringFill.style.strokeDashoffset = offset;
        ringFill.style.stroke = score >= 80 ? '#10B981' : '#F97316';
    }

    const badge = document.getElementById('res-readiness-badge');
    if (badge) {
        if (score >= 80) {
            badge.className = 'badge-status excellent';
            badge.textContent = 'EXCELLENT READINESS';
        } else if (score >= 60) {
            badge.className = 'badge-status poor';
            badge.textContent = 'NEEDS OPTIMIZATION';
        } else {
            badge.className = 'badge-status poor';
            badge.textContent = 'NEEDS OPTIMIZATION';
        }
    }

    // 3. Severity Counts
    const summary = data.summary || {};
    document.getElementById('count-critical').textContent = summary.critical || 0;
    document.getElementById('count-high').textContent = summary.high || 0;
    document.getElementById('count-medium').textContent = summary.medium || 0;
    document.getElementById('count-low').textContent = summary.low || 0;

    // 4. AI Reasoning Banner
    const llmObs = data.llm_observations || {};
    const bannerSub = document.getElementById('banner-ai-sub');
    const bannerTitle = document.getElementById('banner-ai-title');
    if (bannerSub) {
        const modelDisplay = llmObs.model || 'gemini-3-flash-preview';
        if (llmObs.status === 'SUCCESS') {
            if (bannerTitle) bannerTitle.textContent = 'Live Dynamic AI Reasoning Active';
            bannerSub.textContent = `gemini (${modelDisplay}) live reasoning operational. Multi-skill findings validated with calibrated confidence.`;
        } else if (llmObs.status === 'RATE_LIMITED') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Live Gemini API Rate Limited 429 - Quota Exceeded. Create a new key at aistudio.google.com or enable billing, then update .env and restart server.)`;
        } else if (llmObs.status === 'INVALID_KEY') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Invalid API Key - HTTP 401/403).`;
        } else if (llmObs.status === 'NOT_CONFIGURED') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (No API Key Configured).`;
        } else if (llmObs.status === 'UNAVAILABLE') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (API Key Not Available).`;
        } else if (llmObs.status === 'DISABLED') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (AI Reasoning Disabled by Configuration).`;
        } else if (llmObs.status === 'CIRCUIT_OPEN') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Circuit Breaker Open - Repeated Failures).`;
        } else if (llmObs.status === 'PROVIDER_UNAVAILABLE') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Provider Service Unavailable - HTTP 5xx).`;
        } else if (llmObs.status === 'TIMEOUT') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Request Timeout).`;
        } else if (llmObs.status === 'MALFORMED_RESPONSE') {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            bannerSub.textContent = `Deterministic fallback engine active. (Malformed API Response).`;
        } else {
            if (bannerTitle) bannerTitle.textContent = 'Deterministic Fallback Engine Active';
            const errorDetail = llmObs.error_details || llmObs.status || 'Fallback Mode';
            bannerSub.textContent = `Deterministic fallback engine active. (${errorDetail}).`;
        }
    }


    // 5. Audit Evidence Pipeline Nodes
    updateEvidencePipelineNodes(data);

    // 6. Skill Category Scores Cards & Progress Bars
    document.getElementById('dim-score-crawl').textContent = crawlScore;
    document.getElementById('dim-score-semantic').textContent = semanticScore;
    document.getElementById('dim-score-corroboration').textContent = corroborationScore;
    document.getElementById('dim-score-engagement').textContent = engagementScore;

    const barCrawl = document.getElementById('bar-fill-crawl');
    const barSemantic = document.getElementById('bar-fill-semantic');
    const barCorroboration = document.getElementById('bar-fill-corroboration');
    const barEngagement = document.getElementById('bar-fill-engagement');

    if (barCrawl) barCrawl.style.width = `${crawlScore}%`;
    if (barSemantic) barSemantic.style.width = `${semanticScore}%`;
    if (barCorroboration) barCorroboration.style.width = `${corroborationScore}%`;
    if (barEngagement) barEngagement.style.width = `${engagementScore}%`;

    // 7. Render Findings List
    renderFindingsList(data.findings || []);
}

function updateEvidencePipelineNodes(data) {
    const collection = data.collection || {};

    const nodes = [
        { id: 'node-1', text: 'Live Website Fetched', ok: collection.http_fetch_success },
        { id: 'node-2', text: 'Robots.txt Inspected', ok: collection.robots_checked },
        { id: 'node-3', text: 'Sitemap Discovered & Parsed', ok: collection.sitemap_found },
        { id: 'node-4', text: 'Server HTML Inspected', ok: true },
        { id: 'node-5', text: 'JS-Rendered DOM Inspected', ok: collection.playwright_used },
        { id: 'node-6', text: 'Schema.org & Metadata Extracted', ok: true },
        { id: 'node-7', text: 'Wikidata & Wikipedia Corroborated', ok: collection.entity_corroboration_attempted }
    ];

    nodes.forEach(n => {
        const el = document.getElementById(n.id);
        if (el) {
            if (n.ok) {
                el.className = 'pipe-node pipe-ok';
                el.innerHTML = `<span class="node-icon">✓</span> <span class="node-text">${n.text}</span>`;
            } else {
                el.className = 'pipe-node pipe-unavail';
                el.innerHTML = `<span class="node-icon">⚠️</span> <span class="node-text">${n.text} (Unavailable)</span>`;
            }
        }
    });
}

function renderFindingsList(findings) {
    const container = document.getElementById('findings-list-container');
    if (!container) return;

    let filtered = findings || [];

    // Filter by Skill Tab
    if (activeSkillFilter !== 'all') {
        filtered = filtered.filter(f => (f.source_skill || '').toLowerCase() === activeSkillFilter.toLowerCase());
    }

    // Filter by Severity Dropdown
    if (activeSeverityFilter !== 'all') {
        filtered = filtered.filter(f => (f.severity || '').toLowerCase() === activeSeverityFilter.toLowerCase());
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div class="finding-card-item"><p style="color: var(--text-muted);">No diagnostic findings match the selected filter.</p></div>';
        return;
    }

    container.innerHTML = filtered.map(f => {
        const sev = (f.severity || 'medium').toLowerCase();
        const priority = f.priority || 'P2';
        const confPercent = Math.round((f.confidence || 1.0) * 100);
        const reasoningSrc = f.reasoning_source || 'deterministic';
        const origin = f.evidence_origin || 'LIVE_OBSERVED';
        const action = f.suggested_action || {};
        const affectedUrl = (f.affected_urls || [])[0] || `https://${currentAuditData ? currentAuditData.site : 'facebook.com'}`;

        let sevClass = `badge-sev-${sev}`;
        let sevText = sev.toUpperCase();

        return `
            <div class="finding-card-item">
                <div class="finding-top-row">
                    <div class="finding-badge-group">
                        <span class="badge-sev ${sevClass}">${sevText}</span>
                        <span class="badge-priority">${priority}</span>
                        <span class="finding-title-text">${escapeHtml(f.title)}</span>
                    </div>
                    <span class="finding-id-tag">${escapeHtml(f.id)}</span>
                </div>

                <div class="finding-meta-line">
                    <span>Category: <strong>${escapeHtml(f.primary_dimension || f.category || 'discoverability')}</strong></span> • 
                    <span>Skill: <strong>${escapeHtml(f.source_skill || 'crawl-render-audit')}</strong></span> • 
                    <span>Confidence: <strong>${confPercent}%</strong></span> • 
                    <span>Reasoning: <strong>${reasoningSrc}</strong></span>
                    <span class="pill-live">${origin}</span>
                </div>

                <div class="evidence-box">
                    <strong>Observed Evidence:</strong> ${escapeHtml(f.evidence)}
                </div>

                <div class="dual-grid">
                    <div class="grid-box-matters">
                        <span class="box-kicker">WHY IT MATTERS FOR AI SEARCH</span>
                        <p>${escapeHtml(f.why_it_matters || f.mechanism_impact || 'Impacts AI search indexing and retrieval confidence.')}</p>
                    </div>
                    <div class="grid-box-remediation">
                        <span class="box-kicker">RECOMMENDED REMEDIATION (WHAT)</span>
                        <p>${escapeHtml(action.summary || 'Implement recommended remediation steps.')}</p>
                    </div>
                </div>

                <div class="implementation-guide-box">
                    <span class="box-kicker">IMPLEMENTATION GUIDE (HOW)</span>
                    <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 4px;">${escapeHtml(action.how || 'Implement recommended HTML tags or server configuration.')}</p>
                    <p style="font-size: 11px; color: var(--text-muted);">Affected URL(s): <a href="${escapeHtml(affectedUrl)}" target="_blank" class="affected-url-link">${escapeHtml(affectedUrl)}</a></p>
                </div>
            </div>
        `;
    }).join('');
}

/* ==========================================================================
   FILTER & EXPORT HANDLERS
   ========================================================================== */

function filterSkill(skill, tabBtn) {
    activeSkillFilter = skill;
    const tabs = document.querySelectorAll('.tab-btn, .tab-matrix-btn');
    tabs.forEach(t => t.classList.remove('active'));
    if (tabBtn) tabBtn.classList.add('active');

    if (currentAuditData) {
        renderFindingsList(currentAuditData.findings || []);
    }
}

function filterSeverity(sev) {
    activeSeverityFilter = sev;
    if (currentAuditData) {
        renderFindingsList(currentAuditData.findings || []);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&')
        .replace(/</g, '<')
        .replace(/>/g, '>')
        .replace(/"/g, '"')
        .replace(/'/g, '&#039;');
}

function bindExportBtn() {
    const exportBtn = document.getElementById('export-json-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            if (!currentAuditData) {
                alert('No active audit report available to export.');
                return;
            }
            const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentAuditData, null, 2));
            const downloadAnchor = document.createElement('a');
            downloadAnchor.setAttribute("href", dataStr);
            const domainSlug = (currentAuditData.site || 'audit').replace(/[^a-z0-9]/gi, '_').toLowerCase();
            downloadAnchor.setAttribute("download", `brand_ai_audit_${domainSlug}.json`);
            document.body.appendChild(downloadAnchor);
            downloadAnchor.click();
            downloadAnchor.remove();
        });
    }
}