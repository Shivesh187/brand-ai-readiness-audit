// Brand AI Readiness Audit — Original 1st UI Application Controller
const API_BASE = 'http://127.0.0.1:8080';

let currentAuditData = null;
let activeSkillFilter = 'all';
let activeSeverityFilter = 'all';

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    bindExportBtn();
});

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
            const llmStatus = data.llm_key_configured ? 'Gemini 3.6-flash Ready' : 'Fallback Mode';
            
            if (statusPill) {
                statusPill.className = 'status-pill status-online';
                statusPill.innerHTML = `<span class="status-dot"></span> System Operational (${pwStatus} • ${llmStatus})`;
            }
        }
    } catch (e) {
        if (statusPill) {
            statusPill.className = 'status-pill status-loading';
            statusPill.innerHTML = `<span class="status-dot"></span> Server Connecting...`;
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
    btnText.textContent = 'Auditing Brand...';
    btnSpinner.classList.remove('hidden');

    const progressSection = document.getElementById('progress-section');
    const resultsSection = document.getElementById('results-section');

    if (resultsSection) resultsSection.classList.add('hidden');
    if (progressSection) progressSection.classList.remove('hidden');

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

        setTimeout(() => {
            if (progressSection) progressSection.classList.add('hidden');
            if (resultsSection) resultsSection.classList.remove('hidden');
        }, 800);

    } catch (err) {
        alert(`Audit Error: ${err.message}`);
        if (progressSection) progressSection.classList.add('hidden');
    } finally {
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
            el.className = 'stage-item waiting';
            const icon = el.querySelector('.stage-icon');
            if (icon) icon.textContent = '○';
        }
    });

    let current = 0;
    const interval = setInterval(() => {
        if (current > 0 && current <= stages.length) {
            const prev = document.getElementById(stages[current - 1]);
            if (prev) {
                prev.className = 'stage-item complete';
                const icon = prev.querySelector('.stage-icon');
                if (icon) icon.textContent = '✓';
            }
        }

        if (current < stages.length) {
            const curr = document.getElementById(stages[current]);
            if (curr) {
                curr.className = 'stage-item running';
                const icon = curr.querySelector('.stage-icon');
                if (icon) icon.textContent = '●';
                
                const statusLabel = document.getElementById('exec-current-status');
                if (statusLabel) {
                    statusLabel.textContent = curr.textContent.trim();
                }
            }
            current++;
        } else {
            clearInterval(interval);
        }
    }, 600);
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
    if (bannerSub) {
        if (llmObs.status === 'SUCCESS') {
            bannerSub.textContent = `gemini (${llmObs.model || 'gemini-3.6-flash'}) reasoning active. Cross-skill findings validated with confidence calibration.`;
        } else {
            bannerSub.textContent = `Deterministic fallback engine active. (${llmObs.status || 'Fallback Mode'}).`;
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
    const tabs = document.querySelectorAll('.tab-btn');
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
