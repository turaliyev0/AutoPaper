import { useEffect, useState } from "react";
import { api, Run } from "../api/client";
import "./RunsPage.css";

interface Props {
  onOpen: (id: string) => void;
  onNew: () => void;
}

const STATUS_DOT: Record<string, string> = {
  pending: "#f59e0b",
  running: "#3b82f6",
  done:    "#22c55e",
  error:   "#ef4444",
};

export default function RunsPage({ onOpen, onNew }: Props) {
  const [runs, setRuns] = useState<Run[]>([]);

  useEffect(() => {
    const load = () => api.getRuns().then(setRuns).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  async function del(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    await api.deleteRun(id);
    setRuns((r) => r.filter((x) => x.run_id !== id));
  }

  return (
    <div className="runs-page">
      <div className="runs-header">
        <div>
          <h1>Runs</h1>
          <p className="sub">All pipeline executions</p>
        </div>
        <button className="btn btn-primary new-btn" onClick={onNew}>
          + New Run
        </button>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📄</div>
          <h2>No runs yet</h2>
          <p>Upload your paper data to generate an IEEE-formatted manuscript.</p>
          <button className="btn btn-primary" onClick={onNew}>Start your first run</button>
        </div>
      ) : (
        <div className="run-list">
          {runs.map((r) => (
            <div key={r.run_id} className="run-card" onClick={() => onOpen(r.run_id)}>
              <div className="run-left">
                <span className="run-dot" style={{ background: STATUS_DOT[r.status] }} />
                <div>
                  <div className="run-title">{r.paper_title || r.run_id}</div>
                  <div className="run-meta">
                    <span className="chip">{r.ieee_format}</span>
                    <span className="chip status-chip" data-s={r.status}>{r.status}</span>
                    {r.sections_total > 0 && (
                      <span className="chip">{r.sections_ok}/{r.sections_total} sections</span>
                    )}
                    {r.status === "done" && (
                      <>
                        <span className="chip pass">{r.validation_pass} pass</span>
                        {r.validation_warn > 0 && <span className="chip warn">{r.validation_warn} warn</span>}
                        {r.validation_fail > 0 && <span className="chip fail">{r.validation_fail} fail</span>}
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="run-right">
                {r.has_pdf && (
                  <a
                    className="btn btn-ghost btn-sm pdf-btn"
                    href={api.pdfUrl(r.run_id)}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    ↓ PDF
                  </a>
                )}
                <span className="run-date">{new Date(r.created_at).toLocaleDateString()}</span>
                {r.status !== "running" && (
                  <button className="btn btn-danger btn-sm" onClick={(e) => del(e, r.run_id)}>
                    ×
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
