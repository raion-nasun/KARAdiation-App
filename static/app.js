/* 방사선 소식 PWA — app.js */

// ── 상태 ──────────────────────────────────
const STATE = {
  tab: 'home',
  cat: '전체',
  searchCat: '전체',
  searchQ: '',
  offset: 0,
  searchOffset: 0,
  recentSearches: JSON.parse(localStorage.getItem('recentSearches') || '[]'),
  prefs: JSON.parse(localStorage.getItem('prefs') || '{"dimRead":true}'),
  currentDetail: null,
};

const CAT_CLASS = {
  '산업 뉴스':      'industry',
  'KARA 주요이벤트': 'kara',
  '국내외 공고':    'announce',
  '업계 행사':      'event',
  '국제 동향':      'intl',
};

// ── 초기화 ────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.getElementById('splash').classList.add('hidden');
    setTimeout(() => document.getElementById('splash').remove(), 450);
  }, 2000);

  loadStats();
  loadTopIssues();
  setupHomeSearch();
  setupHomeSearchFilterChips();
  renderRecentSearches();
});

// ── 탭 전환 ───────────────────────────────
function switchTab(tab) {
  STATE.tab = tab;
  // 카테고리 오버레이가 열려있으면 닫기
  document.getElementById('categoryOverlay').classList.remove('open');
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.getElementById(`screen-${tab}`).classList.add('active');

  if (tab === 'star') loadFavorites();
  if (tab === 'analysis') loadAnalysis();
  if (tab === 'settings') loadSettingsStats();
}

// ── 카테고리 오버레이 ─────────────────────
function openCategory(cat) {
  STATE.cat = cat;
  document.getElementById('catOverlayTitle').textContent = cat;
  document.getElementById('categoryOverlay').classList.add('open');
  loadFeed();
}

function closeCategory() {
  document.getElementById('categoryOverlay').classList.remove('open');
}

// ── 통계 ──────────────────────────────────
async function loadStats() {
  try {
    const d = await fetch('/api/stats').then(r => r.json());
    const unread = d.unread || 0;
    const badge = document.getElementById('unreadBadge');
    if (unread > 0) {
      badge.textContent = unread > 99 ? '99+' : unread;
      badge.style.display = 'block';
    } else {
      badge.style.display = 'none';
    }
    const sub = document.getElementById('homeSubtitle');
    if (d.last_collect) {
      const t = (d.last_collect.run_at || '').slice(0, 16);
      sub.textContent = `${t} 수집 · 전체 ${d.total}건`;
    }
  } catch (e) {}
}

async function loadSettingsStats() {
  try {
    const d = await fetch('/api/stats').then(r => r.json());
    const lc = d.last_collect;
    document.getElementById('lastCollectVal').textContent =
      lc ? `${(lc.run_at || '').slice(0, 16)} (+${lc.count_added}건)` : '없음';
    document.getElementById('totalArticlesVal').textContent = `${d.total}건`;
  } catch (e) {}
}

// ── 피드 ──────────────────────────────────
async function loadFeed(append = false) {
  if (!append) STATE.offset = 0;
  const params = new URLSearchParams({
    category: STATE.cat,
    search: '',
    starred: '0',
    unread: '0',
    offset: STATE.offset,
  });
  const items = await fetch(`/api/news?${params}`).then(r => r.json());
  const feed = document.getElementById('newsFeed');

  if (!append) feed.innerHTML = '';

  if (!items.length && !append) {
    feed.innerHTML = `<div class="empty-state">
      <div class="empty-icon">📡</div>
      <div class="empty-title">수집된 뉴스가 없습니다</div>
      <div class="empty-sub">매일 오전 5시에 자동으로 수집됩니다</div>
    </div>`;
    return;
  }

  items.forEach(item => feed.appendChild(makeCard(item)));

  if (items.length === 50) {
    const btn = document.createElement('button');
    btn.className = 'load-more-btn';
    btn.textContent = '더 보기';
    btn.onclick = () => { STATE.offset += 50; btn.remove(); loadFeed(true); };
    feed.appendChild(btn);
  }
  loadStats();
}

// ── 카드 생성 ─────────────────────────────
function makeCard(item) {
  const cls = CAT_CLASS[item.category] || 'industry';
  const div = document.createElement('div');
  const read = item.is_read && STATE.prefs.dimRead;
  div.className = `news-card cat-${cls} ${read ? 'read' : ''}`;
  div.dataset.id = item.id;

  const isAE = item.category === '국내외 공고' || item.category === '업계 행사';
  const regionBadge = (isAE && item.region)
    ? `<span class="region-badge ${item.region === '국내' ? 'domestic' : 'overseas'}">${item.region}</span>` : '';

  const extraParts = [];
  if (isAE && item.end_date) extraParts.push(`마감 ${esc(item.end_date)}`);
  if (isAE && item.location) extraParts.push(`📍 ${esc(item.location)}`);
  const extraLine = extraParts.length
    ? `<div class="card-extra">${extraParts.join(' · ')}</div>` : '';

  div.innerHTML = `
    <div class="card-body">
      <div class="card-top">
        ${regionBadge}
        <span class="card-cat cat-badge-${cls}">${item.category}</span>
        <span class="card-source">${esc(item.source || '')}</span>
        <span class="card-date">${(item.published || '').slice(0, 10)}</span>
      </div>
      <div class="card-title">${esc(item.title)}</div>
      ${item.summary ? `<div class="card-summary">${esc(item.summary)}</div>` : ''}
      ${extraLine}
    </div>
    <div class="card-right">
      <button class="btn-star ${item.is_starred ? 'on' : ''}"
        onclick="event.stopPropagation(); toggleStar(${item.id}, this)"
        aria-label="즐겨찾기">${item.is_starred ? '★' : '☆'}</button>
      ${!item.is_read ? '<div class="unread-dot"></div>' : ''}
    </div>`;

  div.addEventListener('click', () => openDetail(item));
  return div;
}


// ── 상세 보기 ─────────────────────────────
async function openDetail(item) {
  STATE.currentDetail = item;
  await fetch(`/api/read/${item.id}`, { method: 'POST' });

  // 카드 읽음 처리
  const card = document.querySelector(`.news-card[data-id="${item.id}"]`);
  if (card && STATE.prefs.dimRead) card.classList.add('read');
  const dot = card?.querySelector('.unread-dot');
  if (dot) dot.remove();

  const cls = CAT_CLASS[item.category] || 'industry';
  document.getElementById('detailHdrCat').textContent = item.category;

  const isAE = item.category === '국내외 공고' || item.category === '업계 행사';
  const regionBadge = (isAE && item.region)
    ? `<span class="region-badge ${item.region === '국내' ? 'domestic' : 'overseas'}" style="margin-right:6px">${item.region}</span>` : '';

  // 기간/장소 정보 블록
  let infoBlock = '';
  if (isAE) {
    const rows = [];
    const start = (item.published || '').slice(0, 10);
    if (item.end_date) {
      const label = item.category === '업계 행사' ? '행사 기간' : '접수 기간';
      rows.push(`<div class="detail-info-row"><span class="detail-info-label">${label}</span><span>${esc(start)} ~ ${esc(item.end_date)}</span></div>`);
    } else if (start) {
      const label = item.category === '업계 행사' ? '행사일' : '공고일';
      rows.push(`<div class="detail-info-row"><span class="detail-info-label">${label}</span><span>${esc(start)}</span></div>`);
    }
    if (item.location) {
      rows.push(`<div class="detail-info-row"><span class="detail-info-label">장소</span><span>${esc(item.location)}</span></div>`);
    }
    rows.push(`<div class="detail-info-row"><span class="detail-info-label">기관</span><span>${esc(item.source || '')}</span></div>`);
    if (rows.length) infoBlock = `<div class="detail-info-block">${rows.join('')}</div>`;
  }

  const body = document.getElementById('detailBody');
  body.innerHTML = `
    <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:10px">
      ${regionBadge}<span class="detail-badge cat-badge-${cls}">${item.category}</span>
    </div>
    <h1 class="detail-title">${esc(item.title)}</h1>
    ${isAE ? infoBlock : `
    <div class="detail-meta">
      <span>${esc(item.source || '')}</span>
      <span>·</span>
      <span>${(item.published || '').slice(0, 10)}</span>
    </div>`}
    <div class="ai-summary-section" id="aiSummarySection">
      <div class="ai-summary-label">✦ AI 요약</div>
      <div class="ai-summary-content" id="aiSummaryContent">
        <div class="ai-summary-loading"><span class="ai-spinner"></span> 요약 생성 중...</div>
      </div>
    </div>`;

  // 하단 고정 액션 바 설정
  const urlBtn = document.getElementById('detailUrlBtn');
  const starBtn = document.getElementById('detailStarBtn');
  urlBtn.onclick = () => openUrl(item.url || '');
  starBtn.className = `btn-star-detail ${item.is_starred ? 'on' : ''}`;
  starBtn.textContent = item.is_starred ? '★' : '☆';
  starBtn.onclick = () => toggleStarDetail(item.id);
  document.getElementById('detailActions').style.display = 'flex';

  document.getElementById('detailOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  loadStats();

  // AI 요약
  fetch(`/api/summarize/${item.id}`)
    .then(r => r.json())
    .then(d => {
      const cont = document.getElementById('aiSummaryContent');
      if (!cont) return;
      if (d.summary) {
        cont.innerHTML = `<p class="ai-summary-text">${esc(d.summary)}</p>`;
      } else {
        cont.innerHTML = `<p class="ai-summary-error">${esc(d.error || '요약을 불러올 수 없습니다.')}</p>`;
      }
    })
    .catch(() => {
      const cont = document.getElementById('aiSummaryContent');
      if (cont) cont.innerHTML = '<p class="ai-summary-error">요약을 불러올 수 없습니다.</p>';
    });
}

function closeDetail() {
  document.getElementById('detailOverlay').classList.remove('open');
  document.getElementById('detailActions').style.display = 'none';
  document.body.style.overflow = '';
}

function openUrl(url) {
  if (url && url !== 'undefined') window.open(url, '_blank', 'noopener');
}

async function toggleStarDetail(id) {
  await fetch(`/api/star/${id}`, { method: 'POST' });
  const btn = document.getElementById('detailStarBtn');
  const isOn = btn.classList.contains('on');
  btn.classList.toggle('on');
  btn.textContent = isOn ? '☆' : '★';
  showToast(isOn ? '즐겨찾기 해제' : '즐겨찾기에 저장됨');

  // 피드 카드도 업데이트
  const cardStar = document.querySelector(`.news-card[data-id="${id}"] .btn-star`);
  if (cardStar) { cardStar.classList.toggle('on', !isOn); cardStar.textContent = isOn ? '☆' : '★'; }
  loadStats();
}

// ── 즐겨찾기 탭 ───────────────────────────
async function loadFavorites() {
  const items = await fetch('/api/news?category=전체&search=&starred=1&unread=0&offset=0').then(r => r.json());
  const feed = document.getElementById('favFeed');
  const sub = document.getElementById('starSubtitle');
  sub.textContent = `저장된 기사 ${items.length}건`;

  if (!items.length) {
    feed.innerHTML = `<div class="empty-state">
      <div class="empty-icon">☆</div>
      <div class="empty-title">즐겨찾기가 없습니다</div>
      <div class="empty-sub">기사 카드의 ☆ 버튼을 눌러 저장하세요</div>
    </div>`;
    return;
  }

  // 날짜별 그룹화
  const groups = {};
  items.forEach(item => {
    const d = (item.published || '').slice(0, 10) || '날짜 없음';
    if (!groups[d]) groups[d] = [];
    groups[d].push(item);
  });

  feed.innerHTML = '';
  Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0])).forEach(([date, arr]) => {
    const sec = document.createElement('div');
    sec.className = 'fav-section-title';
    sec.textContent = date;
    feed.appendChild(sec);
    arr.forEach(item => {
      const card = document.createElement('div');
      card.className = 'fav-card';
      card.innerHTML = `
        <span class="fav-star">★</span>
        <div class="fav-content">
          <div class="fav-cat">${esc(item.category)}</div>
          <div class="fav-title">${esc(item.title)}</div>
          <div class="fav-meta">${esc(item.source || '')} · ${(item.published || '').slice(0, 10)}</div>
        </div>`;
      card.addEventListener('click', () => openDetail(item));
      feed.appendChild(card);
    });
  });
}

// ── 주요 이슈 Top 3 ────────────────────────
const RANK_COLORS = ['#FF9F0A', '#AEAEB2', '#C47B35'];
const RANK_LABELS = ['1ST', '2ND', '3RD'];

async function loadTopIssues() {
  const list = document.getElementById('topIssuesList');
  try {
    const items = await fetch('/api/top-issues').then(r => r.json());
    if (!items.length) { list.innerHTML = ''; return; }
    list.innerHTML = items.map((item, i) => {
      const cls = CAT_CLASS[item.category] || 'industry';
      const title = (item.title || '').slice(0, 60) + (item.title?.length > 60 ? '…' : '');
      return `
        <div class="top-issue-card" onclick="openTopIssue(${item.id}, '${esc(item.category)}')">
          <div class="top-issue-rank" style="color:${RANK_COLORS[i]}">
            <span class="top-issue-rank-num">${i + 1}</span>
          </div>
          <div class="top-issue-body">
            <span class="top-issue-cat cat-badge-${cls}">${item.category}</span>
            <div class="top-issue-title">${esc(title)}</div>
          </div>
          <div class="top-issue-arrow"><i class="ti ti-arrow-right"></i></div>
        </div>`;
    }).join('');
  } catch(e) {
    list.innerHTML = '';
  }
}

function openTopIssue(id, category) {
  STATE.cat = category;
  document.getElementById('catOverlayTitle').textContent = category;
  document.getElementById('categoryOverlay').classList.add('open');
  loadFeed();
  // 피드 로드 후 해당 기사로 스크롤
  setTimeout(() => {
    const card = document.querySelector(`.news-card[data-id="${id}"]`);
    if (card) { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); card.click(); }
  }, 600);
}

// ── 홈 검색 ───────────────────────────────
let searchTimer = null;

function setupHomeSearch() {
  const inp = document.getElementById('homeSearchInput');
  const clearBtn = document.getElementById('homeClearBtn');
  inp.addEventListener('input', () => {
    const hasVal = inp.value.length > 0;
    clearBtn.classList.toggle('visible', hasVal);
    document.getElementById('homeSearchPanel').classList.toggle('open', hasVal || document.activeElement === inp);
    document.getElementById('catGrid').classList.toggle('hidden-grid', hasVal);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runHomeSearch(inp.value.trim()), 350);
  });
  inp.addEventListener('focus', () => {
    document.getElementById('homeSearchPanel').classList.add('open');
    document.getElementById('catGrid').classList.add('hidden-grid');
    document.getElementById('topIssuesSection').style.display = 'none';
    if (!inp.value) renderRecentSearches();
  });
  inp.addEventListener('blur', () => {
    setTimeout(() => {
      if (!inp.value) {
        document.getElementById('homeSearchPanel').classList.remove('open');
        document.getElementById('catGrid').classList.remove('hidden-grid');
        document.getElementById('topIssuesSection').style.display = '';
      }
    }, 200);
  });
}

function setupHomeSearchFilterChips() {
  document.getElementById('homeSearchFilterChips').addEventListener('click', e => {
    const chip = e.target.closest('.filter-chip');
    if (!chip) return;
    document.querySelectorAll('#homeSearchFilterChips .filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    STATE.searchCat = chip.dataset.cat;
    if (STATE.searchQ) runHomeSearch(STATE.searchQ);
  });
}

async function runHomeSearch(q) {
  STATE.searchQ = q;
  const res = document.getElementById('homeSearchResults');
  const recent = document.getElementById('recentSearches');

  if (!q) {
    res.innerHTML = '';
    res.appendChild(recent);
    renderRecentSearches();
    return;
  }

  STATE.recentSearches = [q, ...STATE.recentSearches.filter(s => s !== q)].slice(0, 8);
  localStorage.setItem('recentSearches', JSON.stringify(STATE.recentSearches));

  const params = new URLSearchParams({ category: STATE.searchCat, search: q, starred: '0', unread: '0', offset: 0 });
  const items = await fetch(`/api/news?${params}`).then(r => r.json());

  res.innerHTML = '';
  if (!items.length) {
    res.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-title">"${esc(q)}" 검색 결과 없음</div>
      <div class="empty-sub">다른 키워드로 검색해보세요</div>
    </div>`;
    return;
  }
  items.forEach(item => res.appendChild(makeCard(item)));
}

function clearHomeSearch() {
  const inp = document.getElementById('homeSearchInput');
  inp.value = '';
  document.getElementById('homeClearBtn').classList.remove('visible');
  STATE.searchQ = '';
  document.getElementById('homeSearchPanel').classList.remove('open');
  document.getElementById('catGrid').classList.remove('hidden-grid');
  document.getElementById('topIssuesSection').style.display = '';
}

function renderRecentSearches() {
  const chips = document.getElementById('recentChips');
  if (!chips) return;
  chips.innerHTML = STATE.recentSearches.length
    ? STATE.recentSearches.map(s => `
        <div class="recent-chip" onclick="applyRecent('${esc(s)}')">${esc(s)}</div>`).join('')
    : '<span style="font-size:13px;color:var(--text3)">최근 검색어 없음</span>';
}

function applyRecent(q) {
  const inp = document.getElementById('homeSearchInput');
  inp.value = q;
  document.getElementById('homeClearBtn').classList.add('visible');
  document.getElementById('homeSearchPanel').classList.add('open');
  document.getElementById('catGrid').classList.add('hidden-grid');
  runHomeSearch(q);
}

// ── 분석 ───────────────────────────────────
async function loadAnalysis() {
  const body = document.getElementById('analysisBody');
  try {
    const d = await fetch('/api/stats').then(r => r.json());
    const cats = [
      { key: '산업 뉴스',      cls: 'industry', label: '산업 뉴스' },
      { key: 'KARA 주요이벤트', cls: 'kara',     label: 'KARA 이벤트' },
      { key: '국내외 공고',    cls: 'announce',  label: '국내외 공고' },
      { key: '업계 행사',      cls: 'event',     label: '업계 행사' },
      { key: '국제 동향',      cls: 'intl',      label: '국제 동향' },
    ];
    const catCounts = {};
    (d.by_category || []).forEach(c => { catCounts[c.category] = c.cnt; });
    const total = d.total || 1;
    const unread = d.unread || 0;

    body.innerHTML = `
      <div class="analysis-summary">
        <div class="analysis-summary-card">
          <div class="analysis-summary-num">${total}</div>
          <div class="analysis-summary-label">전체 기사</div>
        </div>
        <div class="analysis-summary-card accent-red">
          <div class="analysis-summary-num">${unread}</div>
          <div class="analysis-summary-label">읽지 않음</div>
        </div>
        <div class="analysis-summary-card">
          <div class="analysis-summary-num">${total - unread}</div>
          <div class="analysis-summary-label">읽은 기사</div>
        </div>
      </div>
      <div class="analysis-section-title">카테고리별 현황</div>
      <div class="analysis-cat-list">
        ${cats.map(c => {
          const cnt = catCounts[c.key] || 0;
          const pct = total ? Math.round(cnt / total * 100) : 0;
          return `<div class="analysis-cat-row">
            <div class="analysis-cat-dot cat-dot-${c.cls}"></div>
            <div class="analysis-cat-name">${c.label}</div>
            <div class="analysis-bar-wrap">
              <div class="analysis-bar cat-bar-${c.cls}" style="width:${pct}%"></div>
            </div>
            <div class="analysis-cat-cnt">${cnt}건</div>
          </div>`;
        }).join('')}
      </div>
      <div class="analysis-section-title">최근 수집</div>
      <div class="analysis-collect-info">
        <div class="analysis-info-row">
          <span>마지막 수집</span>
          <span>${d.last_collect ? (d.last_collect.run_at || '').slice(0,16) : '없음'}</span>
        </div>
        <div class="analysis-info-row">
          <span>이번 수집 추가</span>
          <span>${d.last_collect ? '+' + d.last_collect.count_added + '건' : '—'}</span>
        </div>
        <div class="analysis-info-row">
          <span>수집 주기</span>
          <span>매일 오전 05:00</span>
        </div>
      </div>`;
  } catch(e) {
    body.innerHTML = `<div class="empty-state"><div class="empty-icon">📊</div><div class="empty-title">통계를 불러올 수 없습니다</div></div>`;
  }
}

// ── 별/읽음 ───────────────────────────────
async function toggleStar(id, btn) {
  await fetch(`/api/star/${id}`, { method: 'POST' });
  const isOn = btn.classList.contains('on');
  btn.classList.toggle('on', !isOn);
  btn.textContent = isOn ? '☆' : '★';
  showToast(isOn ? '즐겨찾기 해제' : '즐겨찾기에 저장됨');
  loadStats();
}

async function markAllReadGlobal() {
  await fetch('/api/read_all', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: '전체' }) });
  showToast('전체 읽음 처리 완료');
  loadFeed();
  loadStats();
}

function toggleNotif(el) {
  if (el.checked && 'Notification' in window) {
    Notification.requestPermission();
  }
  savePref('notif', el.checked);
}

function savePref(key, val) {
  STATE.prefs[key] = val;
  localStorage.setItem('prefs', JSON.stringify(STATE.prefs));
}

// ── 토스트 ────────────────────────────────
let toastTimer;
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2500);
}

// ── 유틸 ──────────────────────────────────
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ESC 키로 닫기 (상세 → 카테고리 순서로)
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (document.getElementById('detailOverlay').classList.contains('open')) closeDetail();
  else if (document.getElementById('categoryOverlay').classList.contains('open')) closeCategory();
});
// 안드로이드 뒤로가기
window.addEventListener('popstate', () => {
  if (document.getElementById('detailOverlay').classList.contains('open')) closeDetail();
  else if (document.getElementById('categoryOverlay').classList.contains('open')) closeCategory();
});
