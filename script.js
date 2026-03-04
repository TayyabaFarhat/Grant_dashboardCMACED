/* ═══════════════════════════════════════════════════════════════
   CMACED Startup Intelligence Dashboard — script.js
   Superior University × ID92
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────────
const S = {
  opps:       [],
  archive:    [],
  tab:        'all',
  query:      '',
  regionFilter: '',
  typeFilter:   '',
  sortBy:     'deadline',
};

// ── DOM ────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const oppGrid       = $('oppGrid');
const skeletonGrid  = $('skeletonGrid');
const emptyState    = $('emptyState');
const searchInput   = $('searchInput');
const searchClear   = $('searchClear');
const modal         = $('modal');
const modalBody     = $('modalBody');

// ── Boot ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  bindEvents();
  loadData();
  setFooterBuild();
});

// ── Theme ──────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('cmaced-theme') || 'dark';
  applyTheme(saved);
}
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  $('themeIcon').textContent = t === 'dark' ? '☀' : '◑';
  localStorage.setItem('cmaced-theme', t);
}
$('themeBtn').addEventListener('click', () => {
  const cur = document.documentElement.getAttribute('data-theme');
  applyTheme(cur === 'dark' ? 'light' : 'dark');
});

// ── Data Loading ───────────────────────────────────────────────
async function loadData() {
  setStatus('loading');
  try {
    const bust = '?v=' + Date.now();
    const [r1, r2] = await Promise.allSettled([
      fetch('opportunities.json' + bust),
      fetch('archive.json' + bust),
    ]);

    if (r1.status === 'fulfilled' && r1.value.ok) {
      const d = await r1.value.json();
      S.opps = Array.isArray(d) ? d : (d.opportunities || []);
    } else {
      S.opps = fallbackData();
    }

    if (r2.status === 'fulfilled' && r2.value.ok) {
      const d = await r2.value.json();
      S.archive = Array.isArray(d) ? d : [];
    }

  } catch (e) {
    console.warn('Fallback data:', e.message);
    S.opps = fallbackData();
  }

  hideSkeleton();
  updateHero();
  updateStats();
  render();
  setStatus('live');
}

function setStatus(state) {
  const dot  = $('statusDot');
  const text = $('statusText');
  if (state === 'loading') {
    dot.className  = 'status-dot';
    text.textContent = 'Loading…';
  } else if (state === 'live') {
    dot.className  = 'status-dot live';
    const now = new Date();
    text.textContent = 'Live · ' + now.toLocaleDateString('en-PK', {day:'numeric',month:'short'});
  }
}

function hideSkeleton() {
  skeletonGrid.style.display = 'none';
  oppGrid.hidden = false;
}

function setFooterBuild() {
  const el = $('footerBuild');
  if (el) el.textContent = 'Build ' + new Date().toISOString().slice(0,10);
}

// ── Hero ───────────────────────────────────────────────────────
function updateHero() {
  const today = new Date();
  const in7   = new Date(today.getTime() + 7 * 86400e3);
  const in48  = new Date(today.getTime() - 48 * 36e5);

  $('heroTotal').textContent   = S.opps.length;
  $('heroNew').textContent     = S.opps.filter(o => o.date_added && new Date(o.date_added) >= in48).length;
  $('heroClosing').textContent = S.opps.filter(o => {
    if (!o.deadline) return false;
    const d = new Date(o.deadline);
    return d >= today && d <= in7;
  }).length;

  const now = new Date();
  $('heroTimestamp').textContent = now.toLocaleDateString('en-PK', {
    day:'2-digit', month:'short', year:'numeric'
  }) + ' · ' + now.toLocaleTimeString('en-PK', {hour:'2-digit',minute:'2-digit'});
}

// ── Stats ──────────────────────────────────────────────────────
function updateStats() {
  const all   = S.opps;
  const total = all.length || 1; // avoid /0
  const today = new Date();
  const in7   = new Date(today.getTime() + 7 * 86400e3);
  const in48  = new Date(today.getTime() - 48 * 36e5);

  const natCount  = all.filter(o => o.region === 'national').length;
  const intlCount = all.filter(o => o.region === 'international').length;
  const closingCount = all.filter(o => {
    if (!o.deadline) return false;
    const d = new Date(o.deadline); return d >= today && d <= in7;
  }).length;
  const newCount = all.filter(o => o.date_added && new Date(o.date_added) >= in48).length;

  $('sTotal').textContent   = all.length;
  $('sNational').textContent= natCount;
  $('sIntl').textContent    = intlCount;
  $('sClosing').textContent = closingCount;
  $('sNew').textContent     = newCount;

  // Progress bars (relative to total)
  const pct = n => Math.round((n / total) * 100) + '%';
  setTimeout(() => {
    $('barNational').style.width  = pct(natCount);
    $('barIntl').style.width      = pct(intlCount);
    $('barClosing').style.width   = pct(closingCount);
    $('barNew').style.width       = pct(newCount);
  }, 200);
}

// ── Filter & Sort ──────────────────────────────────────────────
function getFiltered() {
  const today = new Date();
  const in7   = new Date(today.getTime() + 7 * 86400e3);
  const query = S.query.toLowerCase();

  let pool = S.tab === 'archive' ? S.archive : S.opps;

  // Tab filter
  if (S.tab === 'national')     pool = pool.filter(o => o.region === 'national');
  else if (S.tab === 'international') pool = pool.filter(o => o.region === 'international');
  else if (S.tab === 'closing') pool = pool.filter(o => {
    if (!o.deadline) return false;
    const d = new Date(o.deadline); return d >= today && d <= in7;
  });
  else if (['grant','competition','hackathon','accelerator','fellowship'].includes(S.tab))
    pool = pool.filter(o => o.type === S.tab);

  // Region dropdown filter
  if (S.regionFilter) pool = pool.filter(o => o.region === S.regionFilter);

  // Type dropdown filter
  if (S.typeFilter) pool = pool.filter(o => o.type === S.typeFilter);

  // Search
  if (query) pool = pool.filter(o =>
    [o.name, o.organization, o.requirements, o.country]
      .some(f => (f || '').toLowerCase().includes(query))
  );

  // Sort
  const result = [...pool];
  if (S.sortBy === 'deadline') {
    result.sort((a, b) => {
      if (!a.deadline) return 1;
      if (!b.deadline) return -1;
      return new Date(a.deadline) - new Date(b.deadline);
    });
  } else if (S.sortBy === 'new') {
    result.sort((a, b) => new Date(b.date_added || 0) - new Date(a.date_added || 0));
  } else if (S.sortBy === 'prize') {
    result.sort((a, b) => parsePrize(b.prize) - parsePrize(a.prize));
  }

  return result;
}

function parsePrize(s) {
  if (!s) return 0;
  const m = s.replace(/,/g,'').match(/[\d.]+/);
  return m ? parseFloat(m[0]) : 0;
}

// ── Render ─────────────────────────────────────────────────────
function render() {
  const data = getFiltered();
  const isArchive = S.tab === 'archive';

  $('resultsCount').textContent = `${data.length} result${data.length !== 1 ? 's' : ''}`;
  $('resultsHint').textContent  = data.length > 0
    ? (S.tab === 'closing' ? '⏳ Closing within 7 days' : '')
    : '';

  if (data.length === 0) {
    oppGrid.innerHTML = '';
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;
  oppGrid.innerHTML = data.map((o, i) => cardHTML(o, isArchive, i)).join('');

  // Attach click → modal
  oppGrid.querySelectorAll('.opp-card').forEach(card => {
    card.addEventListener('click', e => {
      if (e.target.closest('.btn-apply') || e.target.closest('.btn-visit')) return;
      openModal(card.dataset.id, isArchive);
    });
  });
}

// ── Card HTML ──────────────────────────────────────────────────
function cardHTML(o, isArchive, idx) {
  const today  = new Date();
  const dl     = o.deadline ? new Date(o.deadline) : null;
  const in48   = new Date(today.getTime() - 48 * 36e5);
  const in7    = new Date(today.getTime() + 7 * 86400e3);

  const isNew     = !isArchive && o.date_added && new Date(o.date_added) >= in48;
  const isClosing = !isArchive && dl && dl >= today && dl <= in7;

  let cls = 'opp-card';
  if (o.region === 'national') cls += ' is-national';
  if (isNew) cls += ' is-new';
  if (isClosing) cls += ' is-closing';
  if (isArchive) cls += ' is-archived';

  const typeBadge = `<span class="type-badge tb-${o.type || 'grant'}">${o.type || 'grant'}</span>`;
  const flag = o.region === 'national' ? '🇵🇰' : '🌍';

  // Deadline chip
  let dlChip = '';
  if (isArchive) {
    dlChip = `<span class="meta-chip">📁 Archived</span>`;
  } else if (dl) {
    const daysLeft = Math.ceil((dl - today) / 86400e3);
    const urgentCls = isClosing ? ' urgent' : '';
    const countdown = isClosing ? `<span class="countdown-tag">${daysLeft}d left</span>` : '';
    dlChip = `<span class="meta-chip deadline${urgentCls}">📅 ${fmtDate(dl)}${countdown}</span>`;
  }

  const prizeChip = o.prize
    ? `<span class="meta-chip prize">💰 ${esc(o.prize)}</span>`
    : '';

  const applyBtn = o.application_link
    ? `<a class="btn-apply" href="${esc(o.application_link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Apply Now ↗</a>`
    : '';
  const visitBtn = o.source && o.source !== o.application_link
    ? `<a class="btn-visit" href="${esc(o.source)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗</a>`
    : '';

  const delay = `animation-delay:${Math.min(idx * 25, 400)}ms`;

  return `
  <article class="${cls}" data-id="${esc(o.id)}" style="${delay}" role="button" tabindex="0"
    onkeydown="if(event.key==='Enter')this.click()">
    <div class="card-top">
      <div class="card-badges">${typeBadge}</div>
      <span class="region-pill" title="${o.region === 'national' ? 'Pakistan' : 'International'}">${flag}</span>
    </div>
    <div>
      <div class="card-title">${esc(o.name || 'Untitled')}</div>
      <div class="card-org">${esc(o.organization || '')}</div>
    </div>
    ${o.requirements ? `<p class="card-desc">${esc(o.requirements)}</p>` : ''}
    <div class="card-meta-row">${dlChip}${prizeChip}</div>
    <div class="card-footer">
      <span class="card-source" title="${esc(o.source || '')}">${esc(domainOf(o.source))}</span>
      <div class="card-actions">${visitBtn}${applyBtn}</div>
    </div>
  </article>`;
}

// ── Modal ──────────────────────────────────────────────────────
function openModal(id, isArchive) {
  const pool = isArchive ? S.archive : S.opps;
  const o = pool.find(x => x.id === id);
  if (!o) return;

  const dl = o.deadline ? new Date(o.deadline) : null;
  const today = new Date();
  const in7   = new Date(today.getTime() + 7 * 86400e3);
  const isClosing = dl && dl >= today && dl <= in7;
  const daysLeft = dl ? Math.ceil((dl - today) / 86400e3) : null;

  modalBody.innerHTML = `
    <div class="modal-badge-row">
      <span class="type-badge tb-${o.type || 'grant'}">${o.type || 'grant'}</span>
      <span class="type-badge" style="background:var(--bg-elevated);color:var(--text-3);border:1px solid var(--border)">${o.region === 'national' ? '🇵🇰 Pakistan' : '🌍 International'}</span>
      ${isClosing ? `<span class="type-badge" style="background:rgba(245,166,35,0.15);color:var(--amber);border:1px solid rgba(245,166,35,0.3)">⏳ ${daysLeft}d left</span>` : ''}
    </div>
    <h2 class="modal-title">${esc(o.name || '')}</h2>
    <p class="modal-org">${esc(o.organization || '')}</p>
    <div class="modal-grid">
      ${mf('Deadline', dl ? fmtDate(dl) + (isClosing ? ' — closing soon' : '') : 'Not specified')}
      ${mf('Prize / Funding', o.prize || 'Not specified')}
      ${mf('Country', o.country || 'Not specified')}
      ${mf('Date Added', o.date_added ? fmtDate(new Date(o.date_added)) : 'N/A')}
      ${mf('Requirements', o.requirements || 'See official program page', true)}
      ${o.source ? mfLink('Official Source', o.source) : ''}
    </div>
    <div class="modal-actions">
      ${o.application_link
        ? `<a class="modal-apply" href="${esc(o.application_link)}" target="_blank" rel="noopener">Apply Now ↗</a>`
        : `<span style="font-size:13px;color:var(--text-3)">No direct link verified. Check official source.</span>`
      }
      ${o.source
        ? `<a class="modal-visit" href="${esc(o.source)}" target="_blank" rel="noopener">🔗 Official Site</a>`
        : ''
      }
    </div>
  `;

  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  $('modalClose').focus();
}

function mf(label, value, full = false) {
  return `<div class="mf${full ? ' full' : ''}">
    <div class="mf-label">${label}</div>
    <div class="mf-value">${esc(value)}</div>
  </div>`;
}
function mfLink(label, url) {
  return `<div class="mf full">
    <div class="mf-label">${label}</div>
    <a class="mf-value mf-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>
  </div>`;
}

function closeModal() {
  modal.hidden = true;
  document.body.style.overflow = '';
}
$('modalClose').addEventListener('click', closeModal);
$('modalBackdrop').addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });

// ── Events ─────────────────────────────────────────────────────
function bindEvents() {
  // Tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      S.tab = btn.dataset.tab;
      render();
    });
  });

  // Search
  searchInput.addEventListener('input', e => {
    S.query = e.target.value;
    searchClear.classList.toggle('visible', S.query.length > 0);
    render();
  });
  searchClear.addEventListener('click', () => {
    searchInput.value = ''; S.query = '';
    searchClear.classList.remove('visible');
    searchInput.focus();
    render();
  });

  // Filters
  $('regionFilter').addEventListener('change', e => { S.regionFilter = e.target.value; render(); });
  $('typeFilter').addEventListener('change',   e => { S.typeFilter   = e.target.value; render(); });
  $('sortSelect').addEventListener('change',   e => { S.sortBy       = e.target.value; render(); });

  // Export
  $('exportBtn').addEventListener('click', exportCSV);
  $('footerExport').addEventListener('click', e => { e.preventDefault(); exportCSV(); });

  // Reset
  $('resetFilters').addEventListener('click', resetAll);
}

function resetAll() {
  searchInput.value = '';
  S.query = ''; S.regionFilter = ''; S.typeFilter = ''; S.sortBy = 'deadline';
  $('regionFilter').value = ''; $('typeFilter').value = ''; $('sortSelect').value = 'deadline';
  searchClear.classList.remove('visible');
  // Go back to All tab
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelector('.tab[data-tab="all"]').classList.add('active');
  S.tab = 'all';
  render();
}

// ── CSV Export ─────────────────────────────────────────────────
function exportCSV() {
  const rows = [...S.archive];
  if (rows.length === 0) { alert('Archive is currently empty.'); return; }
  const keys = ['id','name','organization','type','country','region','deadline','prize','requirements','application_link','source','date_added','status'];
  const lines = [
    keys.join(','),
    ...rows.map(o => keys.map(k => `"${(o[k]||'').toString().replace(/"/g,'""')}"`).join(','))
  ];
  const blob = new Blob([lines.join('\n')], {type:'text/csv;charset=utf-8;'});
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), {href:url, download:`cmaced-archive-${new Date().getFullYear()}.csv`});
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

// ── Helpers ────────────────────────────────────────────────────
function esc(s) {
  return String(s||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}
function fmtDate(d) {
  return d.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
}
function domainOf(url) {
  try { return new URL(url).hostname.replace('www.',''); } catch { return url||''; }
}

// ── Fallback Data ──────────────────────────────────────────────
function fallbackData() {
  const t = new Date();
  const d = n => new Date(t.getTime() + n * 86400e3).toISOString().slice(0,10);
  const today = t.toISOString().slice(0,10);

  return [
    {
      id:'ignite-startup-fund', name:'Ignite Startup Fund',
      organization:'Ignite National Technology Fund', type:'grant',
      country:'Pakistan', region:'national', deadline:d(45),
      prize:'PKR 5–25 million',
      requirements:'Early-stage tech startups registered in Pakistan. Working prototype required.',
      application_link:'https://ignite.org.pk/programs/', source:'https://ignite.org.pk',
      date_added:d(-1), status:'Open'
    },
    {
      id:'plan9-incubator', name:'Plan9 Incubation Program',
      organization:'PITB – Punjab Information Technology Board', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(30),
      prize:'Office space + PKR 1M seed',
      requirements:'Tech-based startup teams from Punjab. Pre-revenue or early revenue stage.',
      application_link:'https://plan9.pitb.gov.pk', source:'https://plan9.pitb.gov.pk',
      date_added:d(-2), status:'Open'
    },
    {
      id:'nic-lahore', name:'National Incubation Center Lahore',
      organization:'NIC Lahore / STZA', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(20),
      prize:'USD 10,000 + mentorship',
      requirements:'Pakistani founders. Tech/innovation focused. Presentation to panel required.',
      application_link:'https://niclahore.com', source:'https://niclahore.com',
      date_added:d(-3), status:'Open'
    },
    {
      id:'yc-accelerator', name:'Y Combinator Accelerator',
      organization:'Y Combinator', type:'accelerator',
      country:'USA', region:'international', deadline:d(60),
      prize:'USD 500,000',
      requirements:'Any stage, any country. Online application. Equity-based investment.',
      application_link:'https://www.ycombinator.com/apply', source:'https://www.ycombinator.com',
      date_added:d(-1), status:'Open'
    },
    {
      id:'hult-prize', name:'Hult Prize Global Competition',
      organization:'Hult Prize Foundation', type:'competition',
      country:'Global', region:'international', deadline:d(14),
      prize:'USD 1,000,000',
      requirements:'University student teams. Social impact focus. Virtual application open worldwide.',
      application_link:'https://www.hultprize.org', source:'https://www.hultprize.org',
      date_added:today, status:'Open'
    },
    {
      id:'mit-solve-challenge', name:'MIT Solve Global Challenge',
      organization:'MIT Solve', type:'competition',
      country:'Global', region:'international', deadline:d(90),
      prize:'USD 10,000–150,000',
      requirements:'Social entrepreneurs worldwide. Online application accepted from Pakistan.',
      application_link:'https://solve.mit.edu', source:'https://solve.mit.edu',
      date_added:d(-4), status:'Open'
    },
    {
      id:'google-startups-accelerator', name:'Google for Startups Accelerator',
      organization:'Google', type:'accelerator',
      country:'Global', region:'international', deadline:d(50),
      prize:'USD 100,000 in Cloud credits (equity-free)',
      requirements:'Series A or earlier. AI/ML focused preferred. Virtual participation available.',
      application_link:'https://startup.google.com/programs/accelerator/', source:'https://startup.google.com',
      date_added:d(-2), status:'Open'
    },
    {
      id:'msft-founders-hub', name:'Microsoft for Startups Founders Hub',
      organization:'Microsoft', type:'grant',
      country:'Global', region:'international', deadline:d(365),
      prize:'USD 150,000 in Azure credits',
      requirements:'Pre-seed to Series A. No equity required. Open to Pakistan-based startups.',
      application_link:'https://www.microsoft.com/en-us/startups', source:'https://www.microsoft.com/en-us/startups',
      date_added:d(-5), status:'Open'
    },
    {
      id:'seedstars-world', name:'Seedstars World Competition',
      organization:'Seedstars World', type:'competition',
      country:'Global', region:'international', deadline:d(25),
      prize:'USD 500,000 investment',
      requirements:'Early-stage tech startups. Local qualifying rounds then global finals.',
      application_link:'https://www.seedstars.com/programs/', source:'https://www.seedstars.com',
      date_added:d(-2), status:'Open'
    },
    {
      id:'hec-innovation-fund', name:'HEC Innovation & Research Fund',
      organization:'Higher Education Commission Pakistan', type:'grant',
      country:'Pakistan', region:'national', deadline:d(35),
      prize:'PKR 2–10 million',
      requirements:'University-affiliated researchers and student entrepreneurs in Pakistan.',
      application_link:'https://hec.gov.pk/english/services/faculty/NRPU/Pages/Default.aspx', source:'https://hec.gov.pk',
      date_added:d(-6), status:'Open'
    },
    {
      id:'pseb-ites-support', name:'PSEB IT Export Startup Support',
      organization:'Pakistan Software Export Board', type:'grant',
      country:'Pakistan', region:'national', deadline:d(18),
      prize:'PKR 3 million + export facilitation',
      requirements:'IT/software companies targeting export markets. Must be PSEB registered.',
      application_link:'https://pseb.org.pk/startups', source:'https://pseb.org.pk',
      date_added:d(-5), status:'Open'
    },
    {
      id:'devpost-hackathons', name:'Devpost Global Hackathons',
      organization:'Devpost', type:'hackathon',
      country:'Global', region:'international', deadline:d(7),
      prize:'Varies per hackathon',
      requirements:'Virtual. Open to all nationalities. Individual or team submission.',
      application_link:'https://devpost.com/hackathons', source:'https://devpost.com',
      date_added:d(-1), status:'Open'
    },
    {
      id:'masschallenge-accelerator', name:'MassChallenge Global Accelerator',
      organization:'MassChallenge', type:'accelerator',
      country:'Global', region:'international', deadline:d(55),
      prize:'USD 250,000 equity-free',
      requirements:'No equity taken. Open to international founders including Pakistan.',
      application_link:'https://masschallenge.org', source:'https://masschallenge.org',
      date_added:d(-4), status:'Open'
    },
    {
      id:'cmaced-startup-grant', name:'CMACED Internal Startup Grant',
      organization:'CMACED – Superior University', type:'grant',
      country:'Pakistan', region:'national', deadline:d(10),
      prize:'PKR 500,000',
      requirements:'Currently enrolled Superior University students. Working prototype required.',
      application_link:'https://superior.edu.pk', source:'https://superior.edu.pk',
      date_added:today, status:'Open'
    },
    {
      id:'lums-entrepreneurship', name:'LUMS Centre for Entrepreneurship Program',
      organization:'LUMS – Lahore University of Management Sciences', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(40),
      prize:'Mentorship + USD 5,000 seed',
      requirements:'Open to all Pakistani university graduates and students.',
      application_link:'https://lums.edu.pk/centre-entrepreneurship', source:'https://lums.edu.pk',
      date_added:d(-7), status:'Open'
    },
    {
      id:'500-global', name:'500 Global Accelerator',
      organization:'500 Global', type:'accelerator',
      country:'Global', region:'international', deadline:d(42),
      prize:'USD 150,000 investment',
      requirements:'Early-stage startups. Open to Pakistani founders. Online application.',
      application_link:'https://500.co/accelerators', source:'https://500.co',
      date_added:d(-3), status:'Open'
    },
  ];
}
