const app = document.getElementById('app');
const CROWE_LOGO_WHITE = '/static/assets/crowe-logo-white.svg';
const CROWE_LOGO_COLOR = '/static/assets/crowe-logo.svg';
const COGNOS_REPORT_URL = 'https://example.com/demo-cognos-report';

const ROLES = [
  'Partner',
  'Managing Director',
  'Senior Manager',
  'Manager',
  'Senior Staff',
  'Staff',
  'Intern',
  'Project Services',
  'Other',
];
const MODEL_TYPES = ['ALM', 'CECL', 'Stress Testing', 'AML/BSA', 'Other'];
const ADJUSTMENT_TYPES = ['markdown', 'c360', 'bima', 'change_order'];
const state = { expandedSnapshots: new Set() };

function svgIcon(name) {
  const paths = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-7h6v7"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
    settings: '<path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 9 19.35a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.07 14H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.65 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.07V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.65a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.37 9c.22.6.8 1 1.44 1H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    upload: '<path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M5 21h14"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/><path d="M12 7v5l3 2"/>',
    file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 15H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
  };
  return `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function money(value) {
  return Number(value || 0).toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
}

function num(value, digits = 1) {
  return Number(value || 0).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function pct(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function statusClass(status) {
  return String(status || 'On Track').replace(/\s+/g, '');
}

function progressClass(value, status) {
  if (status === 'Over Budget' || value >= 0.95) return 'over-budget';
  if (status === 'Watch' || value >= 0.8) return 'watch';
  return '';
}

async function api(path, options = {}) {
  const init = { ...options };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
    init.body = JSON.stringify(init.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok || (payload && payload.error)) {
    const message = payload?.error?.message || `Request failed: ${response.status}`;
    const error = new Error(message);
    error.payload = payload;
    throw error;
  }
  return payload.data;
}

function navLink(path, label, iconName) {
  const current = window.location.pathname;
  const active = current === path ? 'active' : '';
  return `<a class="nav-link ${active}" href="${path}" data-link>${svgIcon(iconName)}<span>${label}</span></a>`;
}

function shell(title, body, actions = '') {
  return `
    <div class="layout">
      <aside class="sidebar">
        <div class="brand">
          <a class="brand-mark" href="/" data-link>
            <img class="brand-logo" src="${CROWE_LOGO_WHITE}" alt="Crowe">
            <span class="brand-product">Budget Tracker</span>
          </a>
          <div class="brand-subtitle">Engagement controls</div>
        </div>
        <nav class="nav">
          ${navLink('/', 'Home', 'home')}
          ${navLink('/dashboard', 'Dashboard', 'file')}
          ${navLink('/engagements/new', 'New Engagement', 'plus')}
          ${navLink('/settings', 'Settings', 'settings')}
        </nav>
      </aside>
      <main class="main">
        <header class="topbar">
          <h1>${escapeHtml(title)}</h1>
          <div class="topbar-actions">${actions}</div>
        </header>
        <section class="content">${body}</section>
      </main>
    </div>
  `;
}

function setPage(title, body, actions = '') {
  app.innerHTML = shell(title, body, actions);
}

function loadingCard() {
  return '<div class="card"><div class="muted">Loading...</div></div>';
}

function showToast(message) {
  const old = document.querySelector('.toast');
  if (old) old.remove();
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

function bindLinks(root = document) {
  root.querySelectorAll('[data-link]').forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      navigate(link.getAttribute('href'));
    });
  });
}

function navigate(path) {
  window.history.pushState({}, '', path);
  render();
}

function renderLanding() {
  app.innerHTML = `
    <div class="landing-page">
      <header class="landing-topbar">
        <a class="landing-logo" href="/" data-link>
          <img src="${CROWE_LOGO_WHITE}" alt="Crowe">
          <span>Engagement Budget Tracker</span>
        </a>
        <nav class="landing-nav" aria-label="Primary">
          <a href="/dashboard" data-link>Dashboard</a>
          <a href="/engagements/new" data-link>New Engagement</a>
          <a href="/settings" data-link>Settings</a>
        </nav>
      </header>
      <main>
        <section class="landing-hero">
          <div class="landing-angle one"></div>
          <div class="landing-angle two"></div>
          <div class="landing-hero-copy">
            <div class="landing-kicker">Crowe engagement finance</div>
            <h1>Engagement Budget Tracker</h1>
            <p>Track budgets, Cognos imports, weekly snapshots, projected fees, and export-ready budget reporting from one focused control center.</p>
            <div class="landing-actions">
              <a class="btn primary landing-cta" href="/dashboard" data-link>${svgIcon('file')}Open Dashboard</a>
              <a class="btn ghost landing-cta" href="/engagements/new" data-link>${svgIcon('plus')}Start Engagement</a>
            </div>
          </div>
          <div class="landing-visual" aria-label="Engagement budget dashboard preview">
            <div class="landing-panel">
              <div class="preview-toolbar">
                <span></span><span></span><span></span>
                <strong>Weekly Budget Run</strong>
              </div>
              <div class="preview-grid">
                <div class="preview-stat amber"><span>Projected Final</span><strong>$25,950</strong></div>
                <div class="preview-stat teal"><span>Fees To Date</span><strong>$18,640</strong></div>
                <div class="preview-stat blue"><span>Hours Used</span><strong>64%</strong></div>
              </div>
              <div class="preview-chart">
                <div class="chart-row"><span>Budget</span><i style="width: 88%"></i></div>
                <div class="chart-row"><span>Actuals</span><i style="width: 62%"></i></div>
                <div class="chart-row"><span>Forecast</span><i style="width: 74%"></i></div>
              </div>
              <div class="preview-table">
                <div><span>Sample engagement</span><strong>On Track</strong></div>
                <div><span>Duplicate entries</span><strong>Skipped</strong></div>
                <div><span>Excel / PDF report</span><strong>Ready</strong></div>
              </div>
            </div>
          </div>
        </section>
        <section class="landing-workflow" aria-label="Workflow">
          <div class="workflow-heading">
            <div class="landing-kicker dark">Weekly operating rhythm</div>
            <h2>Import, review, report.</h2>
          </div>
          <div class="landing-feature-grid">
            <article class="landing-feature"><span>01</span><h3>Model the budget</h3><p>Set SOW fees, phase budgets, team rates, and expected hours before the work starts.</p></article>
            <article class="landing-feature"><span>02</span><h3>Load Cognos actuals</h3><p>Import weekly time and expense files with duplicate detection and validation flags.</p></article>
            <article class="landing-feature"><span>03</span><h3>Send the report</h3><p>Export formatted Excel, HTML, and PDF-ready views with run dates, charts, and clean totals.</p></article>
          </div>
        </section>
      </main>
    </div>
  `;
  bindLinks();
}
async function renderDashboard() {
  setPage('Dashboard', loadingCard(), `<a class="btn primary" href="/engagements/new" data-link>${svgIcon('plus')}New Engagement</a>`);
  bindLinks();
  try {
    const data = await api('/api/engagements');
    const metrics = data.metrics;
    const cards = data.engagements
      .map((engagement) => engagementCard(engagement))
      .join('') || '<div class="empty">No engagements yet.</div>';
    setPage(
      'Dashboard',
      `
      <div class="grid metric-grid">
        ${metricCard('Active Engagements', metrics.total_active_engagements)}
        ${metricCard('Hours MTD', num(metrics.total_hours_mtd))}
        ${metricCard('Fees MTD', money(metrics.total_fees_mtd))}
        ${metricCard('Watch / Over Budget', metrics.watch_or_over_budget)}
      </div>
      <div class="grid card-grid" style="margin-top:16px">${cards}</div>
      `,
      `<a class="btn primary" href="/engagements/new" data-link>${svgIcon('plus')}New Engagement</a>`
    );
    bindLinks();
  } catch (error) {
    setPage('Dashboard', `<div class="card">${escapeHtml(error.message)}</div>`);
  }
}

function metricCard(label, value) {
  return `<div class="card"><div class="metric-label">${label}</div><div class="metric-value">${value}</div></div>`;
}

function miniMetric(label, value) {
  return `<div class="row between"><span class="muted small">${label}</span><strong>${value}</strong></div>`;
}

function engagementCard(engagement) {
  const m = engagement.metrics || {};
  const hoursPct = m.total_budgeted_hours ? m.hours_to_date / m.total_budgeted_hours : 0;
  const feesPct = m.utilization_pct || 0;
  return `
    <a class="card stack" href="/engagements/${engagement.id}" data-link style="color:inherit;text-decoration:none">
      <div class="row between">
        <div>
          <div class="section-title">${escapeHtml(engagement.client_name)}</div>
          <div class="muted small">${escapeHtml(engagement.engagement_code)} - ${escapeHtml(engagement.engagement_lead || 'No lead')}</div>
        </div>
        ${statusBadge(m.status)}
      </div>
      <div class="stack tight">
        <div class="row between small"><span>Hours</span><span>${num(m.hours_to_date)} / ${num(m.total_budgeted_hours)}</span></div>
        <div class="progress ${progressClass(hoursPct, m.status)}"><span style="width:${Math.min(hoursPct * 100, 100)}%"></span></div>
      </div>
      <div class="stack tight">
        <div class="row between small"><span>Fees</span><span>${money(m.fees_to_date_contract)} / ${money(m.net_budget)}</span></div>
        <div class="progress ${progressClass(feesPct, m.status)}"><span style="width:${Math.min(feesPct * 100, 100)}%"></span></div>
      </div>
      <div class="muted small">Last import: ${escapeHtml(engagement.last_import_date || 'None')}</div>
    </a>
  `;
}

function statusBadge(status) {
  return `<span class="badge ${statusClass(status)}">${escapeHtml(status || 'On Track')}</span>`;
}

async function renderNewEngagement() {
  const settings = await api('/api/settings/rates').catch(() => ({ rates: {} }));
  const wizard = {
    step: 1,
    engagement: {
      engagement_code: '',
      client_name: '',
      model_type: '',
      model_vendor: '',
      engagement_lead: '',
      first_week_with_entry: '',
      max_sow_fees: 0,
      change_order_amt: 0,
    },
    team: [blankMember(settings.rates)],
    phases: [],
    rates: settings.rates || {},
  };

  function draw() {
    const titles = ['Engagement Info', 'Team', 'Phases'];
    setPage(
      'New Engagement',
      `
      <div class="wizard-steps">
        ${titles.map((title, idx) => `<div class="wizard-step ${wizard.step === idx + 1 ? 'active' : ''}"><div class="small muted">Step ${idx + 1}</div><strong>${title}</strong></div>`).join('')}
      </div>
      <div class="card stack">
        ${wizard.step === 1 ? engagementFields(wizard.engagement) : ''}
        ${wizard.step === 2 ? teamEditor(wizard.team, wizard.rates) : ''}
        ${wizard.step === 3 ? phaseEditor(wizard.phases) : ''}
        <div class="row between">
          <button class="btn secondary" id="wizard-back" ${wizard.step === 1 ? 'disabled' : ''}>Back</button>
          <div class="row">
            ${wizard.step < 3 ? '<button class="btn primary" id="wizard-next">Next</button>' : '<button class="btn primary" id="wizard-save">Save Engagement</button>'}
          </div>
        </div>
      </div>
      `
    );
    bindWizard();
  }

  function bindWizard() {
    bindLinks();
    document.querySelectorAll('[data-engagement-field]').forEach((field) => {
      field.addEventListener('input', () => {
        wizard.engagement[field.dataset.engagementField] = coerceField(field);
      });
    });
    const code = document.querySelector('[data-engagement-field="engagement_code"]');
    if (code) {
      code.addEventListener('blur', async () => {
        if (!code.value.trim()) return;
        const result = await api(`/api/engagements/check-code?code=${encodeURIComponent(code.value.trim())}`);
        if (!result.available) showToast('Engagement code already exists');
      });
    }
    document.querySelectorAll('[data-team-field]').forEach((field) => {
      field.addEventListener('input', () => {
        const member = wizard.team[Number(field.dataset.index)];
        member[field.dataset.teamField] = coerceField(field);
        if (field.dataset.teamField === 'role') {
          const rate = wizard.rates[field.value] || 0;
          member.internal_rate = rate;
          member.engagement_rate = rate;
          draw();
        } else if (['internal_rate', 'engagement_rate', 'budgeted_hours'].includes(field.dataset.teamField)) {
          updateTeamTotals(wizard.team);
        }
      });
    });
    document.querySelectorAll('[data-phase-field]').forEach((field) => {
      field.addEventListener('input', () => {
        wizard.phases[Number(field.dataset.index)][field.dataset.phaseField] = coerceField(field);
      });
    });
    document.querySelectorAll('[data-remove-team]').forEach((button) => {
      button.addEventListener('click', () => {
        wizard.team.splice(Number(button.dataset.removeTeam), 1);
        draw();
      });
    });
    document.querySelectorAll('[data-remove-phase]').forEach((button) => {
      button.addEventListener('click', () => {
        wizard.phases.splice(Number(button.dataset.removePhase), 1);
        draw();
      });
    });
    document.getElementById('add-team')?.addEventListener('click', () => {
      wizard.team.push(blankMember(wizard.rates));
      draw();
    });
    document.getElementById('add-phase')?.addEventListener('click', () => {
      wizard.phases.push({ phase_name: '', budgeted_hours: 0, budgeted_eng_fees: 0 });
      draw();
    });
    document.getElementById('wizard-back')?.addEventListener('click', () => {
      wizard.step = Math.max(1, wizard.step - 1);
      draw();
    });
    document.getElementById('wizard-next')?.addEventListener('click', () => {
      if (wizard.step === 1 && !validEngagementBasics(wizard.engagement)) return;
      wizard.step += 1;
      draw();
    });
    document.getElementById('wizard-save')?.addEventListener('click', async () => {
      if (!validEngagementBasics(wizard.engagement)) return;
      const team = wizard.team.filter((member) => member.name.trim());
      const phases = wizard.phases.filter((phase) => phase.phase_name.trim());
      try {
        const data = await api('/api/engagements', {
          method: 'POST',
          body: { engagement: wizard.engagement, team, phases },
        });
        showToast('Engagement saved');
        navigate(`/engagements/${data.engagement.id}`);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  draw();
}

function validEngagementBasics(engagement) {
  if (!engagement.engagement_code.trim() || !engagement.client_name.trim()) {
    showToast('Engagement code and client name are required');
    return false;
  }
  return true;
}

function blankMember(rates) {
  const rate = Number(rates?.Staff || 225);
  return { name: '', role: 'Staff', internal_rate: rate, engagement_rate: rate, budgeted_hours: 0 };
}

function coerceField(field) {
  if (field.type === 'checkbox') return field.checked;
  if (field.type === 'number') return Number(field.value || 0);
  return field.value;
}

function engagementFields(engagement) {
  return `
    <div class="form-grid">
      ${inputField('Engagement Code', 'engagement_code', engagement.engagement_code, 'text', true)}
      ${inputField('Client Name', 'client_name', engagement.client_name, 'text', true)}
      ${selectField('Model Type', 'model_type', engagement.model_type, MODEL_TYPES, 'data-engagement-field')}
      ${inputField('Model Vendor', 'model_vendor', engagement.model_vendor)}
      ${inputField('Engagement Lead', 'engagement_lead', engagement.engagement_lead)}
      ${inputField('First Week with Entry', 'first_week_with_entry', engagement.first_week_with_entry, 'date')}
      ${inputField('Max SOW Fees', 'max_sow_fees', engagement.max_sow_fees, 'number', true)}
      ${inputField('Change Order Amount', 'change_order_amt', engagement.change_order_amt, 'number')}
    </div>
  `;
}

function inputField(label, name, value, type = 'text', required = false, attr = 'data-engagement-field') {
  return `
    <div class="field">
      <label>${label}${required ? ' *' : ''}</label>
      <input type="${type}" ${attr}="${name}" value="${escapeHtml(value)}" ${required ? 'required' : ''} ${type === 'number' ? 'step="0.01"' : ''}>
    </div>
  `;
}

function selectField(label, name, value, options, attr, index = '') {
  return `
    <div class="field">
      <label>${label}</label>
      <select ${attr}="${name}" ${index}>
        <option value=""></option>
        ${options.map((option) => `<option value="${escapeHtml(option)}" ${option === value ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}
      </select>
    </div>
  `;
}

function teamEditor(team, rates) {
  const rows = team
    .map(
      (member, index) => `
      <tr>
        <td><input data-team-field="name" data-index="${index}" value="${escapeHtml(member.name)}" placeholder="Last, First"></td>
        <td>
          <select data-team-field="role" data-index="${index}">
            ${ROLES.map((role) => `<option value="${role}" ${role === member.role ? 'selected' : ''}>${role}</option>`).join('')}
          </select>
        </td>
        <td><input type="number" step="0.01" data-team-field="internal_rate" data-index="${index}" value="${member.internal_rate || 0}"></td>
        <td><input type="number" step="0.01" data-team-field="engagement_rate" data-index="${index}" value="${member.engagement_rate || 0}"></td>
        <td><input type="number" step="0.1" data-team-field="budgeted_hours" data-index="${index}" value="${member.budgeted_hours || 0}"></td>
        <td><button class="btn icon secondary" title="Remove" data-remove-team="${index}">${svgIcon('trash')}</button></td>
      </tr>`
    )
    .join('');
  return `
    <div class="row between">
      <h2 class="section-title">Team</h2>
      <button class="btn secondary" id="add-team">${svgIcon('plus')}Add Row</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Role</th><th>Crowe Bill Rate</th><th>Negotiated Rate</th><th>Budgeted Hours</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="row wrap muted small" id="team-totals">${teamTotals(team)}</div>
  `;
}

function updateTeamTotals(team) {
  const target = document.getElementById('team-totals');
  if (target) target.innerHTML = teamTotals(team);
}

function teamTotals(team) {
  const hours = team.reduce((sum, member) => sum + Number(member.budgeted_hours || 0), 0);
  const fees = team.reduce(
    (sum, member) => sum + Number(member.budgeted_hours || 0) * Number(member.engagement_rate || 0),
    0
  );
  return `<span>Total budgeted hours: ${num(hours)}</span><span>Total budgeted fees: ${money(fees)}</span>`;
}

function phaseEditor(phases) {
  const rows = phases
    .map(
      (phase, index) => `
      <tr>
        <td><input data-phase-field="phase_name" data-index="${index}" value="${escapeHtml(phase.phase_name)}"></td>
        <td><input type="number" step="0.1" data-phase-field="budgeted_hours" data-index="${index}" value="${phase.budgeted_hours || 0}"></td>
        <td><input type="number" step="0.01" data-phase-field="budgeted_eng_fees" data-index="${index}" value="${phase.budgeted_eng_fees || 0}"></td>
        <td><button class="btn icon secondary" title="Remove" data-remove-phase="${index}">${svgIcon('trash')}</button></td>
      </tr>`
    )
    .join('');
  return `
    <div class="row between">
      <h2 class="section-title">Phases</h2>
      <button class="btn secondary" id="add-phase">${svgIcon('plus')}Add Phase</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Phase</th><th>Budgeted Hours</th><th>Budgeted Fees</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="muted">No phases configured.</td></tr>'}</tbody>
      </table>
    </div>
  `;
}

async function renderEngagement(id, subroute = '') {
  if (subroute === 'team') return renderTeamConfig(id);
  if (subroute === 'import') return renderImport(id);
  if (subroute === 'adjustments') return renderAdjustments(id);
  if (subroute === 'history') return renderHistory(id);
  if (subroute === 'export') return renderExport(id);

  setPage('Engagement', loadingCard());
  try {
    const data = await api(`/api/engagements/${id}`);
    const e = data.engagement;
    const m = data.metrics;
    const isClosed = e.status === 'Closed';
    setPage(
      e.client_name,
      `
      ${engagementTabs(id)}
      <div class="card stack">
        <div class="row between wrap">
          <div>
            <div class="section-title">${escapeHtml(e.client_name)}</div>
            <div class="muted small">${escapeHtml(e.engagement_code)} - ${escapeHtml(e.engagement_lead || 'No lead')} - ${escapeHtml(e.model_type || 'No model type')}</div>
          </div>
          <div class="row">${statusBadge(m.status)}${isClosed ? '<span class="badge neutral">Closed</span>' : `<button class="btn secondary" id="close-engagement">${svgIcon('file')}Close and Export</button>`}</div>
        </div>
      </div>
      ${isClosed ? completionPanel(id, e) : ''}
      <div class="grid metric-grid" style="margin-top:16px">
        ${metricCard('Total Budgeted Hours', num(m.total_budgeted_hours))}
        ${metricCard('Hours To Date', num(m.hours_to_date))}
        ${metricCard('Hours Remaining', `${num(m.hours_remaining)} - ${pct(m.hours_remaining_pct)}`)}
        ${metricCard('Fees To Date', money(m.fees_to_date_contract))}
      </div>
      <div class="grid two-col" style="margin-top:16px">
        <div class="card stack">
          <div class="row between"><h2 class="section-title">Budget Position</h2><strong>${money(m.net_budget)}</strong></div>
          <div class="progress ${progressClass(m.utilization_pct, m.status)}"><span style="width:${Math.min(m.utilization_pct * 100, 100)}%"></span></div>
          <div class="row wrap muted small">
            <span>Projected final: ${money(m.projected_final)}</span>
            <span>Budget remaining: ${money(m.budget_remaining)}</span>
            <span>Markdown required: ${m.markdown_required ? 'Yes' : 'No'}</span>
            <span>Estimated markdown: ${money(m.markdown_needed)}</span>
          </div>
          ${budgetGraph(m)}
        </div>
        <div class="card stack">
          <div class="card-title"><h2>Week by Week Hours</h2><a class="btn secondary" href="/engagements/${id}/history" data-link>History</a></div>
          ${weeklyHoursChart(data.weekly_summary || [])}
        </div>
      </div>
      <div class="grid two-col" style="margin-top:16px">
        <div class="card stack">
          <div class="card-title"><h2>Recent Imports</h2></div>
          ${recentImports(data.recent_imports)}
        </div>
        <div class="card stack">
          <div class="card-title"><h2>Adjustments Summary</h2><strong>${money(m.adjustment_total)}</strong></div>
          ${adjustmentsList(data.adjustments)}
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-title"><h2>Team</h2></div>
        ${teamSummaryTable(data.team)}
      </div>
      `
    );
    bindLinks();
    bindCompletionActions(id);
    document.getElementById('close-engagement')?.addEventListener('click', async () => {
      if (!confirm('Close this engagement and export a final HTML report?')) return;
      const reportWindow = window.open('', '_blank');
      try {
        await api(`/api/engagements/${id}`, { method: 'PUT', body: { status: 'Closed' } });
        const reportUrl = `/api/engagements/${id}/export/html?narrative=${encodeURIComponent('Final engagement report')}`;
        if (reportWindow) reportWindow.location = reportUrl;
        else window.open(reportUrl, '_blank');
        showToast('Engagement closed and final report opened');
        renderEngagement(id);
      } catch (error) {
        if (reportWindow) reportWindow.close();
        showToast(error.message);
      }
    });
  } catch (error) {
    setPage('Engagement', `<div class="card">${escapeHtml(error.message)}</div>`);
  }
}

function engagementTabs(id) {
  const tabs = [
    ['Overview', `/engagements/${id}`],
    ['Team & Budget', `/engagements/${id}/team`],
    ['Import', `/engagements/${id}/import`],
    ['Adjustments', `/engagements/${id}/adjustments`],
    ['History', `/engagements/${id}/history`],
    ['Export', `/engagements/${id}/export`],
  ];
  const current = window.location.pathname;
  return `<div class="row wrap" style="margin-bottom:16px">${tabs
    .map(([label, path]) => `<a class="btn ${current === path ? 'primary' : 'secondary'}" href="${path}" data-link>${label}</a>`)
    .join('')}</div>`;
}

function recentImports(imports) {
  if (!imports.length) return '<div class="muted small">No imports yet.</div>';
  return imports
    .map((item) => `<div class="row between small"><span>${escapeHtml(item.week_end_date)}</span><span>${item.row_count} rows - ${num(item.hours)} hrs</span></div>`)
    .join('');
}

function teamSummaryTable(team) {
  if (!team.length) return '<div class="empty">No team configured.</div>';
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Role</th><th>Budgeted Hours</th><th>Hours To Date</th><th>Remaining</th><th>Remaining %</th><th>Engagement Rate</th><th>Fees</th><th>Rate Difference</th></tr></thead>
      <tbody>
      ${team
        .map((member) => {
          const cls = member.remaining_pct > 0.3 ? 'row-green' : member.remaining_pct >= 0.1 ? 'row-amber' : 'row-red';
          return `<tr class="${cls}"><td>${escapeHtml(member.name)}</td><td>${escapeHtml(member.role)}</td><td>${num(member.budgeted_hours)}</td><td>${num(member.hours_to_date)}</td><td>${num(member.hours_remaining)}</td><td>${pct(member.remaining_pct)}</td><td>${money(member.engagement_rate)}</td><td>${money(member.fees_to_date)}</td><td>${money(member.rate_diff_total)}</td></tr>`;
        })
        .join('')}
      </tbody>
    </table></div>
  `;
}

function adjustmentsList(adjustments) {
  if (!adjustments.length) return '<div class="muted small">No adjustments logged.</div>';
  return adjustments
    .map((adj) => `<div class="row between small"><span>${escapeHtml(adj.effective_date)} - ${escapeHtml(adj.adjustment_type)}</span><strong>${money(adj.amount)}</strong></div>`)
    .join('');
}

function completionPanel(id, engagement) {
  return `
    <div class="completion-panel">
      <div>
        <div class="section-title">Final reporting complete</div>
        <div class="muted small">Final reports remain available until this engagement is cleared from the database.</div>
      </div>
      <div class="row wrap">
        <a class="btn primary" href="/api/engagements/${id}/export/html?narrative=${encodeURIComponent('Final engagement report')}" target="_blank" rel="noopener noreferrer">${svgIcon('file')}Final HTML / PDF</a>
        <a class="btn secondary" href="/api/engagements/${id}/export/excel">${svgIcon('file')}Final Excel</a>
        <button class="btn danger" id="clear-engagement">${svgIcon('trash')}Clear Engagement Data</button>
      </div>
    </div>
  `;
}

function bindCompletionActions(id) {
  document.getElementById('clear-engagement')?.addEventListener('click', async () => {
    const confirmed = confirm('Clear this closed engagement and all related budgets, imports, adjustments, and time entries from the database? This cannot be undone.');
    if (!confirmed) return;
    await api(`/api/engagements/${id}`, { method: 'DELETE' });
    showToast('Engagement cleared');
    navigate('/dashboard');
  });
}

function chartMax(items, key) {
  return Math.max(1, ...items.map((item) => Number(item[key] || 0)));
}

function weeklyHoursChart(weeks) {
  if (!weeks.length) return '<div class="empty">No weekly hours loaded yet.</div>';
  const maxHours = chartMax(weeks, 'hours');
  return `
    <div class="bar-chart weekly-hours-chart">
      ${weeks
        .map((week) => {
          const width = Math.max(3, Math.min(100, (Number(week.hours || 0) / maxHours) * 100));
          return `<div class="bar-row"><div class="bar-label">${escapeHtml(week.week_end_date || 'No date')}</div><div class="bar-track"><span style="width:${width}%"></span></div><strong>${num(week.hours)}</strong></div>`;
        })
        .join('')}
    </div>
  `;
}

function weeklyHoursTable(weeks) {
  if (!weeks.length) return '<div class="empty">No weekly hours loaded yet.</div>';
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Week End</th><th>Hours</th><th>Fees</th><th>Entries</th><th>Cumulative Hours</th><th>Cumulative Fees</th></tr></thead>
      <tbody>${weeks
        .map((week) => `<tr><td>${escapeHtml(week.week_end_date || '')}</td><td>${num(week.hours)}</td><td>${money(week.fees)}</td><td>${week.entries || 0}</td><td>${num(week.cumulative_hours)}</td><td>${money(week.cumulative_fees)}</td></tr>`)
        .join('')}</tbody>
    </table></div>
  `;
}

function budgetGraph(metrics) {
  const rows = [
    ['Net Budget', metrics.net_budget, 'navy'],
    ['Gross Projected Fees', metrics.gross_projected_fees ?? metrics.projected_final, 'blue'],
    ['Projected Final', metrics.projected_final, 'green'],
    ['Fees To Date', metrics.fees_to_date_contract, 'amber'],
  ];
  const maxValue = Math.max(1, ...rows.map((row) => Number(row[1] || 0)));
  return `
    <div class="bar-chart budget-chart">
      ${rows
        .map(([label, value, tone]) => {
          const width = Math.max(3, Math.min(100, (Number(value || 0) / maxValue) * 100));
          return `<div class="bar-row ${tone}"><div class="bar-label">${label}</div><div class="bar-track"><span style="width:${width}%"></span></div><strong>${money(value)}</strong></div>`;
        })
        .join('')}
    </div>
  `;
}
async function renderTeamConfig(id) {
  const [data, settings] = await Promise.all([api(`/api/engagements/${id}`), api('/api/settings/rates')]);
  const model = JSON.parse(JSON.stringify(data));
  const removedMembers = new Set();
  const removedPhases = new Set();

  function draw() {
    setPage(
      'Team & Budget',
      `
      ${engagementTabs(id)}
      <div class="card stack">
        ${engagementConfigFields(model.engagement)}
        <div class="row between"><h2 class="section-title">Team</h2><button class="btn secondary" id="add-team">${svgIcon('plus')}Add Row</button></div>
        ${configTeamTable(model.team, settings.rates)}
        <div class="row between"><h2 class="section-title">Phases</h2><button class="btn secondary" id="add-phase">${svgIcon('plus')}Add Phase</button></div>
        ${configPhaseTable(model.phases)}
        <div class="row"><button class="btn primary" id="save-config">${svgIcon('save')}Save Changes</button></div>
      </div>
      `
    );
    bindLinks();
    bindConfig();
  }

  function bindConfig() {
    document.querySelectorAll('[data-config-engagement]').forEach((field) => {
      field.addEventListener('input', () => {
        model.engagement[field.dataset.configEngagement] = coerceField(field);
      });
    });
    document.querySelectorAll('[data-config-team]').forEach((field) => {
      field.addEventListener('input', () => {
        const member = model.team[Number(field.dataset.index)];
        member[field.dataset.configTeam] = coerceField(field);
        if (field.dataset.configTeam === 'role') {
          const rate = settings.rates[field.value] || 0;
          member.internal_rate = rate;
          member.engagement_rate = rate;
          draw();
        }
      });
    });
    document.querySelectorAll('[data-config-phase]').forEach((field) => {
      field.addEventListener('input', () => {
        model.phases[Number(field.dataset.index)][field.dataset.configPhase] = coerceField(field);
      });
    });
    document.querySelectorAll('[data-remove-member]').forEach((button) => {
      button.addEventListener('click', async () => {
        const index = Number(button.dataset.removeMember);
        const member = model.team[index];
        if (member.id) removedMembers.add(member.id);
        model.team.splice(index, 1);
        draw();
      });
    });
    document.querySelectorAll('[data-remove-phase-row]').forEach((button) => {
      button.addEventListener('click', () => {
        const index = Number(button.dataset.removePhaseRow);
        const phase = model.phases[index];
        if (phase.id) removedPhases.add(phase.id);
        model.phases.splice(index, 1);
        draw();
      });
    });
    document.getElementById('add-team')?.addEventListener('click', () => {
      model.team.push(blankMember(settings.rates));
      draw();
    });
    document.getElementById('add-phase')?.addEventListener('click', () => {
      model.phases.push({ phase_name: '', budgeted_hours: 0, budgeted_eng_fees: 0, sort_order: model.phases.length });
      draw();
    });
    document.getElementById('save-config')?.addEventListener('click', async () => {
      try {
        await api(`/api/engagements/${id}`, { method: 'PUT', body: model.engagement });
        for (const memberId of removedMembers) await api(`/api/engagements/${id}/team/${memberId}`, { method: 'DELETE' });
        for (const phaseId of removedPhases) await api(`/api/engagements/${id}/phases/${phaseId}`, { method: 'DELETE' });
        for (const member of model.team.filter((item) => item.name?.trim())) {
          if (member.id) await api(`/api/engagements/${id}/team/${member.id}`, { method: 'PUT', body: member });
          else await api(`/api/engagements/${id}/team`, { method: 'POST', body: member });
        }
        for (const [index, phase] of model.phases.filter((item) => item.phase_name?.trim()).entries()) {
          phase.sort_order = index;
          if (phase.id) await api(`/api/engagements/${id}/phases/${phase.id}`, { method: 'PUT', body: phase });
          else await api(`/api/engagements/${id}/phases`, { method: 'POST', body: phase });
        }
        showToast('Changes saved');
        renderTeamConfig(id);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  draw();
}

function engagementConfigFields(e) {
  return `
    <div class="form-grid three">
      ${configInput('Engagement Code', 'engagement_code', e.engagement_code)}
      ${configInput('Client Name', 'client_name', e.client_name)}
      ${configInput('Engagement Lead', 'engagement_lead', e.engagement_lead)}
      ${configSelect('Model Type', 'model_type', e.model_type, MODEL_TYPES)}
      ${configInput('Model Vendor', 'model_vendor', e.model_vendor)}
      ${configInput('First Week with Entry', 'first_week_with_entry', e.first_week_with_entry, 'date')}
      ${configInput('Max SOW Fees', 'max_sow_fees', e.max_sow_fees, 'number')}
      ${configInput('Change Order Amount', 'change_order_amt', e.change_order_amt, 'number')}
      ${configInput('C360 Amount', 'c360_amount', e.c360_amount, 'number')}
      ${configInput('BIMA Amount', 'bima_amount', e.bima_amount, 'number')}
      <div class="field"><label>C360 Used</label><select data-config-engagement="c360_used"><option value="0" ${!e.c360_used ? 'selected' : ''}>No</option><option value="1" ${e.c360_used ? 'selected' : ''}>Yes</option></select></div>
      <div class="field"><label>Status</label><select data-config-engagement="status"><option ${e.status === 'Active' ? 'selected' : ''}>Active</option><option ${e.status === 'Closed' ? 'selected' : ''}>Closed</option></select></div>
    </div>
  `;
}

function configInput(label, name, value, type = 'text') {
  return `<div class="field"><label>${label}</label><input type="${type}" step="0.01" data-config-engagement="${name}" value="${escapeHtml(value)}"></div>`;
}

function configSelect(label, name, value, options) {
  return selectField(label, name, value, options, 'data-config-engagement');
}

function configTeamTable(team) {
  const rows = team
    .map(
      (member, index) => `
      <tr>
        <td><input data-config-team="name" data-index="${index}" value="${escapeHtml(member.name)}"></td>
        <td><select data-config-team="role" data-index="${index}">${ROLES.map((role) => `<option value="${role}" ${role === member.role ? 'selected' : ''}>${role}</option>`).join('')}</select></td>
        <td><input type="number" step="0.01" data-config-team="internal_rate" data-index="${index}" value="${member.internal_rate || 0}"></td>
        <td><input type="number" step="0.01" data-config-team="engagement_rate" data-index="${index}" value="${member.engagement_rate || 0}"></td>
        <td><input type="number" step="0.1" data-config-team="budgeted_hours" data-index="${index}" value="${member.budgeted_hours || 0}"></td>
        <td><button class="btn icon secondary" title="Remove" data-remove-member="${index}">${svgIcon('trash')}</button></td>
      </tr>`
    )
    .join('');
  return `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Crowe Bill Rate</th><th>Negotiated Rate</th><th>Budgeted Hours</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function configPhaseTable(phases) {
  const rows = phases
    .map(
      (phase, index) => `
      <tr>
        <td><input data-config-phase="phase_name" data-index="${index}" value="${escapeHtml(phase.phase_name)}"></td>
        <td><input type="number" step="0.1" data-config-phase="budgeted_hours" data-index="${index}" value="${phase.budgeted_hours || 0}"></td>
        <td><input type="number" step="0.01" data-config-phase="budgeted_eng_fees" data-index="${index}" value="${phase.budgeted_eng_fees || 0}"></td>
        <td><button class="btn icon secondary" title="Remove" data-remove-phase-row="${index}">${svgIcon('trash')}</button></td>
      </tr>`
    )
    .join('');
  return `<div class="table-wrap"><table><thead><tr><th>Phase</th><th>Budgeted Hours</th><th>Budgeted Fees</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="muted">No phases configured.</td></tr>'}</tbody></table></div>`;
}

async function renderImport(id) {
  setPage(
    'Weekly Import',
    `
    ${engagementTabs(id)}
    <div class="grid two-col">
      <div class="card stack">
        <div class="import-source">
          <div>
            <div class="section-title">Cognos source report</div>
            <div class="muted small">Open the Power BI report, export the current weekly data, then upload or paste it below.</div>
          </div>
          <a class="btn secondary" href="${COGNOS_REPORT_URL}" target="_blank" rel="noopener noreferrer">${svgIcon('upload')}Open Cognos Report</a>
        </div>
        <div class="field"><label>Paste Cognos Export</label><textarea id="import-text"></textarea></div>
        <div class="field"><label>Upload CSV or XLSX</label><input type="file" id="import-file" accept=".csv,.txt,.xlsx"></div>
        <button class="btn primary" id="preview-import">${svgIcon('upload')}Preview Import</button>
      </div>
      <div class="card stack" id="import-summary"><div class="muted">No preview loaded.</div></div>
    </div>
    <div id="preview-table" style="margin-top:16px"></div>
    `
  );
  bindLinks();
  let previewRows = [];
  document.getElementById('preview-import').addEventListener('click', async () => {
    try {
      const file = document.getElementById('import-file').files[0];
      let data;
      if (file) {
        const form = new FormData();
        form.append('file', file);
        const response = await fetch(`/api/engagements/${id}/import/preview`, { method: 'POST', body: form });
        const payload = await response.json();
        if (!response.ok || payload.error) throw new Error(payload.error?.message || 'Import failed');
        data = payload.data;
      } else {
        data = await api(`/api/engagements/${id}/import/preview`, {
          method: 'POST',
          body: { text: document.getElementById('import-text').value },
        });
      }
      previewRows = data.rows;
      drawPreview(data.summary, previewRows);
    } catch (error) {
      showToast(error.message);
    }
  });

  function drawPreview(summary, rows) {
    document.getElementById('import-summary').innerHTML = `
      ${miniMetric('Rows', summary.total)}
      ${miniMetric('To Import', summary.to_import)}
      ${miniMetric('Duplicates', summary.duplicates)}
      ${miniMetric('Flagged', summary.flagged)}
      <div class="field"><label>Snapshot Notes</label><textarea id="import-notes" style="min-height:80px"></textarea></div>
      <button class="btn primary" id="commit-import">${svgIcon('save')}Commit Import</button>
    `;
    document.getElementById('preview-table').innerHTML = `
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Include</th><th>Transaction</th><th>Worker</th><th>Week End</th><th>Hours</th><th>Fees</th><th>Flag</th><th>Memo</th></tr></thead>
            <tbody>
              ${rows
                .map(
                  (row) => `
                  <tr class="flag-${row.flag || ''}">
                    <td><input type="checkbox" data-preview-id="${escapeHtml(row.transaction_id)}" ${row.included ? 'checked' : ''} ${row.selectable ? '' : 'disabled'}></td>
                    <td>${escapeHtml(row.transaction_id)}</td>
                    <td>${escapeHtml(row.worker_name)}</td>
                    <td>${escapeHtml(row.week_end_date)}</td>
                    <td>${num(row.hours)}</td>
                    <td>${money(row.fees_contract_rate)}</td>
                    <td>${escapeHtml(row.flag || '')}</td>
                    <td>${escapeHtml(row.memo)}</td>
                  </tr>`
                )
                .join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
    document.getElementById('commit-import').addEventListener('click', async () => {
      const checks = [...document.querySelectorAll('[data-preview-id]')];
      const included = checks.filter((item) => item.checked && !item.disabled).map((item) => item.dataset.previewId);
      const excluded = checks.filter((item) => !item.checked && !item.disabled).map((item) => item.dataset.previewId);
      try {
        const result = await api(`/api/engagements/${id}/import/commit`, {
          method: 'POST',
          body: {
            included_transaction_ids: included,
            excluded_transaction_ids: excluded,
            notes: document.getElementById('import-notes').value,
          },
        });
        showToast(`Imported ${result.imported} rows`);
        navigate(`/engagements/${id}/history`);
      } catch (error) {
        showToast(error.message);
      }
    });
  }
}

async function renderAdjustments(id) {
  const data = await api(`/api/engagements/${id}`);
  const rows = data.adjustments;
  setPage(
    'Adjustments',
    `
    ${engagementTabs(id)}
    <div class="grid two-col">
      <div class="card">
        <div class="card-title"><h2>Adjustment Log</h2><strong>${money(data.metrics.adjustment_total)}</strong></div>
        ${adjustmentsTable(rows)}
      </div>
      <div class="card stack">
        <h2 class="section-title" id="adjustment-form-title">Add Adjustment</h2>
        <input type="hidden" id="adjustment-id">
        ${selectField('Type', 'adjustment_type', '', ADJUSTMENT_TYPES, 'id')}
        <div class="field"><label>Effective Date</label><input type="date" id="effective_date"></div>
        <div class="field"><label>Amount</label><input type="number" step="0.01" id="amount"></div>
        <div class="field"><label>Description</label><textarea id="description" style="min-height:90px"></textarea></div>
        <button class="btn primary" id="save-adjustment">${svgIcon('save')}Save Adjustment</button>
      </div>
    </div>
    `
  );
  bindLinks();
  bindAdjustments(id, rows);
}

function adjustmentsTable(rows) {
  if (!rows.length) return '<div class="empty">No adjustments logged.</div>';
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Description</th><th></th></tr></thead>
      <tbody>${rows
        .map((row) => `<tr><td>${escapeHtml(row.effective_date)}</td><td>${escapeHtml(row.adjustment_type)}</td><td>${money(row.amount)}</td><td>${escapeHtml(row.description)}</td><td class="row"><button class="btn icon secondary" title="Edit" data-edit-adjustment="${row.id}">${svgIcon('edit')}</button><button class="btn icon secondary" title="Delete" data-delete-adjustment="${row.id}">${svgIcon('trash')}</button></td></tr>`)
        .join('')}</tbody>
    </table></div>
  `;
}

function bindAdjustments(id, rows) {
  document.querySelectorAll('[data-edit-adjustment]').forEach((button) => {
    button.addEventListener('click', () => {
      const row = rows.find((item) => item.id === Number(button.dataset.editAdjustment));
      document.getElementById('adjustment-form-title').textContent = 'Edit Adjustment';
      document.getElementById('adjustment-id').value = row.id;
      document.getElementById('adjustment_type').value = row.adjustment_type;
      document.getElementById('effective_date').value = row.effective_date || '';
      document.getElementById('amount').value = row.amount || 0;
      document.getElementById('description').value = row.description || '';
    });
  });
  document.querySelectorAll('[data-delete-adjustment]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!confirm('Delete this adjustment?')) return;
      await api(`/api/engagements/${id}/adjustments/${button.dataset.deleteAdjustment}`, { method: 'DELETE' });
      showToast('Adjustment deleted');
      renderAdjustments(id);
    });
  });
  document.getElementById('save-adjustment').addEventListener('click', async () => {
    const adjustmentId = document.getElementById('adjustment-id').value;
    const body = {
      adjustment_type: document.getElementById('adjustment_type').value,
      effective_date: document.getElementById('effective_date').value,
      amount: Number(document.getElementById('amount').value || 0),
      description: document.getElementById('description').value,
    };
    try {
      if (adjustmentId) await api(`/api/engagements/${id}/adjustments/${adjustmentId}`, { method: 'PUT', body });
      else await api(`/api/engagements/${id}/adjustments`, { method: 'POST', body });
      showToast('Adjustment saved');
      renderAdjustments(id);
    } catch (error) {
      showToast(error.message);
    }
  });
}

async function renderHistory(id) {
  const [snapshots, data] = await Promise.all([
    api(`/api/engagements/${id}/snapshots`),
    api(`/api/engagements/${id}`),
  ]);
  const weeks = data.weekly_summary || [];
  setPage(
    'Snapshot History',
    `
    ${engagementTabs(id)}
    <div class="grid two-col">
      <div class="card stack">
        <div class="card-title"><h2>Week by Week Hours</h2><strong>${num(data.metrics.hours_to_date)} hrs</strong></div>
        ${weeklyHoursChart(weeks)}
      </div>
      <div class="card stack">
        <div class="card-title"><h2>Weekly Detail</h2></div>
        ${weeklyHoursTable(weeks)}
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="card-title"><h2>Snapshot Imports</h2></div>
      ${historyTable(id, snapshots)}
    </div>
    `
  );
  bindLinks();
  bindHistory(id, snapshots);
}

function historyTable(id, snapshots) {
  if (!snapshots.length) return '<div class="empty">No snapshots yet.</div>';
  return `
    <div class="table-wrap"><table>
      <thead><tr><th></th><th>Week End</th><th>Imported At</th><th>Rows</th><th>Hours</th><th>Fees</th><th>Cumulative Hours</th><th>Cumulative Fees</th><th>Notes</th><th></th></tr></thead>
      <tbody>
        ${snapshots
          .map((row) => `
          <tr>
            <td><button class="btn icon secondary" title="Expand" data-expand-snapshot="${row.id}">${svgIcon('chevron')}</button></td>
            <td>${escapeHtml(row.week_end_date)}</td><td>${escapeHtml(row.imported_at)}</td><td>${row.row_count}</td><td>${num(row.hours)}</td><td>${money(row.fees)}</td><td>${num(row.cumulative_hours)}</td><td>${money(row.cumulative_fees)}</td><td>${escapeHtml(row.notes)}</td>
            <td><button class="btn icon secondary" title="Delete" data-delete-snapshot="${row.id}">${svgIcon('trash')}</button></td>
          </tr>
          <tr id="snapshot-detail-${row.id}" style="display:none"><td colspan="10"><div class="muted">Loading...</div></td></tr>`)
          .join('')}
      </tbody>
    </table></div>
  `;
}

function bindHistory(id) {
  document.querySelectorAll('[data-expand-snapshot]').forEach((button) => {
    button.addEventListener('click', async () => {
      const snapshotId = button.dataset.expandSnapshot;
      const row = document.getElementById(`snapshot-detail-${snapshotId}`);
      const opening = row.style.display === 'none';
      row.style.display = opening ? 'table-row' : 'none';
      if (!opening || row.dataset.loaded) return;
      const snapshot = await api(`/api/engagements/${id}/snapshots/${snapshotId}`);
      row.querySelector('td').innerHTML = snapshotEntries(snapshot.entries);
      row.dataset.loaded = '1';
    });
  });
  document.querySelectorAll('[data-delete-snapshot]').forEach((button) => {
    button.addEventListener('click', async () => {
      if (!confirm('Delete this snapshot and its time entries?')) return;
      await api(`/api/engagements/${id}/snapshots/${button.dataset.deleteSnapshot}`, { method: 'DELETE' });
      showToast('Snapshot deleted');
      renderHistory(id);
    });
  });
}

function snapshotEntries(entries) {
  return `
    <div class="table-wrap"><table>
      <thead><tr><th>Worker</th><th>Date</th><th>Hours</th><th>Fees</th><th>Memo</th></tr></thead>
      <tbody>${entries.map((entry) => `<tr><td>${escapeHtml(entry.worker_name)}</td><td>${escapeHtml(entry.entry_date)}</td><td>${num(entry.hours)}</td><td>${money(entry.fees_contract_rate)}</td><td>${escapeHtml(entry.memo)}</td></tr>`).join('')}</tbody>
    </table></div>
  `;
}

async function renderExport(id) {
  const data = await api(`/api/engagements/${id}`);
  setPage(
    'Export',
    `
    ${engagementTabs(id)}
    <div class="grid two-col">
      <div class="card stack">
        <h2 class="section-title">${escapeHtml(data.engagement.client_name)}</h2>
        <div class="print-note small">HTML opens in a new tab and invokes the browser print dialog.</div>
        <div class="field"><label>Status Narrative</label><textarea id="narrative"></textarea></div>
        <div class="row">
          <button class="btn primary" id="html-export">${svgIcon('file')}HTML / PDF</button>
          <a class="btn secondary" href="/api/engagements/${id}/export/excel">${svgIcon('file')}Excel</a>
        </div>
      </div>
      <div class="card stack">
        ${miniMetric('Net Budget', money(data.metrics.net_budget))}
        ${miniMetric('Projected Final', money(data.metrics.projected_final))}
        ${miniMetric('Markdown Needed', money(data.metrics.markdown_needed))}
      </div>
    </div>
    `
  );
  bindLinks();
  document.getElementById('html-export').addEventListener('click', () => {
    const narrative = encodeURIComponent(document.getElementById('narrative').value);
    window.open(`/api/engagements/${id}/export/html?narrative=${narrative}`, '_blank');
  });
}

async function renderSettings() {
  const data = await api('/api/settings/rates');
  const rates = data.rates;
  setPage(
    'Settings',
    `
    <div class="grid two-col">
      <div class="card stack">
        <div class="card-title"><h2>Bill Rate Table</h2></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Role</th><th>Default Rate</th></tr></thead>
            <tbody>${Object.entries(rates)
              .map(([role, rate]) => `<tr><td>${escapeHtml(role)}</td><td><input type="number" step="0.01" data-rate-role="${escapeHtml(role)}" value="${rate}"></td></tr>`)
              .join('')}</tbody>
          </table>
        </div>
        <button class="btn primary" id="save-rates">${svgIcon('save')}Save Rates</button>
      </div>
      <div class="card stack">
        <div class="card-title"><h2>Database</h2></div>
        <div class="small muted">${escapeHtml(data.database.path)}</div>
        <div>Last modified: ${escapeHtml(data.database.last_modified || 'Not created')}</div>
        <a class="btn secondary" href="/api/settings/backup">${svgIcon('file')}Backup</a>
      </div>
    </div>
    `
  );
  bindLinks();
  document.getElementById('save-rates').addEventListener('click', async () => {
    const next = {};
    document.querySelectorAll('[data-rate-role]').forEach((field) => {
      next[field.dataset.rateRole] = Number(field.value || 0);
    });
    await api('/api/settings/rates', { method: 'PUT', body: { rates: next } });
    showToast('Rates saved');
    renderSettings();
  });
}

function showDbError() {
  app.innerHTML = `
    <div class="error-page">
      <div class="card stack">
        <h1>Database Error</h1>
        <p>The app could not open or initialize the local SQLite database.</p>
        <pre>${escapeHtml(window.DB_ERROR)}</pre>
        <p class="muted">Restore a recent backup or move the damaged database file before launching again.</p>
      </div>
    </div>
  `;
}

function render() {
  if (window.DB_ERROR) {
    showDbError();
    return;
  }
  const path = window.location.pathname;
  if (path === '/') return renderLanding();
  if (path === '/dashboard') return renderDashboard();
  if (path === '/engagements/new') return renderNewEngagement();
  if (path === '/settings') return renderSettings();
  const match = path.match(/^\/engagements\/(\d+)(?:\/([^/]+))?$/);
  if (match) return renderEngagement(Number(match[1]), match[2] || '');
  setPage('Not Found', '<div class="card">Page not found.</div>');
}

window.addEventListener('popstate', render);
render();

