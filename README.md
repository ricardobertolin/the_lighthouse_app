# The Lighthouse

A daily personal news digest that pulls from trusted RSS feeds and GNews search,
scores articles by relevance + reputation + corroboration, synthesizes the best
stories with Claude, and publishes a self-contained HTML page you can install as
a PWA on any device.

---

## Quick start

### 1. Python environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

> **First run:** `sentence-transformers` downloads the `all-MiniLM-L6-v2` model
> (~80 MB) on first use. It is cached locally after that.

### 2. API keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Yes — fallback text used if absent |
| `GNEWS_API_KEY` | [gnews.io](https://gnews.io) | No — RSS-only mode if absent |

Set them as **user-level environment variables** (never in code or committed files):

```powershell
# Windows PowerShell — persistent, user-level, never touches any file
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
[System.Environment]::SetEnvironmentVariable("GNEWS_API_KEY", "your-key", "User")
```

```bash
# macOS / Linux — add to ~/.zshrc or ~/.bashrc
export ANTHROPIC_API_KEY="sk-ant-..."
export GNEWS_API_KEY="your-key"
```

The code reads them via `os.environ.get(...)` — keys are never written to any file
and are not present in the repository. The `.gitignore` also blocks `.env` files as
an extra safety net.

### 3. Run

```bash
# Full pipeline — generates docs/index.html and opens it in the browser
python -m digest

# Skip fetch/score/LLM; re-render today's saved articles with fresh weather (~3 s)
python -m digest --render-only

# Override weather condition for UI testing
python -m digest --weather sunny     # sunny | cloudy | rainy | foggy | snow | thunderstorm

# Render all six weather variants to separate files and open each in the browser
python -m digest --all-weathers

# Full pipeline without opening the browser (useful for scheduled/headless runs)
python -m digest --no-browser

# Stage 1 only — fetch + dedup, print article list (no LLM, no scoring)
python -m digest --fetch-only

# Use an alternate config file
python -m digest --config /path/to/my-config.yaml
```

---

## PWA — install as an app

The digest is published to `docs/index.html`, which GitHub Pages serves at a stable
HTTPS URL. From there you can install it as a Progressive Web App:

- **Android (Chrome):** open the URL → three-dot menu → *Add to Home screen*
- **iPhone (Safari):** open the URL → Share → *Add to Home Screen*
- **Desktop (Chrome/Edge):** click the install icon in the address bar

The service worker (`docs/sw.js`) uses a **network-first** strategy: it always
fetches the latest digest when online and falls back to the cached version when
offline, so you can still read yesterday's digest without a connection.

### GitHub Pages setup

1. Push the repository to GitHub.
2. Go to **Settings → Pages → Source** and set it to **Deploy from a branch**,
   branch `main`, folder `/docs`.
3. Your digest will be live at `https://<user>.github.io/<repo>/`.

`docs/index.html` is committed each time you run the script (it is not gitignored).
`docs/sw.js` and `docs/manifest.json` are static and only change when you update
the app itself.

---

## Scheduling (daily digest at 10 AM)

10 AM local time (Curitiba, UTC-3) is the recommended run time: Brazilian morning
editions are out, European morning news is published, and the US East Coast morning
cycle is in full swing — while still leaving the whole day to read.

### Windows — Task Scheduler

Create a `.ps1` launcher that runs the pipeline and then pushes to GitHub:

```powershell
# lighthouse-daily.ps1
Set-Location "C:\path\to\SW0043_The_Lighthouse"
& "C:\path\to\.venv\Scripts\python.exe" -m digest --no-browser
git add docs/index.html
git commit -m "digest: $(Get-Date -Format 'yyyy-MM-dd')"
git push
```

> **No API keys in the script.** Windows reads `ANTHROPIC_API_KEY` and
> `GNEWS_API_KEY` from user-level environment variables set with
> `SetEnvironmentVariable(..., "User")` — the script never needs to reference them.

Then in Task Scheduler:
1. **Create Basic Task** → name it `The Lighthouse`
2. Trigger: **Daily** at **10:00 AM**
3. Action: `powershell.exe` with argument `-NonInteractive -File "C:\path\to\lighthouse-daily.ps1"`
4. **Properties → General:** check *Run only when user is logged on*
5. **Properties → Settings:** uncheck *Stop task if it runs longer than…*

### macOS — launchd

```xml
<!-- ~/Library/LaunchAgents/com.lighthouse.digest.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.lighthouse.digest</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-c</string>
    <string>
      cd /path/to/SW0043_The_Lighthouse &&
      .venv/bin/python -m digest --no-browser &&
      git add docs/index.html &&
      git commit -m "digest: $(date +%F)" &&
      git push
    </string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/lighthouse.log</string>
  <key>StandardErrorPath</key><string>/tmp/lighthouse.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.lighthouse.digest.plist
```

### Linux — systemd user timer

**`~/.config/systemd/user/lighthouse.service`**
```ini
[Unit]
Description=The Lighthouse daily digest

[Service]
Type=oneshot
WorkingDirectory=/path/to/SW0043_The_Lighthouse
ExecStart=/bin/bash -c ".venv/bin/python -m digest --no-browser && git add docs/index.html && git commit -m 'digest: $(date +%%F)' && git push"
StandardOutput=journal
StandardError=journal
```

**`~/.config/systemd/user/lighthouse.timer`**
```ini
[Unit]
Description=Run The Lighthouse at 10 AM daily

[Timer]
OnCalendar=*-*-* 10:00:00
Persistent=true
Unit=lighthouse.service

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now lighthouse.timer
```

---

## Configuration — `config.yaml`

| Field | Description |
|-------|-------------|
| `trusted_feeds` | RSS feed URLs fetched every run. |
| `search_topics` | English GNews queries (one API call each). |
| `search_topics_pt` | Portuguese GNews queries for Curitiba/Paraná coverage. |
| `interest_paragraph` | Free-text description of your interests — edit this to tune what floats to the top. |
| `domain_reputation.trusted` | Domains that receive the `trusted_score` boost. |
| `domain_reputation.trusted_score` | Score for trusted domains (default `0.85`, range 0–1). |
| `domain_reputation.neutral_score` | Score for unknown domains (default `0.40`). |
| `domain_reputation.blocked` | Domains dropped before scoring. |
| `weights.relevance` | Weight of relevance sub-score in the final blend. |
| `weights.reputation` | Weight of reputation sub-score. |
| `weights.corroboration` | Weight of cross-source corroboration sub-score. |
| `top_n` | Articles sent to Claude and shown in the digest (default `20`). |
| `gnews.max_daily_queries` | Cap on GNews API calls per run (default `15`). |
| `gnews.rate_limit_seconds` | Minimum seconds between GNews requests (default `1.1`). |
| `browser` | Browser to open locally: `default`, `brave`, `chrome`, `firefox`, or an absolute path. |

---

## Pipeline stages

| Stage | Module | Description |
|-------|--------|-------------|
| 1a | `fetch.fetch_rss` | Pull all trusted RSS feeds |
| 1b | `fetch.GNewsProvider` | Query GNews in English and Portuguese |
| 2 | `fetch.dedup_and_corroborate` | Dedup by URL hash; count distinct domains per story |
| 3 | `score.score_articles` | Embed articles + interest paragraph; compute blended score |
| 4 | (implicit) | Merge with today's DB articles; keep `top_n` |
| 4b | `fetch.enrich_missing_images` | Fetch `og:image` for articles without a thumbnail |
| 5 | `synthesize.synthesize` | Claude call → bilingual headlines, summaries, intro, category, region |
| 6 | `weather.fetch_weather` | Open-Meteo daily forecast for Curitiba |
| 7 | `render.render` | Build `docs/index.html` with weather scene + article grid |
| 8 | `render.open_browser` | Open in configured browser |

---

## Security

- **API keys** are read exclusively from environment variables. They are never
  written to any file in this repository.
- **`.gitignore`** blocks `.env` files, `digest.db`, and temporary render outputs
  (`digest_*.html`) as additional safeguards.
- **`config.yaml`** contains only non-secret settings and is safe to commit to a
  public repository.
- **`docs/index.html`** is the daily digest output — it contains only public news
  summaries and is intentionally committed for GitHub Pages.
