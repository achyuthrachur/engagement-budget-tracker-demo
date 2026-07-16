# Engagement Budget Tracker

The canonical implementation of the B2A Engagement Budget Tracker PRD. It supports simple and complex engagements in one data model, weekly phase/person planning, Cognos import review, budget controls and revisions, adjustment and expense ledgers, history, Excel export, and a print-ready HTML report.

All bundled demo data is synthetic and anonymized.

## Run from source

Python 3.11 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. The app creates `budget_tracker.db` beside the source. Use **Load Demo Data** in Settings to copy the bundled synthetic dataset.

Existing version-1 databases are migrated automatically on startup. A `.pre-v2.bak.db` backup is written before migration.

## Test

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

The optional browser workflow requires Playwright and a running server:

```powershell
npm install -D @playwright/test
npx playwright install chromium
$env:BUDGET_TRACKER_PORT = '8877'
python app.py
# In a second terminal:
node .\tests\browser_smoke.cjs
```

## Build the portable Windows app

```powershell
.\build.bat
```

The build produces a `release` folder containing the executable, launcher, installer and quick-start guide. Run `install.bat` for a standard-user installation and desktop shortcut.

Production data is stored under `%LOCALAPPDATA%\Crowe\B2A Budget Tracker`, separate from the installed executable so an application update cannot overwrite the database. The launcher reuses an existing tracker process when one is already running.

## Release status

The application includes first-run guidance, a permanent Help center, safe import defaults, automatic recovery backups, validated restore, governed active-engagement changes and plain-language weekly instructions. Organizational code signing and observed user-acceptance signoff remain release-owner responsibilities.

## Deployment

`api/index.py` and `vercel.json` support the existing Vercel demo deployment. Serverless storage is temporary, so hosted demo data may reset between instances.
