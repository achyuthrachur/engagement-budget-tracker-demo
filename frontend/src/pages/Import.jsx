import { useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { AlertTriangle, CheckCircle2, UploadCloud } from "lucide-react";
import { MetricCard } from "../components/MetricCard";
import { formatHours, formatMoney } from "../format";
import { api } from "../api";

const FLAG_GUIDANCE = {
  zero_hours: "Zero-hour source record",
  worker_unknown: "Imported and queued for team assignment",
  worker_unauthorized: "Known inactive worker requires review",
  project_mismatch: "Imported and queued for review",
  unmatched_phase: "Imported and queued for phase assignment",
  variance_flagged: "Review the week-over-week change",
};

async function uploadPreview(engagementId, file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/engagements/${engagementId}/import/preview`, { method: "POST", body: form });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || "Preview failed");
  return body.data;
}

function UnmatchedResolution({ engagementId, phases }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [selection, setSelection] = useState({});

  useEffect(() => {
    api(`/api/engagements/${engagementId}/unmatched-phases`)
      .then(setRows)
      .catch((err) => setError(err.message));
  }, [engagementId]);

  if (!rows || rows.length === 0) return null;

  async function assign(desc) {
    const phaseId = selection[desc];
    if (!phaseId) return;
    setError(null);
    try {
      await api(`/api/engagements/${engagementId}/unmatched-phases`, {
        method: "PATCH",
        body: { phase_id: Number(phaseId), phase_desc: desc },
      });
      setRows((prev) => prev.filter((row) => row.phase_desc !== desc));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card">
      <h2>Previously imported unmatched time</h2>
      {error && <p className="hint danger-text">{error}</p>}
      {rows.map((row) => (
        <div className="resolution-row" key={row.phase_desc || "(blank)"}>
          <span>
            <b>{row.phase_desc || "(blank)"}</b> · {formatHours(row.hours)} hours · {row.workers} worker
            {row.workers === 1 ? "" : "s"}
          </span>
          <select
            value={selection[row.phase_desc] || ""}
            onChange={(e) => setSelection((prev) => ({ ...prev, [row.phase_desc]: e.target.value }))}
          >
            <option value="">Choose a phase</option>
            {phases.map((phase) => (
              <option key={phase.id} value={phase.id}>
                {phase.phase_name}
              </option>
            ))}
          </select>
          <button className="btn secondary" onClick={() => assign(row.phase_desc)}>
            Assign
          </button>
        </div>
      ))}
    </section>
  );
}

export default function Import() {
  const { engagementId, engagement, phases, reload } = useOutletContext();
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [pastedText, setPastedText] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const [preview, setPreview] = useState(null);
  const [phaseAssignments, setPhaseAssignments] = useState({});
  const [notes, setNotes] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState(null);
  const [commitResult, setCommitResult] = useState(null);

  const closed = engagement.status === "closed";

  async function handlePreview() {
    setPreviewing(true);
    setPreviewError(null);
    try {
      const data = file
        ? await uploadPreview(engagementId, file)
        : await api(`/api/engagements/${engagementId}/import/preview`, { method: "POST", body: { text: pastedText } });
      setPreview(data);
      setPhaseAssignments({});
      setCommitResult(null);
      setConfirming(false);
    } catch (err) {
      setPreviewError(err.message);
    } finally {
      setPreviewing(false);
    }
  }

  async function handleCommit() {
    setCommitting(true);
    setCommitError(null);
    try {
      const phase_assignments = {};
      Object.entries(phaseAssignments).forEach(([desc, phaseId]) => {
        if (phaseId) phase_assignments[desc] = Number(phaseId);
      });
      const removals = preview.rows_to_remove || [];
      const result = await api(`/api/engagements/${engagementId}/import/commit`, {
        method: "POST",
        body: { phase_assignments, confirm_removals: removals.length > 0, notes },
      });
      setCommitResult(result);
      setPreview(null);
      setFile(null);
      setPastedText("");
      setNotes("");
      setConfirming(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      reload();
    } catch (err) {
      setCommitError(err.message);
    } finally {
      setCommitting(false);
    }
  }

  const unmatchedDescs = preview
    ? [...new Set(preview.rows.filter((row) => row.flags?.includes("unmatched_phase")).map((row) => row.phase_desc))]
    : [];
  const removals = preview?.rows_to_remove || [];

  return (
    <>
      <UnmatchedResolution engagementId={engagementId} phases={phases} />

      <section className="card">
        <div className="section-head">
          <div>
            <span className="eyebrow">Cognos actuals</span>
            <h2>Preview before committing</h2>
          </div>
        </div>
        <p className="hint">Upload the raw workbook or paste the full tab-delimited export. Header preambles and summary footers are handled automatically.</p>
        <label className="upload-zone">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.csv,.txt"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <UploadCloud size={20} />
          <strong>{file ? file.name : "Choose a Cognos file"}</strong>
          <span>.xlsx, .csv or .txt</span>
        </label>
        <label className="field">
          <span>Or paste export</span>
          <textarea rows={8} value={pastedText} onChange={(e) => setPastedText(e.target.value)} />
        </label>
        {previewError && <p className="hint danger-text">{previewError}</p>}
        <button className="btn primary" onClick={handlePreview} disabled={previewing || closed || (!file && !pastedText.trim())}>
          {previewing ? "Previewing…" : "Preview import"}
        </button>
        {closed && <p className="hint">Closed engagements do not accept imports.</p>}
      </section>

      {commitResult && (
        <div className="alert success stagger-in">
          <CheckCircle2 size={16} />
          <span>
            {commitResult.imported} inserted, {commitResult.updated} updated, {commitResult.removed} removed
            {commitResult.backup_path ? " · recovery backup created" : ""}
          </span>
        </div>
      )}

      {preview && (
        <>
          <div className="metrics-grid">
            <MetricCard index={0} label="Insert" value={preview.rows_to_insert} format={(v) => String(Math.round(v))} />
            <MetricCard index={1} label="Update" value={preview.rows_to_update} format={(v) => String(Math.round(v))} />
            <MetricCard index={2} label="Remove" value={removals.length} format={(v) => String(Math.round(v))} />
            <MetricCard index={3} label="Exceptions" value={preview.summary.flagged} format={(v) => String(Math.round(v))} />
          </div>

          <section className="card">
            <h2>Covered period {preview.covered_start_date || "—"} to {preview.covered_end_date || "—"}</h2>
            <div className="flag-key">
              <span><b>Pending exceptions</b> stay included until resolved or excluded</span>
              <span><b>Updates</b> correct rows in place</span>
              <span><b>Removals</b> require confirmation</span>
              <span><b>Exclusions</b> remain auditable</span>
            </div>
          </section>

          {unmatchedDescs.length > 0 && (
            <section className="card">
              <h2>Phase assignments</h2>
              <p className="hint">Assign each Cognos phase description once. The selection applies to every matching row in this preview.</p>
              <div className="assignment-grid">
                {unmatchedDescs.map((desc) => (
                  <label className="field compact" key={desc || "(blank)"}>
                    <span>Assign "{desc || "(blank)"}" to</span>
                    <select
                      value={phaseAssignments[desc] || ""}
                      onChange={(e) => setPhaseAssignments((prev) => ({ ...prev, [desc]: e.target.value }))}
                    >
                      <option value="">Leave pending</option>
                      {phases.map((phase) => (
                        <option key={phase.id} value={phase.id}>
                          {phase.phase_name}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </section>
          )}

          <section className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Worker</th>
                    <th>Week end</th>
                    <th>Phase</th>
                    <th>Hours</th>
                    <th>Contract fees</th>
                    <th>Review</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={row.transaction_id} className={row.flag || ""}>
                      <td>{row.reconciliation_action}</td>
                      <td>{row.worker_name}</td>
                      <td>{row.week_end_date}</td>
                      <td>{row.phase_desc || "Unmatched"}</td>
                      <td>{formatHours(row.hours)}</td>
                      <td>{formatMoney(row.fees_contract_rate)}</td>
                      <td>
                        {(row.flags || []).map((flag) => (
                          <span className="flag" key={flag}>
                            {flag.replaceAll("_", " ")}
                          </span>
                        ))}
                        <small className="flag-guidance">{FLAG_GUIDANCE[row.flag] || "Ready to reconcile"}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {removals.length > 0 && (
              <>
                <div className="alert warning">
                  <AlertTriangle size={16} />
                  <span>
                    <strong>{removals.length} source rows will be removed</strong> — the new file is authoritative for this period.
                  </span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Transaction</th>
                        <th>Worker</th>
                        <th>Week</th>
                        <th>Hours</th>
                        <th>Fees</th>
                      </tr>
                    </thead>
                    <tbody>
                      {removals.map((row) => (
                        <tr key={row.transaction_id}>
                          <td className="mono">{row.transaction_id}</td>
                          <td>{row.worker_name}</td>
                          <td>{row.week_end_date}</td>
                          <td>{formatHours(row.hours)}</td>
                          <td>{formatMoney(row.fees_contract_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <label className="field">
              <span>Snapshot notes</span>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Example: Week ending July 12, reviewed against Cognos by reviewer"
              />
            </label>

            {engagement.status === "planning" && (
              <div className="alert warning">
                <AlertTriangle size={16} />
                <span>
                  <strong>First committed import</strong> — this activates the engagement and locks baseline hours, rates and statement of work budgets.
                </span>
              </div>
            )}

            {!confirming ? (
              <button className="btn primary" onClick={() => setConfirming(true)}>
                Review and commit import
              </button>
            ) : (
              <div className="commit-confirm">
                <p>
                  {preview.rows_to_insert} insert, {preview.rows_to_update} update and {removals.length} removal.
                  A recovery backup will be created automatically.
                </p>
                {commitError && <p className="hint danger-text">{commitError}</p>}
                <div className="button-row">
                  <button className="btn primary" onClick={handleCommit} disabled={committing}>
                    {committing ? "Committing…" : engagement.status === "planning" ? "Activate and commit" : "Confirm commit"}
                  </button>
                  <button className="btn secondary" onClick={() => setConfirming(false)} disabled={committing}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
