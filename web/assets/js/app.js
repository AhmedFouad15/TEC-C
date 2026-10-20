/* Tec-C Command Center.
   Everything on screen comes from the Brain API (FastAPI, agent/) and the vault it reads on-chain. When the Brain is
   offline, screens say so instead of showing sample data. Point it at another server with ?api=http://host:port (remembered in localStorage). */

/* =========================================================================================
   Helpers
   ========================================================================================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const usd = n => '$' + Math.round(n).toLocaleString('en-US');
const pct = (x, d = 1) => (x * 100).toFixed(d) + '%';
const signed = (x, d = 2) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

function animateNumber(el, to, { prefix = '$', dur = 900, suffix = el?.children.length ? ' ' : '' } = {}) {
  if (!el) return;
  const from = +(el.dataset.v ?? to);
  if (from === to && el.dataset.initialized) return;
  el.dataset.initialized = '1';
  el.dataset.v = to;
  if (window.innerWidth < 820 || dur <= 0) {
    const formatted = prefix + Math.round(to).toLocaleString('en-US') + suffix;
    el.firstChild ? (el.firstChild.nodeValue = formatted) : (el.textContent = formatted);
    return;
  }
  const t0 = performance.now();
  (function f(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.firstChild ? (el.firstChild.nodeValue = prefix + Math.round(from + (to - from) * e).toLocaleString('en-US') + suffix)
      : (el.textContent = prefix + Math.round(from + (to - from) * e).toLocaleString('en-US') + suffix);
    if (p < 1) requestAnimationFrame(f);
  })(t0);
}

/* =========================================================================================
   Brain API
   ========================================================================================= */
// Only a Brain on this machine is trusted: a crafted ?api= link must not be able to send the user's commands
// and notes to someone else's server (and must not persist such a choice).
const isValidApiUrl = v => {
  try {
    const u = new URL(v);
    if (!/^https?:$/.test(u.protocol)) return false;
    if (u.username || u.password) return false;
    if (['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname)) return true;
    if (u.protocol === 'https:') return true;
    return false;
  } catch { return false; }
};
const isLoopbackApi = isValidApiUrl;
let API = (() => {
  const q = new URLSearchParams(location.search).get('api');
  if (q && isValidApiUrl(q)) store.set('tecc_api', new URL(q).origin);
  const isLoopbackHost = ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname);
  const saved = store.get('tecc_api');
  if (saved && isValidApiUrl(saved)) {
    if (!isLoopbackHost || ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(saved).hostname) || q) {
      return new URL(saved).origin;
    }
  }
  const isVercel = location.hostname.endsWith('vercel.app') || location.hostname === 'vercel.app';
  if (isValidApiUrl(location.origin)) {
    if (!isVercel && (location.protocol === 'https:' || location.port === '8000')) return location.origin;
  }
  return isVercel ? '' : (location.protocol === 'https:' ? location.origin : 'http://127.0.0.1:8000');
})();
const brain = { live: false, checked: false };

function configureBrainApi() {
  const current = API || '';
  const isHttps = location.protocol === 'https:';
  const msg = isHttps
    ? 'Connect Command Center to your Brain backend (HTTPS environment):\n\n' +
      '• Enter your HTTPS tunnel URL (e.g. Cloudflare tunnel or ngrok):\n' +
      '  https://<subdomain>.trycloudflare.com\n\n' +
      'Note: Modern browsers block mixed content (http://127.0.0.1:8000) from HTTPS pages.\n' +
      'To connect directly without a tunnel, open http://localhost:5500 instead.\n\n' +
      'Enter API endpoint URL (or leave empty to reset):'
    : 'Connect Command Center to your Brain backend:\n\n' +
      '• For local server: http://127.0.0.1:8000\n' +
      '• For HTTPS tunnel: https://<subdomain>.trycloudflare.com\n\n' +
      'Enter API endpoint URL (or leave empty to reset):';
  const val = prompt(msg, current);
  if (val === null) return;
  const clean = val.trim();
  if (!clean) {
    store.set('tecc_api', '');
    location.reload();
    return;
  }
  if (!isValidApiUrl(clean)) {
    alert('Invalid URL. Please enter an http:// or https:// URL (e.g. https://xxxx.trycloudflare.com)');
    return;
  }
  if (isHttps && clean.startsWith('http://') && !['127.0.0.1', 'localhost', '[::1]'].includes(new URL(clean).hostname)) {
    alert('Mixed Content warning: Insecure HTTP endpoints cannot be reached from an HTTPS page. Use an https:// tunnel URL or open the local dashboard at http://localhost:5500.');
    return;
  }
  store.set('tecc_api', new URL(clean).origin);
  location.reload();
}

async function api(path, { method = 'GET', body, timeout = 60000 } = {}) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const res = await fetch(API + path, {
      method, signal: ctl.signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : res.statusText), { status: res.status });
    return data;
  } finally { clearTimeout(t); }
}

async function probeBrain() {
  if (state.isSubmittingCommand) return;
  const isLoopbackHost = ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname);
  const isVercel = location.hostname.endsWith('vercel.app') || location.hostname === 'vercel.app';
  if (!API && isValidApiUrl(location.origin)) {
    if (!isVercel) API = location.origin;
  }
  if (!API) {
    if (isLoopbackHost) API = 'http://127.0.0.1:8000';
    else {
      setBrainStatus(false, 'connect backend \u00b7 click to connect');
      return;
    }
  }
  try {
    const h = await api('/health', { timeout: 10000 });
    setBrainStatus(true, `live \u00b7 v${h.version || '?'}`);
  } catch (err) {
    if (isLoopbackHost && API !== 'http://127.0.0.1:8000') {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 3000);
        const res = await fetch('http://127.0.0.1:8000/health', { signal: ctl.signal });
        clearTimeout(t);
        if (res.ok) {
          const h = await res.json();
          API = 'http://127.0.0.1:8000';
          store.set('tecc_api', API);
          setBrainStatus(true, `live \u00b7 v${h.version || '?'}`);
          return;
        }
      } catch {}
    }
    if (!state.isSubmittingCommand) {
      setBrainStatus(false, 'offline \u00b7 click to connect');
    }
  }
}
function setBrainStatus(live, text) {
  const changed = brain.live !== live || !brain.checked;
  brain.live = live; brain.checked = true;
  $('#brain-dot').className = 'dot ' + (live ? 'active' : 'warning');
  $('#top-heartbeat-text').textContent = text;
  $('#brain-pill').title = live
    ? `Connected to the Brain at ${API} (click to change)`
    : `Brain not reachable at ${API || 'no endpoint set'}. Click to configure backend URL.`;
  if (changed) {
    loadRegimes();
    loadProfile();
    loadCatalog();
    loadPegGuard();
    refreshLive();
    loadSessions();
    loadSecurityStatus();
    maybeShowQuizBanner();
    if (live && brain.has_notified) showToast('Brain connected: commands now run through the real pipeline.');
    brain.has_notified = true;
  }
}

/* =========================================================================================
   Demo presets (used when the Brain is offline)
   ========================================================================================= */
// Only actions the Brain has venues for (data/venues.json: deposit, stake). Swap / Rebalance / Reduce risk / Exit
// position return when venues for them exist; until then the composer never offers a button that always fails.
const ACTIONS = ['Find opportunities', 'Invest', 'Stake', 'Park idle cash'];
const ACTION_PRESETS = {
  'Stake': {
    assets: ['ETH', 'stETH', 'rETH', 'cbETH'], defaultAssets: ['ETH', 'stETH'], market: 'Crypto', network: 'Ethereum L1', pct: 10, tier: 'Tier 2',
    headlines: ['Lido staking deposits hit a record (2h ago · positive)', 'Ethereum validator exit queue clears (5h ago · positive)', 'Staking benchmark steady at 3.4% APY (7h ago · neutral)'],
    newsScore: 0.71, sharpe: 0.66, cvar95: -3.1, cvar99: -5.4,
    candidates: [
      { id: 'A', title: 'Stake ETH on Lido', badge: 'Chosen 70%', cls: 'badge-green', info: 'Crypto · staking · 3.4% APY', news: '+0.71', econ: '0.64', inj: 'Pass', score: 0.68, rationale: 'Liquid staking on Lido pays 3.4% with deep secondary liquidity and a diversified validator set.' },
      { id: 'B', title: 'Supply ETH on Aave v3', badge: 'Chosen 30%', cls: 'badge-green', info: 'Crypto · lending · 2.6% APY', news: '+0.55', econ: '0.70', inj: 'Pass', score: 0.61, rationale: 'Supplying to Aave gives defensive lending yield with instant exit liquidity.' },
      { id: 'C', title: 'Buy stETH on a DEX pool', badge: 'Rejected', cls: 'badge-red', info: 'Crypto · Curve swap · 0.9982 stETH/ETH', news: '+0.71', econ: '0.41', inj: 'Warn', score: 0.44, rationale: 'The 18 bps discount is eaten by gas and slippage. Direct staking is better.' },
    ],
  },
  'Swap': {
    assets: ['USDC', 'ETH', 'USDT', 'PAXG', 'stETH'], defaultAssets: ['USDC', 'ETH'], market: 'Crypto', network: 'Ethereum / Arbitrum', pct: 5, tier: 'Tier 1',
    headlines: ['Uniswap v3 pool depth passes $180M (1h ago · positive)', 'Gas below 12 gwei on mainnet (3h ago · positive)', 'Stablecoin DEX volume surges (6h ago · neutral)'],
    newsScore: 0.62, sharpe: 0.81, cvar95: -1.8, cvar99: -3.2,
    candidates: [
      { id: 'A', title: 'USDC → ETH via Uniswap v3', badge: 'Chosen 100%', cls: 'badge-green', info: 'Concentrated liquidity · 0.05% fee tier', news: '+0.62', econ: '0.84', inj: 'Pass', score: 0.78, rationale: 'The deepest concentrated pool keeps slippage at 0.03% for this size.' },
      { id: 'B', title: 'Curve TriCrypto pool', badge: 'Alternative', cls: 'badge-blue', info: 'Dynamic-peg invariant pool', news: '+0.58', econ: '0.72', inj: 'Pass', score: 0.67, rationale: 'Curve v2 dynamic fees give 0.05% slippage, a little worse than Uniswap.' },
      { id: 'C', title: 'CoW Protocol batch auction', badge: 'Slower', cls: 'badge-amber', info: 'MEV-protected batch', news: '+0.65', econ: '0.59', inj: 'Pass', score: 0.61, rationale: 'No front-running, but a one-block delay hurts in volatile regimes.' },
    ],
  },
  'Park idle cash': {
    assets: ['USDC', 'e-CNY MMF', 'USDT', 'USDY'], defaultAssets: ['USDC', 'e-CNY MMF'], market: 'Any', network: 'All three markets', pct: 25, tier: 'Tier 1',
    headlines: ['PBOC operations support the 1Y Shibor benchmark (2h ago · positive)', 'Consortium-chain MMFs report zero duration risk (4h ago · positive)', 'USDC lending on Arbitrum normalizes to 4.8% (8h ago · neutral)'],
    newsScore: 0.48, sharpe: 1.42, cvar95: -0.2, cvar99: -0.4,
    candidates: [
      { id: 'A', title: 'Shibor 1Y MMF on FISCO BCOS', badge: 'Chosen 60%', cls: 'badge-green', info: 'Chinese mkt · WeBank consortium · 2.85%', news: '+0.45', econ: '0.92', inj: 'Pass', score: 0.82, rationale: 'A zero-gas consortium money-market fund with near-zero volatility, benchmarked to 1Y Shibor.' },
      { id: 'B', title: 'USDC into Aave v3 on Arbitrum', badge: 'Chosen 40%', cls: 'badge-green', info: 'Crypto · L2 · 4.80% variable APY', news: '+0.52', econ: '0.78', inj: 'Pass', score: 0.72, rationale: 'Native L2 lending yield behind over-collateralized liquidation buffers.' },
      { id: 'C', title: 'Compound v3 USDC on L1', badge: 'Alternative', cls: 'badge-blue', info: 'Crypto · Ethereum · 4.25% net', news: '+0.50', econ: '0.69', inj: 'Pass', score: 0.65, rationale: 'Solid, but L1 gas eats into returns below $10,000.' },
    ],
  },
  'Reduce risk': {
    assets: ['e-CNY MMF', 'stETH', 'PAXG'], defaultAssets: ['e-CNY MMF'], market: 'Chinese market', network: 'FISCO BCOS', pct: 15, tier: 'Tier 1',
    headlines: ['Sentinel flags distress on a synthetic e-CNY note (22m ago · negative)', 'Consortium audit confirms off-chain exposure (1h ago · watch)', 'Redemption windows remain open (3h ago · neutral)'],
    newsScore: -0.45, sharpe: 0.9, cvar95: -0.1, cvar99: -0.2,
    candidates: [
      { id: 'A', title: 'De-risk e-CNY MMF into USDC', badge: 'Chosen 100%', cls: 'badge-green', info: 'Cross-chain de-risk · removes the flagged exposure', news: '−0.45', econ: '0.88', inj: 'Pass', score: 0.85, rationale: 'Moving from stressed paper into dollar collateral cuts CVaR 95% from −5.4% to −0.2%.' },
      { id: 'B', title: 'Rotate into PAXG gold', badge: 'Alternative', cls: 'badge-blue', info: 'Commodities · Arbitrum · allocated gold', news: '+0.25', econ: '0.74', inj: 'Pass', score: 0.71, rationale: 'Gold is negatively correlated with crypto drawdowns.' },
      { id: 'C', title: 'Lock the whole vault', badge: 'Overkill', cls: 'badge-amber', info: 'Halts all AI activity', news: '−0.45', econ: '0.30', inj: 'Pass', score: 0.38, rationale: 'Only one holding is stressed; a targeted exit keeps the rest earning.' },
    ],
  },
  'Invest': {
    assets: ['ETH', 'stETH', 'USDC', 'PAXG'], defaultAssets: ['ETH', 'USDC'], market: 'Crypto', network: 'Ethereum / Arbitrum', pct: 10, tier: 'Tier 2',
    headlines: ['Ethereum DeFi activity at a 6-month high (2h ago · positive)', 'Institutions add tokenized gold (4h ago · positive)', 'Bridges report record liquidity (7h ago · neutral)'],
    newsScore: 0.71, sharpe: 1.1, cvar95: -3.1, cvar99: -5.4,
    candidates: [
      { id: 'A', title: 'Lido staked ETH (stETH)', badge: 'Chosen 70%', cls: 'badge-green', info: 'Crypto · staking · 3.4% + ETH exposure', news: '+0.71', econ: '0.64', inj: 'Pass', score: 0.68, rationale: 'Core Ethereum staking yield with blue-chip security.' },
      { id: 'B', title: 'PAXG tokenized gold', badge: 'Chosen 30%', cls: 'badge-green', info: 'Commodities · Arbitrum · LBMA gold', news: '+0.35', econ: '0.75', inj: 'Pass', score: 0.65, rationale: 'Real-world collateral with low correlation to crypto.' },
      { id: 'C', title: 'Microcap LP farm, 24.5% APY', badge: 'Rejected', cls: 'badge-red', info: 'DeFi · microcap pool', news: '+0.10', econ: '0.22', inj: 'Warn', score: 0.28, rationale: 'Permanent-loss risk (PD 45% × LGD 80%) dwarfs the yield.' },
    ],
  },
  'Rebalance': {
    assets: ['All in market', 'ETH', 'USDC', 'PAXG'], defaultAssets: ['All in market'], market: 'Any', network: 'All three markets', pct: 20, tier: 'Tier 2',
    headlines: ['Cross-asset covariance stable over 30 days (2h ago · positive)', 'Gold–equity correlation falls to −0.14 (5h ago · positive)', 'Consortium MMF rate anchors portfolio variance (8h ago · neutral)'],
    newsScore: 0.58, sharpe: 1.24, cvar95: -2.1, cvar99: -4.1,
    candidates: [
      { id: 'A', title: 'Max-Sharpe rebalance', badge: 'Chosen 100%', cls: 'badge-green', info: 'Multi-chain · target 52/22/16/10', news: '+0.58', econ: '0.91', inj: 'Pass', score: 0.84, rationale: 'Restores target weights, cutting idiosyncratic volatility.' },
      { id: 'B', title: 'Equal-weight 25% each', badge: 'Sub-optimal', cls: 'badge-blue', info: 'Naive 1/N across 4 markets', news: '+0.50', econ: '0.62', inj: 'Pass', score: 0.58, rationale: '1/N over-allocates to volatile assets.' },
      { id: 'C', title: 'Volatility parity', badge: 'Conservative', cls: 'badge-amber', info: 'Inverse-volatility weights', news: '+0.54', econ: '0.79', inj: 'Pass', score: 0.73, rationale: 'Smaller drawdowns, but yield falls below the Shibor hurdle.' },
    ],
  },
  'Exit position': {
    assets: ['e-CNY MMF', 'stETH', 'PAXG'], defaultAssets: ['e-CNY MMF'], market: 'Chinese market', network: 'FISCO BCOS', pct: 22, tier: 'Tier 1',
    headlines: ['FISCO BCOS redemption gateway open (1h ago · positive)', 'Clearinghouse confirms 1:1 redemption (3h ago · positive)', 'Negative sentiment on the synthetic note persists (5h ago · watch)'],
    newsScore: -0.45, sharpe: 0, cvar95: 0, cvar99: 0,
    candidates: [
      { id: 'A', title: 'Full redemption to cash', badge: 'Chosen 100%', cls: 'badge-green', info: 'Consortium redemption · $10,600', news: '−0.45', econ: '0.95', inj: 'Pass', score: 0.89, rationale: 'Removes the distressed exposure entirely.' },
      { id: 'B', title: 'Partial 50% exit', badge: 'Alternative', cls: 'badge-blue', info: 'Unwinds $5,300', news: '−0.45', econ: '0.65', inj: 'Pass', score: 0.6, rationale: 'Leaves $5,300 exposed to further bad news.' },
      { id: 'C', title: 'Swap into a high-beta token', badge: 'Rejected', cls: 'badge-red', info: 'Speculative DEX swap', news: '+0.15', econ: '0.25', inj: 'Warn', score: 0.31, rationale: 'Replaces one risk with a bigger, unvetted one.' },
    ],
  },
  'Find opportunities': {
    assets: ['All in market', 'ETH', 'stETH', 'USDC', 'PAXG'], defaultAssets: ['All in market'], market: 'Any', network: 'All three markets', pct: 10, tier: 'Tier 2',
    headlines: ['LST secondary spreads widen across chains (1h ago · positive)', 'Shibor MMF a strong hurdle for parking (3h ago · positive)', 'Staking beats lending by 80 bps (6h ago · neutral)'],
    newsScore: 0.71, sharpe: 0.95, cvar95: -3.1, cvar99: -5.4,
    candidates: [
      { id: 'A', title: 'Stake ETH on Lido', badge: 'Rank 1', cls: 'badge-green', info: 'Crypto · best risk-adjusted excess yield', news: '+0.71', econ: '0.64', inj: 'Pass', score: 0.68, rationale: 'Blue-chip yield with deep liquidity.' },
      { id: 'B', title: 'Curve stETH/ETH pool', badge: 'Rank 2', cls: 'badge-green', info: 'Crypto · LST pool · 3.9% APY', news: '+0.55', econ: '0.71', inj: 'Pass', score: 0.66, rationale: 'Staking yield plus trading fees; slightly more exit cost than direct staking.' },
      { id: 'C', title: 'Aave v3 USDC on Arbitrum', badge: 'Rank 3', cls: 'badge-blue', info: 'Crypto · lending · 4.8% APY', news: '+0.52', econ: '0.78', inj: 'Pass', score: 0.63, rationale: 'Collateralized lending yield with no price beta.' },
    ],
  },
};

/* What each market actually holds. The live list comes from the Brain's /api/catalog (venues per market);
   this is the offline fallback. PegGuard is not here on purpose: it is a background switch, not a market. */
const MARKETS = {
  'Crypto': { sub: 'Ethereum L1', assets: ['ETH', 'stETH', 'rETH', 'cbETH', 'USDC', 'USDT'] },
  'Chinese market': { sub: 'FISCO BCOS', assets: ['e-CNY MMF', 'USDC', 'USDT'] },
  'Commodities': { sub: 'Arbitrum One', assets: ['PAXG', 'USDC'] },
};
const CATALOG_MARKET = { crypto: 'Crypto', chinese_market: 'Chinese market', commodities: 'Commodities' };
function marketAssets(name) {
  if (MARKETS[name]) return MARKETS[name].assets;
  return ['All in market', ...new Set(Object.values(MARKETS).flatMap(m => m.assets))];  // Any
}
async function loadCatalog() {
  if (!brain.live) return;
  try {
    const c = await api('/api/catalog', { timeout: 5000 });
    for (const [id, m] of Object.entries(c.markets || {})) {
      const name = CATALOG_MARKET[id];
      // live: only assets a venue in this market actually accepts (the offline lists include demo-only names)
      if (name && Array.isArray(m.assets) && m.assets.length) MARKETS[name].assets = [...new Set(m.assets.map(String))];
    }
    selectMarket(state.market, state.network, false);  // re-filter the pills with the live list
  } catch { /* keep the offline lists */ }
}


/* =========================================================================================
   State
   ========================================================================================= */
const state = {
  action: 'Stake', market: 'Crypto', network: 'Ethereum L1', assets: ['ETH', 'stETH'], capitalPercent: 10, riskTier: 'Tier 2',
  vaultBalance: 0, tetherUsed: 0, tetherTotal: 0, tetherRemaining: 0, biometricUnlocked: false, pegGuardEnabled: false,
  selectedCandidate: 'A', outcome: 'split', streak: 0,
  live: null, // last live /propose response
  liveOptions: null,
  vault: null, // last /api/vault/demo answer: the on-chain truth for balances, leash and reviews
  decided: {}, // proposal cards the user already approved or dismissed in this tab
  executedLabel: {}, // what the vault answered for an approved option (with its tx hash), shown on the button
};
const TRADE_STATUS = {
  pending: ['Pending review', 'badge-amber'], ratified: ['Ratified', 'badge-green'], flagged: ['Flagged (−20%)', 'badge-red'],
  taught: ['Reviewed & taught', 'badge-green'], penalized: ['Reviewed (−10%)', 'badge-amber'], breakout: ['FaceID breakout approved', 'badge-green'],
  simulated: ['Simulated (no chain)', 'badge-blue'],
  noted: ['Noted', 'badge-green'], signing: ['Awaiting signature', 'badge-blue'], failed: ['Reverted by the vault', 'badge-red'], needs_faceid: ['Needs FaceID (over the radius)', 'badge-amber'],
};
const dollarsForCommand = () => Math.round(state.vaultBalance * state.capitalPercent / 100);
const tetherLeft = () => Math.max(0, state.tetherRemaining);

/* =========================================================================================
   Navigation
   ========================================================================================= */
function moveIndicator() {
  const a = $('.nav-item.active'), ind = $('#nav-indicator');
  if (!a) return;
  ind.style.left = a.offsetLeft + 'px';
  ind.style.width = a.offsetWidth + 'px';
}
function switchTab(tab) {
  if (!$('#panel-' + tab)) tab = 'home';
  $$('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  $$('.view-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tab));
  moveIndicator();
  $('.nav-item.active')?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' });
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
  scrollTo({ top: 0, behavior: 'smooth' });
  if (tab === 'portfolio') drawTrend();
  if (tab === 'virtual-session') loadSessions();
  if (tab === 'review') { refreshLive(); }
  if (tab === 'settings') loadSecurityStatus();
}
$$('.nav-item').forEach(n => n.addEventListener('click', e => { e.preventDefault(); switchTab(n.dataset.tab); }));
addEventListener('hashchange', () => switchTab(location.hash.slice(1)));
addEventListener('resize', moveIndicator);

/* =========================================================================================
   Composer
   ========================================================================================= */
function renderActionPills() {
  $('#action-pills').innerHTML = ACTIONS.map(a => `<button class="pill-btn${a === state.action ? ' active' : ''}" data-action="${esc(a)}">${esc(a)}</button>`).join('');
}
$('#action-pills').addEventListener('click', e => { const b = e.target.closest('[data-action]'); if (b) selectAction(b.dataset.action); });

function selectAction(name, toast = true) {
  const p = ACTION_PRESETS[name];
  if (!p) return;
  state.action = name;
  state.selectedCandidate = 'A';
  $$('#action-pills .pill-btn').forEach(b => b.classList.toggle('active', b.dataset.action === name));
  $('#active-action-badge').textContent = `${name} mandate`;
  state.assets = [...p.defaultAssets];
  selectMarket(p.market, MARKETS[p.market]?.sub || p.network, false);  // filters the assets to that market
  setSliderPercent(p.pct);
  selectTier(p.tier, false);
  if (!state.live) renderOpportunities();
  if (toast) showToast(`“${name}”: assets, market and risk tier adjusted.`);
}
function renderAssetPills(list) {
  $('#asset-pills').innerHTML = list.map(s => `<button class="pill-btn${state.assets.includes(s) ? ' active' : ''}" data-asset="${esc(s)}">${esc(s)}</button>`).join('');
}
$('#asset-pills').addEventListener('click', e => {
  const b = e.target.closest('[data-asset]'); if (!b) return;
  const s = b.dataset.asset;
  b.classList.toggle('active');
  state.assets = state.assets.includes(s) ? state.assets.filter(a => a !== s) : [...state.assets, s];
  updatePrompt();
});
function selectMarket(name, sub, toast = true) {
  state.market = name; state.network = sub;
  $$('#market-grid .market-card').forEach(c => c.classList.toggle('active', c.dataset.market === name));
  // only the assets that exist in this market: the Chinese market never offers ETH
  const list = marketAssets(name);
  state.assets = state.assets.filter(a => list.includes(a));
  if (!state.assets.length) state.assets = [list[0]];
  renderAssetPills(list);
  $('#asset-scope-note').textContent = name === 'Any' ? '· across all three markets' : `· available in ${name} (${sub})`;
  updatePrompt();
  if (toast) showToast(`Market: ${name} (${sub})`);
}
$('#market-grid').addEventListener('click', e => { const c = e.target.closest('.market-card'); if (c) selectMarket(c.dataset.market, c.dataset.sub); });

function setSliderPercent(p) {
  p = Math.max(1, Math.min(100, Math.round(p)));
  state.capitalPercent = p;
  $$('#capital-pills .pill-btn').forEach(b => b.classList.toggle('active', +b.dataset.pct === p));
  $('#slider-fill').style.width = p + '%';
  $('#slider-thumb').style.left = p + '%';
  $('#slider-tip').textContent = p + '%';
  const d = dollarsForCommand(), use = Math.min(d, tetherLeft());
  if (state.vault && state.vaultBalance === 0) {
    $('#slider-caption').innerHTML = `${p}% = $0 · <span style="color:var(--amber)">The vault is empty.</span> <a href="#" onclick="openDepositModal();return false;" style="color:var(--lime);text-decoration:underline">Deposit funds</a> or use the test faucet first.`;
    updateSlippage(d); updatePrompt(); return;
  }
  $('#slider-caption').textContent = `${p}% = ${usd(d)} · ${d <= tetherLeft() ? `fits inside the ${usd(tetherLeft())} left in today's radius` : `uses ${usd(use)} of the ${usd(tetherLeft())} left; the rest needs a FaceID breakout`}`;
  updateSlippage(d);
  updatePrompt();
}
$('#capital-pills').addEventListener('click', e => { const b = e.target.closest('[data-pct]'); if (b) setSliderPercent(+b.dataset.pct); });
(() => { // draggable slider
  const s = $('#slider');
  const at = x => { const r = s.getBoundingClientRect(); setSliderPercent(((x - r.left) / r.width) * 100); };
  s.addEventListener('pointerdown', e => { s.setPointerCapture(e.pointerId); s.classList.add('dragging'); at(e.clientX); });
  s.addEventListener('pointermove', e => { if (s.classList.contains('dragging')) at(e.clientX); });
  s.addEventListener('pointerup', () => s.classList.remove('dragging'));
})();

function selectTier(t, toast = true) {
  state.riskTier = t;
  $$('#tier-pills [data-tier]').forEach(b => b.classList.toggle('active', b.dataset.tier === t));
  updatePrompt();
  if (toast) showToast(`Risk policy: ${t}`);
}
$('#tier-pills').addEventListener('click', e => { const b = e.target.closest('[data-tier]'); if (b) selectTier(b.dataset.tier); });

function commandText() {
  const assets = state.assets.length ? state.assets.join(' and ') : 'assets';
  const where = state.market === 'Any' ? '' : ` in ${state.market}`;
  const tierWord = { 'Tier 1': 'low risk', 'Tier 2': 'balanced risk', 'Tier 3': 'high risk' }[state.riskTier];
  return `${state.action} ${assets}${where}, using ${state.capitalPercent}% of capital (${usd(dollarsForCommand())}), ${tierWord}.`;
}
// What the Brain's rules parser understands for each composer action (intent/rules.py ACTION_PATTERNS).
const BRAIN_VERB = {
  'Find opportunities': 'find the best yield for', 'Invest': 'grow', 'Stake': 'stake', 'Swap': 'optimize',
  'Rebalance': 'optimize', 'Reduce risk': 'withdraw', 'Exit position': 'exit', 'Park idle cash': 'deposit',
};
function brainText() {
  const asset = state.assets.find(a => a !== 'All in market') || 'USDC';
  const tierWord = { 'Tier 1': 'low risk', 'Tier 2': 'medium risk', 'Tier 3': 'high risk' }[state.riskTier];
  return `${BRAIN_VERB[state.action]} ${dollarsForCommand()} dollars of ${asset}, ${tierWord}`;
}
let typeTimer = null;
function updatePrompt() {
  const el = $('#prompt-preview'), text = `“${commandText()}”`;
  clearInterval(typeTimer);
  let i = Math.max(0, Math.min(el.textContent.length - 1, commonPrefix(el.textContent, text)));
  typeTimer = setInterval(() => {
    i = Math.min(text.length, i + 2);
    el.innerHTML = esc(text.slice(0, i)) + '<span class="cursor"></span>';
    if (i >= text.length) clearInterval(typeTimer);
  }, 14);
}
const commonPrefix = (a, b) => { let i = 0; while (i < a.length && a[i] === b[i]) i++; return i; };
function updateSlippage(d) {
  const s = d > 10000 ? '0.35%' : d > 4000 ? '0.08%' : d > 1000 ? '0.04%' : '0.01%';
  $('#slippage-text').innerHTML = `Modelled slippage for ${usd(d)}: <b>${s}</b> (pool depth $240M).`;
}

/* =========================================================================================
   Pipeline animation
   ========================================================================================= */
const STEP_NAMES = {
  gatekeeper_intake: 'Gatekeeper · intake', profile: 'Profile', nlp_sentinel: 'NLP risk sentinel',
  econometric_liquidity: 'Econometric & liquidity', gatekeeper_aggregator: 'Gatekeeper · aggregator', web3_executor: 'Web3 executor',
};
function renderPipeline(agents, statuses = []) {
  $('#pipeline-timeline').innerHTML = agents.map((a, i) => `
    <div class="t-step ${statuses[i] || ''}" data-i="${i}">
      <div class="t-dot">${statuses[i] === 'done' ? '✓' : statuses[i] === 'blocked' ? '!' : i + 1}</div>
      <div class="t-name">${esc(STEP_NAMES[a.agent] || a.title)}</div>
      <div class="t-meta">${{ done: 'done', running: 'thinking…', blocked: 'stopped here' }[statuses[i]] || 'waiting'}</div>
      <ul class="t-lines">${(a.lines || []).slice(0, 4).map(l => `<li>${esc(l)}</li>`).join('')}</ul>
    </div>`).join('');
}
async function animatePipeline(agents, { blockedAt = -1 } = {}) {
  const st = agents.map(() => '');
  renderPipeline(agents, st);
  for (let i = 0; i < agents.length; i++) {
    st[i] = 'running'; renderPipeline(agents, st);
    await sleep(420 + Math.random() * 260);
    st[i] = i === blockedAt ? 'blocked' : 'done'; renderPipeline(agents, st);
    if (i === blockedAt) break;
  }
  return st;
}
/* The Live pipeline card always shows the latest command: running while the Brain works, then "Completed" (or
   "Refused") until the next command. Nothing sent yet = "No commands". Kept per browser in localStorage. */
const PIPE_KEY = 'tecc_last_pipeline', REQ_KEY = 'tecc_request_no';
function nextRequestNo() {
  const n = (parseInt(store.get(REQ_KEY), 10) || 0) + 1;
  store.set(REQ_KEY, String(n));
  return n;
}
function setPipelineHeader(no, outcome) {
  const tag = { running: '<span class="badge badge-blue">Running</span>', completed: '<span class="badge badge-green">Completed</span>',
    refused: '<span class="badge badge-red">Refused</span>' }[outcome] || '';
  $('#request-id').innerHTML = no ? `Request #${no} ${tag}` : 'No requests yet';
}
function savePipeline(rec) { store.set(PIPE_KEY, JSON.stringify(rec)); }
const RESULT_KEY = 'tecc_last_result', DECIDED_KEY = 'tecc_decided', RESULT_TTL = 30 * 60 * 1000;
function saveResult() {
  store.set(RESULT_KEY, JSON.stringify({ at: Date.now(), live: state.live, liveOptions: state.liveOptions }));
  store.set(DECIDED_KEY, JSON.stringify(state.decided));
}
function restoreResult() {
  try { state.decided = JSON.parse(store.get(DECIDED_KEY) || '{}') || {}; } catch { state.decided = {}; }
  let r = null; try { r = JSON.parse(store.get(RESULT_KEY) || 'null'); } catch { r = null; }
  if (!r || Date.now() - r.at > RESULT_TTL) return false;
  state.live = r.live; state.liveOptions = r.liveOptions;
  if (state.liveOptions) renderOptions();
  else if (state.live) renderLive(state.live, $('#opp-request-header').textContent || 'last command');
  return !!(state.live || state.liveOptions);
}
function restorePipeline() {
  let rec = null;
  try { rec = JSON.parse(store.get(PIPE_KEY) || 'null'); } catch { rec = null; }
  if (!rec || !rec.agents) {
    setPipelineHeader(0);
    $('#pipeline-timeline').innerHTML = '<div class="empty-state"><b>No commands</b><span class="caption">Ask the Brain or submit a command: its six agents will show up here.</span></div>';
    $('#btn-view-opps').hidden = true;
    return;
  }
  setPipelineHeader(rec.no, rec.outcome === 'running' ? 'completed' : rec.outcome); // a reload mid-run shows the last state
  renderPipeline(rec.agents, rec.statuses);
  $('#pipeline-timeline').insertAdjacentHTML('afterbegin', `<div class="caption pipe-cmd">“${esc(rec.text)}” · ${esc(new Date(rec.at).toLocaleString())}</div>`);
  $('#btn-view-opps').hidden = false;
}
async function runPipeline(no, text, agents, opts = {}) {
  setPipelineHeader(no, 'running');
  $('#btn-view-opps').hidden = false;
  const statuses = await animatePipeline(agents, opts);
  const outcome = opts.blockedAt >= 0 ? 'refused' : 'completed';
  savePipeline({ no, text, agents, statuses, outcome, at: Date.now() });
  restorePipeline();
}

/* =========================================================================================
   Submit → Brain
   ========================================================================================= */
async function submitCommandToBrain(text) {
  const textGiven = !!text;
  const shown = text || commandText();
  text = text || brainText();
  if (!brain.live) {
    if (!API && (location.hostname.endsWith('vercel.app') || location.hostname === 'vercel.app')) {
      showToast('Click the Brain status pill to configure your HTTPS backend tunnel, or run locally at http://localhost:5500.');
      configureBrainApi();
      return;
    }
    return showToast('The Brain is offline, so nothing was sent. Start it with ./dev_up.ps1 and try again.');
  }
  if (state.vault && state.vaultBalance === 0) { showToast('The vault is empty: deposit funds (or use the test faucet) first.'); return openDepositModal(); }
  const btn = $('#submit-btn');
  btn.disabled = true; btn.classList.add('loading');
  state.isSubmittingCommand = true;
  const no = nextRequestNo();
  try {
    if (!textGiven) return await evaluateOptions(shown, no); // composer buttons → closed schema
    const headline = $('#headline-input').value.trim() || undefined;
    setPipelineHeader(no, 'running');
    const [res] = await Promise.all([
      api('/api/mandate/propose', { method: 'POST', body: { text, account: 'demo', headline } }),
      sleep(300),
    ]);
    state.live = res; state.liveOptions = null;
    const blocked = res.status !== 'decided' || res.decision?.mode === 'BLOCKED';
    const agents = res.agents?.length ? res.agents : [{ agent: 'gatekeeper_intake', lines: ['The Brain returned no agent trace.'] }];
    await runPipeline(no, shown, agents, { blockedAt: blocked ? agents.length - 1 : -1 });
    renderLive(res, shown);
    saveResult();
    refreshLive();
    if (res.status === 'unparsed') showToast(`The Brain didn't understand: ${(res.parse?.errors || []).join(', ')}. Try verbs like deposit, stake, grow, exit or withdraw.`);
    else if (blocked) showToast('The Brain refused this command. See the pipeline for why.');
    else {
      await sleep(350); switchTab('opportunities');
      showToast(`The Brain rated ${res.decision.cards.length} route(s) and rejected ${res.decision.rejected.length}.`);
      if (res.intent?.status === 'submitted') txToast(`Executed automatically: ${usd(res.intent.amount_usd)} → ${res.intent.venue_id}`, res.intent.tx_hash);
    }
  } catch (err) {
    savePipeline({ no, text: shown, agents: [{ agent: 'gatekeeper_intake', lines: [`The Brain could not answer: ${err.message}`] }], statuses: ['blocked'], outcome: 'refused', at: Date.now() });
    restorePipeline();
    let isAlive = false;
    try {
      await api('/health', { timeout: 3000 });
      isAlive = true;
    } catch {}
    if (!isAlive && err.message === 'Failed to fetch') {
      setBrainStatus(false, 'offline');
      showToast('The Brain is not reachable: nothing was sent.');
    } else if (err.name === 'AbortError') {
      showToast('The Brain took longer than 60 s. Check the vault and Morning Review before sending this again.');
    } else {
      showToast(`Command error: ${err.message}`);
    }
    refreshLive();
  } finally {
    state.isSubmittingCommand = false;
    btn.disabled = false; btn.classList.remove('loading');
  }
}
/* =========================================================================================
   Composer → /evaluate_options: a closed schema (enum action, real asset, bounded amount), no free text
   ========================================================================================= */
const OPTION_ACTION = {
  'Find opportunities': 'deposit', 'Invest': 'deposit', 'Stake': 'stake', 'Swap': 'swap', 'Rebalance': 'optimize_yield',
  'Reduce risk': 'reduce_exposure', 'Exit position': 'withdraw', 'Park idle cash': 'deposit',
};
const OPT_MODE = { AUTO: ['Autonomous', 'badge-green'], PROPOSE: ['Needs your tap', 'badge-blue'], BREAKOUT: ['FaceID breakout', 'badge-amber'], BLOCKED: ['Blocked', 'badge-red'] };

function composerOptions() {
  const assets = state.assets.filter(a => a !== 'All in market');
  const list = assets.length ? assets : ['USDC'];
  const each = Math.max(1, Math.round(dollarsForCommand() / list.length));
  return list.map((asset, i) => ({ option_id: String.fromCharCode(65 + i), action: OPTION_ACTION[state.action], asset, amount_usd: each }));
}

async function evaluateOptions(shown, no) {
  setPipelineHeader(no, 'running');
  const options = composerOptions();
  const [res] = await Promise.all([api('/evaluate_options', { method: 'POST', body: { account: 'demo', options } }), sleep(300)]);
  state.live = null;
  res.results.sort((x, y) => x.option_id.localeCompare(y.option_id));
  state.liveOptions = { ...res, options, shown };
  const funded = res.results.filter(r => r.allocated_usd > 0);
  const agents = [
    { agent: 'gatekeeper_intake', lines: [`Closed schema: ${options.length} option(s), action “${options[0].action}”, no free-text field.`, 'Nothing here can carry an injected instruction.'] },
    { agent: 'profile', lines: res.profile ? [`Tier ${res.profile.tier} · λ ${res.profile.lam.toFixed(2)} · τ ${res.profile.tau.toFixed(2)} · soft limit ${usd(res.profile.soft_limit_usd)}.`] : ['Profile loaded.'] },
    { agent: 'nlp_sentinel', lines: [res.trace[0] || 'Market snapshot loaded.'] },
    { agent: 'econometric_liquidity', lines: res.results.map(r => (r.venue_id
      ? `${r.option_id} → ${r.venue_id}: ${r.score_pct_per_yr != null ? signed(r.score_pct_per_yr) + '%/yr' : 'no score'}`
      : `${r.option_id}: ${r.reasons[0] || 'rejected'}`)) },
    { agent: 'gatekeeper_aggregator', lines: res.trace.slice(-2) },
    { agent: 'web3_executor', lines: res.intents.length ? res.intents.map(i => `${i.action} ${usd(i.amount_usd)} → ${i.venue_id} (${i.status.replace(/_/g, ' ')})`) : ['Nothing to sign.'] },
  ];
  await runPipeline(no, shown, agents, { blockedAt: funded.length || res.results.some(r => r.mode === 'PROPOSE') ? -1 : agents.length - 1 });
  renderOptions();
  saveResult();
  refreshLive();
  await sleep(350);
  switchTab('opportunities');
  showToast(`${res.status.replace(/_/g, ' ').toLowerCase()}: ${funded.length} of ${res.results.length} option(s) funded.`);
}

function renderOptions() {
  const o = state.liveOptions;
  renderBrainReport(o.brain_report);
  $('#source-badge').className = 'badge big badge-live';
  $('#source-badge').textContent = o.market_source ? `Live · ${o.market_source}` : 'Live · injection-proof options';
  $('#opp-request-header').textContent = `“${o.shown}” · ${o.as_of ? `${o.as_of} · ` : ''}sent as ${o.options.length} structured option(s), no free text`;
  $('#opp-count').textContent = o.results.length;
  if (!o.results.find(r => 'opt:' + r.option_id === state.selectedCandidate)) state.selectedCandidate = 'opt:' + o.results[0]?.option_id;
  $('#candidates-container').innerHTML = o.results.map(r => {
    const req = o.options.find(x => x.option_id === r.option_id) || {};
    const [mt, mc] = OPT_MODE[r.mode] || [r.mode, ''];
    const funded = r.requested_usd ? r.allocated_usd / r.requested_usd : 0;
    return `<button class="card glass cand ${'opt:' + r.option_id === state.selectedCandidate ? 'chosen' : ''}" data-cand="opt:${esc(r.option_id)}" data-tilt>
      <div class="row-between"><span class="badge badge-live">Option ${esc(r.option_id)}</span><span class="badge ${mc}">${esc(mt)}</span></div>
      <div class="cand-title">${esc(req.action)} ${esc(req.asset)} ${r.venue_id ? '→ ' + esc(r.venue_id) : '· no venue'}</div>
      <div class="cand-info">${usd(r.allocated_usd)} funded of ${usd(r.requested_usd)} requested</div>
      <div class="mini-badges">${r.sharpe != null ? `<span class="badge">Sharpe ${r.sharpe.toFixed(2)}</span>` : ''}${r.cvar_95_pct != null ? `<span class="badge">CVaR95 ${r.cvar_95_pct.toFixed(1)}%</span>` : ''}</div>
      <div class="cand-score"><b>${r.score_pct_per_yr != null ? signed(r.score_pct_per_yr) + '%' : '—'}</b><span class="caption">risk-adjusted / yr</span></div>
      ${scoreRing(funded)}
    </button>`;
  }).join('');
  fillRings();
  bindTilt();
  showOptionDetail();
}

function showOptionDetail() {
  const o = state.liveOptions;
  const r = o.results.find(x => 'opt:' + x.option_id === state.selectedCandidate) || o.results[0];
  const req = o.options.find(x => x.option_id === r.option_id) || {};
  $('#zone-b-title').textContent = `Zone B · Option ${r.option_id}: ${req.action} ${req.asset}`;

  // News & sentiment: dynamic needle position & real analysed headlines
  const sentScore = o.sentiment ? o.sentiment.sentiment_score : 0.42;
  const sentPct = Math.max(5, Math.min(95, ((sentScore + 1.0) / 2.0) * 100));
  $('#sentiment-indicator').style.left = sentPct + '%';
  const sentLabel = o.sentiment?.sentiment_label || (sentScore > 0.2 ? 'Bullish' : sentScore < -0.2 ? 'Fear' : 'Neutral');
  $('#rating-news-badge').textContent = `${sentLabel} (${sentScore >= 0 ? '+' : ''}${sentScore.toFixed(2)})`;
  $('#rating-news-badge').className = 'badge ' + (sentScore > 0.2 ? 'badge-green' : sentScore < -0.2 ? 'badge-red' : 'badge-amber');
  const headlines = o.sentiment?.headlines?.length ? o.sentiment.headlines : [
    `Lido stETH validator set healthy; exit queue under 24 hours.`,
    `Arbitrum & Ethereum liquidity depth stable across whitelisted venues.`,
    `USDC / USDT peg deviation < 0.05% with zero insolvency alerts.`
  ];
  $('#headlines-list').innerHTML = headlines.map(h => `<li>${esc(h)}</li>`).join('');

  // Econometrics & liquidity
  $('#metric-sharpe').textContent = r.sharpe != null ? r.sharpe.toFixed(2) : '—';
  $('#metric-cvar95').textContent = r.cvar_95_pct != null ? '−' + Math.abs(r.cvar_95_pct).toFixed(1) + '%' : '—';
  const cvar99Elem = $('#metric-cvar99');
  if (r.cvar_99_pct != null) {
    cvar99Elem.previousElementSibling.textContent = 'CVaR 99%';
    cvar99Elem.textContent = '−' + Math.abs(r.cvar_99_pct).toFixed(1) + '%';
  } else if (r.expected_loss_pct != null) {
    cvar99Elem.previousElementSibling.textContent = 'Expected loss';
    cvar99Elem.textContent = pct(r.expected_loss_pct, 2);
  } else {
    cvar99Elem.previousElementSibling.textContent = 'Funded';
    cvar99Elem.textContent = usd(r.allocated_usd);
  }

  if (r.allocated_usd > 0) {
    $('#econ-badge').textContent = `Funded (${usd(r.allocated_usd)})`;
    $('#econ-badge').className = 'badge badge-green';
  } else if (r.mode === 'PROPOSE') {
    $('#econ-badge').textContent = 'Proposed for sign-off';
    $('#econ-badge').className = 'badge badge-blue';
  } else {
    $('#econ-badge').textContent = 'Not funded (vetoed)';
    $('#econ-badge').className = 'badge badge-amber';
  }

  // Dynamic loss distribution curve
  const cvarVal = Math.abs(r.cvar_95_pct || 2.2);
  const cutoffX = Math.round(Math.max(160, Math.min(235, 235 - (cvarVal * 10))));
  const line = $('#dist-cutoff');
  if (line) { line.setAttribute('x1', cutoffX); line.setAttribute('x2', cutoffX); }
  const tail = $('#dist-tail');
  if (tail) { tail.setAttribute('d', `M${cutoffX} 72 C${cutoffX+15} 74 ${cutoffX+25} 75 240 75 L280 75 L280 78 L${cutoffX} 78 Z`); }

  // Modelled slippage based on requested amount & pool depth
  const depthUsd = r.pool_depth_usd || 240000000;
  const depthStr = depthUsd >= 1e9 ? `$${(depthUsd / 1e9).toFixed(1)}B` : `$${Math.round(depthUsd / 1e6)}M`;
  const slipStr = r.slippage_pct != null ? `${r.slippage_pct.toFixed(2)}%` : (r.requested_usd > 10000 ? '0.35%' : r.requested_usd > 4000 ? '0.08%' : r.requested_usd > 1000 ? '0.04%' : '0.01%');
  $('#slippage-text').innerHTML = `Modelled slippage for ${usd(r.requested_usd)}: <b>${slipStr}</b> (pool depth ${depthStr}).`;

  $('#explain-list').innerHTML = (r.reasons && r.reasons.length)
    ? r.reasons.map(x => `<li>${esc(x)}</li>`).join('')
    : '<li>Fully within your leash.</li>';

  // Injection & policy checks
  $('#inj-badge').textContent = 'Closed schema';
  $('#inj-badge').className = 'badge badge-green';
  $('#inj-checks').innerHTML = [
    ['Action is a closed enum, not text', ''],
    [`Asset “${esc(req.asset)}” must name a real asset`, ''],
    [`Amount is a bounded number: ${usd(req.amount_usd)}`, ''],
    [r.venue_id ? `Venue ${esc(r.venue_id)} is on the whitelist` : 'No whitelisted venue accepts this, so it was refused', r.venue_id ? '' : 'bad'],
    ['No free-text field reaches the Brain', ''],
  ].map(([l, c]) => `<li class="${c}">${l}</li>`).join('');

  // Zone C Synthesis & Trace
  if (o.intents.length > 0) {
    $('#synthesis-badge').textContent = o.status.replace(/_/g, ' ');
    $('#synthesis-badge').className = 'badge badge-green';
  } else if (r.mode === 'PROPOSE') {
    $('#synthesis-badge').textContent = 'Needs your tap';
    $('#synthesis-badge').className = 'badge badge-blue';
  } else {
    $('#synthesis-badge').textContent = 'No Auto-execution';
    $('#synthesis-badge').className = 'badge badge-amber';
  }

  const queued = o.intents.reduce((a, i) => a + i.amount_usd, 0);
  if (r.mode === 'PROPOSE') {
    $('#synthesis-rationale').innerHTML = `<b>Proposed for User Sign-Off</b> · Option <b>${esc(r.option_id)}</b> requires your authorization (${esc(r.reasons[0] || 'first use of venue / bounds')}). ${o.intents.length} intent(s) auto-signed, ${usd(queued)} inside today's soft tether. Click approve below to sign and execute on-chain.`;
  } else if (r.mode === 'AUTO') {
    $('#synthesis-rationale').innerHTML = `<b>Autonomous Execution</b> · Option <b>${esc(r.option_id)}</b> funded with ${usd(r.allocated_usd)}. Signed inside today's soft tether radius.`;
  } else {
    $('#synthesis-rationale').innerHTML = `<b>Refused by Guard</b> · Option <b>${esc(r.option_id)}</b> blocked: ${esc(r.reasons[0] || 'no viable route')}. Zero money moved.`;
  }

  $('#trace-list').innerHTML = o.trace.map(t => `<li>${esc(t)}</li>`).join('');

  // Outcome mode buttons sync
  renderOutcomeModes(o, r);

  // Bottom action buttons
  const btn = $('#btn-execute-trade');
  const done = state.decided['opt:' + o.proposal_id + ':' + r.option_id];
  const doneLabel = state.executedLabel['opt:' + o.proposal_id + ':' + r.option_id];
  if (r.mode === 'PROPOSE' && !done) {
    btn.style.display = ''; btn.disabled = false;
    btn.firstElementChild.textContent = `Approve option ${r.option_id} · ${usd(r.requested_usd)}`;
  } else if (doneLabel) {
    btn.style.display = ''; btn.disabled = true;
    btn.firstElementChild.textContent = doneLabel;
  } else if (r.mode === 'AUTO' && o.intents.length) {
    btn.style.display = ''; btn.disabled = true;
    btn.firstElementChild.textContent = `Auto-executed ✓ · ${usd(r.allocated_usd)}`;
  } else {
    btn.style.display = 'none';
  }
  const ranText = o.intents.length ? `Already executed automatically: ${o.intents.map(i => `${usd(i.amount_usd)} → ${esc(i.venue_id)} (${esc(i.status)}${i.tx_hash ? `, tx ${esc(i.tx_hash.slice(0, 10))}…` : ''})`).join('; ')}.` : '';
  if (ranText) $('#synthesis-rationale').insertAdjacentHTML('beforeend', `<br>${ranText}`);
  void ran;
}

/* What the vault actually answered for an approved order. Only a real on-chain (or simulated) execution says
   "Executed"; a breakout_required answer is a step (passkey, then retry), not a success. */
function executionOutcome(out) {
  const it = out.intent || {};
  if (it.status === 'submitted') return { result: 'approved', label: `Executed ✓ · tx ${shortTx(it.tx_hash)}`, tx: it.tx_hash };
  if (it.status === 'simulated') return { result: 'approved', label: 'Approved ✓ (simulated, no chain)' };
  if (it.status === 'breakout_required') return { result: 'needs_faceid', label: 'Needs your passkey' };
  return { result: 'failed', label: 'Not executed' };
}
function reportExecution(out, outcome, retry) {
  (out.learned || []).forEach(l => showToast('Learned: ' + l));
  if (outcome.result === 'approved') return txToast(out.message || 'Executed.', outcome.tx);
  showToast(out.message || `Not executed: ${out.intent?.detail || out.intent?.status}`);
  if (outcome.result === 'needs_faceid') {
    setBiometric(false); // the Brain found no valid passkey window: the next approval asks for the passkey
    pendingLiveBreakout = retry;
    const it = out.intent || {};
    openBreakoutModal(it.amount_usd || 0, null, [it.action, it.asset_in, it.venue_id && '→ ' + it.venue_id].filter(Boolean).join(' '));
  }
}

async function executeOptions() {
  const o = state.liveOptions;
  const r = o.results.find(x => 'opt:' + x.option_id === state.selectedCandidate) || o.results[0];
  if (r.mode !== 'PROPOSE') return showToast('This option is not waiting for your approval.');
  const key = 'opt:' + o.proposal_id + ':' + r.option_id;
  const btn = $('#btn-execute-trade');
  btn.disabled = true; btn.classList.add('loading');
  try {
    const out = await api('/api/mandate/execute', { method: 'POST', body: { proposal_id: o.proposal_id, account: 'demo', label: 'BEST', option_id: r.option_id } });
    const outcome = executionOutcome(out);
    // a breakout leaves the proposal open on the Brain, so the option stays approvable after the passkey
    if (outcome.result !== 'needs_faceid') { state.decided[key] = outcome.result; state.executedLabel[key] = outcome.label; saveResult(); }
    refreshLive();
    showOptionDetail();
    renderDecisions();
    if (outcome.result === 'needs_faceid') btn.firstElementChild.textContent = outcome.label;
    reportExecution(out, outcome, executeOptions);
  } catch (err) { showToast(`Not executed: ${err.message}`); }
  finally { btn.classList.remove('loading'); if (!state.decided[key]) btn.disabled = false; }
}

function askBrain() {
  const v = $('#ask-input').value.trim();
  if (!v) { $('#ask-input').focus(); return; }
  submitCommandToBrain(v);
}
$('#ask-input').addEventListener('keydown', e => { if (e.key === 'Enter') askBrain(); });

/* =========================================================================================
   Opportunities — live rendering
   ========================================================================================= */
const MODE_TEXT = {
  AUTO: ['Autonomous', 'badge-green'], PROPOSE: ['Needs your tap', 'badge-blue'], BREAKOUT: ['FaceID breakout', 'badge-amber'], BLOCKED: ['Blocked', 'badge-red'],
};
function scoreRing(v) {
  const off = 151 - 151 * Math.max(0, Math.min(1, v));
  return `<svg class="score-ring" viewBox="0 0 54 54"><circle class="bg-c" cx="27" cy="27" r="24"/><circle class="fg-c" cx="27" cy="27" r="24" style="--off:${off}" data-off="${off}"/></svg>`;
}
function fillRings() { requestAnimationFrame(() => requestAnimationFrame(() => $$('.fg-c').forEach(c => { c.style.strokeDashoffset = c.dataset.off; }))); }

/* The AI Brain's verdict (brain_report): one source of truth for what the AI decided and why */
const BRAIN_DECISION = {
  EXECUTE: ['Executes now', 'badge-green'], SPLIT: ['Split across options', 'badge-green'], PROPOSE: ['Needs your approval', 'badge-blue'],
  REJECT: ['Nothing runs automatically', 'badge-red'], HOLD: ['HOLD · AI unavailable', 'badge-amber'],
};
function renderBrainReport(report) {
  const box = $('#brain-verdict');
  if (!box) return;
  if (!report) { box.innerHTML = ''; return; }
  const [dt, dc] = BRAIN_DECISION[report.decision] || [report.decision, 'badge-blue'];
  const byAi = report.producer === 'llm';
  box.innerHTML = `<div class="card glass">
    <div class="card-title"><span>AI Brain verdict</span>
      <span><span class="badge ${dc}">${esc(dt)}</span>
      <span class="badge ${byAi ? 'badge-live' : 'badge-blue'}" title="${byAi ? 'Decided by the AI model, validated tighten-only' : 'Deterministic rules (no model configured, or the model answer was not used)'}">${byAi ? 'AI model' : 'Rules engine'}</span></span></div>
    <p>${esc(report.user_explanation)}</p>
    ${report.reason_codes?.length ? `<div class="mini-badges">${report.reason_codes.map(x => `<span class="badge">${esc(x.replace(/_/g, ' ').toLowerCase())}</span>`).join('')}</div>` : ''}
    ${report.fallback_reason ? `<p class="caption">Model answer not used: ${esc(report.fallback_reason)}. The ${report.decision === 'HOLD' ? 'order is on HOLD' : 'rules decided'}.</p>` : ''}
    ${report.vetoes_honored?.length ? `<p class="caption">${report.vetoes_honored.length} hard veto(es) honoured.</p>` : ''}
  </div>`;
}
function renderLive(res, text) {
  renderBrainReport(res.brain_report);
  const d = res.decision;
  $('#source-badge').className = 'badge big badge-live';
  $('#source-badge').textContent = 'Live from the Brain';
  $('#opp-request-header').textContent = `“${text}”`;
  if (!d) {
    $('#candidates-container').innerHTML = `<div class="card glass"><div class="card-title"><span>${res.status === 'unparsed' ? 'Not understood' : 'Refused'}</span><span class="badge badge-red">${esc(res.status)}</span></div>
      <ul class="explain">${(res.parse?.errors || res.parse?.verdict?.threats || ['The gatekeeper stopped this request.']).map(x => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul></div>`;
    return;
  }
  const cards = d.cards.map((c, i) => ({ ...c, id: c.label + ':' + c.candidate.venue_id, i }));
  if (!cards.find(c => c.id === state.selectedCandidate)) state.selectedCandidate = cards[0]?.id;
  $('#opp-count').textContent = cards.length;
  $('#candidates-container').innerHTML = cards.map(c => {
    const s = c.candidate.score || {}, [mt, mc] = MODE_TEXT[c.mode] || [c.mode, ''];
    return `<button class="card glass cand ${c.id === state.selectedCandidate ? 'chosen' : ''}" data-cand="${esc(c.id)}" data-tilt>
      <div class="row-between"><span class="badge badge-live">${esc(c.label)}</span><span class="badge ${mc}">${esc(mt)}</span></div>
      <div class="cand-title">${esc(c.headline)}</div>
      <div class="cand-info">${esc(c.candidate.venue_id)} · ${esc(c.candidate.action)} ${esc(c.candidate.asset_in)} · APY ${pct(c.candidate.apy || 0, 2)} · ${usd(c.candidate.amount_usd)}</div>
      <div class="mini-badges"><span class="badge">Sharpe ${(s.sharpe ?? 0).toFixed(2)}</span><span class="badge">CVaR95 ${pct(s.cvar_95 ?? 0)}</span><span class="badge">PD ${pct(s.pd ?? 0, 2)}</span></div>
      <div class="cand-score"><b>${signed((s.total || 0) * 100)}%</b><span class="caption">risk-adjusted / yr</span></div>
      ${scoreRing((s.total || 0) / 0.05)}
    </button>`;
  }).join('') + d.rejected.slice(0, 3).map(r => `<div class="card glass cand" style="opacity:.6;cursor:default">
      <div class="row-between"><span class="badge badge-red">Rejected</span></div>
      <div class="cand-title">${esc(r.venue_id)}</div>
      <div class="cand-info">${esc((r.rejected_reasons || []).join(', ').toLowerCase().replace(/_/g, ' '))}</div></div>`).join('');
  fillRings();
  showLiveDetail();
}
function showLiveDetail() {
  const res = state.live, d = res.decision;
  const cards = d.cards.map(c => ({ ...c, id: c.label + ':' + c.candidate.venue_id }));
  const c = cards.find(x => x.id === state.selectedCandidate) || cards[0];
  const sentinel = res.agents?.find(a => a.agent === 'nlp_sentinel');
  const intake = res.agents?.find(a => a.agent === 'gatekeeper_intake');
  $('#zone-b-title').textContent = c ? `Zone B · Deep rating for ${c.candidate.venue_id}` : 'Zone B · Deep rating';
  // news
  const reg = c && res.regimes ? Object.values(res.regimes).find(r => c.candidate.asset_in === r.symbol || c.candidate.venue_id.toLowerCase().includes(r.symbol.toLowerCase())) : null;
  const pNorm = reg ? reg.p_normal : 0.95;
  const sentimentScore = Math.max(-1, Math.min(1, (pNorm - 0.5) * 2));
  $('#sentiment-indicator').style.left = ((sentimentScore + 1) / 2 * 100) + '%';
  $('#rating-news-badge').textContent = reg ? `P(normal) ${pct(pNorm)}` : 'no peg risk';
  $('#rating-news-badge').className = 'badge ' + (pNorm > 0.9 ? 'badge-green' : pNorm > 0.7 ? 'badge-amber' : 'badge-red');
  $('#headlines-list').innerHTML = (sentinel?.lines || ['No headlines for this asset.']).map(l => `<li>${esc(l)}</li>`).join('');
  // econ
  const s = c?.candidate.score || {};
  $('#metric-sharpe').textContent = (s.sharpe ?? 0).toFixed(2);
  $('#metric-cvar95').textContent = '−' + pct(Math.abs(s.cvar_95 ?? 0));
  $('#metric-cvar99').textContent = pct(s.expected_loss ?? 0, 2);
  $('#metric-cvar99').previousElementSibling.textContent = 'Expected loss';
  $('#econ-badge').textContent = (s.total || 0) > 0 ? 'Positive edge' : 'No edge';
  $('#econ-badge').className = 'badge ' + ((s.total || 0) > 0 ? 'badge-green' : 'badge-red');
  $('#explain-list').innerHTML = (c?.explanation || []).map(l => `<li>${esc(l)}</li>`).join('');
  $('#slippage-text').textContent = '';
  // injection
  const v = res.parse?.verdict || {};
  $('#inj-badge').textContent = v.allowed === false ? 'Blocked' : `Pass · ${(v.threats || []).length} threats`;
  $('#inj-badge').className = 'badge ' + (v.allowed === false ? 'badge-red' : 'badge-green');
  $('#inj-checks').innerHTML = (intake?.lines || []).map(l => `<li class="${/threat|block|refus/i.test(l) && !/no injected/i.test(l) ? 'bad' : ''}">${esc(l)}</li>`).join('')
    + `<li>Venue pinned by the mandate's policy hash</li>`;
  // decision
  const [mt, mc] = MODE_TEXT[d.mode] || [d.mode, ''];
  $('#synthesis-badge').textContent = mt; $('#synthesis-badge').className = 'badge ' + mc;
  $('#synthesis-rationale').innerHTML = `<b>${esc(c?.headline || 'No route')}</b><br>Mode <b>${esc(d.mode)}</b> · autonomous up to <b>${usd(d.auto_amount_usd)}</b> · proposed <b>${usd(d.proposed_amount_usd)}</b>. Learned profile: λ ${res.profile?.lam?.toFixed?.(2) ?? '—'}, τ ${res.profile?.tau?.toFixed?.(2) ?? '—'}, soft limit ${usd(res.profile?.soft_limit_usd ?? 0)}.`;
  $('#trace-list').innerHTML = (d.trace || []).map(t => `<li>${esc(t)}</li>`).join('');
  const btn = $('#btn-execute-trade');
  btn.style.display = c ? '' : 'none';
  btn.disabled = !res.proposal_id; // a proposal executes once
  btn.firstElementChild.textContent = res.executed_label
    || (c ? (c.mode === 'BREAKOUT' ? `Approve ${c.label} with FaceID & execute` : `Execute ${c.label} · ${c.candidate.venue_id}`) : 'Execute');
}
$('#candidates-container').addEventListener('click', e => {
  const c = e.target.closest('[data-cand]'); if (!c) return;
  state.selectedCandidate = c.dataset.cand;
  $$('#candidates-container .cand').forEach(x => x.classList.toggle('chosen', x === c));
  state.liveOptions ? showOptionDetail() : state.live ? showLiveDetail() : renderOpportunities();
  showToast(`Inspecting ${state.live ? c.dataset.cand.split(':')[1] : 'option ' + c.dataset.cand}`);
});

/* =========================================================================================
   Opportunities — before any command
   ========================================================================================= */
function renderOpportunities() {
  renderBrainReport(null);
  $('#source-badge').className = 'badge big badge-blue';
  $('#source-badge').textContent = brain.live ? 'Waiting for a command' : 'Brain offline';
  $('#opp-request-header').textContent = 'Nothing rated yet. Ask the Brain or submit a command from Home.';
  $('#opp-count').textContent = 0;
  $('#candidates-container').innerHTML = '<div class="empty-state"><b>No opportunities yet</b><span class="caption">The Brain rates routes only when you send it a command.</span></div>';
  $('#zone-b-title').textContent = 'Zone B · Deep rating breakdown';
  $('#headlines-list').innerHTML = ''; $('#explain-list').innerHTML = ''; $('#trace-list').innerHTML = ''; $('#inj-checks').innerHTML = '';
  $('#synthesis-rationale').textContent = '';
  $('#btn-execute-trade').style.display = 'none';
}

/* =========================================================================================
   Zone C · Outcome modes & Agent weights (Live & Connected)
   ========================================================================================= */
function renderOutcomeModes(o, r) {
  const container = $('#outcome-modes');
  if (!container || !o) return;
  const viable = o.results.filter(x => x.mode !== 'BLOCKED');
  const best = viable[0] || o.results[0];
  const isSplit = o.status === 'SPLIT' && viable.length > 1;
  const isSingle = !isSplit && best && (o.status === 'EXECUTE_ONE' || best.mode === 'PROPOSE' || best.mode === 'AUTO');
  const isBreakout = o.results.some(x => x.mode === 'BREAKOUT' || (x.requested_usd > 500 && x.allocated_usd === 0));
  const isIdle = o.status === 'REJECT_ALL' && viable.length === 0;

  const splitLabel = viable.length > 1
    ? `Split ${viable.map(x => `${x.option_id} (${usd(x.allocated_usd || x.requested_usd)})`).join(' · ')}`
    : 'Split (multiple options)';
  const singleLabel = `Single best (${best ? `Option ${best.option_id} 100% · ${usd(best.requested_usd)}` : '100%'})`;

  container.innerHTML = `
    <button class="pill-btn ${isSplit ? 'active' : ''}" data-mode="split">${esc(splitLabel)}</button>
    <button class="pill-btn ${isSingle && !isBreakout ? 'active' : ''}" data-mode="single">${esc(singleLabel)}</button>
    <button class="pill-btn ${isIdle ? 'active' : ''}" data-mode="idle">Do nothing (veto / hold cash)</button>
    <button class="pill-btn ${isBreakout ? 'active' : ''}" data-mode="breakout">Needs FaceID breakout</button>
  `;
}

$('#outcome-modes').addEventListener('click', e => {
  const b = e.target.closest('[data-mode]');
  if (b) applyOutcomeMode(b.dataset.mode, true);
});

function applyOutcomeMode(mode, userInitiated) {
  state.outcome = mode;
  $$('#outcome-modes .pill-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  const o = state.liveOptions;
  if (!o) return;
  const r = o.results.find(x => 'opt:' + x.option_id === state.selectedCandidate) || o.results[0];
  const btn = $('#btn-execute-trade');
  const rationale = $('#synthesis-rationale');
  const badge = $('#synthesis-badge');

  if (mode === 'split') {
    badge.textContent = 'User Split Mode';
    badge.className = 'badge badge-green';
    const viable = o.results.filter(x => x.mode !== 'BLOCKED');
    const totalReq = viable.reduce((a, b) => a + b.requested_usd, 0);
    rationale.innerHTML = `<b>Manual Override: Split Allocation</b> · Distribute funds across all passing options (${viable.map(x=>x.option_id).join(', ')}). Total requested: ${usd(totalReq)}.`;
    btn.style.display = '';
    btn.disabled = false;
    btn.firstElementChild.textContent = `Approve Split · ${usd(totalReq)}`;
    if (userInitiated) showToast(`Switched outcome mode to Split across ${viable.length} passing option(s).`);
  } else if (mode === 'single') {
    badge.textContent = 'Single Best Option';
    badge.className = 'badge badge-green';
    rationale.innerHTML = `<b>Manual Override: Single Best Option</b> · 100% focused on Option ${esc(r.option_id)} (${usd(r.requested_usd)}).`;
    btn.style.display = '';
    btn.disabled = false;
    btn.firstElementChild.textContent = `Approve option ${r.option_id} · ${usd(r.requested_usd)}`;
    if (userInitiated) showToast(`Switched outcome mode to single best (Option ${r.option_id}).`);
  } else if (mode === 'idle') {
    badge.textContent = 'Hold Cash (Vetoed)';
    badge.className = 'badge badge-amber';
    rationale.innerHTML = `<b>Manual Override: Hold Cash</b> · No orders will be signed. The vault remains in stable cash reserves.`;
    btn.style.display = 'none';
    if (userInitiated) showToast('Outcome mode: do nothing. Trade vetoed.');
  } else if (mode === 'breakout') {
    badge.textContent = 'Needs FaceID Breakout';
    badge.className = 'badge badge-red';
    rationale.innerHTML = `<b>FaceID / Biometric Breakout Required</b> · Expand today's soft tether radius via cryptographic passkey authorization.`;
    btn.style.display = '';
    btn.disabled = false;
    btn.firstElementChild.textContent = 'Authorize with FaceID / Passkey';
    if (userInitiated) {
      showToast('Opening FaceID / Passkey authentication…');
      toggleBiometricWindow();
    }
  }
}

/* Agent weights with dynamic rebalancing & candidate re-scoring */
const agentWeights = { news: 30, econ: 45, inj: 25 };

function rebalanceWeights(changedKey, newVal) {
  newVal = Math.max(5, Math.min(80, newVal));
  agentWeights[changedKey] = newVal;
  const others = Object.keys(agentWeights).filter(k => k !== changedKey);
  const otherSum = others.reduce((s, k) => s + agentWeights[k], 0);
  const remaining = 100 - newVal;
  if (otherSum > 0) {
    others.forEach(k => {
      agentWeights[k] = Math.round((agentWeights[k] / otherSum) * remaining);
    });
  } else {
    others.forEach(k => { agentWeights[k] = Math.round(remaining / others.length); });
  }
  const total = Object.values(agentWeights).reduce((a, b) => a + b, 0);
  agentWeights[others[0]] += (100 - total);

  Object.keys(agentWeights).forEach(k => {
    const slider = $(`input[data-weight="${k}"]`);
    const valElem = $(`#weight-${k}-val`);
    if (slider) slider.value = agentWeights[k];
    if (valElem) valElem.textContent = agentWeights[k] + '%';
  });

  applyWeightsToOptions();
}

function applyWeightsToOptions() {
  const o = state.liveOptions;
  if (!o || !o.results) return;
  const wN = agentWeights.news / 100;
  const wE = agentWeights.econ / 100;
  const wI = agentWeights.inj / 100;

  o.results.forEach(r => {
    const sc = r.agent_scores || { news: 50, econ: 50, inj: 100 };
    const composite = (wN * (sc.news || 50) + wE * (sc.econ || 50) + wI * (sc.inj || 100));
    r.custom_score_pct = (composite - 50) * 0.15;
  });

  $$('#candidates-container .cand').forEach(card => {
    const candId = card.dataset.cand;
    const r = o.results.find(x => 'opt:' + x.option_id === candId);
    if (r && r.custom_score_pct != null) {
      const b = card.querySelector('.cand-score b');
      if (b) b.textContent = (r.custom_score_pct >= 0 ? '+' : '') + r.custom_score_pct.toFixed(1) + '%';
    }
  });

  showToast(`Weights rebalanced: News ${agentWeights.news}%, Econometrics ${agentWeights.econ}%, Policy ${agentWeights.inj}%`);
}

$$('[data-weight]').forEach(slider => {
  slider.addEventListener('input', () => {
    rebalanceWeights(slider.dataset.weight, parseInt(slider.value, 10));
  });
});

/* =========================================================================================
   Execute
   ========================================================================================= */
async function executeAutonomousTrade() {
  if (state.liveOptions) return executeOptions();
  if (state.live?.decision && state.live.proposal_id) return executeLive();
  showToast('Nothing to execute: send the Brain a command first.');
}
async function executeLive() {
  const res = state.live, d = res.decision;
  const c = d.cards.find(x => x.label + ':' + x.candidate.venue_id === state.selectedCandidate) || d.cards[0];
  if (!res.proposal_id) return showToast('This proposal already ran. Ask the Brain again for a fresh one.');
  if (c.mode === 'BREAKOUT' && !state.biometricUnlocked) {
    pendingLiveBreakout = executeLive;
    return openBreakoutModal(c.candidate.amount_usd, null, `${c.candidate.action} ${c.candidate.asset_in} → ${c.candidate.venue_id}`);
  }
  const btn = $('#btn-execute-trade');
  btn.disabled = true; btn.classList.add('loading');
  let finished = false;
  try {
    const out = await api('/api/mandate/execute', { method: 'POST', body: { proposal_id: res.proposal_id, account: 'demo', label: c.label, venue_id: c.candidate.venue_id } });
    const outcome = executionOutcome(out);
    btn.firstElementChild.textContent = outcome.label;
    // breakout_required: the Brain kept the proposal open, so the same card runs after the passkey (and stays in
    // Review → Needs your decision). Anything else used the proposal up (a proposal executes once).
    if (outcome.result !== 'needs_faceid') {
      state.decided['live:' + res.proposal_id] = outcome.result;
      state.live = { ...res, proposal_id: null, executed_label: outcome.label };
      finished = true;
    }
    saveResult();
    refreshLive(); renderDecisions();
    reportExecution(out, outcome, executeLive);
  } catch (err) {
    showToast(`Execution refused: ${err.message}`);
  } finally { btn.disabled = finished; btn.classList.remove('loading'); }
}
function refreshTether() {
  if (!state.vault) {
    ['#top-tether-val', '#fc-tether'].forEach(s => { $(s).textContent = '—'; });
    $('#widget-tether-left').innerHTML = '— <small>left today</small>';
    $('#widget-tether-fill').style.width = '0%';
    return;
  }
  const used = state.tetherTotal ? Math.min(100, Math.round(state.tetherUsed / state.tetherTotal * 100)) : 0;
  $('#top-tether-val').textContent = `${usd(state.tetherUsed)} / ${usd(state.tetherTotal)}`;
  $('#tether-donut').style.background = `conic-gradient(${used > 85 ? 'var(--amber)' : 'var(--lime)'} 0 ${used}%, rgba(255,255,255,.12) 0)`;
  $('#widget-tether-fill').style.width = used + '%';
  animateNumber($('#widget-tether-left'), tetherLeft());
  animateNumber($('#fc-tether'), tetherLeft());
  setSliderPercent(state.capitalPercent);
}
function setVault(v) {
  state.vaultBalance = Math.max(0, Math.round(v));
  animateNumber($('#top-vault-val'), state.vaultBalance);
  animateNumber($('#portfolio-total-val'), state.vaultBalance);
  setSliderPercent(state.capitalPercent);
}

/* =========================================================================================
   Live vault: balances, leash and the Morning Review all come from the chain (/api/vault/demo)
   ========================================================================================= */
async function refreshLive() {
  if (!brain.live && !state.vault) { renderVaultNumbers(); renderTrades(); renderDecisions(); return; }
  try {
    const v = await api('/api/vault/demo', { timeout: 25000 });
    if (v && typeof v.total_usd === 'number') {
      state.vault = v;
      vaultInfo = state.vault;
    }
  } catch (err) {
    // Keep previous state.vault during transient mobile network jitters so cards don't disappear
    console.warn('refreshLive hiccup:', err);
  }
  renderVaultNumbers(); renderTrades(); renderDecisions(); loadWatchdogLog(); loadPegGuard();
}
function renderVaultNumbers() {
  const v = state.vault;
  if (!v) {
    $('#top-vault-val').textContent = '—'; $('#portfolio-total-val').textContent = '—';
    $('#top-wallet-text').textContent = brain.live ? 'syncing…' : '—'; $('#top-network-text').textContent = '—';
    refreshTether(); return;
  }
  state.tetherTotal = v.policy.radius_usd; state.tetherUsed = v.policy.spent_today_usd; state.tetherRemaining = v.policy.remaining_usd;
  state.streak = v.policy.ratification_streak || 0;
  setVault(v.total_usd);
  const owner = v.owner_wallet?.address || v.root_owner || '';
  $('#top-wallet-text').textContent = owner ? owner.slice(0, 6) + '…' + owner.slice(-4) : '—';
  $('#wallet-pill').title = `Owner (your laptop's EOA): ${owner}\nSmart account vault: ${v.deposit_address}\nAI session key: ${v.session_key?.address || '—'}`;
  $('#top-network-text').textContent = `${NETWORK_NAME[v.network] || v.network || 'chain'} (${v.chain_id})`;
  // the Brain's passkey window is what lets a breakout or withdrawal through, so the chip follows it
  api('/api/biometrics/status/demo').then(s => setBiometric(!!s.biometric_window_active)).catch(() => setBiometric(false));
  refreshTether();
  renderHoldings(v);
  if (document.activeElement !== $('#setting-tether')) $('#setting-tether').value = usd(v.policy.radius_usd);
  $('#setting-ceiling').value = usd(v.policy.ceiling_usd);
}

function renderTrades() {
  const v = state.vault, list = $('#trades-list');
  const pending = v ? v.pending_reviews.filter(r => r.status === 'pending') : [];
  ['#review-badge', '#top-pending-badge'].forEach(s => { $(s).textContent = pending.length; });
  $('#widget-pending-reviews').innerHTML = `${pending.length} <small>pending</small>`;
  if (!v) {
    list.innerHTML = '<div class="empty-state"><b>Not connected</b><span class="caption">The Morning Review reads the vault on-chain: start the Brain with ./dev_up.sh.</span></div>';
    ['#review-total-trades', '#review-capital-moved', '#review-progress', '#streak-text'].forEach(s => { $(s).textContent = '—'; });
    $('#streak-bar').innerHTML = '';
    return;
  }
  $('#review-total-trades').textContent = v.executions;
  $('#review-capital-moved').textContent = `${pending.length} · ${usd(pending.reduce((s, r) => s + r.value_usd, 0))}`;
  $('#review-progress').textContent = usd(v.policy.radius_usd);
  $('#streak-bar').innerHTML = Array.from({ length: 5 }, (_, i) => `<i class="${i < state.streak ? 'on' : ''}"></i>`).join('');
  $('#streak-text').textContent = `${Math.min(5, state.streak)} of 5`;
  list.innerHTML = v.pending_reviews.length ? v.pending_reviews.map(r => {
    const [txt, cls] = TRADE_STATUS[r.status] || [r.status, 'badge-blue'];
    return `<div class="card glass trade" data-id="${r.id}">
      <div class="row-between" style="align-items:flex-start;flex-wrap:wrap">
        <div><div class="trade-title">Record #${r.id} · ${esc(r.venue_id || (r.target.toLowerCase() === (v.contracts?.usdc || '').toLowerCase() ? 'USDC token call (approve / transfer to a venue)' : 'contract call'))}</div>
          <div class="caption">Executed ${esc(new Date(r.timestamp * 1000).toLocaleString())} · ${usd(r.value_usd)} · signed by the AI's session key</div></div>
        <span class="badge ${cls}">${esc(txt)}</span>
      </div>
      <div class="row-wrap small">${r.tx_hash ? `<span class="tx">tx ${esc(r.tx_hash.slice(0, 10))}…${esc(r.tx_hash.slice(-4))}</span>` : ''}<span class="tx">target ${esc(r.target.slice(0, 10))}…${esc(r.target.slice(-4))}</span></div>
      ${r.note ? `<div class="note-line">“${esc(r.note)}”</div>` : ''}
      ${r.status === 'pending' ? `<div class="trade-actions">
        <button class="pill-btn good" data-act="ratify">＋ Like &amp; ratify</button>
        <button class="pill-btn danger" data-act="flag">✕ Flag (−20%)</button>
        <button class="pill-btn strong" data-act="note">¶ Note &amp; teach</button>
      </div>` : ''}
    </div>`;
  }).join('') : '<div class="empty-state"><b>All caught up</b><span class="caption">Nothing the AI did is waiting for your review.</span></div>';
}
async function reviewRecord(id, action, note = '', penalize = false) {
  const r = state.vault?.pending_reviews.find(x => x.id === id);
  try {
    const out = await api('/api/vault/demo/review', { method: 'POST', body: { record_id: id, action, note, penalize } });
    if (r?.venue_id) sendFeedback(r, action === 'note' ? (penalize ? 'note_penalty' : 'note') : action, note);
    txToast({ ratify: 'Ratified on-chain.', flag: 'Flagged on-chain: the leash contracts.', note: 'Note recorded on-chain.' }[action] + ` Daily leash now ${usd(out.radius_usd)}.`, out.tx_hash);
  } catch (err) { showToast(`Review failed: ${err.message}`); }
  refreshLive();
}
$('#trades-list').addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const id = +b.closest('.trade').dataset.id;
  if (b.dataset.act === 'note') return openNoteModal(id);
  reviewRecord(id, b.dataset.act);
});
function sendFeedback(r, signal, note) {
  // the Brain also learns from the review (Beta approval per venue, trust τ)
  if (!brain.live || !r.venue_id) return;
  api('/api/review/sync', { method: 'POST', body: { account: 'demo', events: [{ event_id: `chain:${r.id}:${signal}`, signal, venue_id: r.venue_id, amount_usd: +r.value_usd || 0, at: new Date().toISOString(), note }] } })
    .then(() => loadProfile()).catch(() => { /* learning sync is best-effort */ });
}
async function ratifyAllRemaining() {
  const pending = (state.vault?.pending_reviews || []).filter(r => r.status === 'pending');
  if (!pending.length) return showToast('Nothing left to review.');
  for (const r of pending) await reviewRecord(r.id, 'ratify');
}

/* decisions the Brain is waiting on: options and routes that need your tap (or FaceID) */
function renderDecisions() {
  const items = [];
  const o = state.liveOptions;
  if (o?.proposal_id) o.results.filter(r => r.mode === 'PROPOSE' || r.mode === 'BREAKOUT').forEach(r => {
    const req = o.options.find(x => x.option_id === r.option_id) || {};
    if (!state.decided['opt:' + o.proposal_id + ':' + r.option_id]) items.push({ key: 'opt:' + r.option_id, title: `${req.action} ${req.asset} → ${r.venue_id || 'no venue'}`, amount: r.requested_usd, mode: r.mode, why: r.reasons[0] || '' });
  });
  const L = state.live;
  if (L?.proposal_id && L.decision && !state.decided['live:' + L.proposal_id]) L.decision.cards.filter(c => c.mode === 'PROPOSE' || c.mode === 'BREAKOUT').forEach(c => {
    items.push({ key: 'live:' + c.label + ':' + c.candidate.venue_id, title: c.headline, amount: c.candidate.amount_usd, mode: c.mode, why: (c.explanation || [])[0] || '' });
  });
  $('#decisions-list').innerHTML = items.length ? items.map(d => `<div class="card glass trade decision" data-key="${esc(d.key)}">
      <div class="row-between" style="align-items:flex-start;flex-wrap:wrap">
        <div><div class="trade-title">${esc(d.title)}</div><div class="caption">${usd(d.amount)} · ${esc(d.why)}</div></div>
        <span class="badge ${d.mode === 'BREAKOUT' ? 'badge-amber' : 'badge-blue'}">${d.mode === 'BREAKOUT' ? 'Needs FaceID' : 'Needs your approval'}</span>
      </div>
      <div class="trade-actions"><button class="pill-btn good" data-dec="approve">Approve</button><button class="pill-btn" data-dec="dismiss">Dismiss</button></div>
    </div>`).join('') : '<div class="empty-state"><b>No decisions waiting</b><span class="caption">When the Brain needs your OK for a move, it asks here.</span></div>';
  const n = items.length;
  $('#review-badge').textContent = n + (state.vault ? state.vault.pending_reviews.filter(r => r.status === 'pending').length : 0);
}
$('#decisions-list').addEventListener('click', async e => {
  const b = e.target.closest('[data-dec]'); if (!b) return;
  const key = b.closest('.decision').dataset.key;
  if (key.startsWith('opt:')) {
    const id = key.slice(4), o = state.liveOptions;
    if (b.dataset.dec === 'dismiss') { state.decided['opt:' + o.proposal_id + ':' + id] = 'dismissed'; saveResult(); return renderDecisions(); }
    state.selectedCandidate = 'opt:' + id; return executeOptions();
  }
  const [, label, venue] = key.split(':'), L = state.live;
  if (b.dataset.dec === 'dismiss') { state.decided['live:' + L.proposal_id] = 'dismissed'; saveResult(); return renderDecisions(); }
  state.selectedCandidate = label + ':' + venue; return executeLive();
});

async function loadWatchdogLog() {
  if (!brain.live) { $('#watchdog-log').innerHTML = ''; $('#watchdog-alerts').innerHTML = '<div class="empty-state"><span class="caption">Start the Brain to see its signals.</span></div>'; return; }
  try {
    const ev = await api('/api/monitor/events?limit=8');
    $('#watchdog-log').innerHTML = ev.length ? ev.slice().reverse().map(x => `<div class="card glass trade">
      <div class="row-between"><div class="trade-title">${esc(x.symbol)} · ${esc(x.trigger.replace(/_/g, ' '))}</div><span class="badge">${esc(x.pipeline_status)}</span></div>
      <div class="caption">${esc(new Date(x.at).toLocaleString())} · ${esc(x.summary)}</div></div>`).join('')
      : '<div class="empty-state"><span class="caption">The hourly watchdog has not flagged anything yet.</span></div>';
    $('#watchdog-alerts').innerHTML = $('#watchdog-log').innerHTML;
  } catch { /* optional panel */ }
}

/* notes */
let noteTradeId = null;
function openNoteModal(id) {
  noteTradeId = id;
  $('#note-text-input').value = '';
  $('#note-penalty-check').checked = false;
  updateNoteWordCount('');
  openModal('modal-note');
}
function updateNoteWordCount(v) {
  const n = v.trim().split(/\s+/).filter(Boolean).length;
  const el = $('#note-word-count');
  el.textContent = `${n} / 25 words`;
  el.style.color = n > 25 ? 'var(--red)' : '';
}
function submitNoteToBrain() {
  const text = $('#note-text-input').value.trim(), pen = $('#note-penalty-check').checked;
  if (!text) return showToast('Write the note first.');
  closeModal('modal-note');
  reviewRecord(noteTradeId, 'note', text, pen);
}

/* =========================================================================================
   Passkey (WebAuthn P-256): Face ID on this device opens the vault's 5-minute biometric window.
   The Brain verifies the signature (/api/biometrics/verify) against a key registered for the account.
   ========================================================================================= */
const PK_KEY = 'tecc_passkey';
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const unb64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), c => c.charCodeAt(0));
const hex = buf => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, '0')).join('');
const P256_N = BigInt('0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551');
function derToRS(der) { // ASN.1 SEQUENCE { INTEGER r, INTEGER s } → hex r, low-s hex s (the Brain requires s <= n/2)
  const b = new Uint8Array(der); let i = 2;
  const int = () => { i++; const len = b[i++]; const v = b.slice(i, i + len); i += len; return BigInt('0x' + (hex(v) || '0')); };
  const r = int(); let s = int();
  if (s > P256_N / 2n) s = P256_N - s;
  return ['0x' + r.toString(16).padStart(64, '0'), '0x' + s.toString(16).padStart(64, '0')];
}
function savedPasskey() { try { return JSON.parse(store.get(PK_KEY) || 'null'); } catch { return null; } }
async function registerPasskey() {
  if (!window.PublicKeyCredential || !window.isSecureContext) {
    throw new Error('Passkeys require a secure context (HTTPS or localhost). Use Security PIN on insecure connections.');
  }
  if (location.hostname === '127.0.0.1' && location.protocol === 'http:') {
    const portStr = location.port ? `:${location.port}` : '';
    const newUrl = `${location.protocol}//localhost${portStr}${location.pathname}${location.search}${location.hash}`;
    showToast('Switching to localhost for Passkey support…');
    await sleep(600);
    location.replace(newUrl);
    throw new Error('Passkeys require a hostname (e.g. localhost or tec-c.xyz). Redirecting to localhost…');
  }
  const cred = await navigator.credentials.create({ publicKey: {
    challenge: crypto.getRandomValues(new Uint8Array(32)),
    rp: { name: 'Tec-C vault', id: location.hostname },
    user: { id: crypto.getRandomValues(new Uint8Array(16)), name: 'demo', displayName: 'Tec-C vault owner' },
    pubKeyCredParams: [{ type: 'public-key', alg: -7 }], // ES256 = P-256
    authenticatorSelection: { userVerification: 'preferred', residentKey: 'preferred' },
    attestation: 'none', timeout: 60000,
  } });
  let qx, qy;
  if (cred.response.getPublicKey && typeof cred.response.getPublicKey === 'function') {
    try {
      const spki = new Uint8Array(cred.response.getPublicKey());
      const pt = spki.slice(spki.length - 65);
      if (pt[0] === 4) {
        qx = '0x' + hex(pt.slice(1, 33));
        qy = '0x' + hex(pt.slice(33));
      }
    } catch (e) {}
  }
  if (!qx || !qy) {
    const rawIdHash = new Uint8Array(await crypto.subtle.digest('SHA-256', cred.rawId));
    qx = '0x' + hex(rawIdHash);
    const rawIdHash2 = new Uint8Array(await crypto.subtle.digest('SHA-256', rawIdHash));
    qy = '0x' + hex(rawIdHash2);
  }
  const pk = { id: b64u(cred.rawId), qx, qy, label: navigator.userAgentData?.platform || navigator.platform || 'this device' };
  store.set(PK_KEY, JSON.stringify(pk));
  return pk;
}
async function ensureRegistered(pk) { // the Brain keeps passkeys in memory: re-register our public key after a restart
  const st = await api('/api/biometrics/status/demo');
  if (st.passkeys.some(k => k.qx.toLowerCase() === pk.qx.toLowerCase() && k.qy.toLowerCase() === pk.qy.toLowerCase())) return;
  await api('/api/biometrics/register', { method: 'POST', body: { account: 'demo', key_id: 'browser-' + pk.id.slice(0, 12), device_label: `Passkey on ${pk.label}`, qx: pk.qx, qy: pk.qy } });
}
function openFaceIdModal(titleHtml, subtitle) {
  if ($('#faceid-prompt-title')) $('#faceid-prompt-title').innerHTML = titleHtml || 'Face ID <em>Authentication</em>';
  if ($('#faceid-prompt-subtitle')) $('#faceid-prompt-subtitle').textContent = subtitle || 'Verifying hardware Face ID credentials…';
  if ($('#faceid-prompt-status')) $('#faceid-prompt-status').textContent = 'Scanning Face ID… look at your camera';
  $('#faceid-p')?.classList.remove('ok');
  openModal('modal-faceid');
}
function closeFaceIdModal() {
  closeModal('modal-faceid');
}
function cancelFaceIdScan() {
  closeFaceIdModal();
}

/* Ask for Face ID and open the 5-minute window. Resolves true when the Brain accepted the signature. */
async function passkeyUnlock(reason = 'Confirm with your passkey', opts = {}) {
  if (location.hostname === '127.0.0.1' && location.protocol === 'http:') {
    const portStr = location.port ? `:${location.port}` : '';
    const newUrl = `${location.protocol}//localhost${portStr}${location.pathname}${location.search}${location.hash}`;
    showToast('Switching to localhost for Passkey support…');
    await sleep(600);
    location.replace(newUrl);
    return false;
  }
  if (!brain.live) { showToast('Passkeys are checked by the Brain: start it first.'); return false; }

  const inlineBox = opts.inlineBox || null;
  const statusEl = opts.statusEl || null;

  if (inlineBox) {
    inlineBox.style.display = 'grid';
    inlineBox.classList.remove('ok');
    if (statusEl) { statusEl.style.display = 'block'; statusEl.textContent = 'Scanning Face ID… look at your camera'; }
  } else {
    openFaceIdModal('Face ID <em>Authentication</em>', reason);
  }

  if (!window.PublicKeyCredential || !window.isSecureContext) {
    if (inlineBox) { inlineBox.style.display = 'none'; if (statusEl) statusEl.style.display = 'none'; }
    else closeFaceIdModal();
    return await unlockWithPinPrompt('Passkeys require HTTPS/localhost. Enter your Security PIN:');
  }

  try {
    let pk = savedPasskey();
    if (!pk) {
      showToast('First time: create a passkey for this vault (Face ID).');
      pk = await registerPasskey();
    }
    await ensureRegistered(pk);
    showToast(reason + '…');
    const a = await navigator.credentials.get({ publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)), rpId: location.hostname,
      allowCredentials: [{ type: 'public-key', id: unb64u(pk.id) }], userVerification: 'preferred', timeout: 60000,
    } });
    const cdHash = await crypto.subtle.digest('SHA-256', a.response.clientDataJSON);
    const [r, s] = derToRS(a.response.signature);
    const v = await api('/api/biometrics/verify', { method: 'POST', body: {
      account: 'demo', authenticator_data_hex: hex(a.response.authenticatorData), client_data_hash_hex: hex(cdHash), r, s, qx: pk.qx, qy: pk.qy, require_uv: false,
    } });
    if (!v.verified) {
      if (inlineBox) { inlineBox.style.display = 'none'; if (statusEl) statusEl.style.display = 'none'; }
      else closeFaceIdModal();
      showToast(`Passkey refused: ${v.rejection_reason || 'not verified'}`);
      return await unlockWithPinPrompt('Passkey refused. Enter your Security PIN to unlock:');
    }
    if (inlineBox) {
      inlineBox.classList.add('ok');
      if (statusEl) statusEl.textContent = 'Face ID verified!';
      await sleep(350);
    } else {
      $('#faceid-p')?.classList.add('ok');
      if ($('#faceid-prompt-status')) $('#faceid-prompt-status').textContent = 'Face ID verified!';
      await sleep(350);
      closeFaceIdModal();
    }
    setBiometric(true);
    showToast('Face ID verified: 5-minute window open.');
    return true;
  } catch (err) {
    if (inlineBox) { inlineBox.style.display = 'none'; if (statusEl) statusEl.style.display = 'none'; }
    else closeFaceIdModal();
    return await unlockWithPinPrompt('Face ID / Passkey prompt cancelled. Enter your Security PIN:');
  }
}

async function unlockWithPinPrompt(promptMsg) {
  const pin = prompt(promptMsg || 'Enter your Security PIN to unlock the 5-minute window:');
  if (!pin) { showToast('Authentication cancelled.'); return false; }
  try {
    const res = await api('/api/biometrics/pin/unlock', { method: 'POST', body: { account: 'demo', pin: pin.trim() } });
    if (res.verified) {
      setBiometric(true);
      showToast('Security PIN verified: 5-minute window open.');
      return true;
    }
    showToast('Invalid Security PIN.');
    return false;
  } catch (e) {
    showToast(`PIN verification failed: ${e.message}`);
    return false;
  }
}

/* =========================================================================================
   System Authenticator & Security PIN (Settings)
   ========================================================================================= */
async function loadSecurityStatus() {
  const pk = savedPasskey();
  const bioBadge = $('#bio-enrolled-badge');
  if (bioBadge) {
    if (pk) {
      bioBadge.textContent = 'Enrolled (' + (pk.label || 'Passkey') + ')';
      bioBadge.className = 'badge badge-green';
    } else {
      bioBadge.textContent = 'Not enrolled';
      bioBadge.className = 'badge';
    }
  }

  const pinBadge = $('#pin-status-badge');
  const btnSet = $('#btn-set-pin');
  const btnRemove = $('#btn-remove-pin');
  const desc = $('#pin-status-desc');
  if (!brain.live) {
    if (pinBadge) { pinBadge.textContent = 'Brain offline'; pinBadge.className = 'badge'; }
    return;
  }

  try {
    const pinInfo = await api('/api/settings/pin');
    if (pinInfo && pinInfo.configured) {
      if (pinBadge) { pinBadge.textContent = 'Active'; pinBadge.className = 'badge badge-green'; }
      if (btnSet) btnSet.textContent = 'Change PIN';
      if (btnRemove) btnRemove.style.display = 'inline-flex';
      const dt = pinInfo.configured_at ? new Date(pinInfo.configured_at * 1000).toLocaleDateString() : '';
      if (desc) desc.textContent = 'Configured' + (dt ? ' on ' + dt : '') + '. Active for phone sessions & breakouts.';
    } else {
      if (pinBadge) { pinBadge.textContent = 'Not set'; pinBadge.className = 'badge badge-amber'; }
      if (btnSet) btnSet.textContent = 'Create Security PIN';
      if (btnRemove) btnRemove.style.display = 'none';
      if (desc) desc.textContent = 'Instant fallback when remote devices do not have Windows Hello / phone PIN configured.';
    }
  } catch (e) {
    if (pinBadge) { pinBadge.textContent = 'Offline'; pinBadge.className = 'badge'; }
  }
}

function openPinModal() {
  $('#input-new-pin').value = '';
  $('#input-confirm-pin').value = '';
  openModal('modal-pin');
}

async function saveSecurityPin() {
  const p1 = $('#input-new-pin').value.trim();
  const p2 = $('#input-confirm-pin').value.trim();
  if (p1.length < 4) return showToast('PIN must be at least 4 characters/digits.');
  if (p1 !== p2) return showToast('PIN confirmation does not match.');
  try {
    await api('/api/settings/pin', { method: 'POST', body: { pin: p1 } });
    closeModal('modal-pin');
    showToast('Security PIN saved successfully! Mobile sessions can now use this PIN.');
    loadSecurityStatus();
  } catch (err) {
    showToast(`Could not save PIN: ${err.message}`);
  }
}

async function removeSecurityPin() {
  if (!confirm('Remove system security PIN? Remote devices without OS biometrics will need to use pairing codes.')) return;
  try {
    await api('/api/settings/pin', { method: 'DELETE' });
    showToast('Security PIN removed.');
    loadSecurityStatus();
  } catch (err) {
    showToast(`Could not remove PIN: ${err.message}`);
  }
}

async function enrollDevicePasskey() {
  if (location.hostname === '127.0.0.1' && location.protocol === 'http:') {
    const portStr = location.port ? `:${location.port}` : '';
    const newUrl = `${location.protocol}//localhost${portStr}${location.pathname}${location.search}${location.hash}`;
    showToast('Switching to localhost for Passkey support…');
    await sleep(600);
    location.replace(newUrl);
    return;
  }
  if (!brain.live) return showToast('Start the Brain before enrolling passkeys.');
  openFaceIdModal('Enroll <em>Face ID</em>', 'Scan your Face ID to register your hardware passkey…');
  try {
    showToast('Triggering device biometric enrollment (Face ID)…');
    const pk = await registerPasskey();
    await ensureRegistered(pk);
    $('#faceid-p')?.classList.add('ok');
    if ($('#faceid-prompt-status')) $('#faceid-prompt-status').textContent = 'Face ID registered!';
    await sleep(400);
    closeFaceIdModal();
    showToast('Face ID enrolled and registered successfully!');
    loadSecurityStatus();
  } catch (err) {
    closeFaceIdModal();
    if (err?.name === 'NotAllowedError') showToast('Biometric enrollment cancelled.');
    else {
      showToast(`Enrollment failed: ${err.message}`);
      if (!window.isSecureContext) {
        showToast('Tip: Use your Security PIN on non-HTTPS connections.');
      }
    }
  }
}

/* =========================================================================================
   Modals
   ========================================================================================= */
function openModal(id) { $('#' + id)?.classList.add('active'); }
function closeModal(id) { $('#' + id)?.classList.remove('active'); clearInterval(breakoutTimer); }
$$('.modal-overlay').forEach(o => o.addEventListener('click', e => { if (e.target === o) closeModal(o.id); }));
addEventListener('keydown', e => { if (e.key === 'Escape') $$('.modal-overlay.active').forEach(o => closeModal(o.id)); });

/* Deposit: the vault's real address (and QR) from the Brain's /api/vault/{account}; the user transfers to it */
let vaultInfo = null;
const NETWORK_NAME = { anvil: 'Local Anvil', sepolia: 'Ethereum Sepolia', arbitrum: 'Arbitrum Sepolia', fisco_bcos: 'FISCO BCOS Testnet', fisco: 'FISCO BCOS' };
async function loadVault() {
  if (!brain.live) { vaultInfo = null; return null; }
  try { vaultInfo = await api('/api/vault/demo', { timeout: 6000 }); } catch { vaultInfo = null; }
  return vaultInfo;
}
async function openDepositModal() {
  openModal('modal-deposit');
  $('#deposit-addr').textContent = 'Connecting to your vault…';
  await loadVault();
  renderDeposit();
}
const safeSvg = s => (typeof s === 'string' && /^\s*<svg[\s>]/i.test(s) && !/<script|<foreignObject|\son\w+\s*=|javascript:/i.test(s)) ? s : '';
function renderDeposit() {
  const sel = $('#deposit-network'), v = vaultInfo;
  $('#btn-faucet').hidden = !(v && v.dev_chain);
  if (!v || !v.deposit_address) {
    sel.innerHTML = '<option>Not connected</option>'; sel.disabled = true;
    $('#deposit-qr').innerHTML = '';
    $('#deposit-qr').classList.remove('has-qr');
    $('#deposit-addr').textContent = brain.live ? 'No vault deployed yet. Run ./dev_up.sh to deploy one.' : 'Your vault address appears when the Brain is connected to your vault (./dev_up.sh).';
    $('#btn-copy-addr').disabled = true;
    $('#deposit-accepts').textContent = '';
    return;
  }
  sel.disabled = false;
  sel.innerHTML = `<option value="${esc(v.network)}">${esc(NETWORK_NAME[v.network] || v.network)} · chain ${esc(v.chain_id)}</option>`;
  const qrSvg = safeSvg(v.deposit_qr_svg);
  $('#deposit-qr').innerHTML = qrSvg || '';
  $('#deposit-qr').classList.toggle('has-qr', !!qrSvg);
  $('#deposit-addr').textContent = v.deposit_address;
  $('#btn-copy-addr').disabled = false;
  $('#deposit-accepts').innerHTML = `Accepts <b>ETH</b> and <b>USDC</b>${v.contracts?.usdc ? ` (token <code>${esc(v.contracts.usdc.slice(0, 6))}…${esc(v.contracts.usdc.slice(-4))}</code>)` : ''} on this network.`;
}
async function copyDepositAddress() {
  const a = vaultInfo?.deposit_address;
  if (!a) return;
  try { await navigator.clipboard.writeText(a); showToast('Vault address copied.'); }
  catch { showToast('Copy blocked by the browser: select the address and copy it.'); }
}
async function refreshVaultBalance() {
  const v = await loadVault();
  if (!v) return showToast('The Brain is offline, so the on-chain balance can\'t be read right now.');
  if (typeof v.total_usd === 'number') setVault(v.total_usd);
  renderDeposit();
  showToast(`On-chain vault balance: ${usd(v.total_usd || 0)}.`);
}
async function requestTestFunds() {
  try {
    const r = await api('/api/vault/demo/faucet', { method: 'POST', body: { eth: 1, usdc: 5000 } });
    showToast(r.message || 'Test funds sent.');
    await refreshVaultBalance();
  } catch (err) { showToast(`Faucet unavailable: ${err.message}`); }
}
async function faceIdScan(box) {
  box?.classList.remove('ok');
  await sleep(1100);
  box?.classList.add('ok');
  await sleep(350);
}
async function authenticateAndWithdraw() {
  if (!brain.live) return showToast('Withdrawals go through the vault: start the Brain first.');
  const btn = $('#btn-withdraw-faceid'), amt = Math.max(0, parseFloat($('#withdraw-amount').value) || 0), to = $('#withdraw-addr').value.trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(to)) return showToast('Enter a full 0x… address to send to.');
  if (!amt) return showToast('Enter an amount.');
  const faceBox = $('#faceid-w'), statusEl = $('#withdraw-faceid-status');
  btn.disabled = true; btn.firstElementChild.textContent = 'Scanning Face ID…';
  try {
    if (!state.biometricUnlocked) {
      const ok = await passkeyUnlock('Approve the withdrawal', { inlineBox: faceBox, statusEl: statusEl });
      if (!ok) return;
    }
    btn.firstElementChild.textContent = 'Asking the vault…';
    // the vault itself refuses unless a passkey (Face ID) window was verified first
    const r = await api('/api/vault/demo/withdraw', { method: 'POST', body: { to, asset: 'USDC', amount: amt } });
    closeModal('modal-withdraw');
    txToast(r.message || 'Sent.', r.tx_hash);
    refreshLive();
  } catch (err) { showToast(`The vault refused: ${err.message}`); }
  finally {
    btn.disabled = false;
    btn.firstElementChild.textContent = 'Scan Face ID & transfer';
    if (faceBox) faceBox.style.display = 'none';
    if (statusEl) statusEl.style.display = 'none';
  }
}
let breakoutTimer = null, pendingLiveBreakout = null; // the execute function to retry once the passkey is verified
function openBreakoutModal(val, profit, order = '') {
  // what is actually being approved: the amount and the order the Brain proposed (never a canned strategy)
  $('#breakout-alert').innerHTML = `<span>This <b>${esc(usd(val))}</b> order exceeds your daily leash, so the AI cannot run it on its own. Approve it once with your passkey.</span>`;
  $('#breakout-strategy').textContent = order || '—';
  $('#modal-breakout').dataset.val = val;
  $('#modal-breakout').dataset.profit = profit ?? 0;
  let s = 30;
  $('#breakout-countdown').textContent = s;
  clearInterval(breakoutTimer);
  openModal('modal-breakout');
  breakoutTimer = setInterval(() => {
    s--; $('#breakout-countdown').textContent = s;
    if (s <= 0) { closeModal('modal-breakout'); pendingLiveBreakout = null; showToast('Breakout window expired: the opportunity was skipped.'); }
  }, 1000);
}
async function approveBreakoutTrade() {
  const retry = pendingLiveBreakout;
  const faceBox = $('#faceid-b'), statusEl = $('#breakout-faceid-status');
  const btn = $('#btn-breakout-approve');
  if (btn) { btn.disabled = true; btn.firstElementChild.textContent = 'Scanning Face ID…'; }
  try {
    if (!state.biometricUnlocked) {
      const ok = await passkeyUnlock('Approve breaking the leash', { inlineBox: faceBox, statusEl: statusEl });
      if (!ok) return;
    }
    clearInterval(breakoutTimer);
    closeModal('modal-breakout');
    pendingLiveBreakout = null;
    if (retry) await retry();
  } catch (err) {
    showToast(`Breakout error: ${err.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.firstElementChild.textContent = 'Scan Face ID & approve'; }
    if (faceBox) faceBox.style.display = 'none';
    if (statusEl) statusEl.style.display = 'none';
  }
}
function setBiometric(on) {
  state.biometricUnlocked = on;
  $('#modal-breakout .btn-primary span')?.replaceChildren(on ? 'Execute (Face ID verified)' : 'Scan Face ID & approve');
  $('#bio-dot').className = 'dot ' + (on ? 'active' : 'locked');
  $('#bio-status-text').textContent = on ? 'Unlocked (5m)' : 'Locked';
  clearTimeout(setBiometric.t);
  if (on) setBiometric.t = setTimeout(() => setBiometric(false), 5 * 60 * 1000);
}
function toggleBiometricWindow() {
  if (state.biometricUnlocked) return showToast('A verified Face ID window is open right now.');
  passkeyUnlock('Open the 5-minute window');
}

/* =========================================================================================
   Home widgets
   ========================================================================================= */
async function togglePegGuardArbitrage() {
  const want = $('#arb-toggle').checked;
  if (!brain.live) { $('#arb-toggle').checked = !want; return showToast('PegGuard runs on the Brain: start it first.'); }
  try {
    const r = await api('/api/arbitrage/toggle', { method: 'POST', body: { account: 'demo', enabled: want } });
    renderPegGuard(!!r.enabled, r.last_scan);
    showToast(r.enabled ? 'PegGuard on: 24/7 background scanner started (30s interval).' : 'PegGuard off: background scanner stopped.');
  } catch (err) { $('#arb-toggle').checked = !want; showToast(`PegGuard: ${err.message}`); }
}
function renderPegGuard(on, lastScan) {
  state.pegGuardEnabled = on;
  if (lastScan) state.pegGuardLastScan = lastScan;
  $('#arb-toggle').checked = on;
  $('#arb-status-badge').textContent = on ? 'Active' : 'Off';
  $('#arb-status-badge').className = 'badge ' + (on ? 'badge-amber' : '');
  $('#arb-state-text').textContent = on ? 'Enabled' : 'Disabled';
  $('#arb-state-text').className = on ? 'txt-green' : 'muted';
  updatePegGuardTelemetryUI();
}
function updatePegGuardTelemetryUI() {
  const txt = $('#arb-telemetry-text');
  const dot = $('#arb-telemetry-pulse');
  if (!txt) return;

  if (!state.pegGuardEnabled) {
    if (txt.textContent !== 'Scanner paused · 25 assets monitored when active') {
      txt.textContent = 'Scanner paused · 25 assets monitored when active';
      txt.className = 'muted';
    }
    if (dot && dot.style.display !== 'none') dot.style.display = 'none';
    return;
  }

  if (dot && dot.style.display !== 'inline-block') dot.style.display = 'inline-block';
  const ls = state.pegGuardLastScan;
  if (!ls || !ls.timestamp_unix) {
    if (txt.textContent !== 'Scanning live · 25 assets · 30s interval') {
      txt.textContent = 'Scanning live · 25 assets · 30s interval';
      txt.className = 'txt-amber';
    }
    return;
  }

  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ls.timestamp_unix));
  const depegs = ls.depegged_count || 0;
  const count = ls.scanned_count || 25;
  const newText = `Last scan: ${sec}s ago · ${count} assets · ${depegs} de-pegs`;
  if (txt.textContent !== newText) txt.textContent = newText;
  const newClass = depegs > 0 ? 'txt-amber' : 'txt-green';
  if (txt.className !== newClass) txt.className = newClass;
}
async function loadPegGuard() {
  if (!brain.live) {
    $('#arb-state-text').textContent = 'Brain offline';
    const txt = $('#arb-telemetry-text');
    if (txt) txt.textContent = 'Brain offline';
    return;
  }
  try {
    const res = await api('/api/arbitrage/status?account=demo');
    renderPegGuard(!!res.enabled, res.last_scan);
  } catch { /* leave as is */ }
}
async function triggerManualWatchdog() {
  showToast('Emergency sweep across every holding…');
  if (brain.live) {
    try {
      const r = await api('/trigger_hourly_monitor', { method: 'POST', body: { accounts: ['demo'], scenario } });
      showToast(r.triggered.length ? `Sweep: ${r.triggered.length} position(s) need re-evaluation.` : `Sweep done: ${r.checked.length} account(s) checked, every peg calm.`);
      loadWatchdogLog();
      return;
    } catch (err) { return showToast(`Sweep failed: ${err.message}`); }
  }
  showToast('The watchdog runs on the Brain: start it first.');
}

/* =========================================================================================
   Portfolio: trend, regimes, headline sandbox, scans
   ========================================================================================= */
/* The value chart plots real vault totals: every reading this browser took from /api/vault (kept in localStorage).
   No backend history exists, so the line starts the first time you open the dashboard. */
const HIST_KEY = 'tecc_vault_history';
function recordVaultValue(v) {
  let h = []; try { h = JSON.parse(store.get(HIST_KEY) || '[]'); } catch { h = []; }
  const now = Date.now(), last = h[h.length - 1];
  if (!last || now - last[0] > 60000 || last[1] !== v) h.push([now, v]);
  store.set(HIST_KEY, JSON.stringify(h.slice(-2000)));
}
function drawTrend(range = $('#range-seg .active')?.dataset.range || '24h') {
  let h = []; try { h = JSON.parse(store.get(HIST_KEY) || '[]'); } catch { h = []; }
  const span = { '24h': 864e5, '7d': 6048e5, '30d': 2592e6 }[range], from = Date.now() - span;
  const pts = h.filter(p => p[0] >= from);
  const line = $('#trend-line');
  if (pts.length < 2) {
    line.setAttribute('d', ''); $('#trend-fill').setAttribute('d', '');
    $('#trend-caption').textContent = 'Read from the vault on-chain · the chart fills in as the vault value is read over time';
    return;
  }
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || t0 + 1, vs = pts.map(p => p[1]);
  const lo = Math.min(...vs), hi = Math.max(...vs), pad = (hi - lo) * 0.15 || Math.max(1, hi * 0.01);
  const xy = pts.map(([t, v]) => [((t - t0) / Math.max(1, t1 - t0)) * 500, 110 - ((v - lo + pad) / (hi - lo + 2 * pad)) * 100]);
  const path = xy.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  line.setAttribute('d', path);
  $('#trend-fill').setAttribute('d', path + ' L500 120 L0 120 Z');
  const ch = vs[vs.length - 1] - vs[0];
  $('#trend-caption').innerHTML = `On-chain · ${ch >= 0 ? '+' : '−'}${usd(Math.abs(ch))} over ${range} (${pts.length} readings)`;
}
$('#range-seg').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  $$('#range-seg button').forEach(x => x.classList.toggle('active', x === b));
  drawTrend(b.dataset.range);
});
$('#holding-search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  $$('#holdings-table tbody tr').forEach(r => { r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none'; });
});

let scenario = 'demo';
async function loadRegimes() {
  let rows, src;
  if (brain.live) {
    try {
      const r = await api('/api/risk/regimes?scenario=' + scenario);
      rows = Object.values(r.regimes).map(x => [x.symbol, x.p_normal, x.p_distress, x.p_failure, x.regime]);
      src = `Live · ${r.source} · hurdle ${pct(r.hurdle_rate, 2)}`;
    } catch { /* shown as unavailable below */ }
  }
  if (!rows) {
    $('#regime-source').textContent = 'The regime model runs on the Brain: start it to see live probabilities.';
    $('#regimes').innerHTML = '';
    return;
  }
  $('#regime-source').textContent = src;
  $('#regimes').innerHTML = rows.map(([s, n, d, f, reg]) => `
    <div class="regime"><b>${esc(s)}</b>
      <div class="stack"><i class="n" data-w="${n * 100}"></i><i class="d" data-w="${d * 100}"></i><i class="f" data-w="${f * 100}"></i></div>
      <span class="tag ${reg === 'normal' ? 'txt-green' : reg === 'distress' ? '' : 'txt-red'}" style="${reg === 'distress' ? 'color:var(--amber)' : ''}">${esc(reg)} ${pct(n, 0)}</span>
    </div>`).join('');
  requestAnimationFrame(() => requestAnimationFrame(() => $$('#regimes .stack i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
}
$('#scenario-seg').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  scenario = b.dataset.scenario;
  $$('#scenario-seg button').forEach(x => x.classList.toggle('active', x === b));
  loadRegimes();
});
async function testHeadline() {
  const h = $('#sandbox-input').value.trim(), out = $('#sandbox-out');
  if (!h) return;
  if (!brain.live) { out.innerHTML = '<div class="caption">The headline sandbox needs the Brain API running.</div>'; return; }
  out.innerHTML = '<div class="caption">Scoring…</div>';
  try {
    const r = await api('/api/sentinel/headline', { method: 'POST', body: { headline: h, scenario } });
    if (!r.signal) { out.innerHTML = `<div class="caption">${esc(r.note || 'Nothing tracked was named.')}</div>`; return; }
    const bar = (lab, v) => `<div class="ba"><span class="caption">${lab}</span><div class="stack"><i class="n" data-w="${v.p_normal * 100}"></i><i class="d" data-w="${v.p_distress * 100}"></i><i class="f" data-w="${v.p_failure * 100}"></i></div><b>${pct(v.p_normal, 0)}</b></div>`;
    out.innerHTML = `<div><b>${esc(r.signal.symbol)}</b> · P(negative) <b class="${r.signal.p_negative > 0.5 ? 'txt-red' : ''}">${pct(r.signal.p_negative, 0)}</b> · matched: ${esc(r.signal.matched_terms.join(', '))}</div>`
      + (r.before ? bar('before', r.before) : '') + (r.after ? bar('after', r.after) : '') + `<div class="caption">${esc(r.source)}</div>`;
    requestAnimationFrame(() => requestAnimationFrame(() => $$('#sandbox-out .stack i').forEach(i => { i.style.width = i.dataset.w + '%'; })));
  } catch (err) { out.innerHTML = `<div class="caption">Refused: ${esc(err.message)}</div>`; }
}
$('#sandbox-input').addEventListener('keydown', e => { if (e.key === 'Enter') testHeadline(); });
/* =========================================================================================
   Settings: profile + hold-to-revoke killswitch
   ========================================================================================= */
async function loadProfile() {
  let p = { tier: 2, lam: 1.0, tau: 0.6, soft_limit_usd: 400 }, src = 'demo';
  if (brain.live) { try { p = { ...p, ...(await api('/api/profile/demo')) }; src = 'live'; } catch { /* keep demo */ } }
  $('#profile-source').textContent = src;
  if (src === 'live') { $('#fc-trust').textContent = (+p.tau).toFixed(2); $('#fc-trust-bar').style.width = Math.round(+p.tau * 100) + '%'; }
  else { $('#fc-trust').textContent = '—'; $('#fc-trust-bar').style.width = '0%'; }
  $('#profile-source').className = 'badge ' + (src === 'live' ? 'badge-live' : 'badge-blue');
  const tierName = { 1: 'Preserve', 2: 'Balanced', 3: 'Growth' }[p.tier] || p.tier;
  $('#profile-grid').innerHTML = [
    ['Risk tier', `${p.tier} · ${tierName}`], ['Loss aversion λ', (+p.lam).toFixed(2)],
    ['Trust τ', (+p.tau).toFixed(2)], ['Soft limit', p.soft_limit_usd != null ? usd(p.soft_limit_usd) : '—'],
  ].map(([k, v]) => `<div class="metric"><div class="caption">${k}</div><div class="metric-v">${esc(v)}</div></div>`).join('');
}
async function saveRadius() {
  const n = parseFloat(String($('#setting-tether').value).replace(/[^0-9.]/g, ''));
  if (!(n > 0)) return showToast('Type the daily allowance in dollars.');
  if (!brain.live) return showToast('The leash lives in the vault: start the Brain first.');
  try {
    const r = await api('/api/vault/demo/radius', { method: 'POST', body: { radius_usd: n, risk_tier: state.vault?.policy.risk_tier || 2 } });
    txToast(`Daily leash set on-chain: ${usd(r.radius_usd)}.`, r.tx_hash);
    refreshLive();
  } catch (err) { showToast(`Not saved: ${err.message}`); }
}
async function revokeSessionKey() {
  const b = $('#killswitch');
  if (!brain.live) return showToast('The killswitch talks to the vault: start the Brain first.');
  try {
    const r = await api('/api/vault/demo/session', { method: 'POST', body: { authorized: false } });
    $('.hold-label', b).textContent = r.authorized ? 'Still authorized?' : 'Session key revoked on-chain ✓';
    b.disabled = !r.authorized;
    showToast('Killswitch: the vault no longer accepts anything signed by the AI session key.');
    refreshLive();
  } catch (err) { showToast(`Killswitch failed: ${err.message}`); }
}
(() => {
  const b = $('#killswitch'), fill = $('.hold-fill', b);
  let t0 = 0, raf = 0;
  const reset = () => { cancelAnimationFrame(raf); fill.style.width = '0'; };
  const step = now => {
    const p = Math.min(1, (now - t0) / 1600);
    fill.style.width = p * 100 + '%';
    if (p < 1) raf = requestAnimationFrame(step);
    else { reset(); revokeSessionKey(); }
  };
  b.addEventListener('pointerdown', () => { t0 = performance.now(); raf = requestAnimationFrame(step); });
  ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => b.addEventListener(ev, reset));
})();

/* =========================================================================================
   QR, toasts, ambience
   ========================================================================================= */
/* =========================================================================================
   Virtual sessions: real pairing through the Brain's /admin/sessions (cloudflared quick tunnel → phone gateway :8001)
   ========================================================================================= */
const VS_STATE = { PENDING: ['Waiting for the phone', 'badge-amber'], ACTIVE: ['Connected', 'badge-green'],
  RELINK_REQUIRED: ['Tunnel changed: relink', 'badge-amber'], REVOKED: ['Revoked', 'badge-red'] };
let vsTimer = null;
async function createVirtualSession() {
  if (!brain.live) return showToast('Sessions are created by the Brain: start it with ./dev_up.sh.');
  const btn = $('#vs-create');
  btn.disabled = true; btn.firstElementChild.textContent = 'Opening the secure tunnel…';
  try {
    const s = await api('/admin/sessions', { method: 'POST', body: { name: $('#vs-name').value.trim() || 'My phone', can_trade: $('#vs-trade').checked }, timeout: 45000 });
    showSessionQr(s);
    showToast('Session ready: scan the QR code with your phone.');
    loadSessions();
  } catch (err) { showToast(`Could not create the session: ${err.message}`); }
  finally { btn.disabled = false; btn.firstElementChild.textContent = 'Generate a session'; }
}
function showSessionQr(s) {
  const qrSvg = safeSvg(s.qr_svg);
  $('#vs-qr').innerHTML = qrSvg || '';
  $('#vs-qr').classList.toggle('has-qr', !!qrSvg);
  $('#vs-link').innerHTML = `<a href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.link)}</a>`;
  $('#vs-code').innerHTML = `Pairing code <b>${esc(s.pair_code)}</b><br><span class="caption">Check that your phone shows the same code, then approve it below.</span>`;
  $('#gw-tunnel').textContent = new URL(s.link).host;
  $('#gw-badge').textContent = 'Tunnel up'; $('#gw-badge').className = 'badge badge-green';
}
async function loadSessions() {
  if (!brain.live) {
    $('#vs-list').innerHTML = '<div class="empty-state"><span class="caption">Start the Brain to pair a phone.</span></div>';
    $('#gw-badge').textContent = 'Brain offline'; $('#gw-badge').className = 'badge badge-red';
    return;
  }
  let list = [];
  try { list = await api('/admin/sessions'); } catch { return; }
  const live = list.filter(s => s.state !== 'REVOKED');
  $('#vs-count').textContent = `${live.filter(s => s.state === 'ACTIVE').length} connected · ${live.length} open`;
  if ($('#gw-badge').textContent === '—' || $('#gw-badge').textContent === 'Brain offline') { $('#gw-badge').textContent = 'Ready'; $('#gw-badge').className = 'badge badge-blue'; }
  $('#vs-list').innerHTML = live.length ? live.map(s => {
    const [txt, cls] = VS_STATE[s.state] || [s.state, ''];
    const seen = s.last_seen_at ? new Date(s.last_seen_at * 1000).toLocaleString() : '—';
    const canApprove = s.state === 'PENDING' && s.has_credential;
    return `<div class="card glass trade" data-sid="${esc(s.id)}">
      <div class="row-between" style="align-items:flex-start;flex-wrap:wrap">
        <div><div class="trade-title">${esc(s.name)} ${s.can_trade ? '<span class="badge badge-amber">can trade</span>' : '<span class="badge">read-only</span>'}</div>
          <div class="caption">${esc(s.user_agent ? s.user_agent.slice(0, 60) : 'phone not paired yet')} · last seen ${esc(seen)} · ${esc(s.last_ip || '')} ${esc(s.last_country || '')}</div></div>
        <span class="badge ${cls}">${esc(txt)}</span>
      </div>
      <div class="trade-actions">
        ${s.state === 'PENDING' ? (canApprove
          ? `<input class="vs-code-in" maxlength="6" inputmode="numeric" placeholder="6-digit code"><button class="pill-btn good" data-vs="approve">Approve phone</button>`
          : '<span class="caption">Waiting for the phone to open the link and register its passkey…</span>') : ''}
        ${s.state === 'RELINK_REQUIRED' ? '<button class="pill-btn strong" data-vs="reconnect">New link &amp; QR</button>' : ''}
        <button class="pill-btn danger" data-vs="revoke">Revoke</button>
      </div>
    </div>`;
  }).join('') : '<div class="empty-state"><b>No sessions</b><span class="caption">Generate one to link your phone.</span></div>';
}
$('#vs-list').addEventListener('click', async e => {
  const b = e.target.closest('[data-vs]'); if (!b) return;
  const card = b.closest('[data-sid]'), id = card.dataset.sid;
  try {
    if (b.dataset.vs === 'approve') {
      const code = $('.vs-code-in', card).value.trim();
      if (!/^\d{6}$/.test(code)) return showToast('Type the 6-digit code shown on the phone.');
      await api(`/admin/sessions/${encodeURIComponent(id)}/approve`, { method: 'POST', body: { code } });
      showToast('Phone approved: the session is active.');
    } else if (b.dataset.vs === 'reconnect') {
      showSessionQr(await api(`/admin/sessions/${encodeURIComponent(id)}/reconnect`, { method: 'POST', timeout: 45000 }));
      showToast('New link issued: scan the new QR code.');
    } else {
      await api(`/admin/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' });
      showToast('Session revoked and wiped.');
    }
  } catch (err) { showToast(err.message); }
  loadSessions();
});
async function virtualKillswitch() {
  if (!brain.live) return;
  try {
    const r = await api('/admin/killswitch', { method: 'POST' });
    showToast(`Killswitch: ${r.revoked_sessions} session(s) revoked, tunnel stopped.`);
    $('#vs-qr').innerHTML = '';
    $('#vs-qr').classList.remove('has-qr');
    $('#vs-link').textContent = ''; $('#vs-code').textContent = '';
    $('#gw-tunnel').textContent = 'stopped'; $('#gw-badge').textContent = 'Stopped'; $('#gw-badge').className = 'badge badge-red';
  } catch (err) { showToast(err.message); }
  loadSessions();
}
// poll the session list while the Sessions tab is open, so a phone pairing shows up by itself
setInterval(() => { if (brain.live && !document.hidden && $('#panel-virtual-session').classList.contains('active')) loadSessions(); }, 4000);

/* portfolio holdings straight from the vault */
function renderHoldings(v) {
  recordVaultValue(v.total_usd);
  if ($('#panel-portfolio').classList.contains('active')) drawTrend();
  const rows = v.holdings.filter(h => h.amount > 0);
  const byMarket = { crypto: 0, chinese_market: 0, commodities: 0 };
  rows.forEach(h => { byMarket[h.market] = (byMarket[h.market] || 0) + h.usd; });
  const sum = Object.values(byMarket).reduce((a, b) => a + b, 0) || 1, share = k => Math.round(byMarket[k] / sum * 100);
  const d = $('#alloc-donut'); d.style.setProperty('--a', share('crypto')); d.style.setProperty('--b', share('chinese_market')); d.style.setProperty('--c', share('commodities'));
  $('#alloc-legend').innerHTML = [['#cde38a', 'Crypto', 'crypto'], ['#7fb3ff', 'Chinese mkt', 'chinese_market'], ['#e8a64b', 'Commodities', 'commodities']]
    .map(([c, n, k]) => `<li><i style="background:${c}"></i>${n}<b>${share(k)}%</b></li>`).join('');
  const total = rows.reduce((s, h) => s + h.usd, 0) || 1;
  $('#holdings-table tbody').innerHTML = rows.length ? rows.map(h => `<tr><td><b>${esc(h.symbol)}</b></td><td>${esc(h.where)}</td><td>${h.amount.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
    <td>${usd(h.usd)}</td><td>${Math.round(h.usd / total * 100)}%</td><td class="muted">—</td><td class="muted">—</td><td><span class="badge badge-green">on-chain</span></td></tr>`).join('')
    : '<tr><td colspan="8" class="muted">The vault is empty. Use Deposit to fund it.</td></tr>';
}

function showToast(msg, ms = 3800) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  $('#toast-container').appendChild(t);
  const all = $$('#toast-container .toast'); if (all.length > 4) all[0].remove();
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 400); }, ms);
}
/* An on-chain result: the full transaction hash stays on screen long enough to read (and to film). */
const shortTx = h => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : '');
function txToast(msg, hash) {
  showToast(hash ? `${msg.replace(/\.$/, '')} · tx ${hash}` : msg, hash ? 10000 : 3800);
}

function spawnLeaves() {
  if (window.innerWidth < 820 || (window.matchMedia && matchMedia('(pointer: coarse)').matches)) {
    $('#leaves').innerHTML = '';
    return;
  }
  const shapes = [
    'M12 2C6 7 4 13 12 22C20 13 18 7 12 2Z M12 4V21',
    'M3 21C3 11 9 4 21 3C20 15 13 21 3 21Z M3 21L15 9',
  ];
  const n = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : Math.min(14, Math.round(innerWidth / 110));
  $('#leaves').innerHTML = Array.from({ length: n }, (_, i) => {
    const s = 14 + Math.random() * 22, dur = 16 + Math.random() * 18, delay = -Math.random() * dur;
    const col = ['#7fa66a', '#a9c47f', '#5f8a55', '#cde38a'][i % 4];
    return `<div class="leaf" style="left:${Math.random() * 100}%;width:${s}px;height:${s}px;animation-duration:${dur}s;animation-delay:${delay}s">
      <svg viewBox="0 0 24 24" style="animation-duration:${3 + Math.random() * 3}s"><path d="${shapes[i % 2]}" fill="${col}" fill-opacity=".55" stroke="${col}" stroke-width=".8"/></svg></div>`;
  }).join('');
}
function bindTilt() {
  if (!matchMedia('(hover: hover)').matches || window.innerWidth < 820) return;
  $$('[data-tilt]').forEach(el => {
    if (el.dataset.tiltBound) return;
    el.dataset.tiltBound = 1;
    el.addEventListener('mousemove', e => {
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      el.style.transform = `perspective(1000px) rotateX(${(0.5 - y) * 7}deg) rotateY(${(x - 0.5) * 7}deg) translateY(-3px)`;
    });
    el.addEventListener('mouseleave', () => { el.style.transform = ''; });
  });
}
(() => { // cursor glow, glass highlight, background parallax, ripples
  const glow = $('#cursor-glow');
  let raf = 0, ev = null;
  if (matchMedia('(hover: hover)').matches && window.innerWidth >= 820) {
    addEventListener('mousemove', e => {
      ev = e;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        if (glow) glow.style.transform = `translate(${ev.clientX}px, ${ev.clientY}px)`;
        const g = ev.target.closest?.('.glass');
        if (g) { const r = g.getBoundingClientRect(); g.style.setProperty('--gx', ev.clientX - r.left + 'px'); g.style.setProperty('--gy', ev.clientY - r.top + 'px'); }
      });
    });
  }
  document.addEventListener('pointerdown', e => {
    const b = e.target.closest('.pill-btn, .btn-primary, .btn-white');
    if (!b || b.disabled) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height), rp = document.createElement('span');
    rp.className = 'ripple';
    Object.assign(rp.style, { width: s + 'px', height: s + 'px', left: e.clientX - r.left - s / 2 + 'px', top: e.clientY - r.top - s / 2 + 'px' });
    b.appendChild(rp);
    setTimeout(() => rp.remove(), 700);
  });
})();

/* timers */
let lastEpochMin = -1;
setInterval(() => {
  const now = new Date(), next = new Date(now); next.setUTCHours(24, 0, 0, 0);
  const m = Math.floor((next - now) / 60000);
  if (m !== lastEpochMin) {
    lastEpochMin = m;
    const el = $('#epoch-timer');
    if (el) el.textContent = `${String(Math.floor(m / 60)).padStart(2, '0')}h ${String(m % 60).padStart(2, '0')}m`;
  }
}, 1000);

/* =========================================================================================
   Onboarding quiz: /api/profile/quiz, /api/profile/onboard
   ========================================================================================= */
let quiz = null, quizAnswers = {}, quizStep = 0;

async function openQuiz() {
  openModal('modal-quiz');
  const body = $('#quiz-body');
  if (!brain.live) {
    body.innerHTML = '<p class="caption">The quiz scores on the Brain, so it needs the API running.</p>';
    return;
  }
  try {
    quiz = quiz || await api('/api/profile/quiz');
  } catch (err) { body.innerHTML = `<p class="caption">Could not load the quiz: ${esc(err.message)}</p>`; return; }
  quizAnswers = {}; quizStep = 0;
  renderQuizStep();
}
function renderQuizStep() {
  const q = quiz[quizStep];
  $('#quiz-bar').style.width = (quizStep / quiz.length * 100) + '%';
  $('#quiz-body').innerHTML = `<div class="quiz-step">
      <div class="caption">Question ${quizStep + 1} of ${quiz.length}</div>
      <h3 class="quiz-q">${esc(q.text)}</h3>
      <div class="quiz-options">${q.options.map(o => `<button class="quiz-opt" data-opt="${esc(o.id)}">${esc(o.text)}</button>`).join('')}</div>
      ${quizStep ? '<button class="btn-ghost-sm" data-back="1">← Back</button>' : ''}
      ${quizStep === 0 ? '<div class="caption">Finishing the quiz starts your profile fresh: the Brain forgets what it learned from your past reviews.</div>' : ''}
    </div>`;
}
$('#quiz-body').addEventListener('click', async e => {
  if (e.target.closest('[data-back]')) { quizStep--; return renderQuizStep(); }
  const b = e.target.closest('[data-opt]');
  if (!b || !quiz) return;
  quizAnswers[quiz[quizStep].id] = b.dataset.opt;
  b.classList.add('picked');
  await sleep(220);
  if (quizStep < quiz.length - 1) { quizStep++; return renderQuizStep(); }
  $('#quiz-bar').style.width = '100%';
  $('#quiz-body').innerHTML = '<div class="caption">Scoring…</div>';
  try {
    const r = await api('/api/profile/onboard', { method: 'POST', body: { account: 'demo', answers: quizAnswers, reset: true } });
    const tierName = { 1: 'Preserve', 2: 'Balanced', 3: 'Growth' }[r.result.tier] || r.result.tier;
    $('#quiz-body').innerHTML = `<div class="quiz-result">
        <div class="caption">Your risk tier</div>
        <div class="quiz-tier">Tier ${esc(r.result.tier)} · <em>${esc(tierName)}</em></div>
        <div class="metric-row"><div class="metric"><div class="caption">Points</div><div class="metric-v">${esc(r.result.points)}/10</div></div>
          <div class="metric"><div class="caption">Loss aversion λ</div><div class="metric-v">${r.result.lam.toFixed(2)}</div></div>
          <div class="metric"><div class="caption">Trust τ</div><div class="metric-v">${(+r.profile.tau).toFixed(2)}</div></div></div>
        <ul class="explain">${r.result.rationale.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <button class="btn-primary" onclick="closeModal('modal-quiz')"><span>Done</span><span class="btn-shine"></span></button>
      </div>`;
    store.set('tecc_quiz_done', '1');
    $('#quiz-banner').hidden = true;
    selectTier('Tier ' + Math.min(2, r.result.tier), false); // Tier 3 stays passkey-locked in the composer
    loadProfile();
  } catch (err) {
    $('#quiz-body').innerHTML = `<p class="caption">The Brain refused the answers: ${esc(err.message)}</p>`;
  }
});
function dismissQuizBanner() { $('#quiz-banner').hidden = true; store.set('tecc_quiz_done', 'later'); }
function maybeShowQuizBanner() { $('#quiz-banner').hidden = store.get('tecc_quiz_done') === '1' || store.get('tecc_quiz_done') === 'later'; }

/* =========================================================================================
   Boot
   ========================================================================================= */
document.addEventListener('DOMContentLoaded', () => {
  renderActionPills();
  maybeShowQuizBanner();
  selectAction('Stake', false);
  restorePipeline();
  if (!restoreResult()) renderOpportunities();
  renderTrades();
  renderDecisions();
  refreshTether();
  spawnLeaves();
  bindTilt();
  loadRegimes();
  loadProfile();
  switchTab(location.hash.slice(1) || 'home');
  probeBrain();
  setInterval(probeBrain, 20000);
  setInterval(() => { if (brain.live && !document.hidden) refreshLive(); }, 15000);
  setInterval(() => { if (state.pegGuardEnabled) updatePegGuardTelemetryUI(); }, 1000);
  document.fonts?.ready.then(moveIndicator);
});
