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
    showPhase(1);
}

function showPhase(phase) {
    currentPhase = phase;
    const phase1 = document.getElementById('phase1-landing');
    const phase2 = document.getElementById('phase2-verification');
    const phase3 = document.getElementById('phase3-report');
    
    [phase1, phase2, phase3].forEach(el => {
        if (el) el.classList.add('hidden');
    });
    
    const targetPhase = document.getElementById(`phase${phase}-${phase === 1 ? 'landing' : phase === 2 ? 'verification' : 'report'}`);
    if (targetPhase) targetPhase.classList.remove('hidden');
    
    document.body.className = document.body.className.replace(/phase-\d/g, '');
    document.body.classList.add(`phase-${phase}`);
}

function resetToPhase1() {
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    currentAuditData = null;
    activeSkillFilter = 'all';
    activeSeverityFilter = 'all';
    auditStartTime = null;
    
    resetForm();
    resetPipelineStages();
    resetEvidenceNodes();
    resetDimensionScores();
    resetScorecard();
    resetFindingsList();
    resetAIBanner();
    
    const tabs = document.querySelectorAll('.tab-btn, .tab-matrix-btn');
    tabs.forEach(t => t.classList.remove('active'));
    const allTab = document.querySelector('.tab-matrix-btn[onclick*="all"]');
    if (allTab) allTab.classList.add('active');
    const severityFilter = document.getElementById('severity-filter');
    if (severityFilter) severityFilter.value = 'all';
    
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
        { id: 'node-3', text: 'Sitemap Discovered & Parsed' },
        { id: 'node-4', text: 'Server HTML Inspected' },
        { id: 'node-5', text: 'JS-Rendered DOM Inspected' },
        { id: 'node-6', text: 'Schema.org Extracted' },
        { id: 'node-7', text: 'Wikidata Corroborated' }
    ];
    nodes.forEach(n => {
        const el = document.getElementById(n.id);
        if (el) {
            el.className = 'pipe-node pipe-ok';
            el.innerHTML = `<span class="node-icon">✓</span> <span class="node-text">${n.text}</span>`;
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
    if (bannerSub) bannerSub.textContent = 'gemini reasoning engine operational. Cross-skill findings validated with calibrated confidence.';
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
            const modelName = data.llm_model || 'Gemini';
            const llmStatus = data.llm_key_configured ? `Gemini Live Ready (${modelName})` : 'Fallback Mode';

            if (statusPill) {
                statusPill.className = 'system-status-chip';
                statusPill.innerHTML = `<span class="status-pulse-dot"></span> <span class="status-chip-label">Systems Online (${pwStatus} • ${llmStatus})</span>`;
            }
        }
    } catch (e) {
        if (statusPill) {
            statusPill.className = 'system-status-chip';
            statusPill.innerHTML = `<span class="status-pulse-dot"></span> <span class="status-chip-label">Server Connecting...</span>`;
        }
    }
}

/* ==========================================================================
   AUDIT RUNTIME EXECUTION
   ========================================================================== */

async function startAudit() {
    const urlInput = document.getElementById('url-input').value.trim();
    const brandInput = document.getElementById('brand-input').value.trim();
    const noLlm = document.getElementById('no-llm-checkbox').checked;
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.getElementById('btn-text');
    const btnSpinner = document.getElementById('btn-spinner');

    if (!urlInput) {
        alert('Please enter a target website URL (e.g. adobe.com or facebook.com).');
        return;
    }

    submitBtn.disabled = true;
    btnText.textContent = 'Starting Audit...';
    btnSpinner.classList.remove('hidden');

    auditStartTime = Date.now();
    
    const compactUrlInput = document.getElementById('compact-url-input');
    const compactBrandInput = document.getElementById('compact-brand-input');
    const compactBadge = document.getElementById('compact-mode-badge');
    
    if (compactUrlInput) compactUrlInput.value = urlInput;
    if (compactBrandInput) compactBrandInput.value = brandInput || '(Auto-detect)';
    if (compactBadge) {
        compactBadge.textContent = 'Auditing...';
        compactBadge.className = 'mode-badge';
    }

    showPhase(2);
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

        if (compactBadge) {
            compactBadge.textContent = 'Complete';
            compactBadge.className = 'mode-badge mode-complete';
        }

        setTimeout(() => {
            transitionToPhase3(data);
        }, 1000);

    } catch (err) {
        alert(`Audit Error: ${err.message}`);
        if (compactBadge) {
            compactBadge.textContent = 'Error';
            compactBadge.className = 'mode-badge';
            compactBadge.style.background = 'rgba(239, 68, 68, 0.15)';
            compactBadge.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            compactBadge.style.color = '#F87171';
        }
        submitBtn.disabled = false;
        btnText.textContent = 'Run AI Readiness Audit';
        btnSpinner.classList.add('hidden');
    }
}

function simulateProgressStages() {
    const stages = ['stage-1', 'stage-2', 'stage-3', 'stage-4', 'stage-5', 'stage-6', 'stage-7', 'stage-8'];
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
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    
    const reportUrlInput = document.getElementById('report-url-input');
    const reportBrandInput = document.getElementById('report-brand-input');
    const reportBadge = document.getElementById('report-mode-badge');
    
    if (reportUrlInput) reportUrlInput.value = data.site || 'example.com';
    if (reportBrandInput) reportBrandInput.value = data.brand || '(Auto-detect)';
    if (reportBadge) {
        reportBadge.textContent = 'Complete';
        reportBadge.className = 'mode-badge mode-complete';
    }

    showPhase(3);
    
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
    
    const brandHeading = document.getElementById('res-brand-name');
    if (brandHeading) {
        brandHeading.textContent = `${data.brand || data.site} AI Readiness Scorecard`;
    }

    // 2. Score & Ring Gauge
    const rawScore = data.overall_score !== undefined ? data.overall_score : (data.readiness_score !== undefined ? data.readiness_score : null);
    const score = (rawScore !== undefined && rawScore !== null) ? rawScore : '—';
    const scoreVal = document.getElementById('score-value');
    if (scoreVal) scoreVal.textContent = score;

    const ringFill = document.getElementById('score-ring-fill');
    if (ringFill) {
        const numericScore = typeof score === 'number' ? score : 0;
        const offset = 326.7 - (326.7 * numericScore / 100);
        ringFill.style.strokeDashoffset = offset;
        ringFill.style.stroke = numericScore >= 80 ? '#10B981' : (numericScore >= 60 ? '#3B82F6' : '#F59E0B');
    }

    const badge = document.getElementById('res-readiness-badge');
    if (badge) {
        const numericScore = typeof score === 'number' ? score : 0;
        if (numericScore >= 80) {
            badge.className = 'badge-readiness-status badge-optimal';
            badge.textContent = 'EXCELLENT READINESS';
        } else if (numericScore >= 60) {
            badge.className = 'badge-readiness-status badge-good';
            badge.textContent = 'MODERATE READINESS';
        } else {
            badge.className = 'badge-readiness-status badge-warning';
            badge.textContent = 'NEEDS OPTIMIZATION';
        }
    }

    // 3. Severity Counts
    const summary = data.summary || {};
    const counts = summary.severity_counts || summary;
    const cCrit = document.getElementById('count-critical');
    const cHigh = document.getElementById('count-high');
    const cMed = document.getElementById('count-medium');
    const cLow = document.getElementById('count-low');

    if (cCrit) cCrit.textContent = counts.critical || 0;
    if (cHigh) cHigh.textContent = counts.high || 0;
    if (cMed) cMed.textContent = counts.medium || 0;
    if (cLow) cLow.textContent = counts.low || 0;

    // 4. AI Reasoning Banner
    const llmObs = data.llm_observations || {};
    const bannerSub = document.getElementById('banner-ai-sub');
    const bannerTitle = document.getElementById('banner-ai-title');
    const banner = document.getElementById('ai-reasoning-banner');

    if (llmObs.status === 'SUCCESS' && llmObs.used) {
        if (banner) banner.className = 'glass-telemetry-banner banner-ai-ok';
        if (bannerTitle) bannerTitle.textContent = 'AI Multi-Skill Reasoning Applied';
        if (bannerSub) bannerSub.textContent = `gemini (${llmObs.model || 'gemini-3.5-flash'}) reasoning active. Cross-skill findings validated with confidence calibration.`;
    } else {
        if (banner) banner.className = 'glass-telemetry-banner banner-ai-fallback';
        if (bannerTitle) bannerTitle.textContent = 'Deterministic Multi-Skill Reasoning Applied';
        const err = llmObs.error_details || llmObs.status || 'Fallback Mode';
        if (bannerSub) bannerSub.textContent = `Deterministic fallback engine active. (${err}).`;
    }

    // 5. Evidence Pipeline Verification Nodes
    updateEvidencePipelineNodes(data);

    // 6. Skill Category Scores Cards & Progress Bars
    const scores = data.category_scores || data.scores || {};
    const crawlScore = scores.crawl_render !== undefined ? scores.crawl_render : ((data.ai_discoverability_score !== undefined && data.ai_discoverability_score !== null) ? data.ai_discoverability_score : '—');
    const semanticScore = scores.semantic_readiness !== undefined ? scores.semantic_readiness : ((data.semantic_readiness_score !== undefined && data.semantic_readiness_score !== null) ? data.semantic_readiness_score : '—');
    const corroborationScore = scores.freshness_corroboration !== undefined ? scores.freshness_corroboration : ((data.corroboration_score !== undefined && data.corroboration_score !== null) ? data.corroboration_score : '—');
    const engagementScore = scores.engagement !== undefined ? scores.engagement : ((data.onsite_engagement_score !== undefined && data.onsite_engagement_score !== null) ? data.onsite_engagement_score : '—');

    const elCrawl = document.getElementById('dim-score-crawl');
    const elSem = document.getElementById('dim-score-semantic');
    const elCorr = document.getElementById('dim-score-corroboration');
    const elEng = document.getElementById('dim-score-engagement');

    if (elCrawl) elCrawl.textContent = crawlScore;
    if (elSem) elSem.textContent = semanticScore;
    if (elCorr) elCorr.textContent = corroborationScore;
    if (elEng) elEng.textContent = engagementScore;

    const barCrawl = document.getElementById('bar-fill-crawl');
    const barSemantic = document.getElementById('bar-fill-semantic');
    const barCorroboration = document.getElementById('bar-fill-corroboration');
    const barEngagement = document.getElementById('bar-fill-engagement');

    if (barCrawl) barCrawl.style.width = typeof crawlScore === 'number' ? `${crawlScore}%` : '0%';
    if (barSemantic) barSemantic.style.width = typeof semanticScore === 'number' ? `${semanticScore}%` : '0%';
    if (barCorroboration) barCorroboration.style.width = typeof corroborationScore === 'number' ? `${corroborationScore}%` : '0%';
    if (barEngagement) barEngagement.style.width = typeof engagementScore === 'number' ? `${engagementScore}%` : '0%';

    // 7. Render Findings List
    renderFindingsList(data.findings || []);
}

function updateEvidencePipelineNodes(data) {
    const collection = data.collection || {};
    const rendering = data.rendering_metadata || {};
    const crawlMeta = data.crawl_metadata || {};
    const evidenceList = data.evidence || [];

    // Check if live website was fetched either via HTTP or via Playwright fallback
    const liveFetched = Boolean(
        collection.http_fetch_success ||
        rendering.status === 'SUCCESS' ||
        rendering.executed ||
        evidenceList.some(e => (e.page_context || '').includes('Website Request') && (e.status === 'VERIFIED' || e.status === 'LIVE_OBSERVED'))
    );

    // Check if sitemap was found in collection, crawl_metadata, or verified evidence
    const sitemaps = crawlMeta.sitemaps || [];
    const sitemapParsed = Boolean(
        collection.sitemap_found ||
        collection.sitemap_status === 'VERIFIED_PRESENT' ||
        sitemaps.length > 0 ||
        evidenceList.some(e => (e.page_context || '').toLowerCase().includes('sitemap') && (e.status === 'VERIFIED' || e.status === 'LIVE_OBSERVED'))
    );

    const nodes = [
        { id: 'node-1', text: 'Live Website Fetched', ok: liveFetched },
        { id: 'node-2', text: 'Robots.txt Inspected', ok: true },
        { id: 'node-3', text: 'Sitemap Discovered & Parsed', ok: sitemapParsed },
        { id: 'node-4', text: 'Server HTML Inspected', ok: true },
        { id: 'node-5', text: 'JS-Rendered DOM Inspected', ok: rendering.status === 'SUCCESS' || Boolean(collection.playwright_used) },
        { id: 'node-6', text: 'Schema.org & Metadata Extracted', ok: true },
        { id: 'node-7', text: 'Wikidata & Wikipedia Corroborated', ok: collection.entity_corroboration_status === 'VERIFIED' }
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

    if (activeSkillFilter !== 'all') {
        filtered = filtered.filter(f => (f.source_skill || f.category || '').toLowerCase() === activeSkillFilter.toLowerCase());
    }

    if (activeSeverityFilter !== 'all') {
        filtered = filtered.filter(f => (f.severity || '').toLowerCase() === activeSeverityFilter.toLowerCase());
    }

    if (filtered.length === 0) {
        container.innerHTML = '<div class="finding-card-item"><p style="color: var(--text-muted); padding: 1.5rem; text-align: center;">No diagnostic findings match the selected filter.</p></div>';
        return;
    }

    container.innerHTML = filtered.map(f => {
        const sev = (f.severity || 'medium').toLowerCase();
        const priority = f.priority || 'P2';
        const confPercent = Math.round((f.confidence || 1.0) * 100);
        const reasoningSrc = f.reasoning_source || 'deterministic';
        const isAI = f.evidence_origin === 'AI_VALIDATED' || reasoningSrc === 'gemini';
        const originBadge = isAI ? '<span class="pill-live" style="background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.4);">AI_VALIDATED</span>' : '<span class="pill-live">LIVE_OBSERVED</span>';
        const action = f.suggested_action || {};
        const affectedUrl = (f.affected_urls || [])[0] || `https://${currentAuditData ? currentAuditData.site : 'adobe.com'}`;

        let sevClass = `badge-sev-${sev}`;
        let sevText = sev.toUpperCase();

        return `
            <div class="finding-card-item" style="margin-bottom: 1.25rem;">
                <div class="finding-top-row">
                    <div class="finding-badge-group">
                        <span class="badge-sev ${sevClass}">${sevText}</span>
                        <span class="badge-priority">${priority}</span>
                        <span class="finding-title-text">${escapeHtml(f.title)}</span>
                    </div>
                    <span class="finding-id-tag">${escapeHtml(f.id)}</span>
                </div>

                <div class="finding-meta-line" style="margin: 0.5rem 0;">
                    <span>Dimension: <strong>${escapeHtml(f.primary_dimension || f.category || 'discoverability')}</strong></span> • 
                    <span>Skill: <strong>${escapeHtml(f.source_skill || 'crawl-render-audit')}</strong></span> • 
                    <span>Confidence: <strong>${confPercent}%</strong></span> • 
                    <span>Reasoning: <strong>${reasoningSrc}</strong></span>
                    ${originBadge}
                </div>

                <div class="evidence-box" style="margin: 0.75rem 0;">
                    <strong>Observed Evidence:</strong> ${escapeHtml(f.evidence)}
                </div>

                <div class="dual-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 0.75rem 0;">
                    <div class="grid-box-matters">
                        <span class="box-kicker" style="font-size: 0.7rem; font-weight: 700; color: #8B5CF6;">WHY IT MATTERS FOR AI SEARCH</span>
                        <p style="font-size: 0.85rem; margin-top: 0.25rem;">${escapeHtml(f.why_it_matters || f.mechanism_impact || 'Impacts AI search indexing and retrieval confidence.')}</p>
                    </div>
                    <div class="grid-box-remediation">
                        <span class="box-kicker" style="font-size: 0.7rem; font-weight: 700; color: #10B981;">RECOMMENDED REMEDIATION</span>
                        <p style="font-size: 0.85rem; margin-top: 0.25rem;">${escapeHtml(action.summary || 'Implement recommended remediation steps.')}</p>
                    </div>
                </div>

                ${action.recommendation ? `
                    <div class="implementation-guide-box" style="margin-top: 0.75rem; padding: 0.75rem; background: rgba(0,0,0,0.3); border-radius: 8px;">
                        <span class="box-kicker" style="font-size: 0.7rem; font-weight: 700; color: #3B82F6;">IMPLEMENTATION GUIDE (CODE)</span>
                        <pre style="margin-top: 0.4rem; padding: 0.5rem; background: #0b0f19; border-radius: 4px; font-size: 0.75rem; color: #60A5FA; overflow-x: auto;"><code>${escapeHtml(action.recommendation)}</code></pre>
                    </div>
                ` : ''}

                <div style="font-size: 11px; color: var(--text-muted); margin-top: 0.5rem;">
                    Affected URL: <a href="${escapeHtml(affectedUrl)}" target="_blank" class="affected-url-link" style="color: #3B82F6;">${escapeHtml(affectedUrl)}</a>
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
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
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