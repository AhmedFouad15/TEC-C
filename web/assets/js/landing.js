/* Tec-C landing interactions: preloader, jaguar slider, cursor, reveals, scroll effects, fireflies. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = matchMedia('(hover: hover)').matches;

  /* ---------- split headlines into animated letters ---------- */
  $$('[data-split]').forEach(h => {
    const lines = h.innerHTML.split(/<br\s*\/?>/i);
    let i = 0;
    h.innerHTML = lines.map(line => line.trim().split(/\s+/).map(word =>
      `<span class="w">${[...word].map(c => `<span class="ch" style="transition-delay:${0.35 + (i++) * 0.035}s">${c}</span>`).join('')}</span>`
    ).join(' ')).join('<br>');
  });

  /* ---------- preloader ---------- */
  const pre = $('#preloader'), num = $('#pre-num'), bar = $('#pre-bar');
  const imgs = $$('img');
  let loaded = 0, shown = 0;
  const bump = () => { loaded++; };
  imgs.forEach(im => (im.complete ? bump() : (im.addEventListener('load', bump), im.addEventListener('error', bump))));
  const t0 = performance.now();
  (function tick() {
    const target = Math.min(100, Math.round((loaded / imgs.length) * 100));
    const minTime = Math.min(100, (performance.now() - t0) / 14); // never faster than ~1.4s, so the eyes get to blink
    shown += (Math.min(target, minTime) - shown) * 0.12 + 0.2;
    shown = Math.min(shown, 100);
    num.textContent = Math.floor(shown);
    bar.style.width = shown + '%';
    if (shown >= 99.5 || performance.now() - t0 > 6000) finish();
    else requestAnimationFrame(tick);
  })();
  let finished = false;
  function finish() {
    if (finished) return;
    finished = true;
    num.textContent = 100; bar.style.width = '100%';
    setTimeout(() => { pre.classList.add('done'); document.body.classList.remove('is-loading'); startSlider(); onScroll(); }, 250);
  }
  setTimeout(finish, 6500); // never trap anyone behind the preloader
  // seen it already this session (or ?skip for screenshots): straight in
  let seen = false;
  try { seen = sessionStorage.getItem('tecc_seen') === '1'; sessionStorage.setItem('tecc_seen', '1'); } catch { /* storage blocked */ }
  if (seen || new URLSearchParams(location.search).has('skip')) { pre.style.transition = 'none'; finish(); }
  const seqAt = parseFloat(new URLSearchParams(location.search).get('seq')); // e.g. ?seq=0.4 to inspect the run
  if (seqAt >= 0 && seqAt <= 1) setTimeout(() => { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, innerHeight * 0.05 + seqAt * ($('#hero-track').offsetHeight - innerHeight)); onScroll(); }, 400);
  const jumpTo = new URLSearchParams(location.search).get('at'); // deep link into a section, e.g. ?at=senses
  if (jumpTo && /^[a-z-]+$/.test(jumpTo)) setTimeout(() => { const el = document.getElementById(jumpTo); if (el) { document.documentElement.style.scrollBehavior = 'auto'; scrollTo(0, el.offsetTop); onScroll(); } }, 400);

  /* ---------- slider ---------- */
  const slides = $$('.slide'), dots = $$('.si');
  const DURATION = 7000;
  let cur = 0, timer = null, startedAt = 0, raf = null, transitioning = false;

  function go(n) {
    n = (n + slides.length) % slides.length;
    if (n === cur) return;
    const prev = slides[cur];
    prev.classList.remove('is-active');
    prev.classList.add('is-leaving');
    setTimeout(() => prev.classList.remove('is-leaving'), 1400);
    slides[n].classList.add('is-active');
    dots.forEach((d, i) => d.classList.toggle('is-active', i === n));
    cur = n;
    restart();
  }
  function progress() {
    const p = Math.min(1, (performance.now() - startedAt) / DURATION);
    const fill = dots[cur].querySelector('.si-track i');
    dots.forEach(d => { if (d !== dots[cur]) d.querySelector('.si-track i').style.height = '0'; });
    fill.style.height = (p * 100) + '%';
    raf = requestAnimationFrame(progress);
  }
  function restart() {
    clearTimeout(timer); cancelAnimationFrame(raf);
    if (reduced || transitioning) return;
    startedAt = performance.now();
    timer = setTimeout(() => go(cur + 1), DURATION);
    progress();
  }
  function startSlider() { restart(); }
  dots.forEach(d => d.addEventListener('click', () => go(+d.dataset.go)));
  addEventListener('keydown', e => {
    if (scrollY > innerHeight * 0.6) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') go(cur + 1);
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') go(cur - 1);
  });
  let touchX = null;
  const hero = $('#hero');
  hero.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; }, { passive: true });
  hero.addEventListener('touchend', e => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) go(cur + (dx < 0 ? 1 : -1));
    touchX = null;
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(timer); cancelAnimationFrame(raf); } else restart(); });

  /* ---------- cursor, spotlight, parallax, magnetic ---------- */
  const dot = $('#cursor-dot'), ring = $('#cursor-ring'), spot = $('#spotlight');
  let mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
  addEventListener('mousemove', e => {
    mx = e.clientX; my = e.clientY;
    if (e.clientY < hero.offsetHeight) {
      spot.style.setProperty('--mx', mx + 'px');
      spot.style.setProperty('--my', my + 'px');
      const px = ((mx / innerWidth) - 0.5) * -24, py = ((my / innerHeight) - 0.5) * -16;
      $$('.slide-media img').forEach(im => { im.style.setProperty('--px', px + 'px'); im.style.setProperty('--py', py + 'px'); });
    }
  });
  if (finePointer) {
    (function follow() {
      rx += (mx - rx) * 0.18; ry += (my - ry) * 0.18;
      dot.style.transform = `translate(${mx}px, ${my}px)`;
      ring.style.transform = `translate(${rx}px, ${ry}px)`;
      requestAnimationFrame(follow);
    })();
    $$('a, button, [data-tilt]').forEach(el => {
      el.addEventListener('mouseenter', () => ring.classList.add('hover'));
      el.addEventListener('mouseleave', () => ring.classList.remove('hover'));
    });
    $$('[data-magnetic]').forEach(el => {
      el.addEventListener('mousemove', e => {
        const r = el.getBoundingClientRect();
        el.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.25}px, ${(e.clientY - r.top - r.height / 2) * 0.35}px)`;
      });
      el.addEventListener('mouseleave', () => { el.style.transform = ''; });
      el.style.transition = 'transform .4s cubic-bezier(.16,1,.3,1), background .3s, box-shadow .3s, color .3s';
    });
    $$('[data-tilt]').forEach(el => {
      el.addEventListener('mousemove', e => {
        const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.setProperty('--ry', ((x - 0.5) * 14) + 'deg');
        el.style.setProperty('--rx', ((0.5 - y) * 12) + 'deg');
        el.style.setProperty('--gx', (x * 100) + '%');
        el.style.setProperty('--gy', (y * 100) + '%');
      });
      el.addEventListener('mouseleave', () => { el.style.setProperty('--rx', '0deg'); el.style.setProperty('--ry', '0deg'); });
    });
  }

  /* ---------- reveal on scroll + counters ---------- */
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    if (!en.isIntersecting) return;
    en.target.classList.add('in');
    $$('[data-count]', en.target).forEach(countUp);
    io.unobserve(en.target);
  }), { threshold: 0.18 });
  $$('.reveal').forEach(el => io.observe(el));
  function countUp(el) {
    const end = +el.dataset.count, pre = el.dataset.prefix || '';
    if (end === 0) { // the AI's withdrawal rights: count *down* to zero for effect
      let v = 99; const t = setInterval(() => { v = Math.max(0, v - 7); el.textContent = pre + v; if (!v) clearInterval(t); }, 40);
      return;
    }
    const t0 = performance.now(), dur = 1600;
    (function f(now) {
      const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 4);
      el.textContent = pre + Math.round(end * e).toLocaleString();
      if (p < 1) requestAnimationFrame(f);
    })(t0);
  }

  /* ---------- scroll-lit statement words ---------- */
  const lit = $('#lit-text');
  const HL = new Set(['strikes', 'once,', 'Tec-C']);
  lit.innerHTML = lit.textContent.split(' ').map(w => `<span class="lw${HL.has(w) ? ' hl' : ''}">${w}</span>`).join(' ');
  const words = $$('.lw', lit);

  /* ---------- scroll-driven effects ---------- */
  const header = $('#site-header'), statement = $('#statement'), track = $('#hero-track');
  const mossRing = $('.statement-ring'), band = $('.terr-band'), terr = $('#territories'), naturePhoto = $('.nature-photo');
  const night = $('#scene-night'), cave = $('#scene-cave'), flash = $('#flash'), runner = $('#runner');
  const runnerEl = () => (document.body.classList.contains('run-sprite') ? $('.runner-sprite') : $('.runner-photo'));
  const caption1 = $('#seq-caption'), caption2 = $('#scene-cave .seq-caption');
  // ?run=sprite swaps the photo for the 1887 Muybridge gallop sprite (19 frames)
  let runMode = new URLSearchParams(location.search).get('run');
  try { runMode = runMode || localStorage.getItem('tecc_run'); } catch { /* storage blocked */ }
  const setRun = m => {
    document.body.classList.toggle('run-sprite', m === 'sprite');
    $('#run-toggle').textContent = m === 'sprite' ? 'Run: 1887 sprite' : 'Run: photo';
    try { localStorage.setItem('tecc_run', m); } catch { /* storage blocked */ }
  };
  setRun(runMode === 'sprite' ? 'sprite' : 'photo');
  $('#run-toggle').addEventListener('click', () => setRun(document.body.classList.contains('run-sprite') ? 'photo' : 'sprite'));
  const clamp01 = v => Math.min(1, Math.max(0, v));
  const seg = (t, a, b) => clamp01((t - a) / (b - a));
  const easeIn = (u, k = 2.6) => Math.pow(u, k);
  const smooth = u => u * u * (3 - 2 * u);
  let seqT = 0;

  function renderRun(now) {
    const t = seqT, el = runnerEl(), sprite = document.body.classList.contains('run-sprite');
    const u = seg(t, 0.12, 0.6);
    const vw = innerWidth / 100, vh = innerHeight / 100;
    const k = easeIn(u);
    const rs = 0.16 + k * 6.2;                                         // grows as it charges the camera
    const stride = Math.sin(now / 1000 * (sprite ? 9 : 13));
    const bob = (sprite ? 0.6 : 1) * stride * 1.4 * vh * Math.min(rs, 2.2);
    const rx = sprite ? (-34 + 38 * smooth(u)) * vw : (24 - 30 * smooth(u)) * vw;
    const ry = (-5 + 20 * k) * vh + bob;
    const rr = (sprite ? -1 : 1) * stride * 2.2 - (u > 0.85 ? (u - 0.85) * 60 : 0) * (sprite ? 1 : -1); // a leap at the end
    el.style.setProperty('--rs', rs.toFixed(3));
    el.style.setProperty('--rx', rx.toFixed(1) + 'px');
    el.style.setProperty('--ry', ry.toFixed(1) + 'px');
    el.style.setProperty('--rr', rr.toFixed(2) + 'deg');
    el.style.setProperty('--rb', (0.8 * (1 - seg(u, 0.78, 0.98) * 0.97)).toFixed(3)); // fills the frame and goes dark
    runner.style.opacity = u > 0 && t < 0.62 ? 1 : 0;
    if (sprite) {
      const f = Math.floor(now / 1000 * 20) % 19;
      el.style.backgroundPosition = (f / 18 * 100) + '% 0';
    }
  }
  (function loop(now) {
    if (seqT > 0.02 && seqT < 0.66) renderRun(now);
    requestAnimationFrame(loop);
  })(performance.now());

  function onScroll() {
    const y = scrollY, vh = innerHeight;
    header.classList.toggle('scrolled', y > 40);
    // the run: hero → night jungle + cave → jaguar charges the camera → inside the cave → light → forest
    const t = clamp01((y - vh * 0.05) / (track.offsetHeight - vh));
    seqT = t;
    const heroOut = seg(t, 0.03, 0.15);
    hero.style.opacity = 1 - heroOut;
    hero.style.transform = `scale(${1 + heroOut * 0.08})`;
    hero.style.filter = heroOut > 0 ? `blur(${heroOut * 8}px)` : '';
    night.style.opacity = seg(t, 0.06, 0.16) * (1 - seg(t, 0.6, 0.64));
    const cam = 1 + seg(t, 0.14, 0.5) * 0.5 + easeIn(seg(t, 0.46, 0.64), 3) * 12; // camera pushes into the mouth
    night.style.setProperty('--cam', cam.toFixed(3));
    caption1.style.setProperty('--co', (seg(t, 0.17, 0.23) * (1 - seg(t, 0.33, 0.4))).toFixed(3));
    cave.style.opacity = seg(t, 0.63, 0.71);
    cave.style.setProperty('--cz', (1 + easeIn(seg(t, 0.68, 0.97), 2.2) * 5.5).toFixed(3));
    cave.style.setProperty('--cb', (0.35 + seg(t, 0.64, 0.95) * 1.1).toFixed(3));
    caption2.style.setProperty('--co', (seg(t, 0.71, 0.76) * (1 - seg(t, 0.83, 0.88))).toFixed(3));
    flash.style.opacity = seg(t, 0.87, 0.97);
    $$('.slide-index, .socials, .scroll-hint').forEach(c => { c.style.opacity = 1 - seg(t, 0.01, 0.05); });
    const nowTransitioning = t > 0.02;
    if (nowTransitioning !== transitioning) { transitioning = nowTransitioning; nowTransitioning ? (clearTimeout(timer), cancelAnimationFrame(raf)) : restart(); }
    document.body.classList.toggle('on-light', t > 0.96);
    if (t <= 0.02 || t >= 0.66) renderRun(performance.now());
    const docSpan = Math.max(1, document.documentElement.scrollHeight - vh);
    naturePhoto.style.setProperty('--ny', (-(y / docSpan) * vh * 0.07).toFixed(1) + 'px'); // stays inside the 8% bleed
    // statement: light words one by one while the moss ring turns
    const sr = statement.getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (vh * 0.75 - sr.top) / (sr.height * 0.75)));
    const n = Math.floor(p * words.length);
    words.forEach((w, i) => w.classList.toggle('on', i < n));
    mossRing.style.setProperty('--ss', 0.85 + p * 0.25);
    mossRing.style.setProperty('--sr', (p * 70) + 'deg');
    // territories: the misty band drifts
    band.style.setProperty('--ty', (terr.getBoundingClientRect().top * -0.12) + 'px');
  }
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onScroll);
  onScroll();

  /* ---------- falling leaves in the forest ---------- */
  (() => {
    const box = $('#nature-leaves');
    const shapes = ['M12 2C6 7 4 13 12 22C20 13 18 7 12 2Z M12 4V21', 'M3 21C3 11 9 4 21 3C20 15 13 21 3 21Z M3 21L15 9'];
    const n = reduced ? 0 : Math.min(16, Math.round(innerWidth / 95));
    box.innerHTML = Array.from({ length: n }, (_, i) => {
      const s = 14 + Math.random() * 24, dur = 15 + Math.random() * 18, delay = -Math.random() * dur;
      const col = ['#ffffff', '#e6efd8', '#7fa66a', '#cde38a'][i % 4];
      return `<div class="nleaf" style="left:${Math.random() * 100}%;width:${s}px;height:${s}px;animation-duration:${dur}s;animation-delay:${delay}s">
        <svg viewBox="0 0 24 24" style="animation-duration:${3 + Math.random() * 3}s"><path d="${shapes[i % 2]}" fill="${col}" fill-opacity=".6" stroke="${col}" stroke-width=".8"/></svg></div>`;
    }).join('');
  })();

  /* ---------- fireflies: amber in the dark, lime in the jungle ---------- */
  const cv = $('#fireflies'), ctx = cv.getContext('2d');
  let W, H, flies = [];
  function size() {
    const dpr = Math.min(2, devicePixelRatio || 1);
    W = cv.width = innerWidth * dpr; H = cv.height = innerHeight * dpr;
    cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
    const count = Math.round(Math.min(34, innerWidth / 40));
    flies = Array.from({ length: count }, () => ({
      x: Math.random() * W, y: Math.random() * H, r: (Math.random() * 1.1 + 0.4) * dpr,
      vx: (Math.random() - 0.5) * 0.25 * dpr, vy: (Math.random() - 0.5) * 0.25 * dpr,
      ph: Math.random() * Math.PI * 2, sp: 0.01 + Math.random() * 0.02,
    }));
  }
  size(); addEventListener('resize', size);
  if (!reduced) (function draw() {
    if (document.body.classList.contains('on-light')) { requestAnimationFrame(draw); return; } // the forest has leaves instead
    ctx.clearRect(0, 0, W, H);
    const col = document.body.classList.contains('on-light') ? '255,255,255' : '232,166,75';
    flies.forEach(f => {
      f.ph += f.sp; f.x += f.vx + Math.sin(f.ph) * 0.15; f.y += f.vy + Math.cos(f.ph * 0.8) * 0.15;
      if (f.x < 0) f.x = W; if (f.x > W) f.x = 0; if (f.y < 0) f.y = H; if (f.y > H) f.y = 0;
      const a = 0.25 + (Math.sin(f.ph * 2) + 1) * 0.3;
      const g = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r * 7);
      g.addColorStop(0, `rgba(${col},${a})`); g.addColorStop(1, `rgba(${col},0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(f.x, f.y, f.r * 7, 0, Math.PI * 2); ctx.fill();
    });
    requestAnimationFrame(draw);
  })();
})();
