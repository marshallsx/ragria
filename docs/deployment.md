# Deploying RIA → embedding on scottdmarshall.com/ai-demo

Goal: host the app on **Streamlit Community Cloud** (free), then embed it as an
`<iframe>` on your AI Demo page. The repo is already deploy-ready — corpus bundled,
safeguards in, themed.

---

## Step 0 — Anthropic: dedicated key + spend limit (your hard cost ceiling)

Do this first — it's the real protection for a public, paid demo.

1. Go to **platform.claude.com → Settings → Workspaces → Create Workspace** (e.g. "RIA Demo").
2. On that workspace, set a **monthly spend limit** (~**$20**). This hard-caps the demo's
   cost no matter what — if hit, the API returns errors and the app shows "unavailable".
3. **Create an API key inside that workspace** → copy it (`sk-ant-…`). This is the key you
   deploy with — keep it separate from your personal `.env` key.

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
   - **Python version:** **3.12** (stable; all dependencies have wheels).
   - **Secrets:** paste this (TOML — the key name must be exactly `ANTHROPIC_API_KEY`):
     ```toml
     ANTHROPIC_API_KEY = "sk-ant-…your-demo-workspace-key…"
     ```
5. Click **Deploy**. First build takes a few minutes (installs `chromadb`, `onnxruntime`,
   etc.). Because the vector store is bundled in the repo, there's **no long embed step** —
   it boots straight up. (The `all-MiniLM-L6-v2` model downloads once on first query, ~10s.)
6. When it's live you'll have your `https://….streamlit.app` URL.

---

## Step 2 — Verify the deployed app

Open the `.streamlit.app` URL and confirm:
- Theme is right: **black background, orange headings/buttons, Archivo font**, no Streamlit chrome.
- Click **"Max back-billing period"** → grounded answer citing **Condition 21BA**.
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
       style="color:#FF6600;">Open the demo full-screen ↗</a>
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
- **Changing the corpus:** re-run ingestion locally (`extract_pages.py → chunk.py →
  embed.py`) and commit the new `chroma/` + `data/interim/slc_chunks.jsonl`.
- **Cost:** monitor in the Anthropic Console; the workspace spend limit is the hard cap.
  App-side caps (per-session 10, daily 300, 300-char input) add friction on top.
- **Sleep:** free apps sleep after inactivity and take ~30s to wake on the next visit
  (the in-memory daily counter resets on wake — harmless).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails on a dependency | Set Python version to **3.12** in Advanced settings. |
| "Anthropic API key missing or invalid" | Secret must be named exactly `ANTHROPIC_API_KEY` (TOML, quoted). |
| Store / "vector store not found" error | Ensure `chroma/` and `data/interim/slc_chunks.jsonl` are committed (they are). |
| Iframe is blank | Confirm the `.streamlit.app` URL works standalone; check the page's Content-Security-Policy allows framing `*.streamlit.app`. |
| Demo says "daily limit" too soon | Raise `MAX_PER_DAY` in `app/main.py` (currently 300). |
