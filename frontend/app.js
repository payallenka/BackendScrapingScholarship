/* =====================================================================
   Scholarship Aggregator — Frontend App
   ===================================================================== */

const API = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `http://${window.location.host}`
  : '';

const DEGREE_LABELS = {
  undergraduate: 'Undergrad',
  masters: 'Masters',
  phd: 'PhD',
  postgraduate: 'Postgrad',
  postdoctoral: 'Postdoc',
  any: 'Any Level',
};

const DEGREE_COLORS = {
  undergraduate: '#4f8ef7',
  masters: '#38d9a9',
  phd: '#cc5de8',
  postgraduate: '#ffa94d',
  postdoctoral: '#ff6b6b',
  any: '#8892b0',
};

// ---- State ----
const state = {
  search: '',
  degree_level: '',
  source_site: '',
  sort: 'scraped_at',
  order: 'desc',
  offset: 0,
  limit: 24,
  total: 0,
  sites: [],
  scraping: false,
};

// ---- DOM refs ----
const $ = id => document.getElementById(id);
const searchInput = $('searchInput');
const gridEl = $('grid');
const totalEl = $('totalCount');
const siteSelect = $('siteSelect');
const sortSelect = $('sortSelect');
const paginationEl = $('pagination');
const scrapeBtn = $('scrapeBtn');
const scrapeDot = $('scrapeDot');
const statsBar = $('statsBar');
const modalOverlay = $('modalOverlay');
const modalContent = $('modalContent');
const degreeChips = document.querySelectorAll('.degree-chip');

// ---- Init ----
async function init() {
  await loadStats();
  await loadSites();
  await fetchScholarships();
  startScrapePoller();
}

// ---- Stats ----
async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    statsBar.innerHTML = `
      <div class="stat-chip"><span class="dot"></span><strong>${data.total.toLocaleString()}</strong> scholarships</div>
      <div class="stat-chip"><strong>${data.with_deadline.toLocaleString()}</strong> with deadlines</div>
      <div class="stat-chip"><strong>${data.with_amount.toLocaleString()}</strong> with amounts</div>
      <div class="stat-chip"><strong>${(data.by_site || []).length}</strong> sources</div>
      ${data.last_scraped ? `<div class="stat-chip" style="margin-left:auto;color:var(--text3)">Last scraped: ${fmtDate(data.last_scraped)}</div>` : ''}
    `;
  } catch (e) {
    statsBar.innerHTML = `<div class="stat-chip" style="color:var(--text3)">Run a scrape to populate the database</div>`;
  }
}

// ---- Sites ----
async function loadSites() {
  try {
    const sites = await apiFetch('/api/sites');
    state.sites = sites;
    siteSelect.innerHTML = `<option value="">All sources (${sites.reduce((a,s) => a + s.count, 0)})</option>` +
      sites.map(s => `<option value="${s.name}">${s.name} (${s.count})</option>`).join('');
  } catch (e) {
    siteSelect.innerHTML = '<option value="">All sources</option>';
  }
}

// ---- Fetch scholarships ----
async function fetchScholarships() {
  setLoading(true);
  const params = new URLSearchParams({
    limit: state.limit,
    offset: state.offset,
    sort: state.sort,
    order: state.order,
  });
  if (state.search) params.set('search', state.search);
  if (state.degree_level) params.set('degree_level', state.degree_level);
  if (state.source_site) params.set('source_site', state.source_site);

  try {
    const data = await apiFetch(`/api/scholarships?${params}`);
    state.total = data.total;
    renderGrid(data.items);
    renderPagination();
    totalEl.innerHTML = data.total
      ? `Showing <strong>${data.items.length}</strong> of <strong>${data.total.toLocaleString()}</strong> scholarships`
      : '';
  } catch (e) {
    gridEl.innerHTML = emptyStateHtml('error');
    totalEl.textContent = '';
    paginationEl.innerHTML = '';
  }
  setLoading(false);
}

// ---- Empty states ----
function emptyStateHtml(type) {
  if (type === 'no-results') return `
    <div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">🔍</div>
      <h3>No matches found</h3>
      <p>Try different keywords or clear your filters.</p>
    </div>`;
  if (type === 'error') return `
    <div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">⚠️</div>
      <h3>Database is empty</h3>
      <p>Click <strong>Run Scraper</strong> in the top-right to fetch scholarships from 17 global sources.</p>
      <div class="empty-steps">
        <div class="empty-step"><span class="step-num">1</span>Click <strong>Run Scraper</strong> above — it runs in the background</div>
        <div class="empty-step"><span class="step-num">2</span>Wait ~10 min for the full scrape to finish</div>
        <div class="empty-step"><span class="step-num">3</span>Or run manually in a terminal:<br><code>PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 3</code></div>
      </div>
    </div>`;
  return `<div class="empty-state" style="grid-column:1/-1"><p>No data.</p></div>`;
}

// ---- Render grid ----
function renderGrid(items) {
  if (!items.length) {
    const hasFilters = state.search || state.degree_level || state.source_site;
    gridEl.innerHTML = emptyStateHtml(hasFilters ? 'no-results' : 'error');
    return;
  }
  gridEl.innerHTML = items.map(renderCard).join('');
  gridEl.querySelectorAll('.card').forEach((el, i) => {
    el.addEventListener('click', () => openModal(items[i]));
  });
}

function renderCard(s) {
  const badge = badgeClass(s.source_site);

  // --- Degree level ---
  const levels = (s.degree_levels || []).filter(d => d !== 'any');
  const degreeText = levels.length
    ? levels.map(d => DEGREE_LABELS[d] || d).join(' · ')
    : 'All Levels';
  const degreeColor = DEGREE_COLORS[levels[0]] || '#8892b0';

  // --- Funding ---
  const ft = s.funding_type;           // "full" | "partial" | null
  const amt = s.amount;                // "Fully Funded" | "$10,000" | null
  let fundingDisplay, fundingColor, fundingIcon;
  if (ft === 'full' || (amt && /fully funded/i.test(amt))) {
    fundingDisplay = 'Fully Funded';
    fundingColor   = '#38d9a9';
    fundingIcon    = '✦';
  } else if (amt) {
    fundingDisplay = amt;
    fundingColor   = '#ffa94d';
    fundingIcon    = '◑';
  } else if (ft === 'partial') {
    fundingDisplay = 'Partial';
    fundingColor   = '#ffa94d';
    fundingIcon    = '◑';
  } else {
    fundingDisplay = 'Not Specified';
    fundingColor   = 'var(--text3)';
    fundingIcon    = '○';
  }

  // --- Eligibility ---
  const nats = s.eligible_nationalities || [];
  const isAfrica = nats.some(n => /africa/i.test(n));
  const isDev    = nats.some(n => /develop|lmic|global south/i.test(n));
  let eligText, eligIcon;
  if (isAfrica)    { eligText = 'African Students';       eligIcon = '🌍'; }
  else if (isDev)  { eligText = 'Developing Countries';   eligIcon = '🌏'; }
  else if (nats.length) { eligText = nats.join(', ');     eligIcon = '🌐'; }
  else             { eligText = 'Open to All';             eligIcon = '🌐'; }

  // --- Deadline ---
  let deadlineDisplay, deadlineColor;
  if (s.deadline) {
    const days = daysUntil(s.deadline);
    if (days === null || days < 0) {
      deadlineDisplay = 'Closed';
      deadlineColor   = 'var(--text3)';
    } else if (days === 0) {
      deadlineDisplay = 'Today!';
      deadlineColor   = '#ff6b6b';
    } else if (days <= 7) {
      deadlineDisplay = `${days} days left`;
      deadlineColor   = '#ff6b6b';
    } else if (days <= 30) {
      deadlineDisplay = fmtDate(s.deadline);
      deadlineColor   = '#ffa94d';
    } else {
      deadlineDisplay = fmtDate(s.deadline);
      deadlineColor   = 'var(--text2)';
    }
  } else if (s.deadline_raw) {
    deadlineDisplay = s.deadline_raw.slice(0, 30);
    deadlineColor   = 'var(--text2)';
  } else {
    deadlineDisplay = 'Not Listed';
    deadlineColor   = 'var(--text3)';
  }

  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">${escHtml(s.title)}</div>
      </div>
      <div class="card-meta">
        <div class="card-meta-row">
          <span class="card-meta-icon">💰</span>
          <span class="card-meta-val" style="color:${fundingColor}">${fundingIcon} ${escHtml(fundingDisplay)}</span>
        </div>
        <div class="card-meta-row">
          <span class="card-meta-icon">📅</span>
          <span class="card-meta-val" style="color:${deadlineColor}">${escHtml(deadlineDisplay)}</span>
        </div>
        <div class="card-meta-row">
          <span class="card-meta-icon">${eligIcon}</span>
          <span class="card-meta-val">${escHtml(eligText)}</span>
        </div>
        <div class="card-meta-row">
          <span class="card-meta-icon">🎓</span>
          <span class="card-meta-val" style="color:${degreeColor}">${escHtml(degreeText)}</span>
        </div>
      </div>
    </div>`;
}

// ---- Modal ----
function openModal(s) {
  const badge = badgeClass(s.source_site);
  const degrees = (s.degree_levels || []).map(d => `
    <span class="degree-pill" style="background:${DEGREE_COLORS[d] || '#8892b0'}22;color:${DEGREE_COLORS[d] || '#8892b0'}">
      ${DEGREE_LABELS[d] || d}
    </span>`).join('');

  const nats = (s.eligible_nationalities || []).join(', ');
  const hosts = (s.host_countries || []).join(', ');
  const tags = [...(s.tags || []), ...(s.fields_of_study || [])];

  modalContent.innerHTML = `
    <div class="modal-header">
      <div>
        <span class="source-badge ${badge}" style="margin-bottom:8px;display:inline-block">${escHtml(s.source_site)}</span>
        <div class="modal-title">${escHtml(s.title)}</div>
        ${s.organization ? `<div style="font-size:0.85rem;color:var(--text2);margin-top:4px">🏛 ${escHtml(s.organization)}</div>` : ''}
      </div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>

    ${s.description ? `
      <div class="modal-section">
        <div class="modal-section-label">Description</div>
        <div class="modal-section-value">${escHtml(s.description)}</div>
      </div>` : ''}

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      ${s.amount ? `
        <div class="modal-section" style="margin:0">
          <div class="modal-section-label">Award</div>
          <div style="font-size:1.1rem;font-weight:700;color:var(--accent2)">${escHtml(s.amount)}</div>
        </div>` : ''}
      ${s.deadline ? `
        <div class="modal-section" style="margin:0">
          <div class="modal-section-label">Deadline</div>
          <div style="font-size:1rem;font-weight:600;color:var(--warn)">${escHtml(s.deadline_raw || s.deadline)}</div>
        </div>` : ''}
    </div>

    ${degrees ? `
      <div class="modal-section">
        <div class="modal-section-label">Degree Level</div>
        <div class="degree-pills">${degrees}</div>
      </div>` : ''}

    ${nats ? `
      <div class="modal-section">
        <div class="modal-section-label">Eligible Nationalities</div>
        <div class="modal-section-value">${escHtml(nats)}</div>
      </div>` : ''}

    ${hosts ? `
      <div class="modal-section">
        <div class="modal-section-label">Study Location</div>
        <div class="modal-section-value">${escHtml(hosts)}</div>
      </div>` : ''}

    ${tags.length ? `
      <div class="modal-section">
        <div class="modal-section-label">Tags</div>
        <div class="modal-tags">${tags.map(t => `<span class="chip">${escHtml(t)}</span>`).join('')}</div>
      </div>` : ''}

    <a href="${escHtml(s.source_url)}" target="_blank" rel="noopener" class="modal-apply">
      View &amp; Apply →
    </a>
  `;
  modalOverlay.classList.add('open');
}

function closeModal() {
  modalOverlay.classList.remove('open');
}

modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) closeModal(); });

// ---- Pagination ----
function renderPagination() {
  const pages = Math.ceil(state.total / state.limit);
  const cur = Math.floor(state.offset / state.limit);
  if (pages <= 1) { paginationEl.innerHTML = ''; return; }

  let html = `<button class="page-btn" ${cur === 0 ? 'disabled' : ''} onclick="gotoPage(${cur-1})">‹</button>`;
  const range = pageRange(cur, pages);
  range.forEach((p) => {
    if (p === '…') {
      html += `<span class="page-info">…</span>`;
    } else {
      html += `<button class="page-btn${p === cur ? ' active' : ''}" onclick="gotoPage(${p})">${p+1}</button>`;
    }
  });
  html += `<button class="page-btn" ${cur >= pages-1 ? 'disabled' : ''} onclick="gotoPage(${cur+1})">›</button>`;
  paginationEl.innerHTML = html;
}

function pageRange(cur, total) {
  if (total <= 7) return Array.from({length:total},(_,i)=>i);
  if (cur < 4) return [0,1,2,3,4,'…',total-1];
  if (cur > total - 5) return [0,'…',total-5,total-4,total-3,total-2,total-1];
  return [0,'…',cur-1,cur,cur+1,'…',total-1];
}

function gotoPage(p) {
  state.offset = p * state.limit;
  fetchScholarships();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---- Scrape ----
scrapeBtn.addEventListener('click', async () => {
  if (state.scraping) return;
  scrapeBtn.disabled = true;
  scrapeBtn.textContent = 'Starting…';
  try {
    await apiFetch('/api/scrape?max_pages=5', { method: 'POST' });
    state.scraping = true;
    scrapeDot.classList.add('active');
    scrapeBtn.textContent = 'Scraping…';
  } catch (e) {
    scrapeBtn.disabled = false;
    scrapeBtn.textContent = 'Run Scraper';
    alert('Failed to start scraper: ' + e.message);
  }
});

function startScrapePoller() {
  setInterval(async () => {
    if (!state.scraping) return;
    try {
      const s = await apiFetch('/api/scrape/status');
      if (!s.running) {
        state.scraping = false;
        scrapeDot.classList.remove('active');
        scrapeBtn.disabled = false;
        scrapeBtn.textContent = 'Run Scraper';
        await loadStats();
        await loadSites();
        await fetchScholarships();
      }
    } catch (e) {}
  }, 3000);
}

// ---- Filters ----
let searchTimer;
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = searchInput.value.trim();
    state.offset = 0;
    fetchScholarships();
  }, 400);
});

degreeChips.forEach(chip => {
  chip.addEventListener('click', () => {
    const val = chip.dataset.value;
    if (state.degree_level === val) {
      state.degree_level = '';
      chip.classList.remove('active');
    } else {
      degreeChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.degree_level = val;
    }
    state.offset = 0;
    fetchScholarships();
  });
});

siteSelect.addEventListener('change', () => {
  state.source_site = siteSelect.value;
  state.offset = 0;
  fetchScholarships();
});

sortSelect.addEventListener('change', () => {
  const [sort, order] = sortSelect.value.split(':');
  state.sort = sort;
  state.order = order;
  state.offset = 0;
  fetchScholarships();
});

$('clearFilters').addEventListener('click', () => {
  state.search = '';
  state.degree_level = '';
  state.source_site = '';
  state.offset = 0;
  searchInput.value = '';
  degreeChips.forEach(c => c.classList.remove('active'));
  siteSelect.value = '';
  sortSelect.value = 'scraped_at:desc';
  fetchScholarships();
});

// ---- Loading state ----
function setLoading(on) {
  if (on) {
    gridEl.innerHTML = Array(6).fill(0).map(() => `
      <div class="skeleton-card">
        <div class="skeleton-line" style="height:14px;width:70%"></div>
        <div class="skeleton-line" style="height:12px;width:40%"></div>
        <div class="skeleton-line" style="height:40px;width:100%"></div>
        <div class="skeleton-line" style="height:12px;width:55%"></div>
      </div>`).join('');
  }
}

// ---- Utilities ----
async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function badgeClass(site) {
  if (!site) return 'badge-default';
  const slug = site.toLowerCase().replace(/[^a-z0-9]/g, '');
  return `badge-${slug}`;
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  if (!iso) return '';
  const [y,m,d] = (iso.split('T')[0] || iso).split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[parseInt(m,10)-1] || m} ${parseInt(d,10)}, ${y}`;
}

function daysUntil(iso) {
  if (!iso) return null;
  const now = new Date(); now.setHours(0,0,0,0);
  const d = new Date(iso); d.setHours(0,0,0,0);
  return Math.round((d - now) / 86400000);
}

// ---- Tab switching ----
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const statsBarEl = $('statsBar');

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    tabBtns.forEach(b => b.classList.toggle('active', b === btn));
    tabContents.forEach(c => c.classList.toggle('active', c.id === `tab-${tab}`));
    statsBarEl.style.display = tab === 'browse' ? '' : 'none';
  });
});

// ---- Match Me ----
const matchForm = $('matchForm');
const matchBtn = $('matchBtn');
const matchBtnText = $('matchBtnText');
const matchBtnSpinner = $('matchBtnSpinner');
const matchInfoPanel = $('matchInfoPanel');
const howItWorksHTML = matchInfoPanel.innerHTML;

matchForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const destination = $('f-destination').value;
  const extra = [$('f-extra').value.trim(), destination ? `Preferred study destination: ${destination}` : ''].filter(Boolean).join('. ');
  const profile = {
    name: $('f-name').value.trim(),
    nationality: $('f-nationality').value,
    current_level: $('f-current').value,
    target_level: $('f-target').value,
    field: $('f-field').value.trim(),
    background: $('f-background').value.trim() || undefined,
    extra: extra || undefined,
  };

  matchBtnText.textContent = 'Searching…';
  matchBtnSpinner.style.display = 'inline-block';
  matchBtn.disabled = true;

  matchInfoPanel.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:16px;color:var(--text3)">
      <div class="btn-spinner" style="width:28px;height:28px;border-width:3px;border-color:rgba(79,142,247,0.25);border-top-color:var(--accent)"></div>
      <div style="font-size:0.88rem">Analysing scholarships…</div>
    </div>`;

  try {
    const res = await fetch(API + '/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const result = await res.json();
    renderReportInPanel(result, profile);
  } catch (err) {
    matchInfoPanel.innerHTML = howItWorksHTML;
    alert('Matching failed: ' + err.message);
  } finally {
    matchBtnText.textContent = '✨ Find My Top 10 Scholarships';
    matchBtnSpinner.style.display = 'none';
    matchBtn.disabled = false;
  }
});

function renderReportInPanel(result, profile) {
  const matches = result.matches || [];
  const cards = matches.map(m => {
    const s = m.scholarship || {};
    const highlights = (m.highlights || []).map(h => `<li>${escHtml(h)}</li>`).join('');
    const deadline = s.deadline ? fmtDate(s.deadline) : (s.deadline_raw || 'Not listed');
    const amount = s.amount || (s.funding_type === 'full' ? 'Fully Funded' : null) || 'Not specified';
    const rankColor = m.rank === 1 ? '#ffd600' : m.rank <= 3 ? '#38d9a9' : m.rank <= 6 ? '#4f8ef7' : '#8892b0';
    return `
      <div class="report-card">
        <div class="report-rank" style="border-color:${rankColor};color:${rankColor}">#${m.rank}</div>
        <div class="report-card-body">
          <div class="report-card-title">${escHtml(s.title || 'Scholarship')}</div>
          ${s.organization ? `<div class="report-card-org">🏛 ${escHtml(s.organization)}</div>` : ''}
          <div class="report-meta-row">
            ${amount !== 'Not specified' ? `<span class="report-meta-tag funding">${escHtml(amount)}</span>` : ''}
            ${s.deadline ? `<span class="report-meta-tag deadline">⏰ ${escHtml(deadline)}</span>` : ''}
            ${(s.degree_levels || []).length ? `<span class="report-meta-tag level">${s.degree_levels.map(d => DEGREE_LABELS[d] || d).join(' · ')}</span>` : ''}
          </div>
          <div class="report-reason">${escHtml(m.reason)}</div>
          ${highlights ? `<ul class="report-highlights">${highlights}</ul>` : ''}
          ${s.source_url ? `<a href="${escHtml(s.source_url)}" target="_blank" rel="noopener" class="report-apply-btn">View &amp; Apply →</a>` : ''}
        </div>
      </div>`;
  }).join('');

  matchInfoPanel.innerHTML = `
    <div class="report-panel-header">
      <div>
        <div class="report-title">✨ Your Top ${matches.length} Matches</div>
        <div class="report-subtitle">${escHtml(profile.name)} · ${escHtml(profile.nationality)} · ${escHtml(profile.field)}</div>
      </div>
      <button class="report-new-search-btn" onclick="resetMatchPanel()">↩ New Search</button>
    </div>
    ${result.summary ? `<div class="report-summary">${escHtml(result.summary)}</div>` : ''}
    <div class="report-meta-info">${result.total_candidates || 0} analysed · ${matches.length} selected</div>
    <div class="report-cards">${cards}</div>
  `;
  matchInfoPanel.scrollTop = 0;
}

function resetMatchPanel() {
  matchInfoPanel.innerHTML = howItWorksHTML;
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ---- Start ----
init();
