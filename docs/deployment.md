# Deploying RIA → embedding on scottdmarshall.com/ai-demo

Goal: host the app on **Streamlit Community Cloud** (free), then embed it as an
`<iframe>` on your AI Demo page. The repo is already deploy-ready — the **three-version**
corpus (v2019 + v2022 + v2025) and BM25 chunks are bundled, safeguards in, themed, and the
temporal / "version history" feature works from the bundled store (no API needed to render it).

---

## Step 0 — Anthropic: dedicated key + spend limit (your hard cost ceiling)

Do this first — it's the real protection for a public, paid demo.

1. Go to **console.anthropic.com → Settings → Workspaces → Create Workspace** (e.g. "RIA Demo").
2. On that workspace, set a **monthly spend limit** (~**$20**). This hard-caps the demo's
   cost no matter what — if hit, the API returns errors and the app shows "unavailable".
   (This is the backstop; the in-app per-session/daily caps are the first line of defence.)
3. **Create an API key inside that workspace** → copy it (`sk-ant-…`). This is the key you
   deploy with — keep it separate from your personal `.env` key, so the public demo's usage
   (and cap) is isolated from your own.

---

## Step 1 — Deploy to Streamlit Community Cloud

1. Go to **share.streamlit.io** and **sign in with GitHub** (authorise access to the
   `marshallsx/ragria` repo).
2. Click **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `marshallsx/ragria`
   - **Branch:** `main`
   - **Main file path:** `app/main.py`
   - **App URL:** pick a subdomain, e.g. `regulatory-intelligence-assistant` → your app
     will live at `https://regulatory-intelligence-assistant.streamlit.app`
4. Open **Advanced settings**:
   - **Python version:** pick the **newest offered (3.13 as of now)**. Our deps are pinned to
     versions that install cleanly on 3.11–3.14; if the newest ever fails, **3.12** is the
     tested fallback. (Cloud may not list 3.14 yet — don't wait for it, 3.13 is fine.)
   - **Secrets:** paste this (TOML — the key name must be exactly `ANTHROPIC_API_KEY`):
     ```toml
     ANTHROPIC_API_KEY = "sk-ant-…your-demo-workspace-key…"
     ```
5. Click **Deploy**. First build takes **~5–10 min** (installs `chromadb`, `onnxruntime`,
   etc.). Because the vector store is bundled in the repo, there's **no long embed step** —
   it boots straight up. (The `all-MiniLM-L6-v2` embedder downloads once on the **first
   question**, so that first answer is slow — ~20–40s — then it's fast.)
6. When it's live you'll have your `https://….streamlit.app` URL.

---

## Step 2 — Verify the deployed app

Open the `.streamlit.app` URL and confirm:
- Theme is right: **black background, orange headings/buttons, Archivo font**, no Streamlit chrome.
- Click **"Max back-billing period"** → grounded answer citing **Condition 21BA**.
- Click a historic example, e.g. **"Business fairness · 2023"** or **"Meter billing · 2020"** →
  the answer resolves the past date **and** the orange **"📜 Version history"** panel renders
  (timeline + green/red diff). This exercises the bundled 3-version store end-to-end.
- Click **"Out of scope ↩"** → the **"Not in the source material"** refusal.
- The **"Question X of 10 this session"** caption appears.

---

## Step 3 — Embed on scottdmarshall.com/ai-demo

Add this to your AI Demo page. `?embed=true` gives a clean, chrome-less embed.

```html
<div style="width:100%; max-width:900px; margin:0 auto;">
  <iframe
    src="https://YOUR-APP-NAME.streamlit.app/?embed=true"
    title="Regulatory Intelligence Assistant (RIA)"
    style="width:100%; height:820px; border:0; border-radius:8px; background:#000;"
    loading="lazy"
    allow="clipboard-write">
  </iframe>
  <p style="text-align:center; margin-top:0.5rem;">
    <a href="https://YOUR-APP-NAME.streamlit.app" target="_blank" rel="noopener"
       style="color:#ECFF1A;">Open the demo full-screen ↗</a>
  </p>
</div>
```

Notes:
- Replace `YOUR-APP-NAME` with your chosen subdomain (both places).
- Tune `height:820px` to taste. The "Open full-screen" link helps mobile users (iframes
  can feel cramped on phones).
- Your site is custom (Node.js, built via Claude Code on Bluehost), so add this snippet to
  the AI Demo page's markup/component **in your website project**, then redeploy to
  Bluehost. Tip: in that project's Claude Code session, ask it to "add this iframe to the
  ai-demo page."

---

## Step 4 — Ongoing

- **Updates:** push to `main` on GitHub → Streamlit Cloud **auto-redeploys**. No manual step.
  (Fixes, new mapped conditions, etc. flow to the live demo on the next push.)
- **Changing the corpus / adding a version:** add the version to `src/versions.py`, then re-run
  `extract_pages.py → chunk.py → embed.py`. `embed.py` **resets the collection**, which creates a
  **new** `chroma/<uuid>/` segment dir and orphans the old one — `rm -rf` the orphaned dir before
  committing, then commit the new `chroma/` + `data/interim/slc_chunks.jsonl`. (Don't commit the
  read-only `chroma.sqlite3` churn that appears just from *querying* the store — that's not a change.)
- **Cost:** monitor in the Anthropic Console; the workspace spend limit is the hard cap.
  App-side caps (per-session 10, daily 300, 300-char input) add friction on top.
- **Sleep:** free apps sleep after inactivity and take ~30s to wake on the next visit
  (the in-memory daily counter resets on wake — harmless).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails on a dependency | Drop the Python version to **3.12** in Advanced settings (tested fallback); send me the log line if it persists. |
| "Anthropic API key missing or invalid" | Secret must be named exactly `ANTHROPIC_API_KEY` (TOML, quoted). |
| First answer errors with a credit/billing 400 | The deploy key's workspace is out of credit / over its spend limit — top up or raise the cap in the Console. |
| Store / "vector store not found" error | Ensure `chroma/` and `data/interim/slc_chunks.jsonl` are committed (they are). |
| Iframe is blank | Confirm the `.streamlit.app` URL works standalone; add `?embed=true`; check the page's Content-Security-Policy allows framing `*.streamlit.app`. |
| Version-history panel doesn't show | Only appears when a **mapped** condition (25E, 4D, 28, 0A, 21B) is in the answer — try a historic example button. |
| Demo says "daily limit" too soon | Raise `MAX_PER_DAY` in `app/main.py` (currently 300). |
