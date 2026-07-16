/* Aesthetic direction: Swiss / typographic. Crowe indigo anchors a dense operational workspace. */
const state = { theme: localStorage.getItem('budget-theme') || 'light' };
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

function navLink(path, label) {
  const active = location.pathname === path || (path !== '/dashboard' && location.pathname.startsWith(path));
  return `<a class="nav-link ${active ? 'active' : ''}" href="${path}" data-link>${label}</a>`;
}

function shell(title, body, actions='') {
  app.innerHTML = `<div class="layout"><aside class="sidebar">
    <a class="brand" href="/dashboard" data-link><img src="/static/assets/crowe-logo-white.svg" alt="Crowe"><span>Engagement<br>Budget Tracker</span></a>
    <nav>${navLink('/dashboard','Dashboard')}${navLink('/engagements/new','New engagement')}${navLink('/settings','Settings')}</nav>
    <div class="sidebar-foot"><span>Local-first · Schema v2</span><button id="theme-toggle" class="theme-toggle" aria-label="Toggle color theme">${state.theme === 'light' ? 'Dark' : 'Light'} mode</button></div>
  </aside><main class="main"><header class="topbar"><div><span class="eyebrow">Budget governance</span><h1>${esc(title)}</h1></div><div class="top-actions">${actions}</div></header><div class="content">${body}</div></main></div>`;
  bindNavigation();
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('budget-theme', state.theme);
    document.documentElement.dataset.theme = state.theme;
    render();
  });
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

function field(label, name, value='', type='text', attrs='') {
  return `<label class="field"><span>${esc(label)}</span><input name="${name}" type="${type}" value="${esc(value)}" ${attrs}></label>`;
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
    shell('Engagement portfolio', `<section class="metrics four">${metric('Active engagements', m.total_active_engagements)}${metric('Hours this month', num(m.total_hours_mtd))}${metric('Fees this month', money(m.total_fees_mtd))}${metric('Needs attention', m.watch_or_over_budget)}</section>
      <div class="section-heading"><div><span class="eyebrow">Portfolio</span><h2>Current engagements</h2></div></div>
      <section class="engagement-grid">${cards || '<div class="empty">No engagements yet. Create the first budget to begin.</div>'}</section>`,
      '<a class="btn primary" href="/engagements/new" data-link>New engagement</a>');
  } catch (error) { shell('Engagement portfolio', errorPanel(error)); }
}

function engagementTabs(id, mode='simple') {
  const tabs = [['Overview',''],['Team and budget','team'],['Weekly import','import'],['Adjustments','adjustments'],
                ['Expenses','expenses'],['History','history'],['Export','export']];
  if (mode === 'complex') tabs.splice(5,0,['Revisions','revisions']);
  return `<nav class="tabs">${tabs.map(([label,route]) => `<a href="/engagements/${id}${route ? `/${route}` : ''}" data-link>${label}</a>`).join('')}</nav>`;
}

async function renderEngagement(id) {
  shell('Engagement overview', '<div class="loading">Loading budget…</div>');
  try {
    const data = await api(`/api/engagements/${id}`);
    const e = data.engagement, m = data.metrics;
    const banner = m.unmatched_phase_rows ? `<a class="alert warning" href="/engagements/${id}/import" data-link><strong>Unmatched phase time</strong><span>${num(m.unmatched_phase_hours)} hours from ${m.unmatched_phase_workers} workers need assignment</span></a>` : '';
    const phaseRows = data.phases.map((p) => `<tr data-phase="${p.id}"><td><a href="/engagements/${id}/phases/${p.id}" data-link>${esc(p.phase_name)}</a></td><td>${num(p.budgeted_hours)}</td><td>${num(p.current_plan_hours)}</td><td>${num(p.current_plan_hours-p.budgeted_hours)}</td><td>${money(p.effective_sow)}</td><td>${money(p.current_plan_eng_fees)}</td><td>${money(p.current_plan_eng_fees-p.effective_sow)}</td></tr>`).join('');
    const teamRows = data.team.map((x) => `<tr><td>${esc(x.name)} ${x.is_offshore ? '<span class="os-badge">OS</span>' : ''}</td><td>${esc(x.role || '')}</td><td>${num(x.budgeted_hours)}</td><td>${num(x.hours_to_date)}</td><td>${num(x.hours_remaining)}</td><td>${money(x.actual_eng_fees)}</td></tr>`).join('');
    shell(e.client_name, `${engagementTabs(id,e.complexity_mode)}${banner}
      <section class="engagement-hero"><div><span class="eyebrow">${esc(e.engagement_code)} · ${esc(e.complexity_mode)} mode</span><h2>${esc(e.engagement_lead || 'Lead not assigned')}</h2></div>${statusBadge(m.status)}</section>
      <section class="metrics five">${metric('Budgeted hours',num(m.total_budgeted_hours))}${metric('Hours to date',num(m.hours_to_date))}${metric('Hours remaining',num(m.hours_remaining),pct(m.hours_remaining_pct))}${metric('Contract fees',money(m.fees_to_date_contract))}${metric('Effective budget',money(m.effective_sow))}</section>
      <section class="card budget-position"><div><div class="section-heading"><h2>Budget position</h2><strong>${pct(m.utilization_pct)} used</strong></div><div class="progress large"><i style="width:${Math.min(100,m.utilization_pct*100)}%"></i></div><div class="inline-stats"><span>Projected final <b>${money(m.projected_final)}</b></span><span>Remaining <b>${money(m.budget_remaining)}</b></span><span>Markdown needed <b>${money(m.markdown_needed)}</b></span></div></div><aside><span>Realization</span><strong>${pct(m.realization)}</strong><small>SOW and change orders minus Crowe-paid expenses, divided by actual standard fees</small></aside></section>
      ${e.complexity_mode === 'complex' ? `<section class="card"><h2>Phase breakdown</h2><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Budget hours</th><th>Current plan</th><th>Variance</th><th>Budget</th><th>Fees planned</th><th>Over/under</th></tr></thead><tbody>${phaseRows}</tbody></table></div></section>` : ''}
      <section class="card"><h2>Engagement team</h2><div class="table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Budget</th><th>Actual</th><th>Remaining</th><th>Engagement fees</th></tr></thead><tbody>${teamRows}</tbody></table></div></section>`);
  } catch (error) { shell('Engagement overview', errorPanel(error)); }
}

async function renderNewEngagement() {
  const settings = await api('/api/settings/rates').catch(() => ({rates:{}}));
  const wizard = {step:1, info:{complexity_mode:'simple',duration_weeks:8},
    team:[{name:'',role:'Manager FY26',internal_rate:settings.rates['Manager FY26'] || 350,budgeted_hours:0}],
    phases:[{phase_name:'',phase_code:'',sow_fees:0}], weekly:{}, settings};
  const titles = ['Engagement','Team','Phases','Weekly budget'];
  function draw() {
    const actions = `<button class="btn secondary" id="back" ${wizard.step===1?'disabled':''}>Back</button><button class="btn primary" id="next">${wizard.step===4?'Create engagement':'Continue'}</button>`;
    const progress = `<div class="wizard-progress">${titles.map((title,index)=>`<div class="${wizard.step===index+1?'active':''} ${wizard.step>index+1?'done':''}"><span>0${index+1}</span>${title}</div>`).join('')}</div>`;
    let body = wizard.step===1 ? wizardInfo(wizard) : wizard.step===2 ? wizardTeam(wizard) : wizard.step===3 ? wizardPhases(wizard) : wizardWeeks(wizard);
    shell('New engagement', `${progress}<section class="card wizard">${body}<div class="wizard-actions">${actions}</div></section>`);
    bind();
  }
  function bind() {
    document.querySelectorAll('[data-info]').forEach((node)=>node.addEventListener('input',()=>{wizard.info[node.dataset.info]=node.type==='number'?Number(node.value):node.value;if(node.dataset.info==='complexity_mode')draw();}));
    document.querySelectorAll('[data-team]').forEach((node)=>node.addEventListener('input',()=>{const [i,key]=node.dataset.team.split(':');wizard.team[i][key]=node.type==='number'?Number(node.value):node.type==='checkbox'?node.checked:node.value;if(key==='role'&&!wizard.team[i].internal_rate)wizard.team[i].internal_rate=settings.rates[node.value]||0;}));
    document.querySelectorAll('[data-phase]').forEach((node)=>node.addEventListener('input',()=>{const [i,key]=node.dataset.phase.split(':');wizard.phases[i][key]=node.type==='number'?Number(node.value):node.value;}));
    document.querySelectorAll('[data-week]').forEach((node)=>node.addEventListener('input',()=>wizard.weekly[node.dataset.week]=Number(node.value||0)));
    document.getElementById('add-team')?.addEventListener('click',()=>{wizard.team.push({name:'',role:'Manager FY26',internal_rate:settings.rates['Manager FY26']||350,budgeted_hours:0});draw();});
    document.getElementById('add-phase')?.addEventListener('click',()=>{wizard.phases.push({phase_name:'',phase_code:'',sow_fees:0});draw();});
    document.querySelectorAll('[data-remove-team]').forEach((b)=>b.addEventListener('click',()=>{wizard.team.splice(Number(b.dataset.removeTeam),1);draw();}));
    document.querySelectorAll('[data-remove-phase]').forEach((b)=>b.addEventListener('click',()=>{wizard.phases.splice(Number(b.dataset.removePhase),1);draw();}));
    document.querySelectorAll('[data-distribute]').forEach((b)=>b.addEventListener('click',()=>{const [pi,ti]=b.dataset.distribute.split(':').map(Number);const weeks=weekDates(wizard.info.first_monday,wizard.info.duration_weeks);const per=Number(wizard.team[ti].budgeted_hours||0)/Math.max(1,weeks.length);weeks.forEach((week)=>wizard.weekly[`${pi}:${ti}:${week}`]=per);draw();}));
    document.getElementById('back')?.addEventListener('click',()=>{wizard.step=Math.max(1,wizard.step-1);draw();});
    document.getElementById('next')?.addEventListener('click',async()=>{
      if(wizard.step===1&&(!wizard.info.engagement_code||!wizard.info.client_name)){toast('Engagement code and client name are required','error');return;}
      if(wizard.step===2&&wizard.team.some((x)=>x.name&&!x.name.includes(','))){toast('Use Last, First for every team member','error');return;}
      if(wizard.step===3&&wizard.info.complexity_mode==='complex'&&wizard.phases.every((x)=>!x.phase_name)){toast('Add at least one phase','error');return;}
      if(wizard.step<4){wizard.step++;draw();return;}
      const team=wizard.team.filter((x)=>x.name);const phases=wizard.phases.filter((x)=>x.phase_name);
      const weekly_budgets=Object.entries(wizard.weekly).map(([key,budgeted_hours])=>{const [phase_index,team_index,week_start_date]=key.split(':');return {phase_index:Number(phase_index),team_index:Number(team_index),week_start_date,budgeted_hours};});
      try{const data=await api('/api/engagements',{method:'POST',body:{engagement:wizard.info,team,phases,weekly_budgets}});history.pushState({},'',`/engagements/${data.engagement.id}`);render();}catch(error){toast(error.message,'error');}
    });
  }
  draw();
}

function wizardInfo(w) {
  const e=w.info;return `<div class="form-grid">${field('Engagement code','engagement_code',e.engagement_code,'text','required data-info="engagement_code"')}${field('Client name','client_name',e.client_name,'text','required data-info="client_name"')}${select('Complexity mode','complexity_mode',e.complexity_mode,[['simple','Simple'],['complex','Complex']],'data-info="complexity_mode"')}${select('Engagement type','engagement_type',e.engagement_type||'Advisory',['Audit','Validation','Tuning','Implementation','Advisory','Other'],'data-info="engagement_type"')}${field('Engagement lead','engagement_lead',e.engagement_lead,'text','data-info="engagement_lead"')}${field('Model type','model_type',e.model_type,'text','data-info="model_type"')}${e.complexity_mode==='complex'?field('First Monday','first_monday',e.first_monday,'date','required data-info="first_monday"')+field('Duration in weeks','duration_weeks',e.duration_weeks,'number','min="1" data-info="duration_weeks"'):field('Signed SOW fees','max_sow_fees',e.max_sow_fees,'number','min="0" step="0.01" data-info="max_sow_fees"')}</div>`;
}

function wizardTeam(w) {
  const roles=Object.keys(w.settings.rates);return `<div class="section-heading"><div><span class="eyebrow">Step two</span><h2>Engagement team</h2></div><button class="btn secondary" id="add-team">Add person</button></div><div class="table-wrap"><table><thead><tr><th>Name (Last, First)</th><th>Role</th><th>Std rate</th><th>Engagement rate</th><th>Contract rate</th><th>DTE</th><th>Budget hours</th><th>Offshore</th><th></th></tr></thead><tbody>${w.team.map((x,i)=>`<tr><td><input data-team="${i}:name" value="${esc(x.name)}"></td><td><select data-team="${i}:role">${roles.map(r=>`<option ${r===x.role?'selected':''}>${esc(r)}</option>`).join('')}</select></td><td><input type="number" data-team="${i}:internal_rate" value="${x.internal_rate||0}"></td><td><input type="number" data-team="${i}:engagement_rate" value="${x.engagement_rate||''}" placeholder="Default"></td><td><input type="number" data-team="${i}:contract_rate" value="${x.contract_rate||''}" placeholder="Default"></td><td><input type="number" data-team="${i}:dte_rate" value="${x.dte_rate||0}"></td><td><input type="number" data-team="${i}:budgeted_hours" value="${x.budgeted_hours||0}"></td><td><input type="checkbox" data-team="${i}:is_offshore" ${x.is_offshore?'checked':''}></td><td><button class="icon-btn" data-remove-team="${i}" aria-label="Remove person">×</button></td></tr>`).join('')}</tbody></table></div>`;
}

function wizardPhases(w) {
  if(w.info.complexity_mode==='simple')return `<div class="empty"><strong>Simple mode uses one General phase</strong><p>The phase is created automatically and remains hidden during normal use.</p></div>`;
  return `<div class="section-heading"><div><span class="eyebrow">Step three</span><h2>Phases and SOW</h2></div><button class="btn secondary" id="add-phase">Add phase</button></div><div class="table-wrap"><table><thead><tr><th>Phase name</th><th>Phase code</th><th>SOW fees</th><th></th></tr></thead><tbody>${w.phases.map((x,i)=>`<tr><td><input data-phase="${i}:phase_name" value="${esc(x.phase_name)}"></td><td><input data-phase="${i}:phase_code" value="${esc(x.phase_code)}" placeholder="Leave blank if unsure"></td><td><input type="number" data-phase="${i}:sow_fees" value="${x.sow_fees||0}"></td><td><button class="icon-btn" data-remove-phase="${i}" aria-label="Remove phase">×</button></td></tr>`).join('')}</tbody></table></div><p class="hint">Phase codes are optional and frequently inconsistent in Cognos exports. Unmatched rows can be assigned during import.</p>`;
}

function weekDates(first, count) {
  if(!first)return [];
  const start=new Date(`${first}T12:00:00`);return Array.from({length:Number(count||1)},(_,i)=>{const day=new Date(start);day.setDate(day.getDate()+i*7);return day.toISOString().slice(0,10);});
}

function wizardWeeks(w) {
  if(w.info.complexity_mode==='simple')return `<div class="review"><span class="eyebrow">Ready to create</span><h2>${esc(w.info.client_name||'New engagement')}</h2><p>${w.team.filter(x=>x.name).length} team members · ${money(w.info.max_sow_fees||0)} signed SOW</p></div>`;
  const weeks=weekDates(w.info.first_monday,w.info.duration_weeks);const phases=w.phases.filter(x=>x.phase_name);const team=w.team.filter(x=>x.name);
  return `<div class="section-heading"><div><span class="eyebrow">Step four</span><h2>Weekly budget grid</h2></div><span>${weeks.length} weeks</span></div>${phases.map((phase,pi)=>`<section class="phase-plan"><h3>${esc(phase.phase_name)}</h3><div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Team member</th>${weeks.map(x=>`<th>${new Date(`${x}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</th>`).join('')}</tr></thead><tbody>${team.map((member,ti)=>`<tr><th><span>${esc(member.name)}</span><button type="button" data-distribute="${pi}:${ti}">Distribute</button></th>${weeks.map(week=>`<td><input type="number" min="0" step="0.25" data-week="${pi}:${ti}:${week}" value="${w.weekly[`${pi}:${ti}:${week}`]??0}"></td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`).join('')}`;
}

async function renderTeamConfig(id) {
  try {
    const [data,settings]=await Promise.all([api(`/api/engagements/${id}`),api('/api/settings/rates')]);const e=data.engagement;
    const memberRows=data.team.map((x)=>`<tr data-member-id="${x.id}"><td><input name="name" value="${esc(x.name)}"></td><td><select name="role">${Object.keys(settings.rates).map(r=>`<option ${r===x.role?'selected':''}>${esc(r)}</option>`).join('')}</select></td><td><input name="internal_rate" type="number" value="${x.internal_rate}"></td><td><input name="engagement_rate" type="number" value="${x.engagement_rate}"></td><td><input name="contract_rate" type="number" value="${x.contract_rate}"></td><td><input name="dte_rate" type="number" value="${x.dte_rate}"></td><td><input name="budgeted_hours" type="number" value="${x.budgeted_hours}" ${e.status!=='planning'?'disabled':''}></td><td><input name="is_offshore" type="checkbox" ${x.is_offshore?'checked':''}></td></tr>`).join('');
    const phases=data.phases.map((p)=>`<tr data-phase-id="${p.id}"><td><a href="/engagements/${id}/phases/${p.id}" data-link>${esc(p.phase_name)}</a></td><td><input name="phase_code" value="${esc(p.phase_code||'')}"></td><td><input name="sow_fees" type="number" value="${p.sow_fees}" ${e.status!=='planning'?'disabled':''}></td><td>${num(p.budgeted_hours)}</td></tr>`).join('');
    shell('Team and budget', `${engagementTabs(id,e.complexity_mode)}<section class="card"><div class="section-heading"><div><span class="eyebrow">Configuration</span><h2>Team rates and hours</h2></div><span>${statusBadge(e.status)}</span></div><div class="table-wrap"><table id="team-config"><thead><tr><th>Name</th><th>Role</th><th>Std</th><th>Engagement</th><th>Contract</th><th>DTE</th><th>Hours</th><th>OS</th></tr></thead><tbody>${memberRows}</tbody></table></div></section>
      <section class="card"><h2>Phases</h2><div class="table-wrap"><table id="phase-config"><thead><tr><th>Phase</th><th>Code</th><th>Signed SOW</th><th>Budget hours</th></tr></thead><tbody>${phases}</tbody></table></div></section>
      <div class="form-actions"><button class="btn primary" id="save-config">Save configuration</button></div>`);
    document.getElementById('save-config').addEventListener('click',async()=>{
      try{
        for(const row of document.querySelectorAll('[data-member-id]')){const body=formObject(rowToForm(row));body.is_offshore=row.querySelector('[name=is_offshore]').checked;await api(`/api/engagements/${id}/team/${row.dataset.memberId}`,{method:'PUT',body});if(e.status==='planning'&&e.complexity_mode==='simple')await api(`/api/engagements/${id}/phase-weeks`,{method:'PUT',body:{rows:[{phase_id:data.phases[0].id,team_member_id:Number(row.dataset.memberId),week_start_date:null,budgeted_hours:Number(body.budgeted_hours||0)}]}});}
        for(const row of document.querySelectorAll('[data-phase-id]')){const body=formObject(rowToForm(row));await api(`/api/engagements/${id}/phases/${row.dataset.phaseId}`,{method:'PUT',body});}
        toast('Configuration saved');renderTeamConfig(id);
      }catch(error){if(error.details?.code==='budget_locked'){const d=error.details;history.pushState({},'',`/engagements/${id}/revisions?target_type=${d.target_type}&target_id=${d.target_id}`);render();}else toast(error.message,'error');}
    });
  }catch(error){shell('Team and budget',errorPanel(error));}
}

function rowToForm(row){const form=document.createElement('form');row.querySelectorAll('input,select').forEach(node=>form.append(node.cloneNode(true)));return form;}

async function renderPhaseDetail(id,phaseId) {
  try{
    const [detail,parent]=await Promise.all([api(`/api/engagements/${id}/phases/${phaseId}`),api(`/api/engagements/${id}`)]);const p=detail.phase,e=parent.engagement;
    const grid=detail.grid;const rows=grid.rows.map((r)=>`<tr><th>${esc(r.member.name)} ${r.member.is_offshore?'<span class="os-badge">OS</span>':''}</th>${r.cells.map(c=>`<td class="${c.variance_flagged?'variance':''}"><label>B <input type="number" data-cell="budgeted" data-phase="${phaseId}" data-member="${r.member.id}" data-week="${c.week_start_date}" value="${c.budgeted_hours}" ${e.status!=='planning'?'disabled':''}></label><label>A <output>${num(c.actual_hours)}</output></label><label>F <input type="number" data-cell="forecasted" data-phase="${phaseId}" data-member="${r.member.id}" data-week="${c.week_start_date}" value="${c.forecasted_hours}" ${e.status==='closed'?'disabled':''}></label></td>`).join('')}</tr>`).join('');
    shell(p.phase_name, `${engagementTabs(id,e.complexity_mode)}<section class="phase-header"><div><span class="eyebrow">${esc(p.phase_code||'No phase code')}</span><h2>${money(p.effective_sow)} effective SOW</h2></div>${statusBadge(p.status)}</section>
      <section class="metrics four">${metric('Budget hours',num(p.budgeted_hours))}${metric('Actual hours',num(p.actual_hours))}${metric('Contract fees',money(p.actual_contract_fees))}${metric('DTE tracking',money(p.actual_dte_fees))}</section>
      <section class="card"><div class="section-heading"><h2>Weekly budget, actual and forecast</h2><button class="btn secondary" id="phase-change-order">Add change order</button></div><div class="weekly-grid-wrap"><table class="weekly-grid"><thead><tr><th>Team member</th>${grid.weeks.map(w=>`<th>${new Date(`${w}T12:00:00`).toLocaleDateString('en-US',{month:'short',day:'numeric'})}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div><div class="legend"><span>B Budget</span><span>A Actual</span><span>F Forecast</span><span class="variance-key">Variance review</span></div><button class="btn primary" id="save-grid">Save weekly grid</button></section>`);
    document.getElementById('phase-change-order').addEventListener('click',()=>{history.pushState({},'',`/engagements/${id}/adjustments?phase=${phaseId}`);render();});
    document.getElementById('save-grid').addEventListener('click',async()=>{const map={};document.querySelectorAll('[data-cell]').forEach(input=>{const key=`${input.dataset.phase}:${input.dataset.member}:${input.dataset.week}`;map[key]??={phase_id:Number(input.dataset.phase),team_member_id:Number(input.dataset.member),week_start_date:input.dataset.week};map[key][`${input.dataset.cell}_hours`]=Number(input.value||0);});try{await api(`/api/engagements/${id}/phase-weeks`,{method:'PUT',body:{rows:Object.values(map)}});toast('Weekly grid saved');renderPhaseDetail(id,phaseId);}catch(error){toast(error.message,'error');}});
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
    document.getElementById('preview-import').addEventListener('click',async()=>{try{let preview;const file=document.getElementById('import-file').files[0];if(file){const form=new FormData();form.append('file',file);const response=await fetch(`/api/engagements/${id}/import/preview`,{method:'POST',body:form});const body=await response.json();if(!response.ok)throw new Error(body.error?.message);preview=body.data;}else preview=await api(`/api/engagements/${id}/import/preview`,{method:'POST',body:{text:document.getElementById('import-text').value}});drawImportPreview(id,preview,data.phases);}catch(error){toast(error.message,'error');}});
  }catch(error){shell('Weekly import',errorPanel(error));}
}

function drawImportPreview(id,preview,phases) {
  const area=document.getElementById('preview-area');const unmatched=[...new Set(preview.rows.filter(r=>r.flags?.includes('unmatched_phase')).map(r=>r.phase_desc))];
  const assigns=unmatched.map((desc,i)=>`<label class="field compact"><span>Assign “${esc(desc||'(blank)')}” to</span><select data-phase-assignment="${esc(desc)}"><option value="">Leave unmatched</option>${phases.map(p=>`<option value="${p.id}">${esc(p.phase_name)}</option>`).join('')}</select></label>`).join('');
  const rows=preview.rows.map((r)=>`<tr class="${r.flag||''}"><td><input type="checkbox" data-include="${esc(r.transaction_id)}" ${r.included?'checked':''} ${r.selectable?'':'disabled'}></td><td>${esc(r.worker_name)}</td><td>${esc(r.week_end_date)}</td><td>${esc(r.phase_desc||'Unmatched')}</td><td>${num(r.hours)}</td><td>${money(r.fees_contract_rate)}</td><td>${(r.flags||[]).map(f=>`<span class="flag">${esc(f.replaceAll('_',' '))}</span>`).join('')}</td></tr>`).join('');
  area.innerHTML=`<section class="metrics four">${metric('Rows',preview.summary.total)}${metric('Ready',preview.summary.to_import)}${metric('Duplicates',preview.summary.duplicates)}${metric('Flagged',preview.summary.flagged)}</section>${assigns?`<section class="card"><h2>Phase assignments</h2><div class="assignment-grid">${assigns}</div></section>`:''}<section class="card"><div class="table-wrap"><table><thead><tr><th>Use</th><th>Worker</th><th>Week end</th><th>Phase</th><th>Hours</th><th>Contract fees</th><th>Review</th></tr></thead><tbody>${rows}</tbody></table></div><label class="field"><span>Snapshot notes</span><textarea id="import-notes"></textarea></label><button class="btn primary" id="commit-import">Commit import</button></section>`;
  document.getElementById('commit-import').addEventListener('click',async()=>{const included_transaction_ids=[...document.querySelectorAll('[data-include]:checked')].map(x=>x.dataset.include);const phase_assignments={};document.querySelectorAll('[data-phase-assignment]').forEach(x=>{if(x.value)phase_assignments[x.dataset.phaseAssignment]=Number(x.value);});try{const result=await api(`/api/engagements/${id}/import/commit`,{method:'POST',body:{included_transaction_ids,phase_assignments,notes:document.getElementById('import-notes').value}});toast(`Imported ${result.imported} rows`);renderImport(id);}catch(error){toast(error.message,'error');}});
}

async function renderAdjustments(id) {
  try{
    const data=await api(`/api/engagements/${id}`),e=data.engagement;const selected=new URLSearchParams(location.search).get('phase')||'';
    const rows=data.adjustments.map(x=>`<tr><td>${esc(x.effective_date||'')}</td><td>${esc(x.adjustment_type)}</td><td>${esc(x.phase_name||'Engagement-wide')}</td><td>${money(x.amount)}</td><td>${esc(x.description||'')}</td><td><button class="icon-btn" data-delete-adjustment="${x.id}">×</button></td></tr>`).join('');
    shell('Budget adjustments', `${engagementTabs(id,e.complexity_mode)}<div class="split-layout"><section class="card"><h2>Adjustment ledger</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Phase</th><th>Amount</th><th>Description</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="6">No adjustments</td></tr>'}</tbody></table></div></section><section class="card side-form"><h2>Add adjustment</h2><form id="adjustment-form">${select('Type','adjustment_type','markdown',['markdown','c360','bima','change_order'])}${field('Effective date','effective_date','', 'date')}${select('Phase','phase_id',selected,[['','Engagement-wide'],...data.phases.map(p=>[p.id,p.phase_name])])}${field('Amount','amount','', 'number','step="0.01"')}<label class="field"><span>Description</span><textarea name="description"></textarea></label><button class="btn primary">Save adjustment</button></form></section></div>`);
    const form=document.getElementById('adjustment-form');const phase=form.elements.phase_id;function phaseRule(){const change=form.elements.adjustment_type.value==='change_order';phase.closest('.field').hidden=!change;phase.required=change;}form.elements.adjustment_type.addEventListener('change',phaseRule);phaseRule();
    form.addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(form);body.phase_id=body.phase_id?Number(body.phase_id):null;try{await api(`/api/engagements/${id}/adjustments`,{method:'POST',body});toast('Adjustment saved');renderAdjustments(id);}catch(error){toast(error.message,'error');}});
    document.querySelectorAll('[data-delete-adjustment]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Delete this adjustment?'))return;await api(`/api/engagements/${id}/adjustments/${b.dataset.deleteAdjustment}`,{method:'DELETE'});renderAdjustments(id);}));
  }catch(error){shell('Budget adjustments',errorPanel(error));}
}

async function renderRevisions(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;const rows=data.revisions.map(x=>`<tr><td>${esc(x.revised_at)}</td><td>${esc(x.phase_name||x.team_member_name||'Engagement')}</td><td>${esc(x.field_name)}</td><td>${num(x.old_value,2)}</td><td>${num(x.new_value,2)}</td><td>${esc(x.reason)}</td></tr>`).join('');const params=new URLSearchParams(location.search),targetType=params.get('target_type'),targetId=params.get('target_id');const fields=targetType==='phase'?['sow_fees']:targetType==='phase_person_week'?['budgeted_hours']:['internal_rate','engagement_rate','contract_rate','dte_rate'];const form=targetType?`<section class="card revision-form"><div><span class="eyebrow">Budget lock</span><h2>Record the reasoned change</h2><p>This update and its reason will be retained in the audit trail.</p></div><form id="revision-form">${select('Field','field_name',fields[0],fields)}${field('New value','new_value','', 'number','required step="0.01"')}<label class="field"><span>Reason</span><textarea name="reason" required></textarea></label><button class="btn primary">Apply revision</button></form></section>`:'';shell('Budget revisions',`${engagementTabs(id,e.complexity_mode)}${form}<section class="card"><div class="section-heading"><div><span class="eyebrow">Audit trail</span><h2>Reasoned re-baselines</h2></div></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Scope</th><th>Field</th><th>Old</th><th>New</th><th>Reason</th></tr></thead><tbody>${rows||'<tr><td colspan="6">No revisions recorded</td></tr>'}</tbody></table></div><p class="hint">Revisions originate from a blocked budget edit after activation.</p></section>`);document.getElementById('revision-form')?.addEventListener('submit',async(event)=>{event.preventDefault();const body={...formObject(event.currentTarget),target_type:targetType,target_id:Number(targetId)};try{await api(`/api/engagements/${id}/revisions`,{method:'POST',body});history.replaceState({},'',`/engagements/${id}/revisions`);toast('Budget revision applied');renderRevisions(id);}catch(error){toast(error.message,'error');}});}catch(error){shell('Budget revisions',errorPanel(error));}
}

async function renderExpenses(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;const rows=data.expenses.map(x=>`<tr><td>${esc(x.incurred_date||'')}</td><td>${esc(x.expense_type.replaceAll('_',' '))}</td><td>${esc(x.phase_name||'Engagement-wide')}</td><td>${esc(x.description||'')}</td><td>${money(x.amount)}</td><td><button class="icon-btn" data-delete-expense="${x.id}">×</button></td></tr>`).join('');shell('Expenses',`${engagementTabs(id,e.complexity_mode)}<div class="split-layout"><section class="card"><h2>Expense ledger</h2><div class="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Phase</th><th>Description</th><th>Amount</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="6">No expenses</td></tr>'}</tbody></table></div><p class="hint">Client-paid expenses do not affect budget or realization calculations.</p></section><section class="card side-form"><h2>Add expense</h2><form id="expense-form">${select('Type','expense_type','crowe_paid',[['crowe_paid','Crowe paid'],['client_paid','Client paid']])}${select('Phase','phase_id','',[['','Engagement-wide'],...data.phases.map(p=>[p.id,p.phase_name])])}${field('Description','description')}${field('Amount','amount','', 'number','step="0.01"')}${field('Incurred date','incurred_date','', 'date')}<button class="btn primary">Save expense</button></form></section></div>`);document.getElementById('expense-form').addEventListener('submit',async(event)=>{event.preventDefault();const body=formObject(event.currentTarget);body.phase_id=body.phase_id?Number(body.phase_id):null;try{await api(`/api/engagements/${id}/expenses`,{method:'POST',body});toast('Expense saved');renderExpenses(id);}catch(error){toast(error.message,'error');}});document.querySelectorAll('[data-delete-expense]').forEach(b=>b.addEventListener('click',async()=>{await api(`/api/engagements/${id}/expenses/${b.dataset.deleteExpense}`,{method:'DELETE'});renderExpenses(id);}));}catch(error){shell('Expenses',errorPanel(error));}
}

async function renderHistory(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;const snapshots=await api(`/api/engagements/${id}/snapshots`);const rows=snapshots.map(x=>`<tr><td>${esc(x.week_end_date)}</td><td>${esc(x.imported_at)}</td><td>${x.row_count}</td><td>${num(x.hours)}</td><td>${money(x.fees)}</td><td>${num(x.cumulative_hours)}</td><td>${money(x.cumulative_fees)}</td><td>${esc(x.notes||'')}</td><td><button class="icon-btn" data-delete-snapshot="${x.id}">×</button></td></tr>`).join('');shell('Snapshot history',`${engagementTabs(id,e.complexity_mode)}<section class="card"><h2>Committed imports</h2><div class="table-wrap"><table><thead><tr><th>Week end</th><th>Imported</th><th>Rows</th><th>Hours</th><th>Fees</th><th>Cumulative hours</th><th>Cumulative fees</th><th>Notes</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="9">No imports</td></tr>'}</tbody></table></div></section>`);document.querySelectorAll('[data-delete-snapshot]').forEach(b=>b.addEventListener('click',async()=>{if(!confirm('Delete this snapshot and its time entries?'))return;await api(`/api/engagements/${id}/snapshots/${b.dataset.deleteSnapshot}`,{method:'DELETE'});renderHistory(id);}));}catch(error){shell('Snapshot history',errorPanel(error));}
}

async function renderExport(id) {
  try{const data=await api(`/api/engagements/${id}`),e=data.engagement;shell('Export engagement',`${engagementTabs(id,e.complexity_mode)}<section class="export-hero"><div><span class="eyebrow">Partner-ready reporting</span><h2>Engagement Summary first</h2><p>Both formats lead with the established Engagement Summary structure. Excel also includes weekly detail, adjustments, expenses and revisions.</p></div><div class="export-actions"><a class="btn primary" href="/api/engagements/${id}/export/excel">Download Excel</a><button class="btn secondary" id="print-report">Open print report</button></div></section><section class="card"><label class="field"><span>Status narrative</span><textarea id="narrative" rows="6" placeholder="Optional context for the print-ready report"></textarea></label></section>`);document.getElementById('print-report').addEventListener('click',()=>window.open(`/api/engagements/${id}/export/html?narrative=${encodeURIComponent(document.getElementById('narrative').value)}`,'_blank'));}catch(error){shell('Export engagement',errorPanel(error));}
}

async function renderSettings() {
  try{const data=await api('/api/settings/rates');const rateRows=Object.entries(data.rates).map(([role,rate])=>`<tr><td><input value="${esc(role)}" data-rate-role></td><td><input type="number" value="${rate}" data-rate-value></td><td>${role.startsWith('Offshore')?'<span class="os-badge">OS</span>':'Onshore'}</td></tr>`).join('');shell('Settings',`<section class="settings-grid"><div class="card"><div class="section-heading"><div><span class="eyebrow">Rate card</span><h2>Default internal rates</h2></div></div><div class="table-wrap"><table><thead><tr><th>Role</th><th>Internal/standard</th><th>Pool</th></tr></thead><tbody id="rate-rows">${rateRows}</tbody></table></div></div><div class="stack"><section class="card"><h2>Budget defaults</h2><form id="settings-form">${field('Engagement discount','engagement_discount_rate',data.engagement_discount_rate,'number','step="0.01"')}${field('Contract discount','contract_discount_rate',data.contract_discount_rate,'number','step="0.01"')}${field('Variance threshold hours','variance_threshold_hours',data.variance_threshold_hours,'number','step="0.25"')}${field('Variance threshold percent','variance_threshold_pct',data.variance_threshold_pct,'number','step="0.01"')}<button class="btn primary">Save settings</button></form></section><section class="card"><h2>Database</h2><p class="mono">${esc(data.db_path)}</p><a class="btn secondary" href="/api/settings/backup">Download backup</a></section></div></section>`);document.getElementById('settings-form').addEventListener('submit',async(event)=>{event.preventDefault();const rates={};document.querySelectorAll('#rate-rows tr').forEach(row=>rates[row.querySelector('[data-rate-role]').value]=Number(row.querySelector('[data-rate-value]').value||0));try{await api('/api/settings/rates',{method:'PUT',body:{...formObject(event.currentTarget),rates}});toast('Settings saved');}catch(error){toast(error.message,'error');}});}catch(error){shell('Settings',errorPanel(error));}
}

function render() {
  if(window.DB_ERROR){shell('Database unavailable',errorPanel(window.DB_ERROR));return;}
  const path=location.pathname;
  if(path==='/'||path==='/dashboard')return renderDashboard();
  if(path==='/engagements/new')return renderNewEngagement();
  if(path==='/settings')return renderSettings();
  let match=path.match(/^\/engagements\/(\d+)\/phases\/(\d+)$/);
  if(match)return renderPhaseDetail(Number(match[1]),Number(match[2]));
  match=path.match(/^\/engagements\/(\d+)(?:\/([^/]+))?$/);
  if(match){const id=Number(match[1]),route=match[2]||'';return ({'':renderEngagement,team:renderTeamConfig,import:renderImport,adjustments:renderAdjustments,revisions:renderRevisions,expenses:renderExpenses,history:renderHistory,export:renderExport}[route]||renderEngagement)(id);}
  shell('Page not found','<div class="empty">The requested page does not exist.</div>');
}

window.addEventListener('popstate',render);
render();
