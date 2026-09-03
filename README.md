# Engagement Budget Tracker

The canonical implementation of the B2A Engagement Budget Tracker PRD. It supports simple and complex engagements in one data model, weekly phase/person planning, Cognos import review, budget controls and revisions, adjustment and expense ledgers, history, Excel export, and a print-ready HTML report.

The bundled demonstration database is generated from the five actual workbooks in `reference\B2A Examples`. Treat it as business data rather than synthetic sample data.

## Run from source

Python 3.11 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. The app creates `budget_tracker.db` beside the source. Use **Load Demo Data** in Settings to copy the bundled workbook-derived dataset.

Existing databases are migrated automatically on startup. The application creates a backup before a database-format migration.

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

The build produces two shareable artifacts:

- `release\B2A_Budget_Tracker.exe` is a true one-file application. Double-clicking it selects an available local port and opens the Dashboard in the default browser.
- `release\B2A_Budget_Tracker_<version>.zip` contains the executable, optional desktop-shortcut installer, launcher, version file and the complete Word instruction guide.

The ZIP contains no Markdown instructions. Open `B2A_Budget_Tracker_Instructions.docx` for first-time setup, engagement creation, the weekly process, recovery, glossary and administrator notes.

The portable application creates `budget_tracker.db` beside `B2A_Budget_Tracker.exe`. The optional installer places both application and database under `%LOCALAPPDATA%\Crowe\B2A Budget Tracker\App`. Back up that database before replacing or moving the installed application. The launcher reuses an existing tracker process when one is already running.

## Release status

The application includes first-run guidance, a permanent Help center, safe import defaults, automatic recovery backups, validated restore, governed active-engagement changes and plain-language weekly instructions. Organizational code signing and observed user-acceptance signoff remain release-owner responsibilities.

## Deployment

`api/index.py` and `vercel.json` support the existing Vercel demo deployment. Serverless storage is temporary, so hosted demo data may reset between instances.
