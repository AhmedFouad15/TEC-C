# Tec-C front end: what was built and how it works

The front end is two static pages in `web/`, with no build step and no framework. It is plain HTML, CSS and JavaScript that talks to the Brain's FastAPI server (`agent/`). Every screen still works when the Brain is offline: it falls back to clearly labelled demo data.

```
web/
├── index.html            landing page (jaguar hero → mist → forest)
├── app.html              Command Center dashboard (9 screens + modals)
├── README.md             short run instructions
├── FRONTEND.md           this file
└── assets/
    ├── css/landing.css   landing styles
    ├── css/app.css       dashboard styles
    ├── js/landing.js     landing interactions and scroll choreography
    ├── js/app.js         dashboard logic and the Brain API client
    └── img/              photos (Wikimedia Commons) and generated fog textures
```

## 1. How to run it

```bash
# terminal 1: the Brain (optional, but needed for live data)
cd agent && .venv/bin/uvicorn tecc_brain.app:app --host 127.0.0.1 --port 8000

# terminal 2: the UI
cd web && python3 -m http.server 3000 --bind 127.0.0.1
```

Open **http://127.0.0.1:3000/** (landing) and **http://127.0.0.1:3000/app.html** (dashboard).
Use `127.0.0.1`, not `localhost`: another project already owns `localhost:3000` on this machine, and the Brain's CORS allows `127.0.0.1:3000`.

## 2. Design

The two pages share one story: **a jaguar in the dark, then a calm, misty forest.**

| | Landing hero | Everything after the hero, and the dashboard |
|---|---|---|
| Mood | dark, cinematic, amber | light, airy sage mist (inspired by the "Pyko" reference) |
| Type | Bebas Neue (big condensed headlines) | Manrope (UI), Instrument Serif *italic* (accent words) |
| Colours | ink `#0b0d0a`, amber `#e8a64b` | sage `#9aa88f`, white text and cards, lime accent `#cde38a` |
| Surfaces | full-bleed photos | white cards (landing) and frosted "glass" cards (dashboard) |

Both pages have a **soft dark edge across the top of the screen** (as in the Pyko reference): almost black at the very top, fading out over about 46% of the screen height. It's a still gradient, so it costs nothing to draw.

Rule followed throughout: after the hero, every section keeps the same light palette and only the background design changes (moss ring, misty photo band, white rules). Foreground elements always contrast clearly with the background.

## 3. Landing page (`index.html`)

**Preloader.** Two blinking amber eyes, "TEC—C" and a load counter. It always ends (6.5 s cap) and is skipped on a second visit in the same tab session or with `?skip`.

**Hero slider (4 slides).** These follow the tiger reference layout, with the jaguar on the left and a huge condensed headline on the right, minus the two small photos:
1. *Instinct on a leash*: the agent wallet
2. *Eyes in the dark*: the NLP risk sentinel
3. *Strike only with edge*: econometrics (Sharpe, CVaR, Shibor hurdle)
4. *The vault never blinks*: on-chain safety

Each slide does a clip-path wipe and a slow Ken Burns zoom, with letter-by-letter headline reveals. The vertical 01–04 index has a progress line, autoplay pauses when the tab is hidden, and you can use arrow keys or swipe. Mouse parallax, a soft amber spotlight and fireflies add depth.

**The transition: mist.** As you scroll, two banks of real-looking fog roll in from the sides and the jaguar dissolves into them. The screen becomes pale mist, then the mist thins and the light forest appears behind it.
- Built with two generated fog textures (`fog.webp` tiles for the slow drift; `fog-bank.webp` has soft edges baked in).
- Scroll progress drives it through a sticky "stage" over a 280vh track.
- History: a cave/running-jaguar version and an "iris" version were tried and removed after feedback.

**Forest sections.**
- **Intro:** "Become the calmest *version of your wallet*". A slowly turning moss ring, a white pill button and floating cards, like the reference.
- **Marquee:** assets and terms scrolling.
- **The hunt:** four white stat cards with count-up numbers ($500 radius, 6 agents, 4 markets, 0 withdrawal rights).
- **Statement:** words light up one by one as you scroll, over a hunter's rangefinder (SVG: turning tick ring, brackets that close in, a range that counts down to "strike"). It replaced a second moss ring that duplicated the intro.
- **Six senses:** the six LangGraph agents as numbered white cards.
- **Territories:** Crypto/Ethereum, Chinese market/FISCO BCOS, Commodities/Arbitrum, plus PegGuard as a background guard (not a market), as glass cards that turn white on hover.
- **The oath:** the four things the AI can never do.
- **CTA and footer:** every link into the app first checks the Brain's `/health`; if it doesn't answer, the visitor goes to the GitHub repo. The footer shows one **Credits** button; the photo credits appear on hover/focus (tap on touch).

**Dev switches:** `?skip` (no preloader), `?seq=0.4` (jump into the transition, 0–1), `?at=senses` (jump to a section).

## 4. Dashboard (`app.html`)

A Pyko-style top bar has a centred pill navigation with a sliding indicator. Under it, a status strip shows the vault balance, the tether donut, **Brain live/demo**, the biometric window, **Risk quiz** and pending reviews. The background is a misty jungle photo with moss, falling leaves and grain; cards are frosted glass with a light that follows the cursor.

| Screen | What it does | Brain endpoint (when live) |
|---|---|---|
| **Home** | Ask bar (free text), command composer (action, market, assets, capital slider, risk tier), live 6-agent pipeline, tether widgets, PegGuard switch, "New here?" quiz banner | `/api/mandate/propose` (ask bar), `/evaluate_options` (composer) |
| **Opportunities** | Zone A candidate cards with score rings; Zone B news, econometrics (Sharpe, CVaR) and injection checks; Zone C decision, agent weights, trace, Execute | `/api/mandate/execute` |
| **Portfolio** | Value and trend chart, allocation donut, holdings table with search, **regime radar** (calm day vs. USDC distress), **headline sandbox**, hourly watchdog, alerts | `/api/risk/regimes`, `/api/sentinel/headline`, `/trigger_hourly_monitor` |
| **Review** | Overnight trades: ratify, flag (−20%), or teach with a note; like-streak bar | `/api/review/sync` (for live trades) |
| **Sessions** | Phone gateway status and a QR code | demo |
| **Safety** | Tether and ceiling settings, elasticity toggle, **hold-to-revoke killswitch**, live learned profile (tier, λ, τ, soft limit), "Retake the risk quiz" | `/api/profile/demo` |
| **Risk quiz** (modal) | Five animated questions, then your tier, λ and the Brain's reasoning; updates the composer tier | `/api/profile/quiz`, `/api/profile/onboard` |

Other modals: deposit (the vault's real address + QR from `/api/vault/{account}`, copy button, on-chain balance refresh, local-chain faucet), biometric withdrawal (FaceID scan animation), breakout request with a 30-second countdown, and note to the Brain. The composer's assets follow the chosen market (`/api/catalog` when live), and PegGuard is a background switch, not a market.

### The two ways to talk to the Brain

1. **Ask bar (free text)** goes to `/propose`. The text first passes the prompt-injection firewall and privacy sieve, then all six agents run. Each agent's real output lines animate in the pipeline card.
2. **Composer buttons (closed schema)** go to `/evaluate_options`. The UI sends only an action enum, a real asset and a bounded number. There is **no text field an attacker could hide an instruction in**, which is the strongest answer to the judges' prompt-injection criterion; the Injection panel says so explicitly.
   Currently the Brain has venues for depositing and staking ETH, USDC, USDT and stETH only. Other combinations come back as honest rejections that show the reason.

### Offline behaviour

The status pill polls `/health` every 20 s. When the Brain isn't reachable, the pill says **demo mode**, presets fill every screen and badges say "Demo data". Nothing pretends to be live.

## 5. Security

- **Everything from the API is escaped** (`esc()`) before it is inserted into the page.
- **Only a Brain on this machine is trusted.** `?api=` accepts only loopback addresses (127.0.0.1, localhost, ::1). A crafted link cannot send your commands and notes to someone else's server, and the choice can't be persisted.
- The Brain's own protections (loopback-only or Bearer token, Host and Origin checks, proposals bound to an account) still apply. The UI runs on an allowed origin.

## 6. Performance (the landing "lag" fix)

The first version of the transition lagged because every scroll frame forced the browser to redraw huge layers. The fix makes **everything that moves use only `transform` and `opacity`**, which the GPU composites without repainting:

- no animated `filter: blur()` on the full-screen jaguar;
- fog drift moves a layer with `transform` instead of animating `background-position`, and fog edges are baked into the image instead of using CSS masks;
- no `mix-blend-mode` spotlight;
- scroll and mouse handlers run at most once per frame (`requestAnimationFrame`) with cached element lists;
- fireflies use a pre-rendered glow sprite (no per-frame gradients), there are fewer of them, and they stop during the transition;
- forest animations stay paused until the forest is visible, and off-screen sections are skipped (`content-visibility: auto`);
- fog and forest images are pre-decoded while the hero shows;
- on the dashboard, the background behind the glass cards is kept still (no parallax, no breathing moss), so the cards don't re-blur every frame;
- **no live frosted-glass blur (`backdrop-filter`) anywhere on the landing.** Re-blurring the animated forest behind the territory cards, marquee and footer froze the first scroll into the forest for several seconds. Those surfaces are now tinted, semi-opaque colours that look almost the same.

**Measured** on a fresh load with an automated scroll:
- through the whole transition: **60 fps, no frames over 25 ms** (before: hitches of up to ~450 ms);
- the whole landing page, hero to footer: **59 fps, 3 of 298 frames over 25 ms** (before: a 12-second freeze);
- dashboard screens: **60 fps, no frames over 25 ms**.

## 7. Assets and licences

All photos come from Wikimedia Commons; authors and licences are listed in the landing footer.

| File | Source | Licence |
|---|---|---|
| jaguar-hero.jpg | Kandukuru Nagarjun | CC BY 2.0 |
| jaguar-gaze.jpg, jaguar-roar.jpg | Eric Kilby | CC BY-SA 2.0 |
| jaguar-jungle.jpg | Alexander Leisser | CC BY-SA 4.0 |
| mist-canopy.jpg | Pradyumnakp | CC0 |
| moss-forest.jpg | Krishna k. sahh | CC0 |
| fog.webp, fog-bank.webp | generated here (1/f spectral noise) | none needed |

Images are resized, compressed and colour-graded in CSS.

## 8. Known limits (be honest in the demo)

- **Simulated screens:** portfolio holdings, watchdog alerts, scenarios, deposit/withdraw and FaceID. Real vault balances need the on-chain event listener (Phase 7, plan 07-03), and real FaceID needs WebAuthn.
- **The quiz overwrites the account's learned profile.** To restore the seeded demo profile, delete `agent/.state/profiles/demo.json`; it re-seeds on the next request.
- **Free-text vocabulary:** the ask bar's parser doesn't know "park" or "invest" yet (a small fix in `agent/tecc_brain/intent/rules.py`). The composer works around this.
- **Phone layout:** designed responsive with breakpoints, but only partly verified at true phone width. Check it on a real phone before the demo.

## 9. History of this work

1. Re-themed the original single-file mockup (`index.html` from the team) into the jungle-glass dashboard and kept all its features.
2. Built the jaguar landing page from the tiger reference.
3. Wired the dashboard to the live Brain API with a demo fallback.
4. Voice-note feedback: light, airy forest sections after the hero; the jaguar only in the hero; removed the "ugly line".
5. The transition went from iris (felt cheap) to a running jaguar into a cave (felt bad) to **mist**.
6. Fixed ring clipping and sizing; the moss rings are now sized by window height so they are never cropped.
7. Added Backtests, the injection-proof options flow and the risk quiz.
8. Security fix: loopback-only `?api=`.
9. Performance passes: 60 fps transition, then the forest sections (removed live backdrop blur).
10. Soft dark top edge on both pages, made longer and darker after feedback.
11. Team notes (2026-10-19): removed Backtests, Scenarios and the 3 pillars; PegGuard became a switch, not a market; assets follow the market; deposit shows the real vault address; the $500 stat became −20% (the leash isn't fixed); rangefinder replaced the duplicate moss ring; credits on hover; CTA fail-safe to the repo; scroll stutter fixed (no `content-visibility`, no layout reads in the scroll handler, colour grades baked into the images). Vercel guide in `DEPLOY_VERCEL.md`.
12. No dummy data (2026-10-19): Review reads the vault's on-chain records and asks for the Brain's pending decisions; Sessions create real cloudflared pairings (QR + code + approve/revoke/relink); tether, trust, vault value, holdings and allocation come from `/api/vault` and `/api/profile`; the pipeline shows the latest command, numbered from #1; PegGuard, killswitch, leash and withdraw call the vault. `dev_up.sh` now runs the Brain with the phone gateway (`virtual_session.runner`, :8000 + :8001) and `TECC_SPAWN_CLOUDFLARED=1`.
13. Passkeys (2026-10-19): the Biometric chip, Withdraw and over-the-leash approvals use WebAuthn in the browser (Face ID, ES256). The public key is registered with `/api/biometrics/register` (re-registered automatically after a Brain restart, since the Brain keeps passkeys in memory) and each assertion goes to `/api/biometrics/verify`. With a verified window, `/api/mandate/execute` runs a BREAKOUT card through the vault's owner sign-approval (local chain); Morning Review records are named after the venue from the Brain's execution ledger.

