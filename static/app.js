/* Aesthetic direction: Swiss / typographic. Crowe indigo anchors a dense operational workspace. */
const state = {
  theme: localStorage.getItem('budget-theme') || 'light',
  onboardingComplete: localStorage.getItem('budget-onboarding-complete') === 'true'
};
document.documentElement.dataset.theme = state.theme;

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const money = (value) => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(Number(value || 0));
const num = (value, digits=1) => Number(value || 0).toLocaleString('en-US', {minimumFractionDigits:digits, maximumFractionDigits:digits});
const pct = (value) => value == null ? '—' : `${num(Number(value)*100, 1)}%`;
const app = document.getElementById('app');

async function api(path, options={}) {
  const init = {method: options.method || 'GET', headers: {...(options.headers || {})}};
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({data:null,error:{message:'Invalid server response'}}));
  if (!response.ok) {
    const error = new Error(payload.error?.message || 'Request failed');
    error.details = payload.error || {};
    throw error;
  }
  return payload.data;
}

function statusBadge(status) {
  return `<span class="status ${String(status || '').toLowerCase().replaceAll(' ','-')}">${esc(status || 'Planning')}</span>`;
}

function metric(label, value, note='') {
  return `<article class="metric"><span>${esc(label)}</span><strong>${value}</strong>${note ? `<small>${esc(note)}</small>` : ''}</article>`;
}

// Paths Flask now hands to the React bundle (see app.py's serve_frontend()).
// A plain, unintercepted <a> here forces a real navigation so the browser
// re-asks Flask instead of the in-page router rendering the retired legacy
// screen from memory. Extend this as more pages port over.
const REACT_ROUTES = new Set(['/dashboard', '/help']);

function navLink(path, label) {
  const active = location.pathname === path || (path !== '/dashboard' && location.pathname.startsWith(path));
  const linkAttr = REACT_ROUTES.has(path) ? '' : 'data-link';
  return `<a class="nav-link ${active ? 'active' : ''}" href="${path}" ${linkAttr}>${label}</a>`;
}

function bindNavigation(root=document) {
  root.querySelectorAll('[data-link]').forEach((link) => link.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    history.pushState({}, '', link.href);
    render();
  }));
}

function toast(message, kind='success') {
  document.querySelector('.toast')?.remove();
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.textContent = message;
  document.body.append(node);
  setTimeout(() => node.remove(), 3200);
}

function errorPanel(error) {
  return `<div class="alert danger"><strong>Unable to continue</strong><span>${esc(error.message || error)}</span></div>`;
}

function helpText(title, text) {
  return `<details class="inline-help"><summary>${esc(title)}</summary><p>${esc(text)}</p></details>`;
}

function confirmAction(title, detail) {
  return window.confirm(`${title}\n\n${detail}\n\nSelect OK to continue or Cancel to go back.`);
}

function field(label, name, value='', type='text', attrs='') {
  return `<label class="field"><span>${esc(label)}</span><input name="${name}" type="${type}" value="${esc(value)}" ${attrs}></label>`;
}

function moneyField(label, name, value='', attrs='') {
  return `<label class="field"><span>${esc(label)}</span><div class="input-prefix"><span>$</span><input name="${name}" type="number" value="${esc(value)}" ${attrs}></div></label>`;
}

function select(label, name, value, options, attrs='') {
  return `<label class="field"><span>${esc(label)}</span><select name="${name}" ${attrs}>${options.map((item) => {
    const pair = Array.isArray(item) ? item : [item,item];
    return `<option value="${esc(pair[0])}" ${String(pair[0]) === String(value) ? 'selected' : ''}>${esc(pair[1])}</option>`;
  }).join('')}</select></label>`;
}

function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function renderDashboard() {
  shell('Engagement portfolio', '<div class="loading">Loading engagements…</div>', '<a class="btn primary" href="/engagements/new" data-link>New engagement</a>');
  try {
    const data = await api('/api/engagements');
    const m = data.metrics;
    const cards = data.engagements.map((item) => {
      const x = item.metrics;
      return `<a class="engagement-card" href="/engagements/${item.id}" data-link>
        <div class="card-kicker"><span>${esc(item.engagement_code)}</span>${statusBadge(x.status)}</div>
        <h2>${esc(item.client_name)}</h2><p>${esc(item.engagement_lead || 'Lead not assigned')}</p>
        <div class="progress"><i style="width:${Math.min(100, Math.max(0, x.utilization_pct*100))}%"></i></div>
        <div class="card-stats"><span><b>${num(x.hours_to_date)}</b> hours</span><span><b>${money(x.fees_to_date_contract)}</b> used</span></div>
        <small>${esc(item.complexity_mode)} mode · Last import ${esc(item.last_import_date || 'none')}</small></a>`;
    }).join('');
    const welcome = !state.onboardingComplete ? `<section class="welcome-card"><div><span class="eyebrow">First-time setup</span><h2>Welcome to the Engagement Budget Tracker</h2><p>Start by reviewing the rate card, then create an engagement. The tracker will guide you before any actual time is committed.</p></div><div class="welcome-actions"><a class="btn secondary" href="/settings" data-link>Review settings</a><button class="btn primary" id="complete-onboarding">I understand</button></div></section>` : '';
    shell('Engagement portfolio', `${welcome}<section class="workflow-card"><div><span class="eyebrow">Weekly routine</span><h2>Run the budget in seven steps</h2></div><ol class="workflow-steps"><li>Back up</li><li>Export Cognos</li><li>Preview</li><li>Resolve warnings</li><li>Commit actuals</li><li>Update forecast</li><li>Export report</li></ol><a href="/help#weekly">Open the guided weekly checklist</a></section><section class="metrics four">${metric('Active engagements', m.total_active_engagements)}${metric('Hours this month', num(m.total_hours_mtd))}${metric('Fees this month', money(m.total_fees_mtd))}${metric('Needs attention', m.watch_or_over_budget)}</section>
      <div class="section-heading"><div><span class="eyebrow">Portfolio</span><h2>Current engagements</h2></div></div>
      <section class="engagement-grid">${cards || '<div class="empty">No engagements yet. Create the first budget to begin.</div>'}</section>`,
      '<a class="btn primary" href="/engagements/new" data-link>New engagement</a>');
    bindNavigation();
    document.getElementById('complete-onboarding')?.addEventListener('click',()=>{localStorage.setItem('budget-onboarding-complete','true');state.onboardingComplete=true;renderDashboard();});
  } catch (error) { shell('Engagement portfolio', errorPanel(error)); }
}

const REACT_ENGAGEMENT_SUBROUTES = new Set(['', 'import', 'exceptions', 'phases', 'hours-overages']);

function engagementTabs(id, mode='simple') {
  const tabs = [['Overview',''],['Phases','phases'],['Exceptions','exceptions'],['Team','team'],['Rate model','rates'],
                ['Weekly import','import'],['Adjustments','adjustments'],['Expenses','expenses'],
                ['History','history'],['Export','export']];
  if (mode === 'complex') tabs.splice(7,0,['Revisions','revisions']);
  // Every route in REACT_ENGAGEMENT_SUBROUTES is React-owned (see app.py) - a plain,
  // unintercepted <a> forces a real navigation there instead of the in-page router
  // rendering the retired legacy screen from memory (same fix as REACT_ROUTES above).
  // Extend the set as more sub-pages port.
  return `<nav class="tabs">${tabs.map(([label,route]) => `<a href="/engagements/${id}${route ? `/${route}` : ''}" ${REACT_ENGAGEMENT_SUBROUTES.has(route) ? '' : 'data-link'}>${label}</a>`).join('')}</nav>`;
}

async function renderEngagement(id) {
  shell('Engagement overview', '<div class="loading">Loading budget…</div>');
  try {
    const data = await api(`/api/engagements/${id}`);
    const e = data.engagement, m = data.metrics;
    const banner = m.pending_exceptions_count ? `<a class="alert warning" href="/engagements/${id}/exceptions" data-link><strong>Exceptions pending review</strong><span>${m.pending_exceptions_count} imported entries are included in totals and need a decision</span></a>` : '';
    const phaseRows = data.phases.map((p) => `<tr data-phase="${p.id}"><td><button class="phase-expander" data-expand-phase="${p.id}" aria-expanded="false" aria-controls="phase-detail-${p.id}">+</button> ${esc(p.phase_name)}</td><td>${num(p.budgeted_hours)}</td><td>${num(p.actual_hours)}</td><td>${num(p.hours_remaining)}</td><td>${money(p.effective_sow)}</td><td>${money(p.actual_contract_fees)}</td><td>${pct(p.realization)}</td><td>${statusBadge(p.status)}</td></tr><tr id="phase-detail-${p.id}" class="inline-phase-row" hidden><td colspan="8"><div class="inline-phase-detail loading">Loading weekly detail...</div></td></tr>`).join('');
    const statusControl=e.status==='active'?`<details class="status-control"><summary>Close engagement</summary><form id="status-form"><p>Closing makes every engagement screen read-only.</p><label class="field"><span>Reason</span><input name="reason" required></label><input type="hidden" name="status" value="closed"><button class="btn danger">Close engagement</button></form></details>`:e.status==='closed'?`<details class="status-control"><summary>Reopen engagement</summary><form id="status-form"><p>Reopening allows forecasts, imports and governed revisions again.</p><label class="field"><span>Reason</span><input name="reason" required></label><input type="hidden" name="status" value="active"><button class="btn primary">Reopen engagement</button></form></details>`:'<p class="hint">Planning remains open until the first Cognos import is committed.</p>';
    shell(e.client_name, `${engagementTabs(id,e.complexity_mode)}${banner}
      <section class="engagement-hero"><div><span class="eyebrow">${esc(e.engagement_code)} · ${esc(e.complexity_mode)} mode</span><h2>${esc(e.engagement_lead || 'Lead not assigned')}</h2></div><div class="status-stack"><div>${statusBadge(e.status)} ${statusBadge(m.status)}</div>${statusControl}</div></section>
      <section class="metrics five">${metric('Budgeted hours',num(m.total_budgeted_hours))}${metric('Actual hours',num(m.hours_to_date))}${metric('Remaining hours',num(m.hours_remaining),pct(m.hours_remaining_pct))}${metric('Effective statement of work budget',money(m.effective_sow))}${metric('Realization',pct(m.realization),m.realization_delta==null?'No prior import':`${m.realization_delta>=0?'+':''}${pct(m.realization_delta)} since prior import`)}</section>
      <section class="card budget-position"><div><div class="section-heading"><h2>Budget position</h2><strong>${pct(m.utilization_pct)} used</strong></div><div class="progress large"><i style="width:${Math.min(100,m.utilization_pct*100)}%"></i></div><div class="inline-stats"><span>Projected final <b>${money(m.projected_final)}</b></span><span>Remaining <b>${money(m.budget_remaining)}</b></span><span>Markdown needed <b>${money(m.markdown_needed)}</b></span></div></div><aside><span>Realization</span><strong>${pct(m.realization)}</strong><small>Statement of work budget and change orders minus Crowe-paid expenses, divided by actual standard fees</small></aside></section>
      <section class="card"><div class="section-heading"><div><span class="eyebrow">Risk by workstream</span><h2>Phase breakdown</h2></div><span>Expand a row for weekly detail</span></div><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Budget hours</th><th>Actual hours</th><th>Remaining</th><th>Effective statement of work budget</th><th>Actual fees</th><th>Realization</th><th>Status</th></tr></thead><tbody>${phaseRows}</tbody></table></div></section>`);
    document.getElementById('status-form')?.addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(event.currentTarget);if(!confirmAction(body.status==='closed'?'Close this engagement':'Reopen this engagement',body.status==='closed'?'All screens become read-only. A recovery backup will be created.':'The engagement will return to active operation.'))return;try{await api(`/api/engagements/${id}`,{method:'PUT',body});toast(`Engagement ${body.status}`);renderEngagement(id);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-expand-phase]').forEach(button=>button.addEventListener('click',async()=>{const row=document.getElementById(`phase-detail-${button.dataset.expandPhase}`);const opening=row.hidden;row.hidden=!opening;button.setAttribute('aria-expanded',String(opening));button.textContent=opening?'−':'+';if(opening&&!row.dataset.loaded){try{const detail=await api(`/api/engagements/${id}/phases/${button.dataset.expandPhase}`);const weeks=detail.grid.weeks;const rows=detail.grid.rows.map(item=>`<tr><th>${esc(item.member.name)}</th>${item.cells.map(cell=>`<td><b><span>Actual hours</span>${num(cell.actual_hours)}</b><small><span>Budget hours ${num(cell.budgeted_hours)}</span><span>Forecast hours ${num(cell.forecasted_hours==null?cell.budgeted_hours:cell.forecasted_hours)}</span></small></td>`).join('')}</tr>`).join('');row.querySelector('.inline-phase-detail').classList.remove('loading');row.querySelector('.inline-phase-detail').innerHTML=`<p class="weekly-detail-explanation">Actual hours are completed time. Budget hours are the approved baseline. Forecast hours are the current estimate for work that remains.</p><div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Person</th>${weeks.map(week=>`<th>Week of ${esc(week)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><a class="btn text" href="/engagements/${id}/phases/${button.dataset.expandPhase}">Open forecast editor</a>`;row.dataset.loaded='true';bindNavigation();}catch(error){row.querySelector('.inline-phase-detail').innerHTML=errorPanel(error);}}}));
  } catch (error) { shell('Engagement overview', errorPanel(error)); }
}

const WIZARD_STEP_TITLES = ['Engagement','Team','Phases','Weekly budget'];

function serializeWizard(wizard) {
  const {settings, draftId, ...rest} = wizard;
  return {...rest, openPhases: Array.from(wizard.openPhases)};
}

let wizardSaveTimer = null;
function scheduleWizardSave(wizard) {
  clearTimeout(wizardSaveTimer);
  wizardSaveTimer = setTimeout(() => persistWizardDraft(wizard), 600);
}
async function persistWizardDraft(wizard) {
  const body = {wizard: serializeWizard(wizard)};
  try {
    if (wizard.draftId) {
      await api(`/api/wizard-drafts/${wizard.draftId}`, {method:'PUT', body});
    } else {
      const data = await api('/api/wizard-drafts', {method:'POST', body});
      wizard.draftId = data.id;
    }
  } catch (e) {}
}

async function renderInProgress() {
  shell('In-progress engagements', '<div class="loading">Loading drafts…</div>', '<a class="btn primary" href="/engagements/new" data-link>New engagement</a>');
  const data = await api('/api/wizard-drafts').catch(() => ({drafts:[]}));
  const drafts = data.drafts || [];
  const body = drafts.length
    ? `<div class="table-wrap"><table><thead><tr><th>Engagement code</th><th>Client</th><th>Step reached</th><th>Last saved</th><th></th></tr></thead><tbody>${drafts.map((d)=>`<tr><td>${esc(d.engagement_code||'Untitled')}</td><td>${esc(d.client_name||'—')}</td><td>${esc(WIZARD_STEP_TITLES[(d.step||1)-1]||'Engagement')}</td><td>${esc(new Date(d.updated_at).toLocaleString())}</td><td><div class="button-row"><a class="btn secondary" href="/engagements/new?draft=${d.id}" data-link>Resume</a><button class="btn text" data-discard-draft="${d.id}">Discard</button></div></td></tr>`).join('')}</tbody></table></div>`
    : `<div class="empty"><strong>No in-progress engagements</strong><p>Anything you start in the New engagement wizard is saved here automatically until you finish creating it.</p></div>`;
  shell('In-progress engagements', body, '<a class="btn primary" href="/engagements/new" data-link>New engagement</a>');
  document.querySelectorAll('[data-discard-draft]').forEach((b)=>b.addEventListener('click', async ()=>{
    if (!confirm('Discard this in-progress engagement? This cannot be undone.')) return;
    await api(`/api/wizard-drafts/${b.dataset.discardDraft}`, {method:'DELETE'}).catch(()=>{});
    renderInProgress();
  }));
}

async function renderNewEngagement() {
  const settings = await api('/api/settings/rates').catch(() => ({rates:{}}));
  const draftId = new URLSearchParams(location.search).get('draft');
  let wizard = null;
  if (draftId) {
    try {
      const data = await api(`/api/wizard-drafts/${draftId}`);
      wizard = data.wizard;
      wizard.openPhases = new Set(wizard.openPhases || [0]);
      wizard.draftId = Number(draftId);
    } catch (e) {
      toast('Could not load that draft — it may have already been created or discarded', 'error');
    }
  }
  if (!wizard) {
    wizard = {step:1, info:{complexity_mode:'simple',duration_weeks:8},
      team:[{name:'',role:'Manager',internal_rate:settings.rates['Manager'] || 350,budgeted_hours:0}],
      phases:[{phase_name:'',phase_code:'',sow_fees:0}], weekly:{}, targets:{}, phaseTeam:{},
      openPhases:new Set([0]), confirmed:false, draftId:null};
  }
  wizard.settings = settings;
  const titles = WIZARD_STEP_TITLES;
  function draw() {
    const actions = `<button class="btn secondary" id="back" ${wizard.step===1?'disabled':''}>Back</button><button class="btn primary" id="next">${wizard.step===4?'Create engagement':'Continue'}</button>`;
    const progress = `<div class="wizard-progress">${titles.map((title,index)=>`<div class="${wizard.step===index+1?'active':''} ${wizard.step>index+1?'done':''}" data-wizard-step="${index+1}"><span>0${index+1}</span>${title}</div>`).join('')}</div>`;
    let body = wizard.step===1 ? wizardInfo(wizard) : wizard.step===2 ? wizardTeam(wizard) : wizard.step===3 ? wizardPhases(wizard) : wizardWeeks(wizard);
    shell('New engagement', `${progress}<section class="card wizard">${body}<div class="wizard-actions">${actions}</div></section>`);
    bind();
    scheduleWizardSave(wizard);
  }
  function bind() {
    document.querySelectorAll('[data-info]').forEach((node)=>node.addEventListener('input',()=>{wizard.info[node.dataset.info]=node.type==='number'?Number(node.value):node.value;if(node.dataset.info==='complexity_mode')draw();}));
    document.querySelectorAll('[data-team]').forEach((node)=>node.addEventListener('input',()=>{const [i,key]=node.dataset.team.split(':');wizard.team[i][key]=node.type==='number'?Number(node.value):node.type==='checkbox'?node.checked:node.value;if(key==='role'){const rate=Number(settings.rates[node.value]||0);wizard.team[i].internal_rate=rate;wizard.team[i].engagement_rate=rate*(1-Number(settings.engagement_discount_rate||0));draw();}}));
    document.querySelectorAll('[data-phase]').forEach((node)=>node.addEventListener('input',()=>{const [i,key]=node.dataset.phase.split(':');wizard.phases[i][key]=node.type==='number'?Number(node.value):node.value;}));
    document.querySelectorAll('[data-week]').forEach((node)=>node.addEventListener('input',()=>{
      wizard.weekly[node.dataset.week]=Number(node.value||0);
      const [pi,ti]=node.dataset.week.split(':');
      const weeks=weekDates(wizard.info.first_monday,wizard.info.duration_weeks);
      const rowTotal=weeks.reduce((sum,week)=>sum+Number(wizard.weekly[`${pi}:${ti}:${week}`]||0),0);
      const rowEl=document.querySelector(`[data-planned="${pi}:${ti}"]`);
      if(rowEl)rowEl.textContent=num(rowTotal);
      const team=wizard.team.filter((x)=>x.name);
      const sel=wizard.phaseTeam[pi];
      const phaseTotal=team.reduce((sum,_member,idx)=>{
        if(sel&&sel[idx]===false)return sum;
        return sum+weeks.reduce((s,week)=>s+Number(wizard.weekly[`${pi}:${idx}:${week}`]||0),0);
      },0);
      const phaseEl=document.querySelector(`[data-phase-planned="${pi}"]`);
      if(phaseEl)phaseEl.textContent=num(phaseTotal);
    }));
    document.querySelectorAll('[data-target]').forEach((node)=>{node.addEventListener('input',()=>{wizard.targets[node.dataset.target]=Number(node.value||0);});node.addEventListener('change',draw);});
    document.getElementById('baseline-confirm')?.addEventListener('change',(event)=>{wizard.confirmed=event.currentTarget.checked;});
    document.getElementById('add-team')?.addEventListener('click',()=>{wizard.team.push({name:'',role:'Manager',internal_rate:settings.rates['Manager']||350,budgeted_hours:0});draw();});
    document.getElementById('add-phase')?.addEventListener('click',()=>{wizard.phases.push({phase_name:'',phase_code:'',sow_fees:0});draw();});
    document.querySelectorAll('[data-remove-team]').forEach((b)=>b.addEventListener('click',()=>{wizard.team.splice(Number(b.dataset.removeTeam),1);draw();}));
    document.querySelectorAll('[data-remove-phase]').forEach((b)=>b.addEventListener('click',()=>{wizard.phases.splice(Number(b.dataset.removePhase),1);draw();}));
    document.querySelectorAll('[data-phase-team]').forEach((node)=>node.addEventListener('change',()=>{const [pi,ti]=node.dataset.phaseTeam.split(':');wizard.phaseTeam[pi]=wizard.phaseTeam[pi]||{};wizard.phaseTeam[pi][ti]=node.checked;if(!node.checked){delete wizard.targets[`${pi}:${ti}`];Object.keys(wizard.weekly).forEach((key)=>{if(key.startsWith(`${pi}:${ti}:`))delete wizard.weekly[key];});}draw();}));
    document.querySelectorAll('[data-phase-toggle]').forEach((node)=>node.addEventListener('toggle',()=>{const pi=Number(node.dataset.phaseToggle);if(node.open)wizard.openPhases.add(pi);else wizard.openPhases.delete(pi);}));
    document.querySelectorAll('[data-distribute]').forEach((b)=>b.addEventListener('click',()=>{const [pi,ti]=b.dataset.distribute.split(':').map(Number);const weeks=weekDates(wizard.info.first_monday,wizard.info.duration_weeks);const per=Number(wizard.targets[`${pi}:${ti}`]||0)/Math.max(1,weeks.length);weeks.forEach((week)=>wizard.weekly[`${pi}:${ti}:${week}`]=per);draw();}));
    document.getElementById('back')?.addEventListener('click',()=>{wizard.step=Math.max(1,wizard.step-1);draw();});
    document.querySelectorAll('[data-wizard-step]').forEach((node)=>node.addEventListener('click',()=>{wizard.step=Number(node.dataset.wizardStep);draw();}));
    document.querySelectorAll('.wizard input, .wizard select, .wizard textarea').forEach((el)=>{el.addEventListener('input',()=>scheduleWizardSave(wizard));el.addEventListener('change',()=>scheduleWizardSave(wizard));});
    document.getElementById('next')?.addEventListener('click',async()=>{
      if(wizard.step===1&&(!wizard.info.engagement_code||!wizard.info.client_name)){toast('Engagement code and client name are required','error');return;}
      if(wizard.step===2&&wizard.team.some((x)=>x.name&&!x.name.includes(','))){toast('Use Last, First for every team member','error');return;}
      if(wizard.step===3&&wizard.info.complexity_mode==='complex'&&wizard.phases.every((x)=>!x.phase_name)){toast('Add at least one phase','error');return;}
      if(wizard.step<4){wizard.step++;if(wizard.step===4&&wizard.info.complexity_mode==='complex'&&!Object.keys(wizard.targets).length){wizard.team.forEach((member,ti)=>wizard.targets[`0:${ti}`]=Number(member.budgeted_hours||0));}draw();return;}
      if(!wizard.confirmed){toast('Confirm that you reviewed the baseline before creating the engagement','error');return;}
      const team=wizard.team.filter((x)=>x.name);const phases=wizard.phases.filter((x)=>x.phase_name);
      if(wizard.info.complexity_mode==='complex'){const mismatched=team.filter((member,ti)=>{const allocated=phases.reduce((sum,_phase,pi)=>sum+Number(wizard.targets[`${pi}:${ti}`]||0),0);return Math.abs(allocated-Number(member.budgeted_hours||0))>0.01;});if(mismatched.length){toast(`Phase target hours do not match the engagement target for ${mismatched.map(x=>x.name).join(', ')}`,'error');return;}const weeklyMismatch=[];phases.forEach((_phase,pi)=>team.forEach((member,ti)=>{const planned=weekDates(wizard.info.first_monday,wizard.info.duration_weeks).reduce((sum,week)=>sum+Number(wizard.weekly[`${pi}:${ti}:${week}`]||0),0);const target=Number(wizard.targets[`${pi}:${ti}`]||0);if(Math.abs(planned-target)>0.01)weeklyMismatch.push(member.name);}));if(weeklyMismatch.length){toast(`Weekly cells do not match phase targets for ${[...new Set(weeklyMismatch)].join(', ')}`,'error');return;}}
      const weekly_budgets=Object.entries(wizard.weekly).map(([key,budgeted_hours])=>{const [phase_index,team_index,week_start_date]=key.split(':');return {phase_index:Number(phase_index),team_index:Number(team_index),week_start_date,budgeted_hours};});
      try{const data=await api('/api/engagements',{method:'POST',body:{engagement:wizard.info,team,phases,weekly_budgets}});clearTimeout(wizardSaveTimer);if(wizard.draftId)await api(`/api/wizard-drafts/${wizard.draftId}`,{method:'DELETE'}).catch(()=>{});history.pushState({},'',`/engagements/${data.engagement.id}`);render();}catch(error){toast(error.message,'error');}
    });
  }
  draw();
}

function wizardInfo(w) {
  const e=w.info;return `<div class="form-grid">${field('Engagement code','engagement_code',e.engagement_code,'text','required data-info="engagement_code"')}${field('Client name','client_name',e.client_name,'text','required data-info="client_name"')}${select('Complexity mode','complexity_mode',e.complexity_mode,[['simple','Simple'],['complex','Complex']],'data-info="complexity_mode"')}${select('Engagement type','engagement_type',e.engagement_type||'Advisory',['Audit','Validation','Tuning','Implementation','Advisory','Other'],'data-info="engagement_type"')}${field('Engagement lead','engagement_lead',e.engagement_lead,'text','data-info="engagement_lead"')}${field('Model type','model_type',e.model_type,'text','data-info="model_type"')}${e.complexity_mode==='complex'?field('First Monday','first_monday',e.first_monday,'date','required data-info="first_monday"')+field('Duration in weeks','duration_weeks',e.duration_weeks,'number','min="1" data-info="duration_weeks"'):moneyField('Signed statement of work fees','max_sow_fees',e.max_sow_fees,'min="0" step="0.01" data-info="max_sow_fees"')}</div>`;
}

function wizardTeam(w) {
  const roles=Object.keys(w.settings.rates);return `<div class="section-heading"><div><span class="eyebrow">Step two</span><h2>Engagement team</h2></div><button class="btn secondary" id="add-team">Add person</button></div><div class="table-wrap"><table><thead><tr><th>Name (Last, First)</th><th>Role</th><th>Standard rate</th><th>Engagement rate</th><th>Budget hours</th><th>Offshore</th><th></th></tr></thead><tbody>${w.team.map((x,i)=>`<tr><td><input data-team="${i}:name" value="${esc(x.name)}"></td><td><select data-team="${i}:role">${roles.map(r=>`<option ${r===x.role?'selected':''}>${esc(r)}</option>`).join('')}</select></td><td><input type="number" data-team="${i}:internal_rate" value="${x.internal_rate||0}" readonly></td><td><input type="number" data-team="${i}:engagement_rate" value="${x.engagement_rate||''}" placeholder="Default"></td><td><input type="number" data-team="${i}:budgeted_hours" value="${x.budgeted_hours||0}"></td><td><input type="checkbox" data-team="${i}:is_offshore" ${x.is_offshore?'checked':''}></td><td><button class="icon-btn" data-remove-team="${i}" aria-label="Remove person">×</button></td></tr>`).join('')}</tbody></table></div>`;
}

function wizardPhases(w) {
  if(w.info.complexity_mode==='simple')return `<div class="empty"><strong>Simple mode uses one General phase</strong><p>The phase is created automatically and remains hidden during normal use.</p></div>`;
  return `<div class="section-heading"><div><span class="eyebrow">Step three</span><h2>Phases and statement of work budgets</h2></div><button class="btn secondary" id="add-phase">Add phase</button></div><div class="table-wrap"><table><thead><tr><th>Phase name</th><th>Phase code</th><th>Statement of work fees</th><th></th></tr></thead><tbody>${w.phases.map((x,i)=>`<tr><td><input data-phase="${i}:phase_name" value="${esc(x.phase_name)}"></td><td><input data-phase="${i}:phase_code" value="${esc(x.phase_code)}" placeholder="Leave blank if unsure"></td><td><div class="input-prefix"><span>$</span><input type="number" data-phase="${i}:sow_fees" value="${x.sow_fees||0}"></div></td><td><button class="icon-btn" data-remove-phase="${i}" aria-label="Remove phase">×</button></td></tr>`).join('')}</tbody></table></div><p class="hint">Phase codes are optional and frequently inconsistent in Cognos exports. Unmatched rows can be assigned during import.</p>`;
}

function weekDates(first, count) {
  if(!first)return [];
  const start=new Date(`${first}T12:00:00`);return Array.from({length:Number(count||1)},(_,i)=>{const day=new Date(start);day.setDate(day.getDate()+i*7);return day.toISOString().slice(0,10);});
}

function wizardWeeks(w) {
  const team=w.team.filter(x=>x.name);
  if(w.info.complexity_mode==='simple')return `<div class="review"><span class="eyebrow">Review before creating</span><h2>${esc(w.info.client_name||'New engagement')}</h2><p>${team.length} team members · ${money(w.info.max_sow_fees||0)} signed statement of work</p>${helpText('What happens next?','The engagement starts in Planning. The first committed Cognos import activates and locks the baseline.')}</div><label class="confirmation"><input id="baseline-confirm" type="checkbox" ${w.confirmed?'checked':''}><span>I reviewed the engagement code, team, rates, hours and signed statement of work.</span></label>`;
  const weeks=weekDates(w.info.first_monday,w.info.duration_weeks);const phases=w.phases.filter(x=>x.phase_name);
  const memberChecks=team.map((member,ti)=>{const phaseTarget=phases.reduce((sum,_phase,pi)=>sum+Number(w.targets[`${pi}:${ti}`]||0),0);const target=Number(member.budgeted_hours||0);const difference=phaseTarget-target;return `<tr class="${Math.abs(difference)>0.01?'needs-review':''}"><td>${esc(member.name)}</td><td>${num(target)}</td><td>${num(phaseTarget)}</td><td>${num(difference)}</td></tr>`;}).join('');
  const isOnPhase=(pi,ti)=>{const sel=w.phaseTeam[pi];return !sel||sel[ti]!==false;};
  const pendingFor=(member,ti,excludePi)=>{const allocatedElsewhere=phases.reduce((sum,_p,pi)=>pi===excludePi?sum:sum+Number(w.targets[`${pi}:${ti}`]||0),0);return Number(member.budgeted_hours||0)-allocatedElsewhere;};
  const phasePlans=phases.map((phase,pi)=>{
    const memberPicker=team.map((member,ti)=>`<label class="phase-team-pick"><input type="checkbox" data-phase-team="${pi}:${ti}" ${isOnPhase(pi,ti)?'checked':''}><span>${esc(member.name)}</span></label>`).join('');
    const selected=team.map((member,ti)=>({member,ti})).filter(({ti})=>isOnPhase(pi,ti));
    const plannedThisPhase=selected.reduce((sum,{ti})=>sum+weeks.reduce((s,week)=>s+Number(w.weekly[`${pi}:${ti}:${week}`]||0),0),0);
    const rows=selected.map(({member,ti})=>{
      const planned=weeks.reduce((sum,week)=>sum+Number(w.weekly[`${pi}:${ti}:${week}`]||0),0);
      const pending=pendingFor(member,ti,pi);
      return `<tr><th><span>${esc(member.name)}</span><label class="target-hours">Phase target <input type="number" min="0" step="0.25" data-target="${pi}:${ti}" value="${w.targets[`${pi}:${ti}`]??0}"></label><small class="hint">${num(pending)} hrs pending across phases</small><button type="button" data-distribute="${pi}:${ti}">Distribute target</button></th>${weeks.map(week=>`<td><input type="number" min="0" step="0.25" data-week="${pi}:${ti}:${week}" value="${w.weekly[`${pi}:${ti}:${week}`]??0}"></td>`).join('')}<td><strong data-planned="${pi}:${ti}">${num(planned)}</strong></td></tr>`;
    }).join('');
    return `<details class="phase-plan" data-phase-toggle="${pi}" ${w.openPhases.has(pi)?'open':''}><summary><span class="eyebrow">Phase ${pi+1}</span><h3>${esc(phase.phase_name)}</h3><span class="phase-summary-meta">${money(phase.sow_fees)} SOW · ${selected.length} of ${team.length} team members · <span data-phase-planned="${pi}">${num(plannedThisPhase)}</span> hrs planned</span></summary><div class="phase-team-picker"><span class="eyebrow">Team on this phase</span><div class="phase-team-grid">${memberPicker}</div></div>${selected.length?`<div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Team member and phase target</th>${weeks.map(x=>`<th>${new Date(`${x}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</th>`).join('')}<th>Planned</th></tr></thead><tbody>${rows}</tbody></table></div>`:'<p class="hint">Select at least one team member to plan weekly hours for this phase.</p>'}</details>`;
  }).join('');
  return `<div class="section-heading"><div><span class="eyebrow">Step four</span><h2>Weekly budget and baseline review</h2></div><span>${weeks.length} weeks</span></div><p class="hint">Expand a phase, choose who is staffed on it, then set a phase target and distribute it across the weeks. The "pending" hint shows how many of each person's total hours are not yet claimed by any phase. Phase targets must add up to the engagement target entered in Step 2.</p>${phasePlans}<section class="review-panel"><div><span class="eyebrow">Reconciliation</span><h3>Confirm every person balances to zero</h3></div><div class="table-wrap"><table><thead><tr><th>Team member</th><th>Engagement target</th><th>Phase targets</th><th>Difference</th></tr></thead><tbody>${memberChecks}</tbody></table></div><div class="review-totals"><span>Phase statement of work total <b>${money(phases.reduce((sum,p)=>sum+Number(p.sow_fees||0),0))}</b></span><span>Planning window <b>${weeks.length} weeks</b></span></div></section><label class="confirmation"><input id="baseline-confirm" type="checkbox" ${w.confirmed?'checked':''}><span>I reviewed the team, rates, phase statement of work budgets and reconciled weekly budget. I understand that the first committed import locks this baseline.</span></label>`;
}

async function renderTeamConfig(id) {
  try {
    const [data,settings]=await Promise.all([api(`/api/engagements/${id}`),api('/api/settings/rates')]);const e=data.engagement;const roles=Object.keys(settings.rates);const disabled=e.status==='closed'?'disabled':'';
    const memberRows=data.team.map((x)=>`<tr data-member-id="${x.id}" class="${x.is_active===0?'inactive-row':''}"><td><input name="name" value="${esc(x.name)}" ${disabled}></td><td><select name="role" ${disabled}>${roles.map(r=>`<option ${r===x.role?'selected':''}>${esc(r)}</option>`).join('')}</select></td><td><input name="internal_rate" type="number" value="${x.internal_rate}" readonly></td><td><input name="engagement_rate" type="number" value="${x.engagement_rate}" ${disabled}></td><td><input name="budgeted_hours" type="number" value="${x.budgeted_hours}" ${e.status!=='planning'?'disabled':''}></td><td><input name="is_offshore" type="checkbox" ${x.is_offshore?'checked':''} ${disabled}></td><td><button class="btn text" data-toggle-member="${x.id}" data-active="${x.is_active===0?0:1}" ${disabled}>${x.is_active===0?'Reactivate':'Deactivate'}</button></td></tr>`).join('');
    const phases=data.phases.map((p)=>`<tr data-phase-id="${p.id}"><td><a href="/engagements/${id}/phases/${p.id}">${esc(p.phase_name)}</a></td><td><input name="phase_code" value="${esc(p.phase_code||'')}" ${disabled}></td><td><div class="input-prefix"><span>$</span><input name="sow_fees" type="number" value="${p.sow_fees}" ${disabled}></div></td><td>${num(p.budgeted_hours)}</td></tr>`).join('');
    const addMember=e.status==='closed'?'':`<section class="card"><div class="section-heading"><div><span class="eyebrow">Roster</span><h2>Add a team member</h2></div></div><p class="hint">Use the worker name exactly as it appears in Cognos. Active engagements retain the reason in the revision audit.</p><form id="add-member-form" class="form-grid">${field('Name (Last, First)','name','','text','required')}${select('Role','role',roles[0],roles,'id="add-member-role"')}${field('Standard rate','internal_rate',settings.rates[roles[0]]||0,'number','readonly')}${field('Engagement rate','engagement_rate','','number','placeholder="Uses discount default" step="0.01"')}${e.status==='planning'?field('Budget hours','budgeted_hours',0,'number','min="0" step="0.25"'):field('Reason for adding after activation','reason','','text','required')}<label class="field checkbox-field"><input name="is_offshore" type="checkbox"><span>Offshore team member</span></label><div class="form-actions"><button class="btn primary">Add team member</button></div></form></section>`;
    shell('Team and budget', `${engagementTabs(id,e.complexity_mode)}<section class="card"><div class="section-heading"><div><span class="eyebrow">Configuration</span><h2>Team rates and hours</h2></div><span>${statusBadge(e.status)}</span></div>${helpText('Why are some values locked?','The first committed import locks baseline hours, rates and statement of work budgets. Changing a locked value opens a reasoned revision.') }<div class="table-wrap"><table id="team-config"><thead><tr><th>Name</th><th>Role</th><th>Standard rate</th><th>Engagement rate</th><th>Hours</th><th>Offshore</th><th>Status</th></tr></thead><tbody>${memberRows}</tbody></table></div></section>
      <section class="card"><h2>Phases</h2><div class="table-wrap"><table id="phase-config"><thead><tr><th>Phase</th><th>Code</th><th>Signed statement of work</th><th>Budget hours</th></tr></thead><tbody>${phases}</tbody></table></div></section>
      ${e.status==='closed'?'':`<div class="form-actions"><button class="btn primary" id="save-config">Save configuration</button></div>`}${addMember}`);
    document.getElementById('save-config')?.addEventListener('click',async()=>{
      try{
        for(const row of document.querySelectorAll('[data-member-id]')){const body=formObject(rowToForm(row));body.is_offshore=row.querySelector('[name=is_offshore]').checked;await api(`/api/engagements/${id}/team/${row.dataset.memberId}`,{method:'PUT',body});if(e.status==='planning'&&e.complexity_mode==='simple')await api(`/api/engagements/${id}/phase-weeks`,{method:'PUT',body:{rows:[{phase_id:data.phases[0].id,team_member_id:Number(row.dataset.memberId),week_start_date:null,budgeted_hours:Number(body.budgeted_hours||0)}]}});}
        for(const row of document.querySelectorAll('[data-phase-id]')){const body=formObject(rowToForm(row));await api(`/api/engagements/${id}/phases/${row.dataset.phaseId}`,{method:'PUT',body});}
        toast('Configuration saved');renderTeamConfig(id);
      }catch(error){if(error.details?.code==='budget_locked'){const d=error.details;history.pushState({},'',`/engagements/${id}/revisions?target_type=${d.target_type}&target_id=${d.target_id}&field_name=${d.field_name||''}`);render();}else toast(error.message,'error');}
    });
    const addForm=document.getElementById('add-member-form');addForm?.addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(addForm);body.is_offshore=addForm.elements.is_offshore.checked;try{await api(`/api/engagements/${id}/team`,{method:'POST',body});toast('Team member added');renderTeamConfig(id);}catch(error){toast(error.message,'error');}});
    document.getElementById('add-member-role')?.addEventListener('change',(event)=>{const rate=Number(settings.rates[event.currentTarget.value]||0);addForm.elements.internal_rate.value=rate;addForm.elements.engagement_rate.value=(rate*(1-Number(settings.engagement_discount_rate||0))).toFixed(2);});
    document.querySelectorAll('[data-toggle-member]').forEach(button=>button.addEventListener('click',async()=>{const active=button.dataset.active==='1';if(!confirmAction(active?'Deactivate team member':'Reactivate team member',active?'Historical time remains, but future imports will flag this worker until reactivated.':'The worker will be available for future imports.'))return;await api(`/api/engagements/${id}/team/${button.dataset.toggleMember}`,{method:'PUT',body:{is_active:!active}});renderTeamConfig(id);}));
  }catch(error){shell('Team and budget',errorPanel(error));}
}

function rowToForm(row){const form=document.createElement('form');row.querySelectorAll('input,select').forEach(node=>form.append(node.cloneNode(true)));return form;}

async function renderPhases(id) {
  try {
    const data=await api(`/api/engagements/${id}`),e=data.engagement;
    const rows=data.phases.map(p=>`<tr data-manage-phase="${p.id}"><td><input name="phase_name" value="${esc(p.phase_name)}" ${e.status==='closed'?'disabled':''}></td><td><input name="phase_code" value="${esc(p.phase_code||'')}" ${e.status==='closed'?'disabled':''}></td><td><input name="sow_fees" type="number" step="0.01" value="${p.sow_fees}" ${e.status==='closed'||p.actual_hours?'disabled':''}></td><td>${num(p.actual_hours)}</td><td>${statusBadge(p.status)}</td><td><a class="btn text" href="/engagements/${id}/phases/${p.id}" data-link>Forecast</a>${!p.is_default&&!p.actual_hours&&e.status!=='closed'?`<button class="btn text danger-text" data-delete-phase="${p.id}">Delete</button>`:''}</td></tr>`).join('');
    const add=e.status==='closed'?'':`<section class="card side-form"><h2>Add phase</h2><p class="hint">A phase added during delivery remains editable until its first actual posts.</p><form id="add-phase-form">${field('Phase name','phase_name','','text','required')}${field('Cognos phase code','phase_code')}${field('Signed statement of work','sow_fees',0,'number','min="0" step="0.01"')}<button class="btn primary">Add phase</button></form></section>`;
    shell('Phases',`${engagementTabs(id,e.complexity_mode)}<div class="split-layout"><section class="card"><div class="section-heading"><div><span class="eyebrow">Persistent phase management</span><h2>Workstreams</h2></div>${e.status==='closed'?'':`<button class="btn primary" id="save-phases">Save phases</button>`}</div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Code</th><th>Statement of work budget</th><th>Actual hours</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>${add}</div>`);
    document.getElementById('save-phases')?.addEventListener('click',async()=>{try{for(const row of document.querySelectorAll('[data-manage-phase]')){const body=formObject(rowToForm(row));await api(`/api/engagements/${id}/phases/${row.dataset.managePhase}`,{method:'PUT',body});}toast('Phases saved');renderPhases(id);}catch(error){toast(error.message,'error');}});
    document.getElementById('add-phase-form')?.addEventListener('submit',async event=>{event.preventDefault();try{await api(`/api/engagements/${id}/phases`,{method:'POST',body:formObject(event.currentTarget)});toast('Phase added');renderPhases(id);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-delete-phase]').forEach(button=>button.addEventListener('click',async()=>{if(!confirmAction('Delete phase','Only phases with no actual time can be deleted.'))return;try{await api(`/api/engagements/${id}/phases/${button.dataset.deletePhase}`,{method:'DELETE'});toast('Phase deleted');renderPhases(id);}catch(error){toast(error.message,'error');}}));
  } catch(error) { shell('Phases',errorPanel(error)); }
}

async function renderExceptions(id) {
  try {
    const [data,exceptions]=await Promise.all([api(`/api/engagements/${id}`),api(`/api/engagements/${id}/exceptions`)]),e=data.engagement;
    const memberOptions=data.team.map(member=>`<option value="${member.id}">${esc(member.name)}</option>`).join('');
    const phaseOptions=data.phases.map(phase=>`<option value="${phase.id}">${esc(phase.phase_name)}</option>`).join('');
    const rows=exceptions.map(item=>`<tr class="${item.status}"><td class="mono">${esc(item.transaction_id||'')}</td><td>${esc(item.worker_name||'')}</td><td>${num(item.hours)}</td><td>${money(item.fees_contract_rate)}</td><td>${esc(item.exception_code.replaceAll('_',' '))}</td><td>${statusBadge(item.status)}</td><td>${item.status!=='pending'||e.status==='closed'?'':`<div class="exception-actions">${item.exception_code.startsWith('worker_')?`<select data-exception-member="${item.id}"><option value="">Create imported worker</option>${memberOptions}</select><button class="btn text" data-assign-team="${item.id}">Assign team</button>`:''}${item.exception_code==='unmatched_phase'?`<select data-exception-phase="${item.id}">${phaseOptions}</select><button class="btn text" data-assign-phase="${item.id}">Assign phase</button>`:''}<input data-exclusion-reason="${item.id}" placeholder="Exclusion reason"><button class="btn text danger-text" data-exclude-exception="${item.id}">Exclude</button></div>`}</td></tr>`).join('');
    shell('Exceptions',`${engagementTabs(id,e.complexity_mode)}<section class="card"><div class="section-heading"><div><span class="eyebrow">Imported entries remain in totals</span><h2>Exception queue</h2></div><span>${exceptions.filter(x=>x.status==='pending').length} pending</span></div><p class="hint">Resolve legitimate time by assigning it. Exclude only an invalid charge; excluded entries remain auditable but stop affecting every calculation and export.</p><div class="table-wrap"><table><thead><tr><th>Transaction</th><th>Worker</th><th>Hours</th><th>Fees</th><th>Type</th><th>Status</th><th>Action</th></tr></thead><tbody>${rows||'<tr><td colspan="7">No import exceptions</td></tr>'}</tbody></table></div></section>`);
    document.querySelectorAll('[data-assign-team]').forEach(button=>button.addEventListener('click',async()=>{const select=document.querySelector(`[data-exception-member="${button.dataset.assignTeam}"]`);try{await api(`/api/engagements/${id}/exceptions/${button.dataset.assignTeam}/assign-team`,{method:'POST',body:select.value?{team_member_id:Number(select.value)}:{}});toast('Worker exception resolved');renderExceptions(id);}catch(error){toast(error.message,'error');}}));
    document.querySelectorAll('[data-assign-phase]').forEach(button=>button.addEventListener('click',async()=>{const select=document.querySelector(`[data-exception-phase="${button.dataset.assignPhase}"]`);try{await api(`/api/engagements/${id}/exceptions/${button.dataset.assignPhase}/assign-phase`,{method:'POST',body:{phase_id:Number(select.value)}});toast('Phase exception resolved');renderExceptions(id);}catch(error){toast(error.message,'error');}}));
    document.querySelectorAll('[data-exclude-exception]').forEach(button=>button.addEventListener('click',async()=>{const reason=document.querySelector(`[data-exclusion-reason="${button.dataset.excludeException}"]`).value;if(!reason){toast('Enter an exclusion reason','error');return;}if(!confirmAction('Exclude this charge','It will stop affecting hours, fees, realization, projections and exports.'))return;try{await api(`/api/engagements/${id}/exceptions/${button.dataset.excludeException}/exclude`,{method:'POST',body:{reason}});toast('Charge excluded');renderExceptions(id);}catch(error){toast(error.message,'error');}}));
  } catch(error) { shell('Exceptions',errorPanel(error)); }
}

async function renderPhaseDetail(id,phaseId) {
  try{
    const [detail,parent]=await Promise.all([api(`/api/engagements/${id}/phases/${phaseId}`),api(`/api/engagements/${id}`)]);const p=detail.phase,e=parent.engagement;
    const grid=detail.grid;const rows=grid.rows.map((r)=>`<tr><th>${esc(r.member.name)} ${r.member.is_offshore?'<span class="os-badge">Offshore</span>':''}</th>${r.cells.map(c=>`<td class="${c.variance_flagged?'variance':''}"><label>Budget hours <input type="number" data-cell="budgeted" data-phase="${phaseId}" data-member="${r.member.id}" data-week="${c.week_start_date}" value="${c.budgeted_hours}" ${e.status!=='planning'&&p.actual_hours?'disabled':''}></label>${e.status==='active'&&p.actual_hours&&c.phase_person_week_id?`<button class="cell-revise" data-revise-budget="${c.phase_person_week_id}" aria-label="Revise budget for ${esc(r.member.name)} ${c.week_start_date}">Revise</button>`:''}<label>Actual hours <output>${num(c.actual_hours)}</output></label><label>Forecast hours <input type="number" data-cell="forecasted" data-phase="${phaseId}" data-member="${r.member.id}" data-week="${c.week_start_date}" value="${c.forecasted_hours??''}" placeholder="Uses budget hours" ${e.status==='closed'?'disabled':''}></label></td>`).join('')}</tr>`).join('');
    const bulk=e.status==='closed'?'':`<form id="bulk-forecast-form" class="bulk-forecast"><div><span class="eyebrow">Bulk future-week update</span><h3>Reforecast a range</h3></div>${select('Person','team_member_id','all',[['all','Whole team'],...grid.rows.map(row=>[row.member.id,row.member.name])])}${field('Start week','start_week',grid.weeks[0]||'','date','required')}${field('End week','end_week',grid.weeks.at(-1)||'','date','required')}${select('Apply as','mode','flat',[['flat','Hours each week'],['spread','Total spread evenly']])}${field('Hours','value',0,'number','min="0" step="0.25" required')}<button class="btn secondary">Apply forecast</button></form>`;
    const assignedIds=new Set(grid.rows.map((r)=>Number(r.member.id)));
    const available=(parent.team||[]).filter((m)=>m.is_active!==0&&!assignedIds.has(Number(m.id)));
    const addMember=e.status==='closed'?'':(available.length?`<form id="add-phase-member-form" class="add-phase-member">${select('Add team member to this phase','team_member_id','',available.map((m)=>[m.id,m.name]))}<button class="btn secondary">Add to phase</button></form>`:'<p class="hint">Every active team member is already on this phase.</p>');
    shell(p.phase_name, `${engagementTabs(id,e.complexity_mode)}<section class="phase-header"><div><span class="eyebrow">${esc(p.phase_code||'No phase code')}</span><h2>${money(p.effective_sow)} effective statement of work budget</h2></div>${statusBadge(p.status)}</section>
      <section class="metrics three">${metric('Budget hours',num(p.budgeted_hours))}${metric('Actual hours',num(p.actual_hours))}${metric('Contract fees',money(p.actual_contract_fees))}</section>
      <section class="card"><div class="section-heading"><h2>Weekly budget, actual and forecast</h2>${e.status==='closed'?'':'<button class="btn secondary" id="phase-change-order">Add change order</button>'}</div>${helpText('How this grid works','Budget hours are the approved baseline. Actual hours come from Cognos. Forecast hours are your estimate for future weeks. A blank forecast uses budget hours; an explicit zero stays zero. Actual hours replace forecast hours when time arrives. Only team members added to this phase appear below.')}${addMember}${bulk}<div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Team member</th>${grid.weeks.map(w=>`<th>Week of ${new Date(`${w}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><div class="legend"><span>Budget hours: approved baseline</span><span>Actual hours: completed time</span><span>Forecast hours: current estimate</span><span class="variance-key">Variance review</span></div>${e.status==='closed'?'':'<button class="btn primary" id="save-grid">Save weekly grid</button>'}</section>`);
    document.getElementById('phase-change-order')?.addEventListener('click',()=>{history.pushState({},'',`/engagements/${id}/adjustments?phase=${phaseId}`);render();});
    document.getElementById('add-phase-member-form')?.addEventListener('submit',async(event)=>{event.preventDefault();const memberId=Number(formObject(event.currentTarget).team_member_id);if(!memberId)return;const weeks=grid.weeks.length?grid.weeks:weekDates(e.first_monday,e.duration_weeks);const addRows=weeks.map((week)=>({phase_id:phaseId,team_member_id:memberId,week_start_date:week,budgeted_hours:0}));try{await api(`/api/engagements/${id}/phase-weeks`,{method:'PUT',body:{rows:addRows}});toast('Team member added to phase');renderPhaseDetail(id,phaseId);}catch(error){toast(error.message,'error');}});
    document.getElementById('save-grid')?.addEventListener('click',async()=>{const map={};document.querySelectorAll('[data-cell]').forEach(input=>{const key=`${input.dataset.phase}:${input.dataset.member}:${input.dataset.week}`;map[key]??={phase_id:Number(input.dataset.phase),team_member_id:Number(input.dataset.member),week_start_date:input.dataset.week};map[key][`${input.dataset.cell}_hours`]=input.dataset.cell==='forecasted'&&input.value===''?null:Number(input.value||0);});try{await api(`/api/engagements/${id}/phase-weeks`,{method:'PUT',body:{rows:Object.values(map)}});toast('Weekly grid saved');renderPhaseDetail(id,phaseId);}catch(error){toast(error.message,'error');}});
    document.getElementById('bulk-forecast-form')?.addEventListener('submit',async event=>{event.preventDefault();const body=formObject(event.currentTarget);body.phase_ids=[phaseId];body.team_member_ids=body.team_member_id==='all'?grid.rows.map(row=>row.member.id):[Number(body.team_member_id)];delete body.team_member_id;try{const result=await api(`/api/engagements/${id}/forecasts/bulk`,{method:'PATCH',body});toast(`${result.updated} forecast cells updated`);renderPhaseDetail(id,phaseId);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-revise-budget]').forEach(button=>button.addEventListener('click',()=>{history.pushState({},'',`/engagements/${id}/revisions?target_type=phase_person_week&target_id=${button.dataset.reviseBudget}&field_name=budgeted_hours`);render();}));
  }catch(error){shell('Phase detail',errorPanel(error));}
}

async function renderImport(id) {
  try{
    const data=await api(`/api/engagements/${id}`),e=data.engagement;
    const unresolved=await api(`/api/engagements/${id}/unmatched-phases`);
    const options=data.phases.map(p=>`<option value="${p.id}">${esc(p.phase_name)}</option>`).join('');
    const resolution=unresolved.length?`<section class="card"><h2>Previously imported unmatched time</h2>${unresolved.map((x,i)=>`<div class="resolution-row"><span><b>${esc(x.phase_desc||'(blank)')}</b> · ${num(x.hours)} hours</span><select data-resolve="${i}">${options}</select><button class="btn secondary" data-assign="${i}" data-desc="${esc(x.phase_desc||'')}">Assign</button></div>`).join('')}</section>`:'';
    shell('Weekly import', `${engagementTabs(id,e.complexity_mode)}${resolution}<section class="card import-card"><div><span class="eyebrow">Cognos actuals</span><h2>Preview before committing</h2><p>Upload the raw workbook or paste the full tab-delimited export. Header preambles and summary footers are handled automatically.</p></div><label class="upload-zone"><input id="import-file" type="file" accept=".xlsx,.csv,.txt"><strong>Choose a Cognos file</strong><span>.xlsx, .csv or .txt</span></label><label class="field"><span>Or paste export</span><textarea id="import-text" rows="8"></textarea></label><button class="btn primary" id="preview-import">Preview import</button></section><div id="preview-area"></div>`);
    document.querySelectorAll('[data-assign]').forEach((button)=>button.addEventListener('click',async()=>{const select=document.querySelector(`[data-resolve="${button.dataset.assign}"]`);try{await api(`/api/engagements/${id}/unmatched-phases`,{method:'PATCH',body:{phase_id:Number(select.value),phase_desc:button.dataset.desc}});toast('Unmatched time assigned');renderImport(id);}catch(error){toast(error.message,'error');}}));
    document.getElementById('preview-import').addEventListener('click',async()=>{try{let preview;const file=document.getElementById('import-file').files[0];if(file){const form=new FormData();form.append('file',file);const response=await fetch(`/api/engagements/${id}/import/preview`,{method:'POST',body:form});const body=await response.json();if(!response.ok)throw new Error(body.error?.message);preview=body.data;}else preview=await api(`/api/engagements/${id}/import/preview`,{method:'POST',body:{text:document.getElementById('import-text').value}});drawImportPreview(id,preview,data.phases,e);}catch(error){toast(error.message,'error');}});
  }catch(error){shell('Weekly import',errorPanel(error));}
}

function drawImportPreview(id,preview,phases,engagement) {
  const area=document.getElementById('preview-area');const unmatched=[...new Set(preview.rows.filter(r=>r.flags?.includes('unmatched_phase')).map(r=>r.phase_desc))];
  const assigns=unmatched.map((desc,i)=>`<label class="field compact"><span>Assign “${esc(desc||'(blank)')}” to</span><select data-phase-assignment="${esc(desc)}"><option value="">Leave unmatched</option>${phases.map(p=>`<option value="${p.id}">${esc(p.phase_name)}</option>`).join('')}</select></label>`).join('');
  const guidance={duplicate:'Already imported and excluded',zero_hours:'No time to import',worker_unknown:'Add or reactivate this worker',project_mismatch:'Wrong project by default—verify before selecting',unmatched_phase:'Assign to a phase or leave engagement-wide',variance_flagged:'Review the week-over-week change'};
  const rows=preview.rows.map((r)=>`<tr class="${r.flag||''}"><td><input type="checkbox" aria-label="Include ${esc(r.worker_name)} ${esc(r.week_end_date)}" data-include="${esc(r.transaction_id)}" ${r.included?'checked':''} ${r.selectable?'':'disabled'}></td><td>${esc(r.worker_name)}</td><td>${esc(r.week_end_date)}</td><td>${esc(r.phase_desc||'Unmatched')}</td><td>${num(r.hours)}</td><td>${money(r.fees_contract_rate)}</td><td>${(r.flags||[]).map(f=>`<span class="flag">${esc(f.replaceAll('_',' '))}</span>`).join('')}<small class="flag-guidance">${esc(guidance[r.flag]||'Review before committing')}</small></td></tr>`).join('');
  area.innerHTML=`<section class="metrics four">${metric('Rows',preview.summary.total)}${metric('Ready',preview.summary.to_import)}${metric('Duplicates',preview.summary.duplicates)}${metric('Flagged',preview.summary.flagged)}</section><section class="flag-key"><h2>What the warnings mean</h2><div><span><b>Project mismatch</b> excluded until you deliberately select it</span><span><b>Unknown worker</b> add the worker in Team and budget</span><span><b>Unmatched phase</b> included but not shown in phase totals</span><span><b>Variance review</b> informational and included</span></div></section>${assigns?`<section class="card"><h2>Phase assignments</h2><p class="hint">Assign each Cognos phase description once. The selection applies to every matching row in this preview.</p><div class="assignment-grid">${assigns}</div></section>`:''}<section class="card"><div class="table-wrap"><table><thead><tr><th>Use</th><th>Worker</th><th>Week end</th><th>Phase</th><th>Hours</th><th>Contract fees</th><th>Review and action</th></tr></thead><tbody>${rows}</tbody></table></div><label class="field"><span>Snapshot notes</span><textarea id="import-notes" placeholder="Example: Week ending July 12, reviewed against Cognos by reviewer"></textarea></label>${engagement.status==='planning'?'<div class="alert warning"><strong>This is the first import</strong><span>Committing it activates the engagement and locks baseline hours, rates and statement of work budgets.</span></div>':''}<button class="btn primary" id="commit-import">Review and commit import</button></section>`;
  document.getElementById('commit-import').addEventListener('click',async()=>{const selected=[...document.querySelectorAll('[data-include]:checked')];const included_transaction_ids=selected.map(x=>x.dataset.include);const selectedRows=preview.rows.filter(r=>included_transaction_ids.includes(r.transaction_id));const selectedHours=selectedRows.reduce((sum,row)=>sum+Number(row.hours||0),0);const selectedFees=selectedRows.reduce((sum,row)=>sum+Number(row.fees_contract_rate||0),0);const unresolvedSelected=selectedRows.filter(row=>row.flags?.includes('unmatched_phase')).length;const message=`${included_transaction_ids.length} rows · ${num(selectedHours)} hours · ${money(selectedFees)} contract fees${unresolvedSelected?` · ${unresolvedSelected} unmatched phase rows`:''}.`;if(!confirmAction(engagement.status==='planning'?'Activate engagement and commit first import':'Commit weekly import',`${message}\n\nA recovery backup will be created automatically.`))return;const phase_assignments={};document.querySelectorAll('[data-phase-assignment]').forEach(x=>{if(x.value)phase_assignments[x.dataset.phaseAssignment]=Number(x.value);});try{const result=await api(`/api/engagements/${id}/import/commit`,{method:'POST',body:{included_transaction_ids,phase_assignments,notes:document.getElementById('import-notes').value}});toast(`Imported ${result.imported} rows and created a recovery backup`);renderImport(id);}catch(error){toast(error.message,'error');}});
}

async function renderAdjustments(id) {
  try{
    const data=await api(`/api/engagements/${id}`),e=data.engagement;const selected=new URLSearchParams(location.search).get('phase')||'';
    const rows=data.adjustments.map(x=>`<tr><td>${esc(x.effective_date||'')}</td><td>${esc(x.adjustment_type.replaceAll('_',' '))}</td><td>${esc(x.phase_name||'Engagement-wide')}</td><td>${money(x.amount)}</td><td>${esc(x.description||'')}</td><td><button class="icon-btn" aria-label="Delete adjustment" data-delete-adjustment="${x.id}" ${e.status==='closed'?'disabled':''}>×</button></td></tr>`).join('');
    shell('Budget adjustments', `${engagementTabs(id,e.complexity_mode)}<div class="split-layout"><section class="card"><h2>Adjustment ledger</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Phase</th><th>Amount</th><th>Description</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="6">No adjustments</td></tr>'}</tbody></table></div></section><section class="card side-form"><h2>Add adjustment</h2><form id="adjustment-form">${select('Type','adjustment_type','markdown',['markdown','c360','bima','change_order'])}${field('Effective date','effective_date','', 'date')}${select('Phase','phase_id',selected,[['','Engagement-wide'],...data.phases.map(p=>[p.id,p.phase_name])])}${field('Amount','amount','', 'number','step="0.01"')}<label class="field"><span>Description</span><textarea name="description"></textarea></label><button class="btn primary">Save adjustment</button></form></section></div>`);
    if(e.status==='closed'){document.querySelector('.side-form')?.remove();return;}
    const form=document.getElementById('adjustment-form');const phase=form.elements.phase_id;function phaseRule(){const change=form.elements.adjustment_type.value==='change_order';phase.closest('.field').hidden=!change;phase.required=change;}form.elements.adjustment_type.addEventListener('change',phaseRule);phaseRule();
    form.addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(form);body.phase_id=body.phase_id?Number(body.phase_id):null;try{await api(`/api/engagements/${id}/adjustments`,{method:'POST',body});toast('Adjustment saved');renderAdjustments(id);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-delete-adjustment]').forEach(b=>b.addEventListener('click',async()=>{if(!confirmAction('Delete budget adjustment','The effective budget and realization will recalculate immediately.'))return;await api(`/api/engagements/${id}/adjustments/${b.dataset.deleteAdjustment}`,{method:'DELETE'});renderAdjustments(id);}));
  }catch(error){shell('Budget adjustments',errorPanel(error));}
}

async function renderRevisions(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;const rows=data.revisions.map(x=>`<tr><td>${esc(x.revised_at)}</td><td>${esc(x.phase_name||x.team_member_name||'Engagement')}</td><td>${esc(x.field_name.replaceAll('_',' '))}</td><td>${num(x.old_value,2)}</td><td>${num(x.new_value,2)}</td><td>${esc(x.reason)}</td></tr>`).join('');const params=new URLSearchParams(location.search),targetType=params.get('target_type'),targetId=params.get('target_id');const fields=targetType==='phase'?['sow_fees']:targetType==='phase_person_week'?['budgeted_hours']:['engagement_rate'];const requestedField=params.get('field_name');const selectedField=fields.includes(requestedField)?requestedField:fields[0];const form=targetType?`<section class="card revision-form"><div><span class="eyebrow">Budget lock</span><h2>Record the reasoned change</h2><p>This update and its reason will be retained in the audit trail.</p></div><form id="revision-form">${select('Field','field_name',selectedField,fields)}${field('New value','new_value','', 'number','required step="0.01"')}<label class="field"><span>Reason</span><textarea name="reason" required placeholder="Explain who approved the change and why"></textarea></label><button class="btn primary">Apply revision</button></form></section>`:'';shell('Budget revisions',`${engagementTabs(id,e.complexity_mode)}${form}<section class="card"><div class="section-heading"><div><span class="eyebrow">Audit trail</span><h2>Reasoned re-baselines</h2></div></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Scope</th><th>Field</th><th>Old</th><th>New</th><th>Reason</th></tr></thead><tbody>${rows||'<tr><td colspan="6">No revisions recorded</td></tr>'}</tbody></table></div><p class="hint">Revisions originate from a blocked budget edit after activation.</p></section>`);document.getElementById('revision-form')?.addEventListener('submit',async(event)=>{event.preventDefault();const body={...formObject(event.currentTarget),target_type:targetType,target_id:Number(targetId)};try{await api(`/api/engagements/${id}/revisions`,{method:'POST',body});history.replaceState({},'',`/engagements/${id}/revisions`);toast('Budget revision applied');renderRevisions(id);}catch(error){toast(error.message,'error');}});}catch(error){shell('Budget revisions',errorPanel(error));}
}

async function renderExpenses(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;const rows=data.expenses.map(x=>`<tr><td>${esc(x.incurred_date||'')}</td><td>${esc(x.expense_type.replaceAll('_',' '))}</td><td>${esc(x.phase_name||'Engagement-wide')}</td><td>${esc(x.description||'')}</td><td>${money(x.amount)}</td><td><button class="icon-btn" aria-label="Delete expense" data-delete-expense="${x.id}">×</button></td></tr>`).join('');const form=e.status==='closed'?'':`<section class="card side-form"><h2>Add expense</h2><form id="expense-form">${select('Type','expense_type','crowe_paid',[['crowe_paid','Crowe paid'],['client_paid','Client paid']])}${select('Phase','phase_id','',[['','Engagement-wide'],...data.phases.map(p=>[p.id,p.phase_name])])}${field('Description','description')}${field('Amount','amount','', 'number','required step="0.01"')}${field('Incurred date','incurred_date','', 'date')}<button class="btn primary">Save expense</button></form></section>`;shell('Expenses',`${engagementTabs(id,e.complexity_mode)}<div class="split-layout"><section class="card"><h2>Expense ledger</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Phase</th><th>Description</th><th>Amount</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="6">No expenses</td></tr>'}</tbody></table></div><p class="hint">Crowe-paid expenses reduce realization. Client-paid expenses are informational and do not affect budget or realization.</p></section>${form}</div>`);document.getElementById('expense-form')?.addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(event.currentTarget);body.phase_id=body.phase_id?Number(body.phase_id):null;try{await api(`/api/engagements/${id}/expenses`,{method:'POST',body});toast('Expense saved');renderExpenses(id);}catch(error){toast(error.message,'error');}});document.querySelectorAll('[data-delete-expense]').forEach(b=>b.addEventListener('click',async()=>{if(!confirmAction('Delete expense','Realization and expense totals will recalculate immediately.'))return;await api(`/api/engagements/${id}/expenses/${b.dataset.deleteExpense}`,{method:'DELETE'});renderExpenses(id);}));}catch(error){shell('Expenses',errorPanel(error));}
}

async function renderHistory(id) {
  try {
    const data=await api(`/api/engagements/${id}`),e=data.engagement;
    const snapshots=await api(`/api/engagements/${id}/snapshots`);
    const rows=snapshots.map(x=>`<tr><td>${esc(x.week_end_date)}</td><td>${esc(x.imported_at)}</td><td>${x.row_count}</td><td>${num(x.hours)}</td><td>${money(x.fees)}</td><td>${num(x.cumulative_hours)}</td><td>${money(x.cumulative_fees)}</td><td>${esc(x.notes||'')}</td><td><button class="icon-btn" aria-label="Delete snapshot for ${esc(x.week_end_date)}" data-delete-snapshot="${x.id}" ${e.status==='closed'?'disabled':''}>×</button></td></tr>`).join('');
    const events=(data.events||[]).map(x=>`<tr><td>${esc(x.created_at)}</td><td>${esc(x.event_type.replaceAll('_',' '))}</td><td>${esc(x.description)}</td></tr>`).join('');
    shell('History and audit',`${engagementTabs(id,e.complexity_mode)}<section class="card"><h2>Committed imports</h2><p class="hint">Delete a snapshot only to correct a bad import. A recovery backup is created automatically before deletion.</p><div class="table-wrap"><table><thead><tr><th>Week end</th><th>Imported</th><th>Rows</th><th>Hours</th><th>Fees</th><th>Cumulative hours</th><th>Cumulative fees</th><th>Notes</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="9">No imports</td></tr>'}</tbody></table></div></section><section class="card"><h2>Activity audit</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Action</th><th>Explanation</th></tr></thead><tbody>${events||'<tr><td colspan="3">No activity recorded</td></tr>'}</tbody></table></div></section>`);
    document.querySelectorAll('[data-delete-snapshot]').forEach(b=>b.addEventListener('click',async()=>{if(!confirmAction('Delete import snapshot','All time entries in this snapshot will be removed. A recovery backup will be created first.'))return;await api(`/api/engagements/${id}/snapshots/${b.dataset.deleteSnapshot}`,{method:'DELETE'});toast('Snapshot deleted and recovery backup created');renderHistory(id);}));
  } catch(error) { shell('History and audit',errorPanel(error)); }
}

async function renderExport(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;shell('Export engagement',`${engagementTabs(id,e.complexity_mode)}<section class="export-hero"><div><span class="eyebrow">Partner-ready reporting</span><h2>Engagement Summary first</h2><p>Both formats lead with the established Engagement Summary structure. Excel also includes weekly detail, adjustments, expenses and revisions.</p></div><div class="export-actions"><a class="btn primary" href="/api/engagements/${id}/export/excel">Download Excel</a><button class="btn secondary" id="print-report">Open print report</button></div></section><section class="card"><label class="field"><span>Status narrative</span><textarea id="narrative" rows="6" placeholder="Optional context for the print-ready report"></textarea></label></section>`);document.getElementById('print-report').addEventListener('click',()=>window.open(`/api/engagements/${id}/export/html?narrative=${encodeURIComponent(document.getElementById('narrative').value)}`,'_blank'));}catch(error){shell('Export engagement',errorPanel(error));}
}

async function renderSettings() {
  try {
    const data=await api('/api/settings/rates');
    const rateRows=Object.entries(data.rates).map(([role,rate])=>`<tr><td><input value="${esc(role)}" data-rate-role readonly></td><td><input type="number" value="${rate}" data-rate-value></td><td>${role.startsWith('Offshore')?'<span class="os-badge">Offshore</span>':'Onshore'}</td></tr>`).join('');
    const backupDate=data.latest_backup_modified?new Date(data.latest_backup_modified*1000).toLocaleString():'No automatic backup yet';
    shell('Settings',`<section class="settings-intro"><div><span class="eyebrow">First-time setup</span><h2>Review these values before creating an engagement</h2><p>Rate and discount defaults are copied to new team members. Existing engagements keep their own values.</p></div><a href="/help#setup">Open setup instructions</a></section><section class="settings-grid"><div class="card"><div class="section-heading"><div><span class="eyebrow">Rate card</span><h2>Default internal rates</h2></div></div><div class="table-wrap"><table><thead><tr><th>Role</th><th>Internal or standard</th><th>Pool</th></tr></thead><tbody id="rate-rows">${rateRows}</tbody></table></div></div><div class="stack"><section class="card"><h2>Budget defaults</h2><form id="settings-form">${field('Engagement discount percent','engagement_discount_rate',Number(data.engagement_discount_rate||0)*100,'number','min="0" max="100" step="0.1"')}${field('Contract discount percent','contract_discount_rate',Number(data.contract_discount_rate||0)*100,'number','min="0" max="100" step="0.1"')}${field('Variance threshold hours','variance_threshold_hours',data.variance_threshold_hours,'number','min="0" step="0.25"')}${field('Variance threshold percent','variance_threshold_pct',Number(data.variance_threshold_pct||0)*100,'number','min="0" step="1"')}${helpText('How discounts work','A 10 percent engagement discount turns a 350 standard rate into a 315 engagement rate. Engagement and contract discounts are applied independently.')}<button class="btn primary">Save settings</button></form></section><section class="card database-card"><h2>Database and recovery</h2><p>Your production data is stored locally at:</p><p class="mono">${esc(data.db_path)}</p><p><b>Latest recovery backup</b><br>${esc(backupDate)}</p><div class="button-row"><button class="btn primary" id="create-backup">Create recovery backup</button><a class="btn secondary" href="/api/settings/backup">Download backup</a></div><form id="restore-form"><label class="upload-zone compact-upload"><input name="file" type="file" accept=".db" required><strong>Choose a backup to restore</strong><span>The current database will be preserved first.</span></label><button class="btn danger">Validate and restore</button></form></section><section class="card"><h2>Guidance</h2><p>Show the welcome checklist again on the Dashboard.</p><button class="btn secondary" id="reset-guide">Reset first-time guide</button><p class="hint">Application version ${esc(data.app_version)} · Schema version ${data.schema_version}</p></section></div></section>`);
    bindNavigation();
    document.getElementById('settings-form').addEventListener('submit',async(event)=>{event.preventDefault();const rates={};document.querySelectorAll('#rate-rows tr').forEach(row=>rates[row.querySelector('[data-rate-role]').value]=Number(row.querySelector('[data-rate-value]').value||0));const body=formObject(event.currentTarget);body.engagement_discount_rate=Number(body.engagement_discount_rate||0)/100;body.contract_discount_rate=Number(body.contract_discount_rate||0)/100;body.variance_threshold_pct=Number(body.variance_threshold_pct||0)/100;body.rates=rates;try{await api('/api/settings/rates',{method:'PUT',body});toast('Settings saved');renderSettings();}catch(error){toast(error.message,'error');}});
    document.getElementById('create-backup').addEventListener('click',async()=>{try{await api('/api/settings/backup',{method:'POST',body:{}});toast('Recovery backup created');renderSettings();}catch(error){toast(error.message,'error');}});
    document.getElementById('restore-form').addEventListener('submit',async(event)=>{event.preventDefault();if(!confirmAction('Restore database backup','The current database will be preserved automatically, then replaced by the selected backup.'))return;const form=new FormData(event.currentTarget);try{const response=await fetch('/api/settings/restore',{method:'POST',body:form});const result=await response.json();if(!response.ok)throw new Error(result.error?.message||'Restore failed');toast('Backup restored successfully');history.pushState({},'','/dashboard');renderDashboard();}catch(error){toast(error.message,'error');}});
    document.getElementById('reset-guide').addEventListener('click',()=>{localStorage.removeItem('budget-onboarding-complete');state.onboardingComplete=false;toast('First-time guide reset');});
  } catch(error) { shell('Settings',errorPanel(error)); }
}

function renderHelp() {
  shell('Help and operating guide',`<section class="help-hero"><div><span class="eyebrow">Engagement Budget Tracker</span><h2>Choose what you need to do</h2><p>These instructions use the same words and buttons you will see in the tracker.</p></div><nav class="help-jumps"><a href="#setup">Set up the tracker</a><a href="#engagement">Create an engagement</a><a href="#weekly">Run the weekly budget</a><a href="#recovery">Correct a mistake</a><a href="#glossary">Understand the terms</a></nav></section>
  <section class="help-section" id="setup"><span class="step-number">01</span><div><h2>Set up the tracker</h2><ol><li>Open Settings.</li><li>Review the role rate card.</li><li>Enter engagement and contract discounts as normal percentages.</li><li>Confirm variance thresholds.</li><li>Select Save settings.</li><li>Create a recovery backup.</li></ol></div></section>
  <section class="help-section" id="engagement"><span class="step-number">02</span><div><h2>Create an engagement</h2><ol><li>Select New engagement.</li><li>Use the exact Cognos project identifier as the engagement code.</li><li>Choose Simple for one overall budget or Complex for phase and weekly planning.</li><li>Add every expected worker using the exact Cognos “Last, First” name.</li><li>Verify rates and offshore status.</li><li>For Complex mode, add every phase and its signed statement of work budget.</li><li>Set phase target hours, distribute across weeks and make every reconciliation difference zero.</li><li>Read and select the baseline confirmation, then create the engagement.</li></ol></div></section>
  <section class="help-section" id="weekly"><span class="step-number">03</span><div><h2>Run the weekly budget</h2><ol><li>Create a recovery backup in Settings.</li><li>Export the raw Time and Cost Detail workbook from Cognos.</li><li>Open the engagement and select Weekly import.</li><li>Choose the file and select Preview import.</li><li>Resolve unknown workers, project mismatches and unmatched phases.</li><li>Review variance warnings and selected totals.</li><li>Select Review and commit import. The tracker creates another recovery backup.</li><li>Return to each phase and update future Forecast values.</li><li>Review Overview, then select Export to create the partner report.</li></ol></div></section>
  <section class="help-section" id="recovery"><span class="step-number">04</span><div><h2>Correct a mistake</h2><p>For a bad import, open History and delete only the affected snapshot. The tracker backs up first. Preview and commit the corrected Cognos file. For a larger problem, use Settings to validate and restore a database backup.</p></div></section>
  <section class="help-section glossary" id="glossary"><span class="step-number">05</span><div><h2>Glossary</h2><dl><dt>Statement of work budget</dt><dd>The signed fee budget for the work.</dd><dt>Standard rate</dt><dd>The internal value of a person’s time.</dd><dt>Engagement rate</dt><dd>The rate used for engagement planned fees.</dd><dt>Contract rate</dt><dd>The rate reported by Cognos and compared with the statement of work budget.</dd><dt>Realization</dt><dd>Effective statement of work budget less Crowe-paid expenses, divided by actual standard fees.</dd><dt>Approved budget addition</dt><dd>An engagement-wide approved budget increase.</dd><dt>Approved budget reduction</dt><dd>An approved budget decrease that requires an explanation.</dd><dt>Change order</dt><dd>An approved addition assigned to a specific phase.</dd><dt>Budget, Actual and Forecast</dt><dd>The approved baseline, imported Cognos time and future estimate.</dd></dl></div></section>`);
}

function shell(title, body, actions='') {
  app.innerHTML = `<div class="layout"><aside class="sidebar">
    <a class="brand" href="/dashboard"><img src="/static/assets/crowe-logo-white.svg" alt="Crowe"><span>Engagement<br>Budget Tracker</span></a>
    <nav>${navLink('/dashboard','Dashboard')}${navLink('/proposals','Proposals')}${navLink('/engagements/new','New engagement')}${navLink('/engagements/drafts','In progress')}${navLink('/settings','Settings')}${navLink('/settings/rate-cards','Rate cards')}${navLink('/help','Help')}</nav>
    <div class="sidebar-foot"><span>Application version ${esc(window.APP_VERSION||'4.0.0')} | Database format ${esc(window.SCHEMA_VERSION||4)}</span><button id="theme-toggle" class="theme-toggle" aria-label="Toggle color theme">${state.theme === 'light' ? 'Dark' : 'Light'} mode</button></div>
  </aside><main class="main"><header class="topbar"><div><span class="eyebrow">Budget governance</span><h1>${esc(title)}</h1></div><div class="top-actions">${actions}</div></header><div class="content">${body}</div></main></div>`;
  bindNavigation();
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('budget-theme', state.theme);
    document.documentElement.dataset.theme = state.theme;
    render();
  });
}

function proposalTabs(id, isNew=false) {
  return `<nav class="tabs"><a href="/proposals" data-link>All proposals</a>${isNew ? '<a href="/proposals/new" data-link>New proposal</a>' : `<a href="/proposals/${id}" data-link>Proposal detail</a>`}</nav>`;
}

function proposalPersonTemplate(role, baseRate=0, discountRate=0) {
  const discount = Number(discountRate || 0);
  const base = Number(baseRate || 0);
  return {id:null,name:'',role,base_rate:base,discount_rate:discount,rough_rate:base*(1-discount),weeks:{}};
}

function ensureProposalWeeks(model) {
  const weeks = weekDates(model.proposal.first_monday, model.proposal.duration_weeks);
  model.people.forEach((person) => {
    const next = {};
    weeks.forEach((week) => {
      next[week] = person.weeks[week] || {budgeted_hours:0, forecasted_hours:null};
    });
    person.weeks = next;
  });
  return weeks;
}

function proposalPersonTotals(person, weeks) {
  const budgeted = weeks.reduce((sum, week) => sum + Number(person.weeks[week]?.budgeted_hours || 0), 0);
  const forecast = weeks.reduce((sum, week) => {
    const cell = person.weeks[week] || {};
    return sum + Number(cell.forecasted_hours == null || cell.forecasted_hours === '' ? cell.budgeted_hours || 0 : cell.forecasted_hours || 0);
  }, 0);
  const baseRate = Number(person.base_rate || 0);
  const planningRate = Number(person.rough_rate || 0);
  const baseFees = forecast * baseRate;
  const fees = forecast * planningRate;
  return {budgeted, forecast, baseFees, discount:baseFees-fees, fees};
}

async function renderDashboard() {
  shell('Engagement portfolio', '<div class="loading">Loading engagements...</div>', '<div class="button-row"><a class="btn secondary" href="/proposals/new" data-link>New proposal</a><a class="btn primary" href="/engagements/new" data-link>New engagement</a></div>');
  try {
    const [data, proposalData] = await Promise.all([api('/api/engagements'), api('/api/proposals').catch(() => ({proposals:[]}))]);
    const m = data.metrics;
    const cards = data.engagements.map((item) => {
      const x = item.metrics;
      const statusSlug = String(x.status || '').toLowerCase().replaceAll(' ','-');
      return `<a class="engagement-card status-${statusSlug}" href="/engagements/${item.id}" data-link>
        <div class="card-kicker"><span>${esc(item.engagement_code)}</span>${statusBadge(x.status)}</div>
        <h2>${esc(item.client_name)}</h2><p>${esc(item.engagement_lead || 'Lead not assigned')}</p>
        <div class="progress status-${statusSlug}"><i style="width:${Math.min(100, Math.max(0, x.utilization_pct*100))}%"></i></div>
        <div class="card-stats"><span><b>${num(x.hours_to_date)}</b> hours</span><span><b>${money(x.fees_to_date_contract)}</b> used</span></div>
        <small>${esc(item.complexity_mode)} mode | Last import ${esc(item.last_import_date || 'none')}</small></a>`;
    }).join('');
    const proposalCards = (proposalData.proposals || []).slice(0,3).map((item) => `<a class="engagement-card proposal-card" href="/proposals/${item.id}" data-link>
      <div class="card-kicker"><span>${esc(item.proposal_code)}</span><span class="status planning">Proposal</span></div>
      <h2>${esc(item.client_name)}</h2><p>${esc(item.engagement_type || 'Planning estimate')}</p>
      <div class="card-stats"><span><b>${num(item.metrics.forecast_hours)}</b> forecast hours</span><span><b>${money(item.metrics.estimated_fees)}</b> estimated fees</span></div>
      <small>${item.metrics.people_count} people | starts ${esc(item.first_monday || 'date not set')}</small></a>`).join('');
    const welcome = !state.onboardingComplete ? `<section class="welcome-card"><div><span class="eyebrow">First-time setup</span><h2>Welcome to the Engagement Budget Tracker</h2><p>Start by reviewing the rate card, then build either a proposal or an engagement. The tracker will guide you before any actual time is committed.</p></div><div class="welcome-actions"><a class="btn secondary" href="/settings" data-link>Review settings</a><button class="btn primary" id="complete-onboarding">I understand</button></div></section>` : '';
    shell('Engagement portfolio', `${welcome}<section class="workflow-card"><div><span class="eyebrow">Weekly routine</span><h2>Run the budget in seven steps</h2></div><ol class="workflow-steps"><li>Back up</li><li>Export Cognos</li><li>Preview</li><li>Resolve warnings</li><li>Commit actuals</li><li>Update forecast</li><li>Export report</li></ol><a href="/help#weekly">Open the guided weekly checklist</a></section><section class="metrics four">${metric('Active engagements', m.total_active_engagements)}${metric('Hours this month', num(m.total_hours_mtd))}${metric('Fees this month', money(m.total_fees_mtd))}${metric('Needs attention', m.watch_or_over_budget)}</section><section class="card"><div class="section-heading"><div><span class="eyebrow">Pre-engagement planning</span><h2>Forecast before creating the engagement</h2></div><a class="btn secondary" href="/proposals" data-link>Open proposals</a></div><div class="engagement-grid">${proposalCards || '<div class="empty">No proposals yet. Start a proposal to estimate staffing and fees before setup.</div>'}</div></section><div class="section-heading"><div><span class="eyebrow">Portfolio</span><h2>Current engagements</h2></div></div><section class="engagement-grid">${cards || '<div class="empty">No engagements yet. Create the first budget to begin.</div>'}</section>`, '<div class="button-row"><a class="btn secondary" href="/proposals/new" data-link>New proposal</a><a class="btn primary" href="/engagements/new" data-link>New engagement</a></div>');
    bindNavigation();
    document.getElementById('complete-onboarding')?.addEventListener('click',()=>{localStorage.setItem('budget-onboarding-complete','true');state.onboardingComplete=true;renderDashboard();});
  } catch (error) { shell('Engagement portfolio', errorPanel(error)); }
}

async function renderProposals() {
  shell('Proposal planning', '<div class="loading">Loading proposals...</div>', '<a class="btn primary" href="/proposals/new" data-link>New proposal</a>');
  try {
    const data = await api('/api/proposals');
    const cards = (data.proposals || []).map((item) => `<a class="engagement-card proposal-card" href="/proposals/${item.id}" data-link><div class="card-kicker"><span>${esc(item.proposal_code)}</span><span class="status planning">Proposal</span></div><h2>${esc(item.client_name)}</h2><p>${esc(item.engagement_type || 'Planning estimate')}</p><div class="card-stats"><span><b>${num(item.metrics.forecast_hours)}</b> forecast hours</span><span><b>${money(item.metrics.estimated_fees)}</b> estimated fees</span></div><small>${item.metrics.people_count} people | starts ${esc(item.first_monday || 'date not set')}</small></a>`).join('');
    shell('Proposal planning', `${proposalTabs()}<section class="welcome-card"><div><span class="eyebrow">Estimate first</span><h2>Forecast staffing before creating the engagement</h2><p>Use proposals to shape the weekly plan, role rates, discounts and expected fees without locking anything into the engagement ledger.</p></div><div class="welcome-actions"><a class="btn primary" href="/proposals/new" data-link>Start proposal</a></div></section><section class="engagement-grid">${cards || '<div class="empty">No proposals yet. Create the first proposal to estimate staffing before setup.</div>'}</section>`, '<a class="btn primary" href="/proposals/new" data-link>New proposal</a>');
  } catch(error) { shell('Proposal planning', errorPanel(error)); }
}

async function renderProposalEditor(id=null) {
  shell(id ? 'Proposal detail' : 'New proposal', '<div class="loading">Loading proposal...</div>');
  try {
    const rateCardData = await api('/api/settings/rate-cards');
    const rateCard = (rateCardData.rate_cards || []).find((card) => card.is_active !== 0) || rateCardData.rate_cards?.[0];
    const roleRates = rateCard?.rates || [];
    if (!roleRates.length) throw new Error('Add at least one governed role in Rate cards before creating a proposal.');
    const defaultRole = roleRates.find((rate) => rate.role_name === 'Manager')?.role_name || roleRates[0].role_name;
    const rateFields = {standard:'standard_rate', engagement:'engagement_rate', contract:'contract_rate'};
    function applyPersonPricing(person) {
      const rate = roleRates.find((item) => item.role_name === person.role) || roleRates[0];
      person.role = rate.role_name;
      person.base_rate = Number(rate[rateFields[model.proposal.rate_basis]] || 0);
      person.discount_rate = Math.min(1, Math.max(0, Number(person.discount_rate || 0)));
      person.rough_rate = Number((person.base_rate * (1-person.discount_rate)).toFixed(2));
    }
    let model = {
      proposal: {proposal_code:'',client_name:'',engagement_type:'Advisory',first_monday:'2026-08-17',duration_weeks:8,rate_basis:'standard',discount_rate:0,notes:''},
      people: []
    };
    model.people = [proposalPersonTemplate(defaultRole, roleRates.find((rate) => rate.role_name === defaultRole)?.standard_rate, 0)];
    if (id) {
      const data = await api(`/api/proposals/${id}`);
      model = {
        proposal: {...data.proposal,rate_basis:data.proposal.rate_basis||'standard',discount_rate:Number(data.proposal.discount_rate||0)},
        people: data.people.map((person) => ({
          id: person.id,
          name: person.name || '',
          role: person.role || defaultRole,
          base_rate: Number(person.base_rate ?? person.rough_rate ?? 0),
          discount_rate: Number(person.discount_rate ?? data.proposal.discount_rate ?? 0),
          rough_rate: Number(person.rough_rate || 0),
          weeks: Object.fromEntries((person.weeks || []).map((week) => [week.week_start_date, {budgeted_hours:Number(week.budgeted_hours || 0), forecasted_hours: week.forecasted_hours == null ? null : Number(week.forecasted_hours || 0)}]))
        }))
      };
    }
    model.people.forEach(applyPersonPricing);
    function draw() {
      const weeks = ensureProposalWeeks(model);
      const totals = model.people.map((person) => proposalPersonTotals(person, weeks));
      const metrics = totals.reduce((sum, item) => ({budgeted:sum.budgeted+item.budgeted,forecast:sum.forecast+item.forecast,baseFees:sum.baseFees+item.baseFees,discount:sum.discount+item.discount,fees:sum.fees+item.fees}), {budgeted:0,forecast:0,baseFees:0,discount:0,fees:0});
      const peopleRows = model.people.map((person, index) => {
        const total = totals[index];
        const roleOptions = roleRates.map((rate) => `<option value="${esc(rate.role_name)}" ${rate.role_name===person.role?'selected':''}>${esc(rate.role_name)}</option>`).join('');
        return `<tr><td><input data-proposal-person="${index}:name" value="${esc(person.name)}" placeholder="Last, First" aria-label="Name for proposal person ${index+1}"></td><td><select data-proposal-person="${index}:role" aria-label="Role for proposal person ${index+1}">${roleOptions}</select></td><td class="money-cell" data-proposal-base-rate="${index}">${money(person.base_rate)}</td><td><input class="discount-input" type="number" min="0" max="100" step="0.25" data-proposal-person="${index}:discount_percent" value="${Number((person.discount_rate*100).toFixed(2))}" aria-label="Discount percent for ${esc(person.name||`proposal person ${index+1}`)}"></td><td class="money-cell" data-proposal-planning-rate="${index}">${money(person.rough_rate)}</td><td data-proposal-budget-total="${index}">${num(total.budgeted)}</td><td data-proposal-forecast-total="${index}">${num(total.forecast)}</td><td class="money-cell" data-proposal-fees="${index}">${money(total.fees)}</td><td><button class="icon-btn" data-remove-proposal-person="${index}" aria-label="Remove proposal person">X</button></td></tr>`;
      }).join('');
      const gridRows = model.people.map((person, index) => `<tr><th>${esc(person.name || `Person ${index+1}`)}<label class="target-hours">Distribute total <button type="button" class="btn text" data-proposal-distribute="${index}">Evenly fill budget</button></label></th>${weeks.map((week) => {
        const cell = person.weeks[week] || {budgeted_hours:0, forecasted_hours:null};
        return `<td><label>Budget hours <input type="number" step="0.25" data-proposal-week="${index}:${week}:budgeted_hours" value="${cell.budgeted_hours ?? 0}"></label><label>Forecast hours <input type="number" step="0.25" data-proposal-week="${index}:${week}:forecasted_hours" value="${cell.forecasted_hours ?? ''}" placeholder="Uses budget hours"></label></td>`;
      }).join('')}<td><strong>${num(totals[index].forecast)}</strong></td></tr>`).join('');
      const conversionRoles = (person,index) => `<select data-convert-role="${index}" aria-label="Confirmed role for ${esc(person.name||`proposal person ${index+1}`)}">${roleRates.map((rate)=>`<option value="${esc(rate.role_name)}" ${rate.role_name===person.role?'selected':''}>${esc(rate.role_name)}</option>`).join('')}</select>`;
      const convertPanel = id ? `<section class="card side-form"><h2>Convert to engagement</h2><p class="hint">Confirm the engagement fields and every proposed person. Proposal discounts and planning rates do not replace governed engagement rates.</p><form id="proposal-convert-form">${field('Engagement code','engagement_code','', 'text','required')}${field('Confirmed client','client_name',model.proposal.client_name,'text','required')}${field('Engagement lead','engagement_lead','','text','required')}${select('Complexity mode','complexity_mode','complex',[['complex','Complex with weekly phases'],['simple','Simple overall budget']])}${field('Engagement first Monday','first_monday',model.proposal.first_monday,'date','required')}<div class="table-wrap"><table><thead><tr><th>Confirmed name</th><th>Role</th><th>Conversion phase</th></tr></thead><tbody>${model.people.map((person,index)=>`<tr><td><input data-convert-name="${index}" value="${esc(person.name)}" required></td><td>${conversionRoles(person,index)}</td><td><input data-convert-phase="${index}" value="Proposal scope" aria-label="Conversion phase for ${esc(person.name||`person ${index+1}`)}"></td></tr>`).join('')}</tbody></table></div><button class="btn primary">Convert proposal</button></form></section>` : '';
      const pricingControls = `<section class="proposal-pricing"><div><span class="eyebrow">Pricing assumptions</span><h3>Choose role rates and discounts</h3><p class="hint">The rate source sets each role's base rate. Individual discounts calculate the planning rate used for this proposal only.</p></div>${select('Rate source','rate_basis',model.proposal.rate_basis,[['standard','Standard rate'],['engagement','Engagement rate'],['contract','Contract rate']],'data-proposal-rate-basis')}${field('Default discount percent','proposal_discount_percent',Number((model.proposal.discount_rate*100).toFixed(2)),'number','min="0" max="100" step="0.25" id="proposal-default-discount"')}<button class="btn secondary" id="apply-proposal-discount" type="button">Apply discount to all people</button></section>`;
      shell(id ? model.proposal.client_name || 'Proposal detail' : 'New proposal', `${proposalTabs(id, !id)}<section class="metrics five proposal-metrics">${metric('People', model.people.length)}${metric('Forecast hours', num(metrics.forecast))}${metric('Fees before discount', money(metrics.baseFees))}${metric('Discount amount', money(metrics.discount))}${metric('Estimated fees', money(metrics.fees))}</section><div class="split-layout"><section class="card"><div class="section-heading"><div><span class="eyebrow">Proposal header</span><h2>Scope, timing and pricing</h2></div><div class="button-row"><button class="btn secondary" id="add-proposal-person">Add person</button><button class="btn primary" id="save-proposal">${id ? 'Save proposal' : 'Create proposal'}</button></div></div><div class="form-grid">${field('Proposal code','proposal_code',model.proposal.proposal_code,'text','required data-proposal="proposal_code"')}${field('Client name','client_name',model.proposal.client_name,'text','required data-proposal="client_name"')}${field('First Monday','first_monday',model.proposal.first_monday,'date','required data-proposal="first_monday"')}${field('Duration weeks','duration_weeks',model.proposal.duration_weeks,'number','min="1" step="1" required data-proposal="duration_weeks"')}${field('Engagement type','engagement_type',model.proposal.engagement_type,'text','data-proposal="engagement_type"')}<label class="field"><span>Notes</span><textarea data-proposal="notes">${esc(model.proposal.notes || '')}</textarea></label></div>${pricingControls}<div class="table-wrap"><table class="proposal-people-table"><thead><tr><th>Name</th><th>Role</th><th>Base role rate</th><th>Discount percent</th><th>Planning rate</th><th>Budget hours</th><th>Forecast hours</th><th>Estimated fees</th><th></th></tr></thead><tbody>${peopleRows}</tbody></table></div></section>${convertPanel}</div><section class="card"><div class="section-heading"><div><span class="eyebrow">Forecast view</span><h2>Weekly plan before engagement setup</h2></div><span>${weeks.length} weeks</span></div><p class="hint">Budget is the starting estimate. Forecast is the current estimate. Leave Forecast blank to reuse the budget value. Enter 0 to explicitly plan no hours for that week.</p><div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Person</th>${weeks.map((week) => `<th>${new Date(`${week}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</th>`).join('')}<th>Forecast</th></tr></thead><tbody>${gridRows}</tbody></table></div></section>`, `${id ? '<a class="btn secondary" href="/proposals" data-link>Back to proposals</a>' : ''}`);
      bindProposalEvents(weeks);
    }
    function bindProposalEvents(weeks) {
      function refreshProposalTotals() {
        const totals=model.people.map(person=>proposalPersonTotals(person,weeks));
        const summary=totals.reduce((sum,item)=>({forecast:sum.forecast+item.forecast,baseFees:sum.baseFees+item.baseFees,discount:sum.discount+item.discount,fees:sum.fees+item.fees}),{forecast:0,baseFees:0,discount:0,fees:0});
        const cards=document.querySelectorAll('.proposal-metrics .metric strong');
        if(cards.length>=5){cards[0].textContent=String(model.people.length);cards[1].textContent=num(summary.forecast);cards[2].textContent=money(summary.baseFees);cards[3].textContent=money(summary.discount);cards[4].textContent=money(summary.fees);}
        totals.forEach((total,index)=>{
          const person=model.people[index];
          const values={baseRate:money(person.base_rate),planningRate:money(person.rough_rate),budget:num(total.budgeted),forecast:num(total.forecast),fees:money(total.fees)};
          const nodes={baseRate:document.querySelector(`[data-proposal-base-rate="${index}"]`),planningRate:document.querySelector(`[data-proposal-planning-rate="${index}"]`),budget:document.querySelector(`[data-proposal-budget-total="${index}"]`),forecast:document.querySelector(`[data-proposal-forecast-total="${index}"]`),fees:document.querySelector(`[data-proposal-fees="${index}"]`)};
          Object.keys(nodes).forEach((key)=>{if(nodes[key])nodes[key].textContent=values[key];});
        });
      }
      document.querySelectorAll('[data-proposal]').forEach((node) => node.addEventListener('input', () => {
        model.proposal[node.dataset.proposal] = node.value;
        if(node.dataset.proposal === 'duration_weeks') model.proposal.duration_weeks = Number(node.value || 1);
      }));
      document.querySelectorAll('[data-proposal="duration_weeks"],[data-proposal="first_monday"]').forEach(node=>node.addEventListener('change',draw));
      document.querySelector('[data-proposal-rate-basis]')?.addEventListener('change', (event) => {
        model.proposal.rate_basis=event.currentTarget.value;
        model.people.forEach(applyPersonPricing);
        draw();
      });
      document.getElementById('proposal-default-discount')?.addEventListener('input',(event)=>{
        model.proposal.discount_rate=Math.min(1,Math.max(0,Number(event.currentTarget.value||0)/100));
      });
      document.getElementById('apply-proposal-discount')?.addEventListener('click',()=>{
        model.people.forEach((person)=>{person.discount_rate=model.proposal.discount_rate;applyPersonPricing(person);});
        draw();
      });
      document.querySelectorAll('[data-proposal-person]').forEach((node) => node.addEventListener(node.tagName==='SELECT'?'change':'input', () => {
        const [index, field] = node.dataset.proposalPerson.split(':');
        const person=model.people[Number(index)];
        if(field==='discount_percent') person.discount_rate=Math.min(1,Math.max(0,Number(node.value||0)/100));
        else person[field]=node.value;
        if(field==='role'||field==='discount_percent')applyPersonPricing(person);
        refreshProposalTotals();
      }));
      document.querySelectorAll('[data-proposal-week]').forEach((node) => node.addEventListener('input', () => {
        const [index, week, field] = node.dataset.proposalWeek.split(':');
        const person = model.people[Number(index)];
        person.weeks[week] ||= {budgeted_hours:0, forecasted_hours:null};
        person.weeks[week][field] = field === 'forecasted_hours' && node.value === '' ? null : Number(node.value || 0);
        refreshProposalTotals();
      }));
      document.getElementById('add-proposal-person')?.addEventListener('click', () => {
        const person=proposalPersonTemplate(defaultRole,0,model.proposal.discount_rate);
        applyPersonPricing(person);
        model.people.push(person);
        draw();
      });
      document.querySelectorAll('[data-remove-proposal-person]').forEach((button) => button.addEventListener('click', () => {
        model.people.splice(Number(button.dataset.removeProposalPerson), 1);
        if(!model.people.length){const person=proposalPersonTemplate(defaultRole,0,model.proposal.discount_rate);applyPersonPricing(person);model.people.push(person);}
        draw();
      }));
      document.querySelectorAll('[data-proposal-distribute]').forEach((button) => button.addEventListener('click', () => {
        const person = model.people[Number(button.dataset.proposalDistribute)];
        const total = proposalPersonTotals(person, weeks).budgeted;
        const per = total / Math.max(1, weeks.length);
        weeks.forEach((week) => { person.weeks[week] = {budgeted_hours:per, forecasted_hours:null}; });
        draw();
      }));
      document.getElementById('save-proposal')?.addEventListener('click', async() => {
        try {
          const payload = {
            proposal: model.proposal,
            people: model.people.map((person) => ({
              id: person.id || undefined,
              name: person.name,
              role: person.role,
              base_rate: person.base_rate,
              discount_rate: person.discount_rate,
              rough_rate: person.rough_rate,
              budgeted_hours: proposalPersonTotals(person, weeks).budgeted,
            })),
            weekly_budgets: model.people.flatMap((person, personIndex) => weeks.map((week) => ({
              proposal_person_id: person.id || undefined,
              person_index: personIndex,
              week_start_date: week,
              budgeted_hours: Number(person.weeks[week]?.budgeted_hours || 0),
              forecasted_hours: person.weeks[week]?.forecasted_hours,
            }))),
          };
          const data = await api(id ? `/api/proposals/${id}` : '/api/proposals', {method:id ? 'PUT' : 'POST', body:payload});
          toast(id ? 'Proposal saved' : 'Proposal created');
          history.replaceState({}, '', `/proposals/${data.proposal.id}`);
          render();
        } catch(error) { toast(error.message, 'error'); }
      });
      document.getElementById('proposal-convert-form')?.addEventListener('submit', async(event) => {
        event.preventDefault();
        try {
          const body = formObject(event.currentTarget);
          body.people=model.people.map((person,index)=>({proposal_person_id:person.id,name:document.querySelector(`[data-convert-name="${index}"]`).value,role:document.querySelector(`[data-convert-role="${index}"]`).value,phase_name:document.querySelector(`[data-convert-phase="${index}"]`).value}));
          const result = await api(`/api/proposals/${id}/convert`, {method:'POST', body});
          toast('Proposal converted to engagement');
          history.pushState({}, '', `/engagements/${result.engagement_id}`);
          render();
        } catch(error) { toast(error.message, 'error'); }
      });
    }
    draw();
  } catch(error) { shell(id ? 'Proposal detail' : 'New proposal', errorPanel(error)); }
}

function drawImportPreview(id,preview,phases,engagement) {
  const area=document.getElementById('preview-area');
  const unmatched=[...new Set(preview.rows.filter(row=>row.flags?.includes('unmatched_phase')).map(row=>row.phase_desc))];
  const assigns=unmatched.map(desc=>`<label class="field compact"><span>Assign "${esc(desc||'(blank)')}" to</span><select data-phase-assignment="${esc(desc)}"><option value="">Leave pending</option>${phases.map(phase=>`<option value="${phase.id}">${esc(phase.phase_name)}</option>`).join('')}</select></label>`).join('');
  const guidance={zero_hours:'Zero-hour source record',worker_unknown:'Imported and queued for team assignment',worker_unauthorized:'Known inactive worker requires review',project_mismatch:'Imported and queued for review',unmatched_phase:'Imported and queued for phase assignment',variance_flagged:'Review the week-over-week change'};
  const rows=preview.rows.map(row=>`<tr class="${row.flag||''}"><td>${esc(row.reconciliation_action)}</td><td>${esc(row.worker_name)}</td><td>${esc(row.week_end_date)}</td><td>${esc(row.phase_desc||'Unmatched')}</td><td>${num(row.hours)}</td><td>${money(row.fees_contract_rate)}</td><td>${(row.flags||[]).map(flag=>`<span class="flag">${esc(flag.replaceAll('_',' '))}</span>`).join('')}<small class="flag-guidance">${esc(guidance[row.flag]||'Ready to reconcile')}</small>${row.before?`<details><summary>Before and after</summary><small>${num(row.before.hours)} hours / ${money(row.before.fees_contract_rate)} to ${num(row.after.hours)} hours / ${money(row.after.fees_contract_rate)}</small></details>`:''}</td></tr>`).join('');
  const removals=(preview.rows_to_remove||[]).map(row=>`<tr><td class="mono">${esc(row.transaction_id)}</td><td>${esc(row.worker_name||'')}</td><td>${esc(row.week_end_date||'')}</td><td>${num(row.hours)}</td><td>${money(row.fees_contract_rate)}</td></tr>`).join('');
  area.innerHTML=`<section class="metrics four">${metric('Insert',preview.rows_to_insert)}${metric('Update',preview.rows_to_update)}${metric('Remove',(preview.rows_to_remove||[]).length)}${metric('Exceptions',preview.summary.flagged)}</section><section class="flag-key"><h2>Covered period ${esc(preview.covered_start_date||'')} to ${esc(preview.covered_end_date||'')}</h2><div><span><b>Pending exceptions</b> stay included until resolved or excluded</span><span><b>Updates</b> correct rows in place</span><span><b>Removals</b> require confirmation</span><span><b>Exclusions</b> remain auditable</span></div></section>${assigns?`<section class="card"><h2>Phase assignments</h2><div class="assignment-grid">${assigns}</div></section>`:''}<section class="card"><div class="table-wrap"><table><thead><tr><th>Action</th><th>Worker</th><th>Week end</th><th>Phase</th><th>Hours</th><th>Contract fees</th><th>Review</th></tr></thead><tbody>${rows}</tbody></table></div>${removals?`<div class="alert warning"><strong>${(preview.rows_to_remove||[]).length} source rows will be removed</strong><span>The new file is authoritative for this period.</span></div><div class="table-wrap"><table><thead><tr><th>Transaction</th><th>Worker</th><th>Week</th><th>Hours</th><th>Fees</th></tr></thead><tbody>${removals}</tbody></table></div>`:''}<label class="field"><span>Snapshot notes</span><textarea id="import-notes"></textarea></label>${engagement.status==='planning'?'<div class="alert warning"><strong>First committed import</strong><span>This activates the engagement.</span></div>':''}<button class="btn primary" id="commit-import">Commit reconciliation</button></section>`;
  document.getElementById('commit-import').addEventListener('click',async()=>{if(!confirmAction(engagement.status==='planning'?'Activate and reconcile first import':'Commit source reconciliation',`${preview.rows_to_insert} insert, ${preview.rows_to_update} update and ${(preview.rows_to_remove||[]).length} removal. A recovery backup will be created.`))return;const phase_assignments={};document.querySelectorAll('[data-phase-assignment]').forEach(input=>{if(input.value)phase_assignments[input.dataset.phaseAssignment]=Number(input.value);});try{const result=await api(`/api/engagements/${id}/import/commit`,{method:'POST',body:{phase_assignments,confirm_removals:(preview.rows_to_remove||[]).length>0,notes:document.getElementById('import-notes').value}});toast(`${result.imported} inserted, ${result.updated} updated and ${result.removed} removed`);renderImport(id);}catch(error){toast(error.message,'error');}});
}

async function renderExport(id) {
  try { const data=await api(`/api/engagements/${id}`),e=data.engagement;shell('Export engagement',`${engagementTabs(id,e.complexity_mode)}<section class="export-hero"><div><span class="eyebrow">Financial and scheduling handoff</span><h2>Choose the audience</h2><p>The financial report mirrors Engagement Summary. The scheduling file is a forward-looking, one-row-per-person hours grid with no totals.</p></div><div class="export-actions"><a class="btn primary" href="/api/engagements/${id}/export/excel">Download financial spreadsheet</a><a class="btn secondary" href="/api/engagements/${id}/export/scheduling">Download scheduling file</a><button class="btn secondary" id="print-report">Open print report</button></div></section><section class="card"><label class="field"><span>Status narrative</span><textarea id="narrative" rows="6"></textarea></label></section>`);document.getElementById('print-report').addEventListener('click',()=>window.open(`/api/engagements/${id}/export/html?narrative=${encodeURIComponent(document.getElementById('narrative').value)}`,'_blank')); } catch(error) { shell('Export engagement',errorPanel(error)); }
}

async function renderRateCards() {
  try { const data=await api('/api/settings/rate-cards');const card=data.rate_cards[0]||{name:'Current governed rates',rates:[]};const rows=card.rates.map((rate,index)=>{const locked=Boolean(rate.locked_at);return `<tr data-governed-rate="${index}"><td><input name="role_name" value="${esc(rate.role_name)}"></td><td><input name="standard_rate" type="number" value="${rate.standard_rate}" ${locked?'readonly title="Locked: already in use by a team member. Create a new rate card vintage to change it."':''}></td><td><input name="engagement_rate" type="number" value="${rate.engagement_rate}"></td><td><input name="contract_rate" type="number" value="${rate.contract_rate}"></td><td><input name="dte_rate" type="number" value="${rate.dte_rate}"></td></tr>`;}).join('');shell('Rate card administration',`<section class="card"><div class="section-heading"><div><span class="eyebrow">Governed defaults</span><h2>${esc(card.name)}</h2></div><button class="btn primary" id="save-rate-card">Save rate card</button></div><p class="hint">Changes apply only to team members added in the future. Existing engagement rates are preserved. Standard rates already in use are locked — create a new rate card vintage to change them.</p><div class="table-wrap"><table><thead><tr><th>Role</th><th>Standard rate</th><th>Engagement rate</th><th>Contract rate</th><th>Advance billing rate</th></tr></thead><tbody>${rows}</tbody></table></div></section>`,'<a class="btn secondary" href="/settings" data-link>Back to settings</a>');document.getElementById('save-rate-card').addEventListener('click',async()=>{if(!confirmAction('Change governed rates','This affects new team members only. Existing engagement rates will not change.'))return;const rates=[...document.querySelectorAll('[data-governed-rate]')].map(row=>formObject(rowToForm(row)));try{await api('/api/settings/rate-cards',{method:'PUT',body:{name:card.name,rates}});toast('Governed rate card saved');renderRateCards();}catch(error){toast(error.message,'error');}}); } catch(error) { shell('Rate card administration',errorPanel(error)); }
}

async function renderEngagementRates(id) {
  try {
    const [data,tiers]=await Promise.all([api(`/api/engagements/${id}`),api(`/api/engagements/${id}/rate-tiers`)]),e=data.engagement;
    const tierRows=tiers.map(tier=>`<tr data-tier-row><td><input name="tier_name" value="${esc(tier.tier_name)}"></td><td><input name="tier_amount" type="number" step="0.01" value="${tier.tier_amount}"></td><td><button type="button" class="btn text danger-text" data-remove-tier>Remove</button></td></tr>`).join('');
    const memberRows=data.team.map(member=>`<tr data-custom-member="${member.id}"><td>${esc(member.name)}</td><td>${esc(member.role||'')}</td><td><input name="engagement_rate" type="number" step="0.01" value="${member.engagement_rate}"></td><td><input name="contract_rate" type="number" step="0.01" value="${member.contract_rate}"></td><td><input name="custom_rate_reason" placeholder="Required master services agreement approval reason"></td><td><button class="btn text" data-save-custom="${member.id}">Apply override</button></td></tr>`).join('');
    shell('Rate model',`${engagementTabs(id,e.complexity_mode)}<section class="card"><div class="section-heading"><div><span class="eyebrow">Engagement pricing</span><h2>Governed discount or flat tiers</h2></div><button class="btn primary" id="save-rate-mode">Save rate model</button></div>${select('Rate mode','rate_mode',e.rate_mode,[['governed','Governed role rates'],['flat_tiered','Flat negotiated tiers']])}<div id="tier-builder"><div class="section-heading"><h3>Flat tiers</h3><button class="btn secondary" id="add-rate-tier">Add tier</button></div><div class="table-wrap"><table><thead><tr><th>Tier name</th><th>Flat rate</th><th></th></tr></thead><tbody id="tier-rows">${tierRows}</tbody></table></div></div></section><section class="card"><div class="section-heading"><div><span class="eyebrow">Master services agreement override</span><h2>Custom member rates</h2></div></div><p class="hint">Every override requires a reason and is written to the revision history.</p><div class="table-wrap"><table><thead><tr><th>Person</th><th>Role</th><th>Engagement</th><th>Contract</th><th>Reason</th><th></th></tr></thead><tbody>${memberRows}</tbody></table></div></section>`);
    const builder=document.getElementById('tier-builder'),mode=document.querySelector('[name="rate_mode"]');const updateMode=()=>builder.hidden=mode.value!=='flat_tiered';mode.addEventListener('change',updateMode);updateMode();
    const bindTierRemovals=()=>document.querySelectorAll('[data-remove-tier]').forEach(button=>button.onclick=()=>button.closest('tr').remove());bindTierRemovals();
    document.getElementById('add-rate-tier').addEventListener('click',()=>{document.getElementById('tier-rows').insertAdjacentHTML('beforeend','<tr data-tier-row><td><input name="tier_name" placeholder="Everyone else"></td><td><input name="tier_amount" type="number" step="0.01" value="0"></td><td><button type="button" class="btn text danger-text" data-remove-tier>Remove</button></td></tr>');bindTierRemovals();});
    document.getElementById('save-rate-mode').addEventListener('click',async()=>{try{await api(`/api/engagements/${id}`,{method:'PUT',body:{rate_mode:mode.value}});if(mode.value==='flat_tiered'){const rows=[...document.querySelectorAll('[data-tier-row]')].map(row=>formObject(rowToForm(row)));await api(`/api/engagements/${id}/rate-tiers`,{method:'PUT',body:{tiers:rows}});}toast('Rate model saved');renderEngagementRates(id);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-save-custom]').forEach(button=>button.addEventListener('click',async()=>{const row=button.closest('[data-custom-member]'),body=formObject(rowToForm(row));body.is_custom_rate=true;try{await api(`/api/engagements/${id}/team/${button.dataset.saveCustom}`,{method:'PUT',body});toast('Custom rate audited and saved');renderEngagementRates(id);}catch(error){toast(error.message,'error');}}));
  } catch(error) { shell('Rate model',errorPanel(error)); }
}

function render() {
  if(window.DB_ERROR){shell('Database unavailable',errorPanel(window.DB_ERROR));return;}
  const path=location.pathname;
  if(path==='/'||path==='/dashboard')return renderDashboard();
  if(path==='/proposals')return renderProposals();
  if(path==='/proposals/new')return renderProposalEditor();
  if(path==='/engagements/new')return renderNewEngagement();
  if(path==='/engagements/drafts')return renderInProgress();
  if(path==='/settings/rate-cards')return renderRateCards();
  if(path==='/settings')return renderSettings();
  if(path==='/help')return renderHelp();
  let match=path.match(/^\/proposals\/(\d+)$/);
  if(match)return renderProposalEditor(Number(match[1]));
  match=path.match(/^\/engagements\/(\d+)\/phases\/(\d+)$/);
  if(match)return renderPhaseDetail(Number(match[1]),Number(match[2]));
  match=path.match(/^\/engagements\/(\d+)(?:\/([^/]+))?$/);
  if(match){const id=Number(match[1]),route=match[2]||'';return ({'':renderEngagement,phases:renderPhases,exceptions:renderExceptions,team:renderTeamConfig,rates:renderEngagementRates,import:renderImport,adjustments:renderAdjustments,revisions:renderRevisions,expenses:renderExpenses,history:renderHistory,export:renderExport}[route]||renderEngagement)(id);}
  shell('Page not found','<div class="empty">The requested page does not exist.</div>');
}

window.addEventListener('popstate',render);
render();
