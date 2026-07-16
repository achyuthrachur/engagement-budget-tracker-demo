# B2A Budget Tracker quick start

## First use

1. Double-click **install.bat**.
2. Use the new **B2A Budget Tracker** desktop shortcut.
3. Open **Settings**.
4. Review role rates, discounts and variance thresholds.
5. Select **Save settings**.
6. Select **Create recovery backup**.

## Create an engagement

1. Select **New engagement**.
2. Use the exact Cognos Project ID as the engagement code.
3. Choose Simple for one overall budget or Complex for phases and weekly planning.
4. Add every worker using the exact Cognos “Last, First” name.
5. Verify each rate and offshore designation.
6. For Complex mode, add each phase and its signed SOW.
7. Set phase target hours, distribute across weeks and make every reconciliation difference zero.
8. Review and confirm the baseline, then create the engagement.

## Weekly checklist

- [ ] Create a recovery backup in Settings
- [ ] Export the raw Time and Cost Detail workbook from Cognos
- [ ] Open the engagement and select Weekly import
- [ ] Choose the file and select Preview import
- [ ] Resolve unknown workers and unmatched phases
- [ ] Leave project mismatches excluded unless independently verified
- [ ] Review variance warnings
- [ ] Review selected rows, hours and contract fees
- [ ] Commit the import
- [ ] Update future Forecast values in each phase
- [ ] Review Overview and Export the partner report

## If something is wrong

- Bad weekly import: open **History**, delete only the affected snapshot and reimport the corrected file.
- Larger problem: open **Settings**, select a known-good `.db` file and use **Validate and restore**.
- The tracker creates a recovery backup before imports, snapshot deletions, status changes and restores.

## Import warnings

| Warning | Action |
|---|---|
| Duplicate | Already imported; remains excluded |
| Zero hours | No time to import; remains excluded |
| Unknown worker | Add or reactivate the worker in Team and budget |
| Project mismatch | Remains excluded unless deliberately selected |
| Unmatched phase | Assign to a tracker phase |
| Variance review | Confirm the week-over-week change is reasonable |

Open **Help** inside the tracker for the full operating guide and glossary.
