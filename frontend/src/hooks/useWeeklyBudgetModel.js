import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

// Fetches a phase's weekly budget/actual/forecast grid and tracks local edits
// keyed by `${teamMemberId}:${weekStartDate}` until an explicit save - mirrors
// the legacy renderPhaseDetail()'s "collect every dirty input, PUT once" flow
// instead of saving per-keystroke.
export function useWeeklyBudgetModel(engagementId, phaseId) {
  const [data, setData] = useState(null); // { phase, grid: { weeks, rows } }
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const reload = useCallback(() => {
    if (!engagementId || !phaseId) return;
    setLoading(true);
    setError(null);
    api(`/api/engagements/${engagementId}/phases/${phaseId}`)
      .then((result) => {
        setData(result);
        setEdits({});
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [engagementId, phaseId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const setCell = useCallback((memberId, week, field, value) => {
    const key = `${memberId}:${week}`;
    setEdits((prev) => ({ ...prev, [key]: { ...prev[key], [field]: value } }));
  }, []);

  const cellValue = useCallback(
    (memberId, week, cell, field) => {
      const edit = edits[`${memberId}:${week}`];
      return edit && field in edit ? edit[field] : cell[field];
    },
    [edits]
  );

  const dirty = Object.keys(edits).length > 0;

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const rows = Object.entries(edits).map(([key, fields]) => {
        const [memberId, week] = key.split(":");
        const row = { phase_id: Number(phaseId), team_member_id: Number(memberId), week_start_date: week };
        if ("budgeted_hours" in fields) row.budgeted_hours = Number(fields.budgeted_hours || 0);
        if ("forecasted_hours" in fields) {
          row.forecasted_hours = fields.forecasted_hours === "" ? null : Number(fields.forecasted_hours);
        }
        return row;
      });
      await api(`/api/engagements/${engagementId}/phase-weeks`, { method: "PUT", body: { rows } });
      reload();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return { data, error, loading, reload, cellValue, setCell, dirty, saving, saveError, save };
}
