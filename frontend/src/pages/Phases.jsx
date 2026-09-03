import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { StatusPill } from "../components/StatusPill";
import { formatHours } from "../format";
import { api } from "../api";

const BLANK_PHASE = { phase_name: "", phase_code: "", sow_fees: 0 };

export default function Phases() {
  const { engagementId, engagement, phases, reload } = useOutletContext();
  const closed = engagement.status === "closed";

  const [rows, setRows] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    setRows(
      Object.fromEntries(
        phases.map((phase) => [phase.id, { phase_name: phase.phase_name, phase_code: phase.phase_code || "", sow_fees: phase.sow_fees }])
      )
    );
  }, [phases]);

  function setField(phaseId, key, value) {
    setMessage(null);
    setRows((prev) => ({ ...prev, [phaseId]: { ...prev[phaseId], [key]: value } }));
  }

  async function savePhases() {
    setSaving(true);
    setError(null);
    try {
      for (const phase of phases) {
        const row = rows[phase.id];
        await api(`/api/engagements/${engagementId}/phases/${phase.id}`, {
          method: "PUT",
          body: { phase_name: row.phase_name, phase_code: row.phase_code, sow_fees: Number(row.sow_fees || 0) },
        });
      }
      setMessage("Phases saved");
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function deletePhase(phase) {
    if (!window.confirm("Delete phase? Only phases with no actual time can be deleted.")) return;
    setError(null);
    try {
      await api(`/api/engagements/${engagementId}/phases/${phase.id}`, { method: "DELETE" });
      setMessage("Phase deleted");
      reload();
    } catch (err) {
      setError(err.message);
    }
  }

  const [newPhase, setNewPhase] = useState(BLANK_PHASE);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

  async function addPhase(event) {
    event.preventDefault();
    setAdding(true);
    setAddError(null);
    try {
      await api(`/api/engagements/${engagementId}/phases`, { method: "POST", body: newPhase });
      setNewPhase(BLANK_PHASE);
      setMessage("Phase added");
      reload();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="split-layout">
      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Persistent phase management</span>
            <h2>Workstreams</h2>
          </div>
          {!closed && (
            <button className="btn primary" onClick={savePhases} disabled={saving}>
              {saving ? "Saving…" : "Save phases"}
            </button>
          )}
        </div>
        {error && <p className="hint danger-text">{error}</p>}
        {message && <p className="hint">{message}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Code</th>
                <th>Statement of work budget</th>
                <th>Actual hours</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {phases.map((phase) => {
                const row = rows[phase.id] || { phase_name: phase.phase_name, phase_code: phase.phase_code || "", sow_fees: phase.sow_fees };
                const sowDisabled = closed || Boolean(phase.actual_hours);
                const canDelete = !phase.is_default && !phase.actual_hours && !closed;
                return (
                  <tr key={phase.id}>
                    <td>
                      <input value={row.phase_name} onChange={(e) => setField(phase.id, "phase_name", e.target.value)} disabled={closed} />
                    </td>
                    <td>
                      <input value={row.phase_code} onChange={(e) => setField(phase.id, "phase_code", e.target.value)} disabled={closed} />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        value={row.sow_fees}
                        onChange={(e) => setField(phase.id, "sow_fees", e.target.value)}
                        disabled={sowDisabled}
                      />
                    </td>
                    <td>{formatHours(phase.actual_hours)}</td>
                    <td>
                      <StatusPill status={phase.status} small />
                    </td>
                    <td>
                      <div className="button-row">
                        <Link className="btn text" to={`/engagements/${engagementId}/phases/${phase.id}`}>
                          Forecast
                        </Link>
                        {canDelete && (
                          <button className="btn text danger-text" onClick={() => deletePhase(phase)}>
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {!closed && (
        <section className="card side-form">
          <h2>Add phase</h2>
          <p className="hint">A phase added during delivery remains editable until its first actual posts.</p>
          <form onSubmit={addPhase}>
            <label className="field">
              <span>Phase name</span>
              <input value={newPhase.phase_name} onChange={(e) => setNewPhase((p) => ({ ...p, phase_name: e.target.value }))} required />
            </label>
            <label className="field">
              <span>Cognos phase code</span>
              <input value={newPhase.phase_code} onChange={(e) => setNewPhase((p) => ({ ...p, phase_code: e.target.value }))} />
            </label>
            <label className="field">
              <span>Signed statement of work</span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={newPhase.sow_fees}
                onChange={(e) => setNewPhase((p) => ({ ...p, sow_fees: e.target.value }))}
              />
            </label>
            {addError && <p className="hint danger-text">{addError}</p>}
            <button className="btn primary" disabled={adding}>
              {adding ? "Adding…" : "Add phase"}
            </button>
          </form>
        </section>
      )}
    </div>
  );
}
