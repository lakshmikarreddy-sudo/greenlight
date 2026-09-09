import { fetchSamples, streamAnalyze } from './api.js';
import { buildExplanation } from './explain.js';

const $ = (id) => document.getElementById(id);

const scenarioButtons = $('scenarioButtons');
const scriptInput = $('scriptInput');
const analyzeBtn = $('analyzeBtn');
const clearBtn = $('clearBtn');
const resetBtn = $('resetBtn');
const eventLog = $('eventLog');
const pipelineList = $('pipelineList');
const briefContent = $('briefContent');
const emptyState = $('emptyState');
const briefDetails = $('briefDetails');
const analysisState = $('analysisState');
const activityState = $('activityState');
const decisionStatus = $('decisionStatus');
const inputHint = $('inputHint');
const demoModePanel = $('demoModePanel');
const pasteModePanel = $('pasteModePanel');
const tabDemo = $('tabDemo');
const tabPaste = $('tabPaste');
const topRisksMeta = $('topRisksMeta');
const toggleTech = $('toggleTech');
const toggleExplain = $('toggleExplain');
const explainPanel = $('explainPanel');
const explainJurisdiction = $('explainJurisdiction');
const explainSteps = $('explainSteps');
const explainStops = $('explainStops');
const explainCheck = $('explainCheck');
const emptyTitle = document.querySelector('#emptyState .empty-title');
const emptyCopy = document.querySelector('#emptyState .empty-copy');

const shortNames = {
  'brooklyn-drone-chase': 'Brooklyn Drone Chase',
  'svalbard-arctic': 'Svalbard Arctic',
  'savannah-pyro': 'Savannah Pyro'
};

const stageOrder = ['INGEST', 'EXTRACT', 'TRIAGE', 'RESEARCH', 'ASSESS', 'MITIGATE', 'GREENLIGHT'];
const eventStage = {
  analysis_started: 'INGEST',
  screenplay_parsed: 'EXTRACT',
  dependency_detected: 'TRIAGE',
  parallel_search_invoked: 'RESEARCH',
  evidence_received: 'RESEARCH',
  dependency_assessed: 'ASSESS',
  mitigation_generated: 'MITIGATE',
  brief_generated: 'GREENLIGHT',
  analysis_completed: 'GREENLIGHT',
  brief: 'GREENLIGHT'
};

// Session state. Results are retained until RESET DEMO.
const resultCache = new Map();
let selectedKey = null;
let selectedSampleId = null;
let selectedScenarioName = null;
let inputMode = 'demo';
let runSequence = 0;
let resetGeneration = 0;
let currentStageIndex = 0;
let stageTimer = null;

function cacheKeyForCurrentInput() {
  return selectedSampleId || 'custom';
}

function getStatusClass(status) {
  const value = String(status || '').toUpperCase();
  if (value === 'RED') return 'status-red';
  if (value === 'YELLOW') return 'status-yellow';
  if (value === 'GREEN') return 'status-green';
  return 'status-muted';
}

function statusRank(status) {
  const value = String(status || '').toUpperCase();
  return value === 'RED' ? 0 : value === 'YELLOW' ? 1 : 2;
}

function compactText(value, max = 155) {
  if (value == null) return '';
  let text = String(value)
    .replace(/\\\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  text = text.replace(/^REVIEW REQUIRED:\s*/i, '');
  text = text.replace(/^CRITICAL REGULATORY BLOCKER:\s*/i, '');
  text = text.replace(/\s*Evidence:\s*['"].*$/i, '');
  text = text.replace(/\s*Evidence:\s*.*$/i, '');

  return text.length > max ? `${text.slice(0, max - 1).trim()}…` : text;
}

function setAnalysisState(state, message) {
  if (!analysisState) return;
  analysisState.className = 'analysis-state';
  analysisState.classList.add({
    live: 'state-live',
    demo: 'state-demo',
    success: 'state-success',
    error: 'state-error',
    ready: 'state-ready'
  }[state] || 'state-ready');
  analysisState.textContent = message || 'READY';
}

function setActivityState(message) {
  if (activityState) activityState.textContent = message || '';
}

function applyPipelineIndex(index) {
  const safe = Math.max(0, Math.min(stageOrder.length - 1, index));
  currentStageIndex = safe;
  pipelineList?.querySelectorAll('li').forEach((li) => {
    const liIndex = stageOrder.indexOf(li.dataset.stage);
    li.classList.toggle('active', liIndex === safe);
    li.classList.toggle('done', liIndex >= 0 && liIndex < safe);
    li.classList.toggle('complete', liIndex === stageOrder.length - 1 && safe === stageOrder.length - 1);
  });
}

function resetPipeline() {
  if (stageTimer) clearTimeout(stageTimer);
  stageTimer = null;
  applyPipelineIndex(0);
}

// Keep each pipeline phase visible long enough for a judge to understand it.
// The backend event order remains untouched; this is presentation-only.
function advancePipelineTo(stage) {
  const target = stageOrder.indexOf(stage);
  if (target < 0) return;
  if (target <= currentStageIndex) return;

  const advanceOne = () => {
    if (currentStageIndex >= target) return;
    applyPipelineIndex(currentStageIndex + 1);
    if (currentStageIndex < target) {
      stageTimer = setTimeout(advanceOne, 320);
    } else {
      stageTimer = null;
    }
  };

  const delay = currentStageIndex < target ? 220 : 0;
  if (stageTimer) clearTimeout(stageTimer);
  stageTimer = setTimeout(advanceOne, delay);
}

function completePipeline() {
  if (stageTimer) clearTimeout(stageTimer);
  stageTimer = null;
  pipelineList?.querySelectorAll('li').forEach((li) => {
    li.classList.remove('active');
    li.classList.add('done');
    li.classList.toggle('complete', li.dataset.stage === 'GREENLIGHT');
  });
  currentStageIndex = stageOrder.length - 1;
}

function eventMessage(evt) {
  const parsed = evt?.parsed || {};
  const data = evt?.data || {};

  switch (evt?.event) {
    case 'analysis_started':
      return 'Screenplay received';
    case 'screenplay_parsed':
      return 'Scenes and production elements extracted';
    case 'dependency_detected':
      return 'Production dependencies triaged';
    case 'parallel_search_invoked':
      return 'Researching production dependencies…';
    case 'evidence_received': {
      const count = parsed.source_count ?? parsed.sources_count ?? parsed.count ??
        data.source_count ?? data.sources_count ?? data.count;
      return count ? `External evidence received · ${count} source${count === 1 ? '' : 's'}` : 'External evidence received';
    }
    case 'dependency_assessed':
      return compactText(parsed.message || data.message || 'Production risk assessed', 125);
    case 'mitigation_generated':
      return compactText(parsed.message || data.message || 'Mitigation plan prepared', 125);
    case 'brief_generated':
      return 'Production decision generated';
    case 'analysis_completed':
      return 'Production intelligence analysis completed successfully.';
    default: {
      const message = parsed.message ?? (typeof data === 'object' ? data.message : data);
      return message ? compactText(message, 140) : 'Analysis update';
    }
  }
}

function renderEvents(cache) {
  if (!eventLog) return;
  eventLog.innerHTML = '';

  if (!cache?.events?.length) {
    eventLog.innerHTML = '<div class="empty-log">No audit events yet.</div>';
    return;
  }

  // Grouped by pipeline phase rather than raw network arrival order: parallel
  // research genuinely returns asynchronously. Arrival order is preserved
  // within a phase.
  const ordered = cache.events
    .map((evt, seq) => ({ evt, seq }))
    .sort((a, b) => {
      const stageA = stageOrder.indexOf(eventStage[a.evt?.event] || 'INGEST');
      const stageB = stageOrder.indexOf(eventStage[b.evt?.event] || 'INGEST');
      return stageA - stageB || a.seq - b.seq;
    });

  // Collapse repeated identical stage+message rows so parallel research does
  // not flood the panel. Nothing is fabricated: the count is the real number
  // of events received, and the timestamp is the latest occurrence.
  const rows = [];
  const seen = new Map();

  ordered.forEach(({ evt }) => {
    const stage = eventStage[evt?.event] || 'INGEST';
    const message = eventMessage(evt);
    const key = `${stage}|${message}`;
    const existing = seen.get(key);

    if (existing) {
      existing.count += 1;
      if (evt?._receivedAt) existing.time = evt._receivedAt;
      return;
    }

    const row = { stage, message, count: 1, time: evt?._receivedAt || null };
    seen.set(key, row);
    rows.push(row);
  });

  // Keep the activity panel readable; do not let it grow indefinitely.
  rows.slice(-16).forEach((row) => {
    const item = document.createElement('div');
    item.className = 'event';
    item.dataset.stage = row.stage;

    const meta = document.createElement('div');
    meta.className = 'meta';
    const time = row.time ? new Date(row.time).toLocaleTimeString() : new Date().toLocaleTimeString();
    meta.textContent = row.count > 1
      ? `${row.stage} · ${time} · ×${row.count}`
      : `${row.stage} · ${time}`;

    const message = document.createElement('div');
    message.className = 'message';
    message.textContent = row.message;

    item.append(meta, message);
    eventLog.appendChild(item);
  });
}

function emptyResultPanels() {
  const defaults = {
    topRisksList: '<span class="muted">(none)</span>',
    evidenceList: '<span class="muted">(none)</span>',
    decisionChainList: '<span class="muted">(none)</span>',
    sceneBreakdownList: '<span class="muted">(none)</span>'
  };
  Object.entries(defaults).forEach(([id, html]) => {
    const el = $(id);
    if (el) el.innerHTML = html;
  });

  briefContent?.classList.add('hidden');
  emptyState?.classList.remove('hidden');

  // Deliberate empty state, not an error state.
  if (emptyTitle) emptyTitle.textContent = 'Ready to analyze';
  if (emptyCopy) emptyCopy.textContent = 'Run an analysis to uncover hidden production blockers.';

  $('overallStatus') && ($('overallStatus').className = 'verdict-pill status-muted');
  $('overallStatus') && ($('overallStatus').textContent = '--');
  $('readinessScore') && ($('readinessScore').textContent = '--');
  $('briefHeadline') && ($('briefHeadline').textContent = '');
  $('whyShort') && ($('whyShort').textContent = '—');
  $('nextShort') && ($('nextShort').textContent = '—');
  $('greenCount') && ($('greenCount').textContent = '0 Green');
  $('yellowCount') && ($('yellowCount').textContent = '0 Yellow');
  $('redCount') && ($('redCount').textContent = '0 Red');
  $('sceneCount') && ($('sceneCount').textContent = '');

  if (decisionStatus) {
    decisionStatus.textContent = 'READY';
    decisionStatus.className = 'decision-status muted';
  }
  if (topRisksMeta) topRisksMeta.textContent = '';
  if (briefDetails) {
    briefDetails.innerHTML = '';
    briefDetails.classList.add('hidden');
  }
  if (toggleTech) {
    toggleTech.textContent = 'View audit trail';
    toggleTech.setAttribute('aria-expanded', 'false');
  }
  clearExplanation();
  explainPanel?.classList.add('hidden');
  toggleExplain?.setAttribute('aria-expanded', 'false');
}

function renderWaitingState(message, copy) {
  emptyResultPanels();
  if (copy && emptyCopy) emptyCopy.textContent = copy;
  if (eventLog) eventLog.innerHTML = `<div class="empty-log">${message}</div>`;
  setActivityState(message);
  setAnalysisState('ready', 'READY');
  resetPipeline();
}

function getDependencies(data) {
  return Array.isArray(data?.assessed_dependencies) ? data.assessed_dependencies : [];
}

function sortedDependencies(data) {
  return [...getDependencies(data)].sort((a, b) => {
    return statusRank(a?.status) - statusRank(b?.status);
  });
}

function renderTopRisks(data) {
  const list = $('topRisksList');
  if (!list) return;
  list.innerHTML = '';

  const deps = sortedDependencies(data);
  if (!deps.length) {
    list.innerHTML = '<span class="muted">No major production risks identified.</span>';
    if (topRisksMeta) topRisksMeta.textContent = '0 flagged';
    return;
  }

  if (topRisksMeta) topRisksMeta.textContent = `${deps.length} flagged`;

  // Every flagged dependency is shown. Truncating to four silently hid three
  // of Svalbard's seven risks while the meta line still claimed seven.
  deps.forEach((dep) => {
    const item = document.createElement('div');
    item.className = 'risk-item';

    const head = document.createElement('div');
    head.className = 'item-head';

    const title = document.createElement('div');
    title.className = 'item-title';
    title.textContent = dep.element || 'Production dependency';

    const pill = document.createElement('span');
    pill.className = `mini-pill ${getStatusClass(dep.status)}`;
    pill.textContent = dep.status || '—';
    head.append(title, pill);

    const why = document.createElement('div');
    why.className = 'item-copy';
    why.textContent = compactText(dep.risk_description || 'Production review required.', 140);

    const action = document.createElement('div');
    action.className = 'item-meta action-line';
    action.textContent = `Next: ${compactText(dep.recommended_action || 'Review required.', 140)}`;

    item.append(head, why, action);
    list.appendChild(item);
  });
}

function renderEvidence(data) {
  const list = $('evidenceList');
  if (!list) return;
  list.innerHTML = '';

  // One card per distinct source, naming every dependency it supports. A
  // source cited by two dependencies previously named only the first, which
  // read as though evidence for the second was missing.
  const byKey = new Map();
  getDependencies(data).forEach((dep) => {
    const source = dep?.parallel_evidence;
    const key = source?.source_url || source?.source_title;
    if (!source || !key) return;
    if (!byKey.has(key)) byKey.set(key, { source, dependencies: [] });
    byKey.get(key).dependencies.push(dep.element);
  });

  const sources = [...byKey.values()];
  const cited = new Set(sources.flatMap((s) => s.dependencies));
  const uncited = getDependencies(data)
    .map((d) => d.element)
    .filter((e) => !cited.has(e));

  if (!sources.length) {
    list.innerHTML = '<span class="muted">No external evidence used.</span>';
    return;
  }

  sources.forEach(({ source, dependencies }) => {
    const card = document.createElement('div');
    card.className = 'evidence-card';

    const title = document.createElement('div');
    title.className = 'item-title';
    const link = document.createElement('a');
    link.href = source.source_url || '#';
    link.target = '_blank';
    link.rel = 'noreferrer noopener';
    link.textContent = source.source_title || 'External evidence';
    title.appendChild(link);

    const relevance = document.createElement('div');
    relevance.className = 'item-copy';
    relevance.textContent = `Supports: ${dependencies.join(' · ')}`;

    const meta = document.createElement('div');
    meta.className = 'item-meta';
    meta.textContent = source.publish_date ? `Published ${source.publish_date}` : 'External research';

    card.append(title, relevance, meta);
    list.appendChild(card);
  });

  // Make the dependency-to-source relationship explicit rather than leaving a
  // shorter list looking like an omission.
  const summary = document.createElement('div');
  summary.className = 'item-meta';
  summary.textContent = uncited.length
    ? `${sources.length} source(s) cited across ${cited.size} dependencies. `
      + `No source bound for: ${uncited.join(' · ')}.`
    : `${sources.length} source(s) cited across ${cited.size} of `
      + `${getDependencies(data).length} dependencies.`;
  list.appendChild(summary);
}

function renderDecisionChain(data) {
  const list = $('decisionChainList');
  if (!list) return;
  list.innerHTML = '';

  const deps = sortedDependencies(data);
  if (!deps.length) {
    list.innerHTML = '<span class="muted">No production dependencies identified.</span>';
    return;
  }

  deps.forEach((dep) => {
    const card = document.createElement('div');
    card.className = 'decision-card-item';

    const head = document.createElement('div');
    head.className = 'item-head';
    const title = document.createElement('div');
    title.className = 'item-title';
    title.textContent = dep.element || 'Production dependency';
    const pill = document.createElement('span');
    pill.className = `mini-pill ${getStatusClass(dep.status)}`;
    pill.textContent = dep.status || '—';
    head.append(title, pill);

    const evidence = document.createElement('div');
    evidence.className = 'chain-line';
    evidence.textContent = `Evidence → ${compactText(dep.parallel_evidence?.source_title || 'External research', 105)}`;

    const mitigation = document.createElement('div');
    mitigation.className = 'chain-line';
    mitigation.textContent = `Mitigation → ${compactText(dep.recommended_action || 'Review required.', 115)}`;

    card.append(head, evidence, mitigation);
    list.appendChild(card);
  });
}

function renderSceneBreakdown(data) {
  const list = $('sceneBreakdownList');
  if (!list) return;
  list.innerHTML = '';

  const scenes = Array.isArray(data?.scenes) ? data.scenes : [];
  if (!scenes.length) {
    list.innerHTML = '<span class="muted">No scenes available.</span>';
    return;
  }

  // Scene severity must follow the FINAL assessed status, not the pre-research
  // initial_risk, otherwise a scene can read YELLOW while the decision it feeds
  // is RED. Joined on element; initial_risk is only a fallback for a scene
  // dependency that has no matching assessment.
  const finalStatus = new Map(
    getDependencies(data).map((dep) => [dep?.element, dep?.status])
  );

  scenes.slice(0, 5).forEach((scene) => {
    const deps = Array.isArray(scene.dependencies) ? scene.dependencies : [];
    const statuses = deps.map((d) =>
      String(finalStatus.get(d?.element) || d?.initial_risk || '').toUpperCase()
    );
    const status = statuses.includes('RED') ? 'RED' :
      statuses.includes('YELLOW') ? 'YELLOW' : 'GREEN';

    const card = document.createElement('div');
    card.className = 'scene-card';

    const head = document.createElement('div');
    head.className = 'item-head';
    const title = document.createElement('div');
    title.className = 'item-title';
    title.textContent = `Scene ${scene.scene_number ?? '—'}`;
    const pill = document.createElement('span');
    pill.className = `mini-pill ${getStatusClass(status)}`;
    pill.textContent = status;
    head.append(title, pill);

    const slug = document.createElement('div');
    slug.className = 'item-meta scene-slug';
    slug.textContent = scene.slugline?.raw || 'Scene heading unavailable';

    const dependencyLine = document.createElement('div');
    dependencyLine.className = 'item-copy';
    dependencyLine.textContent = deps.length
      ? deps.slice(0, 3).map((d) => d.element).filter(Boolean).join(' · ')
      : 'No major production dependencies flagged';

    const impact = document.createElement('div');
    impact.className = 'item-impact';
    impact.textContent = status === 'RED'
      ? 'Impact: production may be blocked.'
      : status === 'YELLOW'
        ? 'Impact: proceed only with required controls.'
        : 'Impact: no major production impact identified.';

    card.append(head, slug, dependencyLine, impact);
    list.appendChild(card);
  });
}

function renderTrace(data) {
  if (!briefDetails) return;
  briefDetails.innerHTML = '';

  const scorecard = data?.scorecard || {};
  const dependencies = getDependencies(data);
  const evidenceCount = new Set(
    dependencies.map((d) => d?.parallel_evidence?.source_url || d?.parallel_evidence?.source_title).filter(Boolean)
  ).size;
  const scenes = scorecard.total_scenes ?? data.total_scenes ?? (data.scenes || []).length;
  const status = scorecard.overall_status ?? data.overall_status ?? '—';

  const rows = [
    ['Input', selectedScenarioName || 'Custom screenplay'],
    ['Pipeline', 'Ingest → Extract → Triage → Research → Assess → Mitigate → Decision'],
    ['Scenes', scenes],
    ['Dependencies', dependencies.length],
    ['Evidence', evidenceCount],
    ['Decision', status]
  ];

  rows.forEach(([label, value]) => {
    const row = document.createElement('div');
    row.className = 'trace-row';
    const key = document.createElement('span');
    key.className = 'trace-key';
    key.textContent = label;
    const val = document.createElement('span');
    val.className = 'trace-value';
    val.textContent = value ?? '—';
    row.append(key, val);
    briefDetails.appendChild(row);
  });
}

// streamAnalyze() hands every event over as { event, data, parsed } where
// `data` is the RAW JSON STRING off the wire and `parsed` is the decoded
// object. The backend wraps the brief as
//   { event_type, stage, message, timestamp, data: { scorecard, scenes, ... } }
// so the brief itself lives at evt.parsed.data. `data` being a non-empty
// string is truthy, which is why `brief?.data || {}` silently produced a
// string and every field read came back undefined.
// Normalize here, once, before anything renders.
function briefData(brief) {
  if (!brief || typeof brief !== 'object') return {};

  const parsed = brief.parsed;
  if (parsed && typeof parsed === 'object') {
    return parsed.data && typeof parsed.data === 'object' ? parsed.data : parsed;
  }

  // Only ever accept an object here, never the raw JSON string.
  return brief.data && typeof brief.data === 'object' ? brief.data : {};
}


function basisClass(basis) {
  if (basis === 'INHERENT') return 'basis-inherent';
  if (basis === 'UNVERIFIED') return 'basis-unverified';
  return 'basis-evidence';
}

function clearExplanation() {
  if (explainSteps) explainSteps.innerHTML = '';
  if (explainStops) explainStops.innerHTML = '';
  if (explainCheck) {
    explainCheck.textContent = '';
    explainCheck.className = 'explain-check';
  }
  if (explainJurisdiction) explainJurisdiction.textContent = '';
}

// Renders the readiness calculation so a judge can follow it line by line and
// add the numbers up themselves. Everything shown comes from the backend's
// score_breakdown; nothing here recomputes risk.
function renderExplanation(brief) {
  if (!explainPanel) return;

  const model = buildExplanation(briefData(brief));
  if (!model) {
    clearExplanation();
    if (explainCheck) explainCheck.textContent = 'No calculation available for this result.';
    return;
  }

  clearExplanation();

  if (explainJurisdiction && model.jurisdiction) {
    explainJurisdiction.textContent = `Jurisdiction applied: ${model.jurisdiction}`;
  }

  // D2: say plainly whether RED came from a hard stop or from accumulation.
  const basisLine = document.createElement('div');
  basisLine.className = 'explain-decision-basis';
  basisLine.dataset.basis = model.decisionBasis;
  basisLine.textContent = `Decision basis: ${model.decisionBasisLabel}`;
  explainSteps.appendChild(basisLine);

  const start = document.createElement('div');
  start.className = 'explain-step';
  start.innerHTML = `<div class="explain-step-head"><span class="explain-element">Starting readiness</span>`
    + `<span class="explain-math">${model.startingScore}</span></div>`;
  explainSteps.appendChild(start);

  model.rows.forEach((row) => {
    const step = document.createElement('div');
    step.className = 'explain-step';
    step.dataset.element = row.element;
    step.dataset.basis = row.basis;

    const head = document.createElement('div');
    head.className = 'explain-step-head';

    const name = document.createElement('span');
    name.className = 'explain-element';
    name.textContent = row.element;

    const pill = document.createElement('span');
    pill.className = `mini-pill ${row.severityClass}`;
    pill.textContent = row.severity;

    const math = document.createElement('span');
    math.className = 'explain-math';
    math.innerHTML = `${row.sharePercent}% of ${row.before} = `
      + `<span class="explain-penalty">-${row.penalty}</span> &rarr; ${row.after}`;

    head.append(name, pill, math);
    step.appendChild(head);

    // D5: the first link of the chain -- the words on the page that produced
    // this dependency. Taken verbatim from the backend model; never inferred.
    if (row.triggers.length || row.scenes.length) {
      const from = document.createElement('div');
      from.className = 'explain-detail explain-from-page';
      const quoted = row.triggers.map((t) => `"${t}"`).join(', ');
      const scenes = row.scenes.length ? ` \u00b7 Scene ${row.scenes.join(', ')}` : '';
      // The default location dependency matches no hazard phrase; say that
      // rather than printing an empty quotation.
      from.textContent = quoted
        ? `From the page: ${quoted}${scenes}`
        : `From the page: no specific hazard phrase matched${scenes}`;
      step.appendChild(from);
    }

    // The basis badge is the point of this panel: an evidence-backed
    // regulatory finding and a hazard-class baseline must never look alike.
    const basis = document.createElement('div');
    basis.className = `explain-basis ${basisClass(row.basis)}`;
    basis.textContent = row.basisLabel;
    step.appendChild(basis);

    const detail = document.createElement('div');
    detail.className = 'explain-detail';
    detail.textContent = row.basisNote;
    step.appendChild(detail);

    if (row.rationale) {
      const why = document.createElement('div');
      why.className = 'explain-detail';
      why.textContent = compactText(row.rationale, 180);
      step.appendChild(why);
    }

    if (row.citation) {
      const cite = document.createElement('div');
      cite.className = 'explain-detail';
      const link = document.createElement('a');
      link.href = row.citation.source_url || '#';
      link.target = '_blank';
      link.rel = 'noreferrer noopener';
      link.textContent = row.citation.source_title || row.citation.source_url;
      cite.append(document.createTextNode(`Evidence [${row.citation.authority_tier}]: `), link);
      step.appendChild(cite);
    } else {
      const none = document.createElement('div');
      none.className = 'explain-detail';
      none.textContent = 'No citation supports this classification.';
      step.appendChild(none);
    }

    if (row.factors.length) {
      const factors = document.createElement('div');
      factors.className = 'explain-detail';
      factors.textContent = `Adjustments: ${row.factors.join(', ')}`;
      step.appendChild(factors);
    }

    if (row.mitigationOffered && !row.mitigationAdopted) {
      const mitigation = document.createElement('div');
      mitigation.className = 'explain-detail';
      mitigation.textContent = 'A substitution exists but is not adopted, so it does not reduce this risk.';
      step.appendChild(mitigation);
    }

    explainSteps.appendChild(step);
  });

  model.hardStops.forEach((stop) => {
    const el = document.createElement('div');
    el.className = `explain-stop${stop.affectsScore ? '' : ' constraint-only'}`;
    el.dataset.ruleId = stop.ruleId;
    el.textContent = stop.affectsScore
      ? `${stop.ruleId}: ${stop.reason}. Readiness ceiling ${stop.scoreCap} applied.`
      : `${stop.ruleId}: ${stop.reason}. Verdict constraint only \u2014 no change to the score.`;
    explainStops.appendChild(el);
  });

  if (model.ceilingAdjustment) {
    const adj = document.createElement('div');
    adj.className = 'explain-stop';
    adj.textContent = `Hard-stop ceiling removed a further ${model.ceilingAdjustment}.`;
    explainStops.appendChild(adj);
  }

  // The panel has to be checkable, not just readable.
  const holds = model.reconstructionHolds;
  explainCheck.className = `explain-check ${holds ? 'ok' : 'mismatch'}`;
  explainCheck.textContent = holds
    ? `${model.startingScore} \u2212 deductions${model.ceilingAdjustment ? ' \u2212 ceiling' : ''}`
      + ` = ${model.reconstructed} \u2014 matches the published readiness of ${model.finalScore}.`
    : `Calculation mismatch: the steps total ${model.reconstructed} but the published readiness is ${model.finalScore}.`;
}

function renderBrief(brief, cache = null) {
  try {
    renderBriefContent(brief, cache);
  } catch (error) {
    console.error('GREENLIGHT renderBrief failed', error, brief);
    handleAnalysisError('The production assessment could not be rendered.', cache);
  }
}

function renderBriefContent(brief, cache) {
  const data = briefData(brief);
  const scorecard = data.scorecard || {};
  const deps = sortedDependencies(data);
  const primary = deps[0];

  const status = String(scorecard.overall_status ?? data.overall_status ?? '').toUpperCase();
  const score = scorecard.readiness_score ?? data.readiness_score;
  const headline = scorecard.verdict_headline || 'Production assessment complete.';

  emptyState?.classList.add('hidden');
  briefContent?.classList.remove('hidden');

  const overall = $('overallStatus');
  if (overall) {
    overall.className = `verdict-pill ${getStatusClass(status)}`;
    overall.textContent = status || '—';
  }

  const readiness = $('readinessScore');
  if (readiness) readiness.textContent = score === 0 || score ? `${score}/100` : 'N/A';

  $('briefHeadline') && ($('briefHeadline').textContent = headline);

  // First-glance summary: deliberately shorter than the Top Risks card.
  const why = primary
    ? compactText(primary.risk_description || 'Production review required.', 130)
    : compactText(data.executive_summary || 'No primary production blocker identified.', 130);
  const next = primary
    ? compactText(primary.recommended_action || 'Review the production assessment.', 120)
    : compactText(data.recommended_next_steps?.[0] || 'Review the production assessment.', 120);

  $('whyShort') && ($('whyShort').textContent = why);
  $('nextShort') && ($('nextShort').textContent = next);

  const green = scorecard.green_count ?? data.green_count ?? 0;
  const yellow = scorecard.yellow_count ?? data.yellow_count ?? 0;
  const red = scorecard.red_count ?? data.red_count ?? 0;
  const scenes = scorecard.total_scenes ?? data.total_scenes ?? (data.scenes || []).length;

  $('greenCount') && ($('greenCount').textContent = `${green} Green`);
  $('yellowCount') && ($('yellowCount').textContent = `${yellow} Yellow`);
  $('redCount') && ($('redCount').textContent = `${red} Red`);
  $('sceneCount') && ($('sceneCount').textContent = `${scenes} scene${scenes === 1 ? '' : 's'}`);

  renderTopRisks(data);
  renderEvidence(data);
  renderDecisionChain(data);
  renderSceneBreakdown(data);
  renderTrace(data);
  renderExplanation(brief);

  if (decisionStatus) {
    decisionStatus.textContent = 'ANALYSIS COMPLETE';
    decisionStatus.className = `decision-status ${getStatusClass(status)}`;
  }

  if (cache) renderEvents(cache);
  setAnalysisState('success', 'COMPLETED');
  setActivityState('Analysis complete');

  // A completed run stays re-runnable. Selecting a scenario never re-runs it.
  if (analyzeBtn) {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze';
  }
}

function renderCached(key) {
  const cache = resultCache.get(key);
  const name = selectedScenarioName || 'Scenario';

  const enableAnalyze = () => {
    if (analyzeBtn) {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = 'Analyze';
    }
  };

  // Nothing analysed for this input yet. Other cache entries stay untouched.
  if (!cache) {
    if (key === 'custom') {
      renderWaitingState(
        'Paste your screenplay and click Analyze to start.',
        'Paste screenplay content, then click Analyze to run the production assessment.'
      );
    } else {
      renderWaitingState(
        `${name} selected — click Analyze to run.`,
        `${name} selected. Click Analyze to run the production assessment.`
      );
    }
    enableAnalyze();
    return;
  }

  // Completed result: brief, audit trail and a complete pipeline all return.
  // renderBrief re-enables Analyze.
  if (cache.brief) {
    renderBrief(cache.brief, cache);
    completePipeline();
    setActivityState('Analysis complete');
    setAnalysisState('success', 'COMPLETED');
    return;
  }

  // A run is still in flight for this key.
  if (cache.running) {
    emptyResultPanels();
    renderEvents(cache);
    setActivityState('Analysis in progress…');
    setAnalysisState('live', 'LIVE ANALYSIS');
    resetPipeline();

    // Rebuild the pipeline position from the events instead of replaying the
    // staged animation from INGEST.
    let highestStage = 0;
    cache.events.forEach((evt) => {
      const index = stageOrder.indexOf(eventStage[evt?.event]);
      if (index > highestStage) highestStage = index;
    });
    applyPipelineIndex(highestStage);

    if (analyzeBtn) {
      analyzeBtn.disabled = true;
      analyzeBtn.textContent = 'Analyzing…';
    }
    return;
  }

  // The run finished without a brief (error or interrupted stream).
  renderWaitingState(
    `${name} analysis did not complete. Click Analyze to retry.`,
    `${name} analysis did not complete. Click Analyze to run it again.`
  );
  enableAnalyze();
}

function selectScenario(id, button) {
  selectedSampleId = id;
  selectedScenarioName = shortNames[id] || id;
  selectedKey = id;
  inputMode = 'demo';

  scenarioButtons?.querySelectorAll('.scenario-btn').forEach((b) => {
    const active = b === button;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', active ? 'true' : 'false');
  });

  scriptInput.value = '';
  scriptInput.placeholder = `${selectedScenarioName} selected — click Analyze to run.`;
  if (inputHint) inputHint.textContent = 'Scenario selected. Click Analyze to run the production assessment.';

  // Restore this scenario's own cached result. Selection never runs an
  // analysis and never touches another scenario's cache entry.
  renderCached(selectedKey);
}

async function loadSamples() {
  try {
    const samples = await fetchSamples();
    scenarioButtons.innerHTML = '';
    samples.forEach((sample) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scenario-btn';
      button.dataset.sampleId = sample.id;
      button.setAttribute('aria-pressed', 'false');
      button.textContent = shortNames[sample.id] || sample.title || sample.id;
      button.addEventListener('click', () => selectScenario(sample.id, button));
      scenarioButtons.appendChild(button);
    });
  } catch (error) {
    console.error('Unable to load demo scenarios:', error);
    scenarioButtons.innerHTML = '<span class="muted">Demo scenarios unavailable. You can still paste a screenplay.</span>';
  }
}

function handleAnalysisError(message, cache) {
  if (cache) cache.running = false;
  setAnalysisState('error', 'ANALYSIS ERROR');
  setActivityState('Analysis failed');
  if (decisionStatus) {
    decisionStatus.textContent = 'ERROR';
    decisionStatus.className = 'decision-status status-red';
  }
  emptyState?.classList.add('hidden');
  briefContent?.classList.remove('hidden');

  const overall = $('overallStatus');
  if (overall) {
    overall.className = 'verdict-pill status-red';
    overall.textContent = 'ERROR';
  }
  $('readinessScore') && ($('readinessScore').textContent = '—');
  $('briefHeadline') && ($('briefHeadline').textContent = compactText(message || 'Unable to complete the production assessment.', 180));
  $('whyShort') && ($('whyShort').textContent = 'The production assessment did not complete.');
  $('nextShort') && ($('nextShort').textContent = 'Try Analyze again, or use Reset Demo to start over.');
}

async function runAnalysis() {
  const key = cacheKeyForCurrentInput();
  const generation = resetGeneration;
  const runId = ++runSequence;
  const payload = {};

  if (selectedSampleId) {
    payload.sample_id = selectedSampleId;
  } else {
    const text = scriptInput.value.trim();
    if (!text) {
      setActivityState('Paste a screenplay before clicking Analyze');
      scriptInput.focus();
      return;
    }
    payload.text = text;
    payload.format = 'text';
  }

  // Replace only this input's previous run. Other scenario results stay intact.
  const cache = { events: [], brief: null, running: true, runId, startedAt: Date.now() };
  resultCache.set(key, cache);

  // Render the run only if this input is currently visible.
  if (selectedKey === key) {
    emptyResultPanels();
    eventLog.innerHTML = '';
    resetPipeline();
    setActivityState('Starting analysis');
    setAnalysisState('live', 'LIVE ANALYSIS');
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing…';
  }

  try {
    await streamAnalyze(payload, (evt) => {
      // Retire this stream if the demo was reset, or if a newer run for this
      // same key has already replaced our cache entry.
      if (generation !== resetGeneration || cache.runId !== runId) return;
      if (resultCache.get(key) !== cache) return;

      evt._receivedAt = Date.now();
      cache.events.push(evt);

      // Always cache the event. Only paint it if the user is viewing this run.
      if (selectedKey === key) {
        renderEvents(cache);
        const stage = eventStage[evt?.event];
        if (stage) advancePipelineTo(stage);

        switch (evt?.event) {
          case 'analysis_started': setActivityState('Reading screenplay'); break;
          case 'screenplay_parsed': setActivityState('Extracting scenes and production elements'); break;
          case 'dependency_detected': setActivityState('Triaging production dependencies'); break;
          case 'parallel_search_invoked':
            setActivityState('Researching production dependencies…');
            setAnalysisState('live', 'RESEARCHING');
            break;
          case 'evidence_received': setActivityState(eventMessage(evt)); break;
          case 'dependency_assessed': setActivityState('Assessing production risk'); break;
          case 'mitigation_generated': setActivityState('Preparing mitigation plan'); break;
          case 'brief_generated': setActivityState('Generating production decision'); break;
          case 'brief':
            cache.brief = evt;
            cache.running = false;
            renderBrief(evt, cache);
            completePipeline();
            break;
          case 'analysis_completed':
            // The `brief` event is the authoritative final result. Never walk
            // the completed state back once it has rendered.
            setActivityState(cache.brief ? 'Analysis complete' : 'Finalizing production assessment');
            break;
          case 'analysis_error':
            cache.running = false;
            handleAnalysisError(eventMessage(evt), cache);
            break;
        }
      } else if (evt?.event === 'brief') {
        cache.brief = evt;
        cache.running = false;
      } else if (evt?.event === 'analysis_error') {
        // A background run must record its own failure, otherwise returning to
        // this scenario would show "Analysis in progress" forever.
        cache.running = false;
        cache.error = eventMessage(evt);
      }
    });
  } catch (error) {
    if (generation !== resetGeneration || cache.runId !== runId) return;
    if (resultCache.get(key) !== cache) return;
    console.error(error);
    cache.running = false;
    cache.error = error?.message || 'Unable to complete the production assessment.';
    cache.events.push({ event: 'analysis_error', parsed: { message: cache.error }, _receivedAt: Date.now() });
    if (selectedKey === key) {
      renderEvents(cache);
      handleAnalysisError(cache.error, cache);
    }
  } finally {
    // The stream is closed, so this run is no longer in flight whether or not
    // it produced a brief.
    cache.running = false;

    // The run is over either way: success, failure or stale. Analyze goes back
    // to being available so the judge is never stuck.
    if (generation === resetGeneration
      && selectedKey === key
      && cache.runId === runId
      && resultCache.get(key) === cache) {
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = 'Analyze';
    }
  }
}

function setInputMode(mode) {
  inputMode = mode === 'paste' ? 'paste' : 'demo';

  tabDemo?.classList.toggle('active', inputMode === 'demo');
  tabDemo?.setAttribute('aria-selected', inputMode === 'demo' ? 'true' : 'false');
  tabPaste?.classList.toggle('active', inputMode === 'paste');
  tabPaste?.setAttribute('aria-selected', inputMode === 'paste' ? 'true' : 'false');
  demoModePanel?.classList.toggle('hidden', inputMode !== 'demo');
  pasteModePanel?.classList.toggle('hidden', inputMode !== 'paste');

  if (inputMode === 'paste') {
    selectedSampleId = null;
    selectedScenarioName = null;
    selectedKey = 'custom';

    scenarioButtons?.querySelectorAll('.scenario-btn').forEach((button) => {
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    });

    scriptInput.value = '';
    scriptInput.placeholder = 'Paste screenplay content for analysis...';
    if (inputHint) inputHint.textContent = 'Paste screenplay content for analysis.';

    // Restores a cached custom result if one exists; never clears it.
    renderCached('custom');
    return;
  }

  // Switching tabs is not switching scenarios: keep the demo selection and its
  // cached result if the judge already picked one.
  if (selectedSampleId) {
    selectScenario(selectedSampleId, scenarioButtons?.querySelector(`[data-sample-id="${selectedSampleId}"]`));
    return;
  }

  scriptInput.value = '';
  scriptInput.placeholder = 'Select a demo scenario above...';
  if (inputHint) inputHint.textContent = 'Select a scenario, then click Analyze to run the production assessment.';

  renderWaitingState('Select a scenario and click Analyze to start.');
  if (analyzeBtn) {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze';
  }
}

analyzeBtn?.addEventListener('click', runAnalysis);

clearBtn?.addEventListener('click', () => {
  // Clear empties the screenplay input only. Reset Demo owns cache clearing.
  scriptInput.value = '';

  if (inputMode === 'paste') {
    scriptInput.placeholder = 'Paste screenplay content for analysis...';
    setActivityState('Input cleared');
    if (resultCache.has('custom')) renderCached('custom');
    return;
  }

  if (selectedScenarioName) {
    scriptInput.placeholder = `${selectedScenarioName} selected — click Analyze to run.`;
    setActivityState(`${selectedScenarioName} selected`);
    if (resultCache.has(selectedSampleId)) renderCached(selectedSampleId);
    return;
  }

  scriptInput.placeholder = 'Select a demo scenario above...';
  setActivityState('Input cleared');
});

resetBtn?.addEventListener('click', () => {
  resetGeneration += 1;
  resultCache.clear();
  selectedKey = null;
  selectedSampleId = null;
  selectedScenarioName = null;
  inputMode = 'demo';

  tabDemo?.classList.add('active');
  tabDemo?.setAttribute('aria-selected', 'true');
  tabPaste?.classList.remove('active');
  tabPaste?.setAttribute('aria-selected', 'false');
  demoModePanel?.classList.remove('hidden');
  pasteModePanel?.classList.add('hidden');

  scenarioButtons?.querySelectorAll('.scenario-btn').forEach((button) => {
    button.classList.remove('active');
    button.setAttribute('aria-pressed', 'false');
  });

  scriptInput.value = '';
  scriptInput.placeholder = 'Select a demo scenario above...';
  if (inputHint) inputHint.textContent = 'Select a scenario, then click Analyze to run the production assessment.';
  if (analyzeBtn) {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze';
  }

  emptyResultPanels();
  eventLog.innerHTML = '<div class="empty-log">Select a scenario and click Analyze to start.</div>';
  setActivityState('Waiting for input');
  resetPipeline();
  setAnalysisState('ready', 'READY');
});

tabDemo?.addEventListener('click', () => setInputMode('demo'));
tabPaste?.addEventListener('click', () => setInputMode('paste'));

toggleExplain?.addEventListener('click', (event) => {
  const open = !explainPanel.classList.contains('hidden');
  explainPanel.classList.toggle('hidden', open);
  event.currentTarget.setAttribute('aria-expanded', open ? 'false' : 'true');
});

toggleTech?.addEventListener('click', (event) => {
  const open = !briefDetails.classList.contains('hidden');
  briefDetails.classList.toggle('hidden', open);
  event.currentTarget.setAttribute('aria-expanded', open ? 'false' : 'true');
  event.currentTarget.textContent = open ? 'View audit trail' : 'Hide audit trail';
});

loadSamples();
