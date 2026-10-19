/* Tec-C Command Center.
   Talks to the Brain API (FastAPI, agent/) when it is running; otherwise every screen falls back to demo data
   and says so. Point it at another server with ?api=http://host:port (remembered in localStorage). */

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
  el.dataset.v = to;
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
const isLoopbackApi = v => {
  try {
    const u = new URL(v);
    return /^https?:$/.test(u.protocol) && ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname) && !u.username && !u.password;
  } catch { return false; }
};
const API = (() => {
  const q = new URLSearchParams(location.search).get('api');
  if (q && isLoopbackApi(q)) store.set('tecc_api', new URL(q).origin);
  const saved = store.get('tecc_api');
  return isLoopbackApi(saved) ? new URL(saved).origin : 'http://127.0.0.1:8000';
})();
const brain = { live: false, checked: false };

async function api(path, { method = 'GET', body, timeout = 15000 } = {}) {
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
  try {
    const h = await api('/health', { timeout: 2500 });
    setBrainStatus(true, `live · v${h.version || '?'}`);
  } catch {
    setBrainStatus(false, 'demo mode');
  }
}
function setBrainStatus(live, text) {
  const changed = brain.live !== live || !brain.checked;
  brain.live = live; brain.checked = true;
  $('#brain-dot').className = 'dot ' + (live ? 'active' : 'warning');
  $('#top-heartbeat-text').textContent = text;
  $('#brain-pill').title = live ? `Connected to the Brain at ${API}` : `Brain not reachable at ${API}: showing demo data. Start it with: cd agent && .venv/bin/uvicorn tecc_brain.app:app`;
  if (changed) {
    loadRegimes();
    loadProfile();
    loadCatalog();
    maybeShowQuizBanner();
    if (live) showToast('Brain connected: commands now run through the real pipeline.');
  }
}

/* =========================================================================================
   Demo presets (used when the Brain is offline)
   ========================================================================================= */
const ACTIONS = ['Find opportunities', 'Invest', 'Stake', 'Swap', 'Rebalance', 'Reduce risk', 'Exit position', 'Park idle cash'];
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
      // the market's own assets stay first (PAXG for commodities); the venues' funding assets are added
      if (name && Array.isArray(m.assets)) MARKETS[name].assets = [...new Set([...MARKETS[name].assets, ...m.assets.map(String)])];
    }
    selectMarket(state.market, state.network, false);  // re-filter the pills with the live list
  } catch { /* keep the offline lists */ }
}

const DEMO_AGENTS = [
  { agent: 'gatekeeper_intake', title: 'Gatekeeper · intake', lines: ['Firewall: no injected instructions found.', 'Privacy sieve: amounts masked before any cloud model.'] },
  { agent: 'profile', title: 'Profile', lines: ['Balanced tier · loss aversion λ 1.00 · trust τ 0.60.'] },
  { agent: 'nlp_sentinel', title: 'NLP risk sentinel', lines: ['All pegs normal; no cluster under stress.'] },
  { agent: 'econometric_liquidity', title: 'Econometric & liquidity', lines: ['3 venues scored against the 1Y Shibor hurdle.'] },
  { agent: 'gatekeeper_aggregator', title: 'Gatekeeper · aggregator', lines: ['Soft tether: (0.5 + 0.5·τ) × radius remaining.'] },
  { agent: 'web3_executor', title: 'Web3 executor', lines: ['Waiting for your choice.'] },
];

/* =========================================================================================
   State
   ========================================================================================= */
const state = {
  action: 'Stake', market: 'Crypto', network: 'Ethereum L1', assets: ['ETH', 'stETH'], capitalPercent: 10, riskTier: 'Tier 2',
  vaultBalance: 48210, tetherUsed: 420, tetherTotal: 1000, biometricUnlocked: false, pegGuardEnabled: true,
  selectedCandidate: 'A', outcome: 'split', requestNo: 412, streak: 3,
  live: null, // last live /propose response
  trades: [
    { id: 1, title: 'Stake 0.4 ETH on Lido', time: '02:14 UTC', market: 'Crypto', val: 964, slippage: '0.08%', pnl: '+$3.20', tx: '0x9a4f…e1c8', status: 'pending', news: '+0.71', econ: '0.64' },
    { id: 2, title: 'Swap 500 USDC to PAXG', time: '03:40 UTC', market: 'Commodities', val: 500, slippage: '0.04%', pnl: '+$1.80', tx: '0x3c7b…41a2', status: 'pending', news: '+0.35', econ: '0.72' },
    { id: 3, title: 'Supply 1 ETH to Aave v3', time: '01:02 UTC', market: 'Crypto', val: 2410, slippage: '0.01%', pnl: '+$4.50', tx: '0x88f1…b902', status: 'ratified', news: '+0.55', econ: '0.70' },
  ],
};
const TRADE_STATUS = {
  pending: ['Pending review', 'badge-amber'], ratified: ['Ratified', 'badge-green'], flagged: ['Flagged (−20%)', 'badge-red'],
  taught: ['Reviewed & taught', 'badge-green'], penalized: ['Reviewed (−10%)', 'badge-amber'], breakout: ['FaceID breakout approved', 'badge-green'],
  simulated: ['Simulated (no chain)', 'badge-blue'],
  signing: ['Awaiting signature', 'badge-blue'], failed: ['Reverted by the vault', 'badge-red'], needs_faceid: ['Needs FaceID (over the radius)', 'badge-amber'],
};
const dollarsForCommand = () => Math.round(state.vaultBalance * state.capitalPercent / 100);
const tetherLeft = () => Math.max(0, state.tetherTotal - state.tetherUsed);

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
}

/* =========================================================================================
   Submit → Brain (live) or demo
   ========================================================================================= */
async function submitCommandToBrain(text) {
  const textGiven = !!text;
  const shown = text || commandText();
  text = text || brainText();
  const btn = $('#submit-btn');
  btn.disabled = true; btn.classList.add('loading');
  state.requestNo++;
  $('#request-id').textContent = `Request #${String(state.requestNo).padStart(4, '0')}`;
  try {
    if (brain.live && !textGiven) return await evaluateOptions(shown); // composer buttons → closed schema
    if (brain.live) {
      const headline = $('#headline-input').value.trim() || undefined;
      const [res] = await Promise.all([
        api('/api/mandate/propose', { method: 'POST', body: { text, account: 'demo', headline } }),
        sleep(300),
      ]);
      state.live = res; state.liveOptions = null;
      const blocked = res.status !== 'decided' || res.decision?.mode === 'BLOCKED';
      const agents = res.agents?.length ? res.agents : DEMO_AGENTS;
      await animatePipeline(agents, { blockedAt: blocked ? agents.length - 1 : -1 });
      renderLive(res, shown);
      if (res.status === 'unparsed') showToast(`The Brain didn't understand: ${(res.parse?.errors || []).join(', ')}. Try verbs like deposit, stake, grow, exit or withdraw.`);
      else if (blocked) showToast('The Brain refused this command. See the pipeline for why.');
      else { await sleep(350); switchTab('opportunities'); showToast(`The Brain rated ${res.decision.cards.length} route(s) and rejected ${res.decision.rejected.length}.`); }
    } else {
      state.live = null; state.liveOptions = null;
      await animatePipeline(DEMO_AGENTS);
      renderOpportunities();
      await sleep(300);
      switchTab('opportunities');
      showToast(`Demo: 3 routes rated for “${state.action}”. Start the Brain API for real results.`);
    }
  } catch (err) {
    showToast(`The Brain could not answer (${err.message}). Showing demo data.`);
    if (err.name === 'AbortError' || err.message === 'Failed to fetch') setBrainStatus(false, 'demo mode');
    state.live = null;
    renderOpportunities();
  } finally {
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

async function evaluateOptions(shown) {
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
  await animatePipeline(agents, { blockedAt: funded.length ? -1 : agents.length - 1 });
  renderOptions();
  await sleep(350);
  switchTab('opportunities');
  showToast(`${res.status.replace(/_/g, ' ').toLowerCase()}: ${funded.length} of ${res.results.length} option(s) funded.`);
}

function renderOptions() {
  const o = state.liveOptions;
  $('#source-badge').className = 'badge big badge-live';
  $('#source-badge').textContent = 'Live · injection-proof options';
  $('#opp-request-header').textContent = `“${o.shown}” · sent as ${o.options.length} structured option(s), no free text`;
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
  $('#sentiment-indicator').style.left = '75%';
  $('#rating-news-badge').textContent = 'Market snapshot';
  $('#rating-news-badge').className = 'badge badge-green';
  $('#headlines-list').innerHTML = `<li>${esc(o.trace[0] || '')}</li>`;
  $('#metric-sharpe').textContent = r.sharpe != null ? r.sharpe.toFixed(2) : '—';
  $('#metric-cvar95').textContent = r.cvar_95_pct != null ? '−' + r.cvar_95_pct.toFixed(1) + '%' : '—';
  $('#metric-cvar99').previousElementSibling.textContent = 'Funded';
  $('#metric-cvar99').textContent = usd(r.allocated_usd);
  $('#econ-badge').textContent = r.allocated_usd > 0 ? 'Funded' : 'Not funded';
  $('#econ-badge').className = 'badge ' + (r.allocated_usd > 0 ? 'badge-green' : 'badge-amber');
  $('#explain-list').innerHTML = r.reasons.map(x => `<li>${esc(x)}</li>`).join('') || '<li>Fully within your leash.</li>';
  $('#slippage-text').textContent = '';
  $('#inj-badge').textContent = 'Closed schema';
  $('#inj-badge').className = 'badge badge-green';
  $('#inj-checks').innerHTML = [
    ['Action is a closed enum, not text', ''],
    [`Asset “${esc(req.asset)}” must name a real asset`, ''],
    [`Amount is a bounded number: ${usd(req.amount_usd)}`, ''],
    [r.venue_id ? `Venue ${esc(r.venue_id)} is on the whitelist` : 'No whitelisted venue accepts this, so it was refused', r.venue_id ? '' : 'bad'],
    ['No free-text field reaches the Brain', ''],
  ].map(([l, c]) => `<li class="${c}">${l}</li>`).join('');
  const [mt] = OPT_MODE[r.mode] || [r.mode];
  $('#synthesis-badge').textContent = o.status.replace(/_/g, ' ');
  $('#synthesis-badge').className = 'badge ' + (o.intents.length ? 'badge-green' : 'badge-amber');
  const queued = o.intents.reduce((a, i) => a + i.amount_usd, 0);
  $('#synthesis-rationale').innerHTML = `<b>${esc(o.status.replace(/_/g, ' '))}</b> · option ${esc(r.option_id)} is <b>${esc(mt)}</b>. ${o.intents.length} intent(s) ready to sign, ${usd(queued)} inside today's soft tether.`;
  $('#trace-list').innerHTML = o.trace.map(t => `<li>${esc(t)}</li>`).join('');
  const btn = $('#btn-execute-trade');
  btn.style.display = o.intents.length ? '' : 'none';
  btn.firstElementChild.textContent = `Sign ${o.intents.length} intent(s) with the session key`;
}

function executeOptions() {
  const o = state.liveOptions;
  o.intents.forEach(i => {
    addTrade({
      title: `${i.action} ${i.asset_in} → ${i.venue_id}`, market: i.market, val: i.amount_usd,
      status: i.status === 'pending_signature' ? 'signing' : 'pending', news: '—', econ: '—',
      tx: i.tx_hash || 'awaiting signature', detail: 'From the injection-proof options flow.',
    });
    spendTether(Math.min(i.amount_usd, tetherLeft()));
  });
  showToast(`${o.intents.length} intent(s) queued for the session key. See Morning Review.`);
  state.liveOptions = { ...o, intents: [] };
  showOptionDetail();
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

function renderLive(res, text) {
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
  btn.firstElementChild.textContent = c ? (c.mode === 'BREAKOUT' ? `Approve ${c.label} with FaceID & execute` : `Execute ${c.label} · ${c.candidate.venue_id}`) : 'Execute';
}
$('#candidates-container').addEventListener('click', e => {
  const c = e.target.closest('[data-cand]'); if (!c) return;
  state.selectedCandidate = c.dataset.cand;
  $$('#candidates-container .cand').forEach(x => x.classList.toggle('chosen', x === c));
  state.liveOptions ? showOptionDetail() : state.live ? showLiveDetail() : renderOpportunities(false);
  showToast(`Inspecting ${state.live ? c.dataset.cand.split(':')[1] : 'option ' + c.dataset.cand}`);
});

/* =========================================================================================
   Opportunities — demo rendering
   ========================================================================================= */
function renderOpportunities(rebuild = true) {
  const p = ACTION_PRESETS[state.action] || ACTION_PRESETS.Stake, d = dollarsForCommand();
  $('#source-badge').className = 'badge big badge-blue';
  $('#source-badge').textContent = brain.live ? 'Demo preset' : 'Demo data · Brain offline';
  $('#opp-request-header').textContent = `Request #${String(state.requestNo).padStart(4, '0')} · ${commandText()}`;
  $('#opp-count').textContent = p.candidates.length;
  if (rebuild) {
    $('#candidates-container').innerHTML = p.candidates.map(c => `
      <button class="card glass cand ${c.id === state.selectedCandidate ? 'chosen' : ''}" data-cand="${c.id}" data-tilt>
        <div class="row-between"><span class="badge ${c.cls}">${esc(c.badge)}</span><span class="caption">Option ${c.id}</span></div>
        <div class="cand-title">${esc(c.title)}</div>
        <div class="cand-info">${esc(c.info)} · ${usd(d)}</div>
        <div class="mini-badges"><span class="badge">News ${esc(c.news)}</span><span class="badge">Econ ${esc(c.econ)}</span><span class="badge ${c.inj === 'Warn' ? 'badge-amber' : ''}">Injection ${esc(c.inj)}</span></div>
        <div class="cand-score"><b>${c.score.toFixed(2)}</b><span class="caption">weighted score</span></div>
        ${scoreRing(c.score)}
      </button>`).join('');
    fillRings();
    bindTilt();
  }
  const c = p.candidates.find(x => x.id === state.selectedCandidate) || p.candidates[0];
  $('#zone-b-title').textContent = `Zone B · Deep rating for option ${c.id}: ${c.title}`;
  $('#rating-news-badge').textContent = `${c.news} ${p.newsScore > 0 ? 'positive' : 'cautious'}`;
  $('#rating-news-badge').className = 'badge ' + (p.newsScore > 0 ? 'badge-green' : 'badge-red');
  $('#sentiment-indicator').style.left = ((p.newsScore + 1) / 2 * 100) + '%';
  $('#headlines-list').innerHTML = p.headlines.map(h => `<li>${esc(h)}</li>`).join('');
  $('#metric-sharpe').textContent = p.sharpe.toFixed(2);
  $('#metric-cvar95').textContent = (p.cvar95 ? '−' + Math.abs(p.cvar95).toFixed(1) : '0.0') + '%';
  $('#metric-cvar99').textContent = (p.cvar99 ? '−' + Math.abs(p.cvar99).toFixed(1) : '0.0') + '%';
  $('#metric-cvar99').previousElementSibling.textContent = 'CVaR 99%';
  $('#econ-badge').textContent = 'Acceptable'; $('#econ-badge').className = 'badge badge-green';
  $('#explain-list').innerHTML = '';
  updateSlippage(d);
  $('#inj-badge').textContent = c.inj === 'Warn' ? 'Warning' : 'Pass · 0 threats';
  $('#inj-badge').className = 'badge ' + (c.inj === 'Warn' ? 'badge-amber' : 'badge-green');
  $('#inj-checks').innerHTML = ['Venue is on the mandate\'s policy whitelist', 'Honeypot test: clean, verified contract', 'Contract age: battle-tested',
    `Amount matches the mandate (${usd(d)})`, 'Instruction scan: zero prompt-override keywords']
    .map((l, i) => `<li class="${c.inj === 'Warn' && i === 1 ? 'warn' : ''}">${esc(l)}</li>`).join('');
  $('#trace-list').innerHTML = '';
  applyOutcomeMode(state.outcome, false);
}

/* outcome modes (demo) */
$('#outcome-modes').addEventListener('click', e => { const b = e.target.closest('[data-mode]'); if (b) applyOutcomeMode(b.dataset.mode, true); });
function applyOutcomeMode(mode, toast) {
  state.outcome = mode;
  $$('#outcome-modes .pill-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  if (state.live) { if (toast) showToast('Live decisions come from the Brain; modes are a demo control.'); return; }
  const p = ACTION_PRESETS[state.action], c = p.candidates.find(x => x.id === state.selectedCandidate) || p.candidates[0];
  const d = dollarsForCommand(), use = Math.min(d, tetherLeft());
  const badge = $('#synthesis-badge'), btn = $('#btn-execute-trade'), r = $('#synthesis-rationale');
  btn.style.display = '';
  const M = {
    split: ['Autonomous split 70/30', 'badge-green', `${esc(c.rationale)}<br><b>Plan:</b> ${usd(d * 0.7)} to option A and ${usd(d * 0.3)} to option B, ${usd(use)} of today's ${usd(tetherLeft())} radius.`, `Execute the split (${usd(d)})`],
    single: ['Single best route', 'badge-green', `${esc(c.rationale)}<br><b>Plan:</b> 100% (${usd(d)}) into option A.`, `Execute option A (${usd(d)})`],
    idle: ['Do nothing', 'badge-amber', 'The risk-adjusted spread does not clear the hurdle after costs. The Brain stays in cash until spreads widen.', ''],
    breakout: ['Needs FaceID breakout', 'badge-red', `The size exceeds today's radius. Execution waits for your phone's FaceID.`, 'Request a FaceID breakout'],
  }[mode];
  badge.textContent = M[0]; badge.className = 'badge ' + M[1];
  r.innerHTML = M[2];
  if (mode === 'idle') btn.style.display = 'none';
  else btn.firstElementChild.textContent = M[3];
  if (toast) showToast(`Outcome mode: ${M[0]}`);
}

/* agent weights */
const agentWeights = { news: 30, econ: 45, inj: 25 };
$$('[data-weight]').forEach(r => r.addEventListener('input', () => {
  agentWeights[r.dataset.weight] = +r.value;
  $(`#weight-${r.dataset.weight}-val`).textContent = r.value + '%';
}));
$$('[data-weight]').forEach(r => r.addEventListener('change', () => showToast(`Agent weights: news ${agentWeights.news}%, econometrics ${agentWeights.econ}%, injection ${agentWeights.inj}%`)));

/* =========================================================================================
   Execute
   ========================================================================================= */
async function executeAutonomousTrade() {
  if (state.liveOptions) return executeOptions();
  if (state.live?.decision && state.live.proposal_id) return executeLive();
  if (state.outcome === 'breakout') return openBreakoutModal(4500, 120);
  const d = dollarsForCommand(), use = Math.min(d, tetherLeft());
  if (d > tetherLeft()) { showToast(`${usd(d)} is above the ${usd(tetherLeft())} left today: FaceID breakout needed.`); return openBreakoutModal(d, Math.round(d * 0.02)); }
  spendTether(use);
  addTrade({ title: `${state.action} ${state.assets.join('/') || ''} · ${state.market}`, market: state.market, val: d, status: 'pending', news: '+0.70', econ: '0.75', tx: fakeTx() });
  showToast(`Demo: ${usd(d)} ${state.action.toLowerCase()} signed with the session key inside the leash.`);
}
async function executeLive() {
  const res = state.live, d = res.decision;
  const c = d.cards.find(x => x.label + ':' + x.candidate.venue_id === state.selectedCandidate) || d.cards[0];
  if (c.mode === 'BREAKOUT' && !state.biometricUnlocked) {
    pendingLiveBreakout = true;
    return openBreakoutModal(c.candidate.amount_usd, null);
  }
  const btn = $('#btn-execute-trade');
  btn.disabled = true; btn.classList.add('loading');
  try {
    const out = await api('/api/mandate/execute', { method: 'POST', body: { proposal_id: res.proposal_id, account: 'demo', label: c.label, venue_id: c.candidate.venue_id } });
    const it = out.intent || {};
    const status = { submitted: 'pending', signed: 'pending', pending_signature: 'signing', simulated: 'simulated', failed: 'failed', breakout_required: 'needs_faceid' }[it.status] || 'pending';
    addTrade({ title: `${c.candidate.action} ${c.candidate.asset_in} → ${c.candidate.venue_id}`, market: it.market || state.market, val: it.amount_usd ?? c.candidate.amount_usd,
      status, news: '—', econ: (c.candidate.score?.total * 100 || 0).toFixed(2) + '%', tx: it.tx_hash || 'no hash (simulated)', detail: it.detail });
    if (it.status === 'submitted') spendTether(Math.min(it.amount_usd || 0, tetherLeft()));
    (out.learned || []).forEach(l => showToast('Learned: ' + l));
    showToast(out.message || `Execution ${it.status}`);
    state.live = { ...res, proposal_id: null }; // a proposal executes once
    btn.firstElementChild.textContent = 'Executed ✓';
  } catch (err) {
    showToast(`Execution refused: ${err.message}`);
  } finally { btn.disabled = false; btn.classList.remove('loading'); }
}
const fakeTx = () => '0x' + Math.random().toString(16).slice(2, 6) + '…' + Math.random().toString(16).slice(2, 6);
function spendTether(amount) { state.tetherUsed += amount; refreshTether(); }
function refreshTether() {
  const used = Math.min(100, Math.round(state.tetherUsed / state.tetherTotal * 100));
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
function setLeash(total, msg) {
  state.tetherTotal = Math.max(100, Math.min(2500, Math.round(total)));
  refreshTether();
  if (msg) showToast(msg.replace('{t}', usd(state.tetherTotal)));
}

/* =========================================================================================
   Morning review
   ========================================================================================= */
function addTrade(t) {
  state.trades.unshift({ id: Date.now(), time: 'just now', slippage: '0.04%', pnl: '+$0.00', fresh: true, ...t });
  renderTrades();
}
function renderTrades() {
  $('#trades-list').innerHTML = state.trades.map(t => {
    const [txt, cls] = TRADE_STATUS[t.status] || TRADE_STATUS.pending;
    return `<div class="card glass trade ${t.fresh ? 'fresh' : ''}" data-id="${t.id}">
      <div class="row-between" style="align-items:flex-start;flex-wrap:wrap">
        <div><div class="trade-title">${esc(t.title)}</div><div class="caption">Executed ${esc(t.time)} · ${esc(t.market)} · ${usd(t.val)}</div></div>
        <span class="badge ${cls}">${txt}</span>
      </div>
      <div class="row-wrap small">
        <span class="badge">News ${esc(t.news)}</span><span class="badge">Econ ${esc(t.econ)}</span><span class="badge">Slippage ${esc(t.slippage)}</span>
        <span class="badge badge-green">P&amp;L ${esc(t.pnl)}</span><span class="tx">tx ${esc(t.tx)}</span>
      </div>
      ${t.detail ? `<div class="caption">${esc(t.detail)}</div>` : ''}
      ${t.note ? `<div class="note-line">“${esc(t.note)}”</div>` : ''}
      ${t.status === 'pending' ? `<div class="trade-actions">
        <button class="pill-btn good" data-act="ratify">＋ Like &amp; ratify</button>
        <button class="pill-btn danger" data-act="flag">✕ Flag (−20%)</button>
        <button class="pill-btn strong" data-act="note">¶ Note &amp; teach</button>
      </div>` : ''}
    </div>`;
  }).join('');
  const pending = state.trades.filter(t => t.status === 'pending').length;
  $('#review-badge').textContent = pending;
  $('#top-pending-badge').textContent = pending;
  $('#widget-pending-reviews').innerHTML = `${pending} <small>pending</small>`;
  $('#review-total-trades').textContent = state.trades.length;
  $('#review-progress').textContent = `${state.trades.length - pending} of ${state.trades.length}`;
  $('#review-capital-moved').textContent = usd(state.trades.reduce((s, t) => s + (+t.val || 0), 0));
  $('#streak-bar').innerHTML = Array.from({ length: 5 }, (_, i) => `<i class="${i < state.streak ? 'on' : ''}"></i>`).join('');
  $('#streak-text').textContent = `${Math.min(5, state.streak)} of 5${state.streak >= 3 ? ' · eligible for a +10% step-up' : ''}`;
  state.trades.forEach(t => { t.fresh = false; });
}
$('#trades-list').addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const id = +b.closest('.trade').dataset.id, t = state.trades.find(x => x.id === id);
  if (b.dataset.act === 'ratify') {
    t.status = 'ratified'; state.streak = Math.min(5, state.streak + 1);
    sendFeedback(t, 'ratify');
    renderTrades();
    if (state.trades.every(x => x.status !== 'pending')) setLeash(state.tetherTotal * 1.1, 'All reviewed: daily leash +10% to {t}.');
    else showToast('Ratified: +1 toward the next leash step-up.');
  } else if (b.dataset.act === 'flag') {
    t.status = 'flagged'; state.streak = 0;
    sendFeedback(t, 'flag');
    renderTrades();
    setLeash(state.tetherTotal * 0.8, 'Flagged: daily leash contracted 20% to {t}.');
  } else openNoteModal(id);
});
function sendFeedback(t, signal, note) {
  // The Brain learns from review events when it is live; venue ids only exist for live trades, so demo trades stay local.
  if (!brain.live || !t.title.includes('→')) return;
  const venue = t.title.split('→')[1].trim();
  api('/api/review/sync', { method: 'POST', body: { account: 'demo', events: [{ event_id: `ui:${t.id}:${signal}`, signal, venue_id: venue, amount_usd: +t.val || 0, at: new Date().toISOString(), note }] } })
    .then(r => { const ch = r?.results?.[0]?.changes || []; showToast(`Brain learned from your ${signal}${ch.length ? ': ' + ch[0] : ''}.`); loadProfile(); })
    .catch(() => { /* review sync is best-effort from the UI */ });
}
function ratifyAllRemaining() {
  const n = state.trades.filter(t => t.status === 'pending').length;
  if (!n) return showToast('Nothing left to review.');
  state.trades.forEach(t => { if (t.status === 'pending') { t.status = 'ratified'; sendFeedback(t, 'ratify'); } });
  state.streak = Math.min(5, state.streak + n);
  renderTrades();
  setLeash(state.tetherTotal * 1.1, `${n} ratified: daily leash +10% to {t}.`);
}

/* notes */
let noteTradeId = null;
function openNoteModal(id) {
  noteTradeId = id;
  const t = state.trades.find(x => x.id === id);
  $('#note-text-input').value = t?.note || 'Lido is fine, but prefer Rocket Pool (rETH) when the yield gap is under 0.2%.';
  $('#note-penalty-check').checked = false;
  updateNoteWordCount($('#note-text-input').value);
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
  const t = state.trades.find(x => x.id === noteTradeId);
  closeModal('modal-note');
  if (t) { t.status = pen ? 'penalized' : 'taught'; t.note = text; sendFeedback(t, pen ? 'note_penalty' : 'note', text); renderTrades(); }
  if (pen) setLeash(state.tetherTotal * 0.9, 'Note learned · leash −10% to {t}.');
  else showToast('Note learned: the firewall read it first, then protocol preferences were updated.');
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
const NETWORK_NAME = { anvil: 'Local test chain (Anvil)', sepolia: 'Ethereum Sepolia', arbitrum: 'Arbitrum', fisco: 'FISCO BCOS' };
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
    $('#deposit-qr').innerHTML = '<div class="qr-empty">QR</div>';
    $('#deposit-addr').textContent = brain.live ? 'No vault deployed yet. Run ./dev_up.sh to deploy one.' : 'Your vault address appears when the Brain is connected to your vault (./dev_up.sh).';
    $('#btn-copy-addr').disabled = true;
    $('#deposit-accepts').textContent = '';
    return;
  }
  sel.disabled = false;
  sel.innerHTML = `<option value="${esc(v.network)}">${esc(NETWORK_NAME[v.network] || v.network)} · chain ${esc(v.chain_id)}</option>`;
  $('#deposit-qr').innerHTML = safeSvg(v.deposit_qr_svg) || '<div class="qr-empty">QR</div>';
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
  const btn = $('#btn-withdraw-faceid'), amt = Math.max(0, parseInt($('#withdraw-amount').value, 10) || 0);
  if (amt > state.vaultBalance) return showToast('That is more than the vault holds.');
  btn.disabled = true; btn.firstElementChild.textContent = 'Verifying FaceID…';
  await faceIdScan($('#faceid-w'));
  btn.disabled = false; btn.firstElementChild.textContent = 'Scan FaceID & transfer';
  closeModal('modal-withdraw');
  $('#faceid-w').classList.remove('ok');
  setVault(state.vaultBalance - amt);
  setBiometric(true);
  showToast(`Passkey verified: ${usd(amt)} sent to your external wallet.`);
}
let breakoutTimer = null, pendingLiveBreakout = false;
function openBreakoutModal(val, profit) {
  $('#breakout-trade-val').textContent = usd(val);
  $('#breakout-trade-profit').textContent = profit == null ? 'an edge the Brain rated' : '+' + usd(profit);
  $('#modal-breakout').dataset.val = val;
  $('#modal-breakout').dataset.profit = profit ?? 0;
  let s = 30;
  $('#breakout-countdown').textContent = s;
  clearInterval(breakoutTimer);
  openModal('modal-breakout');
  breakoutTimer = setInterval(() => {
    s--; $('#breakout-countdown').textContent = s;
    if (s <= 0) { closeModal('modal-breakout'); pendingLiveBreakout = false; showToast('Breakout window expired: the opportunity was skipped.'); }
  }, 1000);
}
async function approveBreakoutTrade() {
  const m = $('#modal-breakout'), box = $('.faceid', m);
  clearInterval(breakoutTimer);
  await faceIdScan(box);
  closeModal('modal-breakout');
  box.classList.remove('ok');
  setBiometric(true);
  if (pendingLiveBreakout) { pendingLiveBreakout = false; return executeLive(); }
  const val = +m.dataset.val, profit = +m.dataset.profit;
  addTrade({ title: `Flash arbitrage ${usd(val)} stablecoin spread`, market: 'Arbitrum', val, status: 'breakout', pnl: '+' + usd(profit), news: '+0.88', econ: '0.94', tx: fakeTx() });
  showToast(`FaceID approved: ${usd(val)} breakout done, +${usd(profit)} captured.`);
}
function setBiometric(on) {
  state.biometricUnlocked = on;
  $('#bio-dot').className = 'dot ' + (on ? 'active' : 'locked');
  $('#bio-status-text').textContent = on ? 'Unlocked (5m)' : 'Locked';
  clearTimeout(setBiometric.t);
  if (on) setBiometric.t = setTimeout(() => setBiometric(false), 5 * 60 * 1000);
}
function toggleBiometricWindow() {
  setBiometric(!state.biometricUnlocked);
  showToast(state.biometricUnlocked ? 'FaceID verified: 5-minute breakout window open.' : 'Biometric window locked.');
}

/* =========================================================================================
   Home widgets
   ========================================================================================= */
function togglePegGuardArbitrage() {
  state.pegGuardEnabled = $('#arb-toggle').checked;
  $('#arb-status-badge').textContent = state.pegGuardEnabled ? 'Active' : 'Paused';
  $('#arb-status-badge').className = 'badge ' + (state.pegGuardEnabled ? 'badge-amber' : 'badge-red');
  $('#arb-state-text').textContent = state.pegGuardEnabled ? 'Enabled' : 'Idle';
  $('#arb-state-text').className = state.pegGuardEnabled ? 'txt-green' : 'muted';
  renderPegGuardNote();
  showToast(state.pegGuardEnabled ? 'PegGuard on: guarding every peg in the background.' : 'PegGuard off.');
}
function renderPegGuardNote() {
  $('#pegguard-note').innerHTML = state.pegGuardEnabled
    ? '🛡 <b>PegGuard is on</b> and guards every peg in the background. It isn\'t a market you pick.'
    : '🛡 PegGuard is off. Switch it on in the PegGuard card to guard pegs in the background.';
}
function executeWatchdogDerisk() {
  const card = $('#watchdog-alert-card');
  card.classList.add('ok');
  $('#watchdog-alert-badge').className = 'badge badge-green';
  $('#watchdog-alert-badge').textContent = 'De-risked';
  $('#watchdog-alert-desc').innerHTML = '<b>Done:</b> $1,060 (10% of the e-CNY MMF) moved into USDC on Arbitrum.';
  $('#watchdog-alert-actions').innerHTML = '<span class="txt-green small"><b>✓ Position guarded</b></span>';
  showToast('Watchdog: $1,060 moved from the e-CNY MMF into USDC.');
}
function dismissWatchdogAlert() {
  const c = $('#watchdog-alert-card');
  c.style.opacity = '0'; c.style.transform = 'translateX(30px)';
  setTimeout(() => { c.outerHTML = '<div class="caption">No active alerts. The forest is quiet.</div>'; }, 450);
  showToast('Alert dismissed.');
}
async function triggerManualWatchdog() {
  showToast('Emergency sweep across every holding…');
  if (brain.live) {
    try {
      const r = await api('/trigger_hourly_monitor', { method: 'POST', body: { accounts: ['demo'], scenario } });
      showToast(r.triggered.length ? `Sweep: ${r.triggered.length} position(s) need re-evaluation.` : `Sweep done: ${r.checked.length} account(s) checked, every peg calm.`);
      return;
    } catch { /* fall through to the demo answer */ }
  }
  await sleep(1300);
  showToast('Sweep complete: every peg at parity, no new alerts.');
}

/* =========================================================================================
   Portfolio: trend, regimes, headline sandbox, scans
   ========================================================================================= */
function drawTrend(range = $('#range-seg .active')?.dataset.range || '24h') {
  const n = { '24h': 24, '7d': 42, '30d': 60 }[range];
  let seed = { '24h': 7, '7d': 13, '30d': 29 }[range], v = 30;
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  const pts = Array.from({ length: n }, (_, i) => { v += (rnd() - 0.38) * 16; v = Math.max(12, Math.min(108, v)); return [i * 500 / (n - 1), 120 - v]; });
  const path = pts.map((p, i) => {
    if (!i) return `M${p[0]} ${p[1]}`;
    const q = pts[i - 1], cx = (q[0] + p[0]) / 2;
    return `C${cx} ${q[1]} ${cx} ${p[1]} ${p[0]} ${p[1]}`;
  }).join(' ');
  const line = $('#trend-line');
  line.setAttribute('d', path);
  $('#trend-fill').setAttribute('d', path + ' L500 120 L0 120 Z');
  line.style.animation = 'none'; void line.getBBox(); line.style.animation = '';
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

const DEMO_REGIMES = {
  demo: { USDC: [0.975, 0.023, 0.002], USDT: [0.972, 0.026, 0.002], DAI: [0.974, 0.023, 0.003], stETH: [0.974, 0.024, 0.002], PAXG: [0.976, 0.023, 0.001] },
  usdc_distress: { USDC: [0.18, 0.67, 0.15], USDT: [0.88, 0.11, 0.01], DAI: [0.42, 0.49, 0.09], stETH: [0.95, 0.045, 0.005], PAXG: [0.97, 0.028, 0.002] },
};
let scenario = 'demo';
async function loadRegimes() {
  let rows, src;
  if (brain.live) {
    try {
      const r = await api('/api/risk/regimes?scenario=' + scenario);
      rows = Object.values(r.regimes).map(x => [x.symbol, x.p_normal, x.p_distress, x.p_failure, x.regime]);
      src = `Live · ${r.source} · hurdle ${pct(r.hurdle_rate, 2)}`;
    } catch { /* demo below */ }
  }
  if (!rows) {
    rows = Object.entries(DEMO_REGIMES[scenario]).map(([s, p]) => [s, ...p, p[0] > 0.8 ? 'normal' : p[2] > 0.1 ? 'failure' : 'distress']);
    src = 'Demo regimes (Brain offline)';
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
function renderScans() {
  const kinds = Array(24).fill('active'); kinds[4] = 'warning'; kinds[22] = 'danger';
  $('#scan-dots').innerHTML = kinds.map((k, i) => `<span class="dot ${k}" style="animation-delay:${i * 30}ms" title="${k === 'active' ? 'clean' : k === 'warning' ? 'market signal' : 'negative news'}"></span>`).join('');
}

/* =========================================================================================
   Settings: profile + hold-to-revoke killswitch
   ========================================================================================= */
async function loadProfile() {
  let p = { tier: 2, lam: 1.0, tau: 0.6, soft_limit_usd: 400 }, src = 'demo';
  if (brain.live) { try { p = { ...p, ...(await api('/api/profile/demo')) }; src = 'live'; } catch { /* keep demo */ } }
  $('#profile-source').textContent = src;
  $('#profile-source').className = 'badge ' + (src === 'live' ? 'badge-live' : 'badge-blue');
  const tierName = { 1: 'Preserve', 2: 'Balanced', 3: 'Growth' }[p.tier] || p.tier;
  $('#profile-grid').innerHTML = [
    ['Risk tier', `${p.tier} · ${tierName}`], ['Loss aversion λ', (+p.lam).toFixed(2)],
    ['Trust τ', (+p.tau).toFixed(2)], ['Soft limit', p.soft_limit_usd != null ? usd(p.soft_limit_usd) : '—'],
  ].map(([k, v]) => `<div class="metric"><div class="caption">${k}</div><div class="metric-v">${esc(v)}</div></div>`).join('');
}
(() => {
  const b = $('#killswitch'), fill = $('.hold-fill', b);
  let t0 = 0, raf = 0;
  const reset = () => { cancelAnimationFrame(raf); fill.style.width = '0'; };
  const step = now => {
    const p = Math.min(1, (now - t0) / 1600);
    fill.style.width = p * 100 + '%';
    if (p < 1) raf = requestAnimationFrame(step);
    else { reset(); $('.hold-label', b).textContent = 'Session key revoked ✓'; b.disabled = true; showToast('Killswitch: the AI session key is revoked. Nothing can move until you issue a new mandate.'); }
  };
  b.addEventListener('pointerdown', () => { t0 = performance.now(); raf = requestAnimationFrame(step); });
  ['pointerup', 'pointerleave', 'pointercancel'].forEach(ev => b.addEventListener(ev, reset));
})();

/* =========================================================================================
   QR, toasts, ambience
   ========================================================================================= */
function renderQR() {
  const N = 21, finder = (x, y) => [[0, 0], [N - 7, 0], [0, N - 7]].some(([fx, fy]) => {
    const dx = x - fx, dy = y - fy;
    return dx >= 0 && dx < 7 && dy >= 0 && dy < 7 && (dx === 0 || dx === 6 || dy === 0 || dy === 6 || (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4));
  });
  const inFinderZone = (x, y) => (x < 8 && y < 8) || (x > N - 9 && y < 8) || (x < 8 && y > N - 9);
  let seed = 42; const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  let html = '';
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const on = inFinderZone(x, y) ? finder(x, y) : r() > 0.52;
    html += `<i class="${on ? '' : 'o'}" style="animation-delay:${(x + y) * 12}ms"></i>`;
  }
  $('#qr').innerHTML = html;
}
function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  $('#toast-container').appendChild(t);
  const all = $$('#toast-container .toast'); if (all.length > 4) all[0].remove();
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 400); }, 3800);
}

function spawnLeaves() {
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
  if (!matchMedia('(hover: hover)').matches) return;
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
  const glow = $('#cursor-glow'), bg = $('.bg-photo');
  let raf = 0, ev = null;
  addEventListener('mousemove', e => {
    ev = e;
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      glow.style.transform = `translate(${ev.clientX}px, ${ev.clientY}px)`;
      const g = ev.target.closest?.('.glass');
      if (g) { const r = g.getBoundingClientRect(); g.style.setProperty('--gx', ev.clientX - r.left + 'px'); g.style.setProperty('--gy', ev.clientY - r.top + 'px'); }
    });
  });
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
let watchdogLeft = 38 * 60 + 10;
setInterval(() => {
  watchdogLeft = watchdogLeft > 0 ? watchdogLeft - 1 : 3600;
  $('#watchdog-timer').textContent = `${Math.floor(watchdogLeft / 60)}:${String(watchdogLeft % 60).padStart(2, '0')}`;
  const now = new Date(), next = new Date(now); next.setUTCHours(24, 0, 0, 0);
  const m = Math.floor((next - now) / 60000);
  $('#epoch-timer').textContent = `${String(Math.floor(m / 60)).padStart(2, '0')}h ${String(m % 60).padStart(2, '0')}m`;
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
  renderPegGuardNote();
  maybeShowQuizBanner();
  selectAction('Stake', false);
  renderPipeline(DEMO_AGENTS, ['done', 'done', 'done', 'running', '', '']);
  renderTrades();
  renderScans();
  renderQR();
  refreshTether();
  spawnLeaves();
  bindTilt();
  loadRegimes();
  loadProfile();
  switchTab(location.hash.slice(1) || 'home');
  probeBrain();
  setInterval(probeBrain, 20000);
  document.fonts?.ready.then(moveIndicator);
});
