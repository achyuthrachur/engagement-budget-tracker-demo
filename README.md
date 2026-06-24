# Engagement Budget Tracker Demo

Synthetic demo build of the Engagement Budget Tracker. All included data is fictitious and anonymized.

## Local run

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

The app creates `budget_tracker.db` from `demo_seed.db` on first run. Delete `budget_tracker.db` to reset the local demo data.

## Vercel

This repository includes `api/index.py` and `vercel.json` for Vercel deployment. The Vercel demo copies `demo_seed.db` to `/tmp` on cold start, so data may reset between serverless instances.
