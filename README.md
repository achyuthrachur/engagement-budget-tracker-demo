# Engagement Budget Tracker Demo

Synthetic demo build of the Engagement Budget Tracker. All included data is fictitious and anonymized.

## Local run

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

The app starts with an empty `budget_tracker.db`. Use the **Load Demo Data** button to copy the synthetic dataset from `demo_seed.db`. Delete `budget_tracker.db` to reset the local demo data.

## Vercel

This repository includes `api/index.py` and `vercel.json` for Vercel deployment. The Vercel demo starts empty in `/tmp`; use **Load Demo Data** to populate the synthetic dataset. Data may reset between serverless instances.
