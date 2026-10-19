# Deploy the Tec-C front end to Vercel

This deploys **only the website** in `web/`, meaning the landing page (`index.html`) and the Command Center (`app.html`). The site is plain HTML, CSS and JS, so there is **no build step**. The Brain (`agent/`) and the contracts are not deployed.

---

## 1. Create the project (dashboard, about 3 minutes)

1. Go to **vercel.com → Add New… → Project** and import the GitHub repo `AhmedFouad15/TEC-C`.
2. On the "Configure Project" screen, set:

   | Setting | Value |
   |---|---|
   | **Root Directory** | `web` (click *Edit* and pick the `web` folder) |
   | **Framework Preset** | `Other` |
   | **Build Command** | leave empty (turn the override on with an empty field if Vercel fills one in) |
   | **Output Directory** | leave empty, or `.` |
   | **Install Command** | leave empty |
   | **Environment Variables** | none |

3. Click **Deploy**. You get a URL like `https://tec-c.vercel.app`.

> **Production branch:** Vercel deploys `main` to production. If these changes are still on another branch, merge them into `main` first, or pick that branch under **Settings → Git → Production Branch**. Every other branch gets its own preview URL.

### Or from the terminal
```bash
npm i -g vercel
cd web
vercel          # first time: log in, "Set up and deploy" → yes, link to a new project
vercel --prod   # deploy to production
```
When it asks for the build settings, keep the defaults. There is nothing to build.

---

## 2. Connect your domain

1. In the project, open **Settings → Domains → Add** and type your domain (e.g. `tec-c.com`, and/or `www.tec-c.com`).
2. Vercel shows the exact DNS records to add at your domain registrar. Usually:
   - **apex** (`tec-c.com`): an **A** record pointing to the IP Vercel shows (typically `76.76.21.21`);
   - **www** (`www.tec-c.com`): a **CNAME** pointing to the value Vercel shows (typically `cname.vercel-dns.com`).
3. Wait until the domain shows **Valid Configuration** (minutes, sometimes up to an hour for DNS). Vercel issues HTTPS automatically.
4. Optional: set `www` to redirect to the apex (or the other way round) in the same Domains screen.

---

## 3. How the site behaves once deployed

- **Landing page:** works fully (jaguar hero, mist, forest sections, credits on hover).
- **"Enter the vault", "Get started", "Open the Command Center" and the other buttons into the app:** each one first checks whether the Brain API answers (`/health`, 2.5-second timeout).
  - Brain reachable → the visitor goes to the Command Center.
  - Brain not reachable → the visitor is sent to the GitHub repo **https://github.com/AhmedFouad15/TEC-C**.

  A front-end-only deployment has no Brain, so on the public site **these buttons lead to the repo**. That is the intended fail-safe.
- **`/app.html` opened directly:** it still loads, in *demo mode* (amber "Brain demo mode" pill, sample data).

---

## 4. Optional: use the deployed site with a Brain running on your own machine

The page talks to `http://127.0.0.1:8000`. To let the deployed domain reach a Brain on your laptop, start the Brain with your domain allowed:
```bash
cd agent
TECC_CORS_ORIGINS="https://your-domain.com,http://localhost:5500" .venv/bin/uvicorn tecc_brain.app:app --host 127.0.0.1 --port 8000
```
Chrome may ask to allow the site to access devices on your local network: click **Allow**. Safari may block an HTTPS page from calling `http://127.0.0.1`. In that case use Chrome, or run the site locally with `./dev_up.sh`.

---

## 5. Files that matter for the deployment

| File | Purpose |
|---|---|
| `web/index.html`, `web/app.html` | the two pages |
| `web/assets/` | CSS, JS, images, favicon |
| `web/vercel.json` | caching for `/assets` and a few security headers |
| `web/.vercelignore` | keeps the team notes (`*.md`) out of the deployment |

Caching is safe across updates because each page loads its CSS/JS with a version query (`app.js?v=21`). Bump the number when you change a file.

## 6. Check after deploying

- [ ] The domain loads the landing page over HTTPS
- [ ] Scrolling through the mist into the forest is smooth
- [ ] Hovering **Credits** in the footer shows the photo credits
- [ ] **Get started** goes to the GitHub repo (no Brain on the public site)
- [ ] `https://your-domain.com/app.html` opens the Command Center in demo mode
- [x] Auto-deployment verified on Vercel
