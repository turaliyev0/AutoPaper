const BASE = (import.meta.env.VITE_API_URL ?? "") + "/api";

export interface Run {
  run_id: string;
  paper_title: string;
  ieee_format: string;
  created_at: string;
  status: "pending" | "running" | "done" | "error";
  execution_dir: string;
  has_pdf: boolean;
  error: string;
  sections_ok: number;
  sections_total: number;
  validation_pass: number;
  validation_warn: number;
  validation_fail: number;
}

export interface StartRunPayload {
  title: string;
  authors: string;
  affiliation: string;
  targetJournal: string;
  overview: string;
  methods: string;
  ieeeFormat: "journal" | "conference";
  images: File[];
}

export const api = {
  async getRuns(): Promise<Run[]> {
    const r = await fetch(`${BASE}/runs`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getRun(id: string): Promise<Run> {
    const r = await fetch(`${BASE}/runs/${id}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  async getLog(id: string): Promise<string[]> {
    const r = await fetch(`${BASE}/runs/${id}/log`);
    if (!r.ok) return [];
    const d = await r.json();
    return d.lines ?? [];
  },

  async deleteRun(id: string): Promise<void> {
    await fetch(`${BASE}/runs/${id}`, { method: "DELETE" });
  },

  async startRun(payload: StartRunPayload): Promise<{ run_id: string }> {
    const fd = new FormData();
    fd.append("title", payload.title);
    fd.append("authors", payload.authors);
    fd.append("affiliation", payload.affiliation);
    fd.append("target_journal", payload.targetJournal);
    fd.append("overview", payload.overview);
    fd.append("methods", payload.methods);
    fd.append("ieee_format", payload.ieeeFormat);
    for (const img of payload.images) fd.append("images", img);
    const r = await fetch(`${BASE}/runs`, { method: "POST", body: fd });
    if (!r.ok) {
      const body = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(body.detail ?? r.statusText);
    }
    return r.json();
  },

  pdfUrl: (id: string) => `${BASE}/runs/${id}/pdf`,
  streamUrl: (id: string) => `${BASE}/runs/${id}/stream`,
};
