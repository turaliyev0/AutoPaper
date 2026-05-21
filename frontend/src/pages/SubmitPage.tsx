import { useRef, useState } from "react";
import { api } from "../api/client";
import "./SubmitPage.css";

interface Props {
  onStarted: (id: string) => void;
}

export default function SubmitPage({ onStarted }: Props) {
  const [title, setTitle]       = useState("");
  const [authors, setAuthors]   = useState("");
  const [affil, setAffil]       = useState("");
  const [journal, setJournal]   = useState("IEEE Transactions on Biomedical Engineering");
  const [overview, setOverview] = useState("");
  const [methods, setMethods]   = useState("");
  const [format, setFormat]     = useState<"journal" | "conference">("journal");
  const [images, setImages]     = useState<File[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const canSubmit = title.trim() && overview.trim();

  async function submit() {
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      const { run_id } = await api.startRun({
        title, authors, affiliation: affil,
        targetJournal: journal,
        overview, methods,
        ieeeFormat: format,
        images,
      });
      onStarted(run_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function removeImage(name: string) {
    setImages((prev) => prev.filter((f) => f.name !== name));
  }

  return (
    <div className="submit-page">
      <div className="submit-header">
        <h1>New Run</h1>
        <p className="sub">Fill in your paper data — AutoPaper will generate a full IEEE manuscript.</p>
      </div>

      <div className="form-grid">
        {/* LEFT — paper identity */}
        <section className="card">
          <h2 className="section-title">Paper Identity</h2>

          <Field label="Title *" hint="Full paper title">
            <input className="inp" value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Chronic Stability in Neuro-Prosthetic Interfaces" />
          </Field>

          <Field label="Authors" hint="Separate multiple authors with commas">
            <input className="inp" value={authors}
              onChange={(e) => setAuthors(e.target.value)}
              placeholder="e.g. A. Smith, B. Jones" />
          </Field>

          <Field label="Affiliation">
            <input className="inp" value={affil}
              onChange={(e) => setAffil(e.target.value)}
              placeholder="e.g. MIT, Department of Bioengineering" />
          </Field>

          <Field label="Target Journal">
            <input className="inp" value={journal}
              onChange={(e) => setJournal(e.target.value)}
              placeholder="e.g. Nature Biomedical Engineering" />
          </Field>

          <Field label="IEEE Format">
            <div className="radio-row">
              {(["journal", "conference"] as const).map((f) => (
                <label key={f} className="radio-opt">
                  <input type="radio" value={f} checked={format === f}
                    onChange={() => setFormat(f)} />
                  <span>{f === "journal" ? "Journal article" : "Conference paper"}</span>
                </label>
              ))}
            </div>
          </Field>
        </section>

        {/* RIGHT — content */}
        <section className="card">
          <h2 className="section-title">Paper Content</h2>

          <Field label="Overview / Description *"
            hint="Introduction, hypothesis, research narrative — the more detail the better">
            <textarea className="inp ta" rows={8} value={overview}
              onChange={(e) => setOverview(e.target.value)}
              placeholder="Describe your research: background, hypothesis, why it matters…" />
          </Field>

          <Field label="Method Notes"
            hint="Experimental parameters, subject model, materials, metrics, procedure">
            <textarea className="inp ta" rows={6} value={methods}
              onChange={(e) => setMethods(e.target.value)}
              placeholder="Subject model, experimental design, data acquisition, analysis metrics…" />
          </Field>
        </section>
      </div>

      {/* Figures */}
      <section className="card figures-card">
        <h2 className="section-title">Figures</h2>
        <p className="field-hint">
          Upload images related to your study. The pipeline will decide which to include — unrelated
          images are automatically excluded.
        </p>

        <div className="drop-zone" onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
            setImages((prev) => [...prev, ...files]);
          }}>
          <span className="drop-icon">🖼</span>
          <span className="drop-label">Drag & drop images, or <u>click to browse</u></span>
          <span className="drop-hint">PNG, JPG, WebP — max 10 files</span>
          <input ref={fileRef} type="file" accept="image/*" multiple style={{ display: "none" }}
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              setImages((prev) => [...prev, ...files]);
              e.target.value = "";
            }} />
        </div>

        {images.length > 0 && (
          <div className="img-list">
            {images.map((f) => (
              <div key={f.name} className="img-pill">
                <span>{f.name}</span>
                <button className="pill-remove" onClick={() => removeImage(f.name)}>×</button>
              </div>
            ))}
          </div>
        )}
      </section>

      {error && <div className="error-banner">{error}</div>}

      <div className="submit-footer">
        <p className="submit-note">
          The pipeline runs <strong>paper input → research → IEEE editor → PDF</strong> and takes ~3-5 minutes.
        </p>
        <button
          className="btn btn-primary submit-btn"
          onClick={submit}
          disabled={!canSubmit || loading}
        >
          {loading ? "Submitting…" : "▶  Generate Manuscript"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      {hint && <span className="field-hint">{hint}</span>}
      {children}
    </div>
  );
}
