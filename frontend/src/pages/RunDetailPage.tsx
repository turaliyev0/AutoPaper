import { useEffect, useRef, useState } from "react";
import { api, Run } from "../api/client";
import "./RunDetailPage.css";

interface Props { runId: string; onBack: () => void; }

const STATUS_COLOR: Record<string, string> = {
  pending: "#f59e0b", running: "#3b82f6", done: "#22c55e", error: "#ef4444",
};

export default function RunDetailPage({ runId, onBack }: Props) {
  const [run, setRun]         = useState<Run | null>(null);
  const [lines, setLines]     = useState<string[]>([]);
  const [tab, setTab]         = useState<"log" | "pdf">("log");
  const logEl                 = useRef<HTMLDivElement>(null);
  const autoScroll            = useRef(true);

  // Load initial state
  useEffect(() => {
    api.getRun(runId).then(setRun);
    api.getLog(runId).then(setLines);
  }, [runId]);

  // SSE stream
  useEffect(() => {
    const es = new EventSource(api.streamUrl(runId));
    es.onmessage = (e) => {
      const event = JSON.parse(e.data) as { type: string; line?: string; status?: string };
      if (event.type === "log" && event.line) {
        setLines((prev) => [...prev, event.line!]);
      }
      if (event.type === "status" || event.type === "done") {
        api.getRun(runId).then(setRun);
        if (event.type === "done") es.close();
      }
    };
    return () => es.close();
  }, [runId]);

  // Auto-scroll log
  useEffect(() => {
    if (autoScroll.current && logEl.current)
      logEl.current.scrollTop = logEl.current.scrollHeight;
  }, [lines]);

  if (!run) return <div className="loading-screen">Loading…</div>;

  const isLive = run.status === "running" || run.status === "pending";
  const isDone = run.status === "done";

  return (
    <div className="detail-page">
      {/* Breadcrumb */}
      <button className="back-link" onClick={onBack}>← All Runs</button>

      {/* Hero */}
      <div className="detail-hero">
        <div className="hero-text">
          <h1 className="detail-title">{run.paper_title}</h1>
          <div className="detail-meta">
            <span className="meta-chip">{run.run_id}</span>
            <span className="meta-chip">{run.ieee_format}</span>
            <span className="meta-chip">{new Date(run.created_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="status-badge" style={{ borderColor: STATUS_COLOR[run.status] }}>
          <span className="status-dot" style={{ background: STATUS_COLOR[run.status] }} />
          {run.status}
          {isLive && <span className="pulse-ring" style={{ borderColor: STATUS_COLOR[run.status] }} />}
        </div>
      </div>

      {/* Stats */}
      {run.sections_total > 0 && (
        <div className="stats-bar">
          <Stat label="Sections" value={`${run.sections_ok}/${run.sections_total}`} />
          <div className="stat-div" />
          <Stat label="Pass" value={run.validation_pass} color="#22c55e" />
          {run.validation_warn > 0 && <Stat label="Warn" value={run.validation_warn} color="#f59e0b" />}
          {run.validation_fail > 0 && <Stat label="Fail" value={run.validation_fail} color="#ef4444" />}
          {isDone && run.has_pdf && (
            <>
              <div className="stat-div" />
              <a className="btn btn-primary pdf-dl" href={api.pdfUrl(runId)}
                target="_blank" rel="noreferrer">
                ↓ Download PDF
              </a>
            </>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="tab-bar">
        <button className={`tab${tab === "log" ? " active" : ""}`} onClick={() => setTab("log")}>
          Live Log {isLive && <span className="blink-dot" />}
        </button>
        {isDone && run.has_pdf && (
          <button className={`tab${tab === "pdf" ? " active" : ""}`} onClick={() => setTab("pdf")}>
            PDF Preview
          </button>
        )}
      </div>

      {/* Log panel */}
      {tab === "log" && (
        <div className="log-panel" ref={logEl}
          onScroll={() => {
            if (!logEl.current) return;
            const { scrollTop, scrollHeight, clientHeight } = logEl.current;
            autoScroll.current = scrollHeight - scrollTop - clientHeight < 80;
          }}>
          {lines.length === 0 && <span className="log-empty">Waiting for pipeline output…</span>}
          {lines.map((ln, i) => <LogLine key={i} text={ln} />)}
          {isLive && <div className="log-cursor">▌</div>}
        </div>
      )}

      {/* PDF panel */}
      {tab === "pdf" && isDone && run.has_pdf && (
        <iframe
          className="pdf-frame"
          src={api.pdfUrl(runId)}
          title="Manuscript PDF"
        />
      )}

      {run.error && <div className="error-box">{run.error}</div>}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="stat">
      <span className="stat-val" style={color ? { color } : undefined}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function LogLine({ text }: { text: string }) {
  const cls =
    /\[OK\]|PASS|successfully|\[ok\]|✓/.test(text) ? "ok" :
    /\[FAIL\]|ERROR|FAIL|error/.test(text)          ? "err" :
    /WARN|warn/.test(text)                          ? "warn" :
    /^={3,}|^-{3,}|STEP\s+\d/.test(text)           ? "section" : "";
  return <div className={`log-line${cls ? " " + cls : ""}`}>{text}</div>;
}
