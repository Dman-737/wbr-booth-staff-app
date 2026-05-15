# WBR Booth Staff Report

Side-project tool for WBR (Kelsey Longhini + Aaron Zauderer at Worldwide Business Research) to view ExpoGenie booth staff data with the Level field joined in, since the legacy WordPress version of ExpoGenie can't show Level on the Booth Staff Report directly.

**How it works:**
1. A scheduled GitHub Action logs into the WBR ExpoGenie portal every 10 minutes
2. It scrapes the Booth Staff Report and the User Report
3. It joins them on Exhibiting Company and writes `data/latest.json`
4. GitHub Pages serves `index.html`, which reads that JSON

No server to maintain. Free. Refreshes itself.

## One-time setup (do these once)

### 1. Create the GitHub repo
- Go to https://github.com/new
- Repo name: `wbr-booth-staff-app` (or whatever you want)
- Private or public — doesn't matter; the data is committed to the repo, so private is safer if the booth staff list is sensitive
- Don't initialize with anything — push from local

### 2. Push this folder to the repo
From your terminal:
```bash
cd "/Users/derekmanuel/Desktop/Cowork OS/wbr-booth-staff-app"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/wbr-booth-staff-app.git
git push -u origin main
```

### 3. Add the ExpoGenie credentials as secrets
- In your repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**
- Add two secrets:
  - `EG_USERNAME` = the ExpoGenie admin email (e.g., `derek@expo-genie.com` or a service account)
  - `EG_PASSWORD` = that account's password

### 4. Turn on GitHub Pages
- **Settings → Pages**
- Source: Deploy from a branch
- Branch: `main`, folder: `/ (root)`
- Save. After ~30 seconds, the URL will appear at the top of the Pages settings page. That's the WBR app URL.

### 5. Trigger the first scrape
- **Actions tab → "Scrape ExpoGenie" workflow → Run workflow**
- Watch it run. It should take 1–2 minutes. When it finishes, `data/latest.json` will be updated and the WBR app will show live data.

## Day-to-day use

WBR opens the app URL, hits Refresh whenever they want the latest data. The Refresh button pulls the most recent scrape (which runs every 10 minutes automatically). They can also download a CSV from the same screen.

## Adjusting the schedule

Edit `.github/workflows/scrape.yml`. The two cron lines control how often it runs. Current settings:
- `*/10 13-23 * * 1-5` — every 10 minutes from 9am to 7pm ET on weekdays (when WBR is most likely to be checking)
- `0 * * * *` — every hour at other times

## Adding more events

Edit the `EVENTS` list at the top of `scraper.py`. The code already supports multiple events; it just only has eTail Boston in the list today.

## Custom domain (optional, do later)

If you want `reports.expo-genie.com` instead of `username.github.io/wbr-booth-staff-app/`:
1. In your DNS provider, add a CNAME record: `reports` → `YOUR-USERNAME.github.io`
2. In the repo: **Settings → Pages → Custom domain** → enter `reports.expo-genie.com`
3. Wait a few minutes for the TLS cert to provision.

## Files

```
.
├── .github/workflows/scrape.yml   # Cron + manual scrape workflow
├── data/latest.json               # Latest scrape output (auto-updated)
├── index.html                     # WBR-facing app
├── scraper.py                     # Playwright scraping logic
├── requirements.txt
└── README.md
```

## When something breaks

Most likely cause: ExpoGenie password changed, or the admin account got locked. Update the `EG_PASSWORD` secret in the repo settings, then re-run the workflow. Second most likely: ExpoGenie changed the page HTML structure — in that case the JS selectors in `scraper.py` need updating.
