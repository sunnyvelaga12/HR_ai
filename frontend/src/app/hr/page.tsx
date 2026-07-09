"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

// ─── Types ────────────────────────────────────────────────────────────────────
type Tab = "overview" | "knowledge" | "employees" | "documents" | "querylogs" | "vectordb" | "analytics" | "settings";

interface Doc {
  id: string;
  filename: string;
  size_bytes: number;
  status: "processing" | "ready" | "error";
  uploaded_at: string;
}

interface Employee {
  id: string;
  fullName: string;
  email: string;
  department: string;
  jobTitle: string;
  officeLocation?: string;
  workMode?: string;
  phone?: string;
  managerName?: string;
  employmentStatus?: string;
  employeeId?: string;
}

interface Stats {
  total_employees: number;
  total_documents: number;
  ready_documents: number;
  department_count: number;
  departments: { department: string; count: number }[];
}

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

interface PreviewRow {
  fullName: string;
  email: string;
  role: string;
  department: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function fmtDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

async function apiFetch(url: string, opts: RequestInit = {}) {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  const res = await fetch(url, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(typeof data === "string" ? data : (data?.detail ?? data?.error ?? "Request failed"));
  return data;
}

// ─── Shared UI ────────────────────────────────────────────────────────────────
function Spinner({ size = 16, color = "#3b82f6" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ animation: "spin 0.8s linear infinite" }}>
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="3" opacity={0.25} />
      <path d="M4 12a8 8 0 018-8" stroke={color} strokeWidth="3" strokeLinecap="round" />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </svg>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; dot: string }> = {
    ready:      { bg: "#f0fdf4", text: "#16a34a", dot: "#16a34a" },
    error:      { bg: "#fef2f2", text: "#dc2626", dot: "#dc2626" },
    processing: { bg: "#fffbeb", text: "#d97706", dot: "#d97706" },
    active:     { bg: "#f0fdf4", text: "#16a34a", dot: "#16a34a" },
    inactive:   { bg: "#f8fafc", text: "#64748b", dot: "#94a3b8" },
  };
  const s = map[status?.toLowerCase()] ?? map.processing;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 10px", borderRadius: 99, background: s.bg, color: s.text, fontSize: 11, fontWeight: 600 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot, display: "inline-block" }} />
      {status ? status.charAt(0).toUpperCase() + status.slice(1) : "—"}
    </span>
  );
}

function ErrBanner({ msg, onClose }: { msg: string; onClose?: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 16px", borderRadius: 10, background: "#fef2f2", border: "1px solid #fecaca", color: "#dc2626", fontSize: 13 }}>
      <span style={{ flexShrink: 0, fontWeight: 700 }}>✕</span>
      <span style={{ flex: 1 }}>{msg}</span>
      {onClose && <button onClick={onClose} style={{ border: "none", background: "none", color: "#dc2626", cursor: "pointer", fontWeight: 700, padding: 0 }}>×</button>}
    </div>
  );
}

function SuccessBanner({ msg }: { msg: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderRadius: 10, background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#16a34a", fontSize: 13 }}>
      <span>✓</span> {msg}
    </div>
  );
}

function InfoBanner({ msg }: { msg: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px", borderRadius: 10, background: "#eff6ff", border: "1px solid #bfdbfe", color: "#1d4ed8", fontSize: 13 }}>
      <span>ℹ</span> {msg}
    </div>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 16, padding: 24, ...style }}>
      {children}
    </div>
  );
}

function StatCard({ label, value, icon, color, sub }: { label: string; value: number | string; icon: string; color: string; sub?: string }) {
  return (
    <Card style={{ display: "flex", alignItems: "center", gap: 16 }}>
      <div style={{ width: 50, height: 50, borderRadius: 14, background: color + "18", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, flexShrink: 0 }}>
        {icon}
      </div>
      <div>
        <p style={{ fontSize: 28, fontWeight: 700, color: "#0f172a", margin: 0, lineHeight: 1.1 }}>{value}</p>
        <p style={{ fontSize: 13, color: "#64748b", margin: 0, marginTop: 3 }}>{label}</p>
        {sub && <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, marginTop: 2 }}>{sub}</p>}
      </div>
    </Card>
  );
}

function DropZone({ accept, label, onFile, file, icon }: { accept: string; label: string; onFile: (f: File) => void; file: File | null; icon: string }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const drop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setOver(false);
    const f = e.dataTransfer.files[0]; if (f) onFile(f);
  }, [onFile]);
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      onClick={() => ref.current?.click()}
      style={{
        border: `2px dashed ${over ? "#3b82f6" : file ? "#16a34a" : "#cbd5e1"}`,
        borderRadius: 12, padding: "28px 20px", textAlign: "center",
        cursor: "pointer", background: over ? "#eff6ff" : file ? "#f0fdf4" : "#f8fafc", transition: "all 0.2s",
      }}
    >
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }} onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
      <div style={{ fontSize: 32, marginBottom: 8 }}>{file ? "✅" : icon}</div>
      {file ? (
        <p style={{ margin: 0, fontSize: 13, color: "#16a34a", fontWeight: 600 }}>{file.name} · {fmtBytes(file.size)}</p>
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 13, color: "#475569", fontWeight: 600 }}>Drag & drop or <span style={{ color: "#3b82f6", textDecoration: "underline" }}>browse</span></p>
          <p style={{ margin: 0, marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{label}</p>
        </>
      )}
    </div>
  );
}

// ─── TAB: Overview ────────────────────────────────────────────────────────────
function OverviewTab({ companyId }: { companyId: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [passkey, setPasskey] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/stats`),
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey`)
    ])
      .then(([st, pk]) => { setStats(st); setPasskey(pk.passkey); })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={32} /></div>;
  if (err) return <ErrBanner msg={err} />;
  if (!stats) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {passkey && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#f1f5f9", padding: "12px 20px", borderRadius: 12, border: "1px solid #e2e8f0" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>Workspace Passkey</span>
            <span style={{ fontSize: 13, color: "#475569" }}>Employees need this to join.</span>
          </div>
          <code style={{ marginLeft: "auto", fontSize: 20, fontWeight: 700, color: "#0f172a", letterSpacing: 1 }}>{passkey}</code>
          <button 
            onClick={() => { navigator.clipboard.writeText(passkey); alert("Copied passkey!"); }} 
            style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
          >Copy</button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16 }}>
        <StatCard label="Total Employees" value={stats.total_employees} icon="👥" color="#3b82f6" />
        <StatCard label="Policy Documents" value={stats.total_documents} icon="📄" color="#6366f1" />
        <StatCard label="Ready for AI" value={stats.ready_documents} icon="✅" color="#16a34a" sub="indexed in Vector DB" />
        <StatCard label="Departments" value={stats.department_count} icon="🏢" color="#d97706" />
      </div>

      {stats.departments.length > 0 && (
        <Card>
          <p style={{ margin: "0 0 16px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Department Breakdown</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {stats.departments.map(d => {
              const pct = stats.total_employees > 0 ? Math.round((d.count / stats.total_employees) * 100) : 0;
              return (
                <div key={d.department}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, color: "#475569", fontWeight: 500 }}>{d.department}</span>
                    <span style={{ fontSize: 13, color: "#94a3b8" }}>{d.count} · {pct}%</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 99, background: "#f1f5f9", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pct}%`, borderRadius: 99, background: "linear-gradient(90deg,#3b82f6,#6366f1)", transition: "width 0.6s ease" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card style={{ background: "linear-gradient(135deg,#0f172a,#1e293b)", border: "1px solid #334155" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
          <div>
            <p style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#f1f5f9" }}>🔒 Multi-Tenant AI Isolation</p>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#94a3b8", lineHeight: 1.6 }}>
              All policies and employee data are stored in Pinecone with your <strong style={{ color: "#60a5fa" }}>company_id</strong> tag.<br/>
              Employees querying the chatbot will <em>only</em> receive answers from your company's data.
            </p>
          </div>
          <div style={{ padding: "8px 16px", borderRadius: 10, background: "#16a34a18", border: "1px solid #16a34a40", color: "#4ade80", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
            ✓ ACTIVE
          </div>
        </div>
        <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 8, background: "#0f172a", fontFamily: "monospace", fontSize: 12, color: "#64748b" }}>
          <span style={{ color: "#60a5fa" }}>filter</span>{': { "company_id": { "$eq": "'}<span style={{ color: "#34d399" }}>{companyId.slice(0,8)}…</span>{'" } }'}
        </div>
      </Card>

      {stats.total_employees === 0 && stats.total_documents === 0 && (
        <Card style={{ textAlign: "center", padding: 48 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🚀</div>
          <p style={{ fontWeight: 700, fontSize: 16, color: "#0f172a", margin: "0 0 8px" }}>Welcome! Let's get started.</p>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>Upload policy documents in the Documents tab and import employees to populate this dashboard.</p>
        </Card>
      )}
    </div>
  );
}

// ─── TAB: AI Knowledge Base ───────────────────────────────────────────────────
function KnowledgeTab({ companyId }: { companyId: string }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([
    { role: "assistant", content: "Hi! I'm your HR assistant. Ask me anything about your company's policies — leave, attendance, salary, or find employee details." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function send() {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput(""); setErr(null);
    const history = msgs.map(m => ({ role: m.role, content: m.content }));
    setMsgs(prev => [...prev, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const data = await apiFetch(`${BACKEND_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history }),
      });
      setMsgs(prev => [...prev, { role: "assistant", content: data.response }]);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <InfoBanner msg="This chat uses RAG — answers are pulled from your Pinecone vector index filtered to your company_id." />
      <Card style={{ display: "flex", flexDirection: "column", height: 520, padding: 0, overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto", padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              {m.role === "assistant" && (
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "linear-gradient(135deg,#3b82f6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0, marginRight: 10, marginTop: 2 }}>🤖</div>
              )}
              <div style={{
                maxWidth: "72%", padding: "10px 14px",
                borderRadius: m.role === "user" ? "16px 16px 4px 16px" : "4px 16px 16px 16px",
                background: m.role === "user" ? "linear-gradient(135deg,#3b82f6,#6366f1)" : "#f1f5f9",
                color: m.role === "user" ? "#fff" : "#0f172a", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap",
              }}>
                {m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 32, height: 32, borderRadius: "50%", background: "linear-gradient(135deg,#3b82f6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, flexShrink: 0 }}>🤖</div>
              <div style={{ padding: "10px 16px", borderRadius: "4px 16px 16px 16px", background: "#f1f5f9", display: "flex", gap: 4, alignItems: "center" }}>
                {[0, 1, 2].map(k => (
                  <span key={k} style={{ width: 6, height: 6, borderRadius: "50%", background: "#94a3b8", display: "inline-block", animation: `bounce 1.2s ease-in-out ${k * 0.2}s infinite` }} />
                ))}
                <style>{`@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}`}</style>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        {err && <div style={{ padding: "0 24px 8px" }}><ErrBanner msg={err} onClose={() => setErr(null)} /></div>}
        <div style={{ padding: "12px 24px 20px", borderTop: "1px solid #e2e8f0", display: "flex", gap: 10 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Ask about leave policy, salary, who is the manager of…"
            style={{ flex: 1, padding: "10px 16px", borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc", fontSize: 13, color: "#0f172a", outline: "none" }}
          />
          <button
            onClick={send} disabled={!input.trim() || loading}
            style={{ padding: "10px 20px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer", opacity: (!input.trim() || loading) ? 0.5 : 1 }}
          >
            Send
          </button>
        </div>
      </Card>
    </div>
  );
}

// ─── TAB: Employees ───────────────────────────────────────────────────────────
function EmployeesTab({ companyId }: { companyId: string }) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importResult, setImportResult] = useState<{ created: number; updated: number; skipped: number } | null>(null);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [sendInvites, setSendInvites] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const [editEmp, setEditEmp] = useState<Employee | null>(null);
  const [editForm, setEditForm] = useState<Partial<Employee>>({});
  const [editSaving, setEditSaving] = useState(false);
  const [editSaveErr, setEditSaveErr] = useState<string | null>(null);

  function openEdit(e: Employee) {
    setEditEmp(e);
    setEditForm({ ...e });
    setEditSaveErr(null);
  }

  async function saveEdit() {
    if (!editEmp) return;
    setEditSaving(true); setEditSaveErr(null);
    try {
      await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/${editEmp.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });
      setEditEmp(null);
      loadEmployees();
    } catch (e: any) {
      setEditSaveErr(e.message);
    } finally {
      setEditSaving(false);
    }
  }

  async function deleteEmp() {
    if (!editEmp) return;
    if (!confirm(`Are you sure you want to delete ${editEmp.fullName}?`)) return;
    setEditSaving(true); setEditSaveErr(null);
    try {
      await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/${editEmp.id}`, { method: "DELETE" });
      setEditEmp(null);
      loadEmployees();
    } catch (e: any) {
      setEditSaveErr(e.message);
    } finally {
      setEditSaving(false);
    }
  }

  function loadEmployees() {
    setLoading(true); setErr(null);
    apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees?limit=200`)
      .then(d => { setEmployees(d.employees); setTotal(d.total); })
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadEmployees(); }, [companyId]);

  async function handlePreview(file: File) {
    setCsvFile(file); setPreview(null); setPreviewErr(null); setImportResult(null);
    setPreviewLoading(true);
    try {
      const form = new FormData(); form.append("file", file);
      const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/preview`, { method: "POST", body: form });
      setPreview(d.rows ?? []);
    } catch (e: any) { setPreviewErr(e.message); }
    finally { setPreviewLoading(false); }
  }

  async function handleImport() {
    if (!csvFile) return;
    setImportLoading(true); setImportErr(null);
    try {
      const form = new FormData(); form.append("file", csvFile);
      const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/employees/import?sendInvites=${sendInvites}`, { method: "POST", body: form });
      setImportResult(d);
      setCsvFile(null); setPreview(null);
      loadEmployees();
    } catch (e: any) { setImportErr(e.message); }
    finally { setImportLoading(false); }
  }

  const filtered = employees.filter(e =>
    (e.fullName || "").toLowerCase().includes(search.toLowerCase()) ||
    (e.email || "").toLowerCase().includes(search.toLowerCase()) ||
    (e.department || "").toLowerCase().includes(search.toLowerCase())
  );

  const workModeColor = (mode?: string) => {
    if (!mode) return "#94a3b8";
    const m = mode.toLowerCase();
    if (m === "remote") return "#3b82f6";
    if (m === "hybrid") return "#8b5cf6";
    return "#16a34a";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Toolbar */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by name, email or department…"
          style={{ flex: 1, minWidth: 200, padding: "9px 14px", borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 13, color: "#0f172a", background: "#f8fafc", outline: "none" }}
        />
        <button
          onClick={() => setShowImport(v => !v)}
          style={{ padding: "9px 18px", borderRadius: 10, border: "none", background: showImport ? "#f1f5f9" : "linear-gradient(135deg,#3b82f6,#6366f1)", color: showImport ? "#475569" : "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
        >
          {showImport ? "← Back to List" : "⬆ Import CSV / Excel"}
        </button>
      </div>

      {showImport ? (
        <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Import Employees via CSV / Excel</p>
            <p style={{ margin: 0, fontSize: 12, color: "#64748b" }}>
              Supported columns: <code style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11 }}>first_name, last_name, email, phone, department, designation, manager_name, office_location, work_mode, employment_status</code>
            </p>
          </div>
          {previewErr && <ErrBanner msg={previewErr} onClose={() => setPreviewErr(null)} />}
          {importErr && <ErrBanner msg={importErr} onClose={() => setImportErr(null)} />}
          {importResult && (
            <SuccessBanner msg={`✅ Import complete — Created: ${importResult.created} | Updated: ${importResult.updated} | Skipped: ${importResult.skipped} | All indexed in Pinecone with company_id`} />
          )}

          <DropZone accept=".csv,.xlsx,.xls" label="CSV or Excel — drag & drop or click to browse" onFile={handlePreview} file={csvFile} icon="📊" />

          {previewLoading && <div style={{ display: "flex", justifyContent: "center", padding: 16 }}><Spinner /></div>}

          {preview && preview.length > 0 && (
            <div>
              <p style={{ margin: "0 0 10px", fontSize: 13, color: "#475569", fontWeight: 600 }}>
                Preview (first {preview.length} rows) — <span style={{ color: "#16a34a" }}>looks good!</span>
              </p>
              <div style={{ overflowX: "auto", borderRadius: 10, border: "1px solid #e2e8f0" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead style={{ background: "#f8fafc" }}>
                    <tr>
                      {["Full Name", "Email", "Role / Designation", "Department"].map(h => (
                        <th key={h} style={{ padding: "8px 14px", textAlign: "left", color: "#64748b", fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((row, i) => (
                      <tr key={i} style={{ borderTop: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "8px 14px", fontWeight: 600, color: "#0f172a" }}>{row.fullName || "—"}</td>
                        <td style={{ padding: "8px 14px", color: "#64748b" }}>{row.email || "—"}</td>
                        <td style={{ padding: "8px 14px", color: "#64748b" }}>{row.role || "—"}</td>
                        <td style={{ padding: "8px 14px", color: "#64748b" }}>{row.department || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#475569", cursor: "pointer" }}>
                  <input type="checkbox" checked={sendInvites} onChange={e => setSendInvites(e.target.checked)} />
                  Send email invitations to new employees
                </label>
              </div>

              <button
                onClick={handleImport}
                disabled={importLoading}
                style={{ marginTop: 12, width: "100%", padding: "12px 0", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#16a34a,#059669)", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: importLoading ? 0.6 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
              >
                {importLoading ? <><Spinner size={14} color="#fff" /> Importing & indexing in Pinecone…</> : `🚀 Import All ${preview.length}+ Employees`}
              </button>
            </div>
          )}
          {preview && preview.length === 0 && <ErrBanner msg="No valid rows found. Check your file has email, first_name, last_name columns." />}
        </Card>
      ) : (
        <Card style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>Showing <strong style={{ color: "#0f172a" }}>{filtered.length}</strong> of {total} employees</p>
            <span style={{ fontSize: 11, color: "#94a3b8", background: "#f8fafc", padding: "3px 10px", borderRadius: 99, border: "1px solid #e2e8f0" }}>
              🔒 All indexed in Pinecone with your company_id
            </span>
          </div>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={28} /></div>
          ) : err ? (
            <div style={{ padding: 16 }}><ErrBanner msg={err} /></div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 14 }}>
              {employees.length === 0 ? "No employees yet. Use ⬆ Import CSV to add your team." : "No employees match your search."}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead style={{ background: "#f8fafc" }}>
                  <tr>
                    {["Employee", "Email", "Department", "Designation", "Location", "Mode"].map(h => (
                      <th key={h} style={{ padding: "11px 16px", textAlign: "left", fontWeight: 600, color: "#64748b", fontSize: 12, whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(emp => (
                    <tr key={emp.id} style={{ borderTop: "1px solid #f1f5f9", transition: "background 0.15s", cursor: "pointer" }}
                      onClick={() => openEdit(emp)}
                      onMouseEnter={e => (e.currentTarget.style.background = "#f8fafc")}
                      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                      <td style={{ padding: "11px 16px", fontWeight: 600, color: "#0f172a" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <div style={{ width: 34, height: 34, borderRadius: "50%", background: "linear-gradient(135deg,#3b82f6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 700, fontSize: 13, flexShrink: 0 }}>
                            {(emp.fullName || "?").charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div>{emp.fullName}</div>
                            {emp.employeeId && <div style={{ fontSize: 11, color: "#94a3b8" }}>{emp.employeeId}</div>}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: "11px 16px", color: "#64748b" }}>{emp.email}</td>
                      <td style={{ padding: "11px 16px", color: "#475569" }}>{emp.department || "—"}</td>
                      <td style={{ padding: "11px 16px", color: "#475569" }}>{(emp as any).jobTitle || "—"}</td>
                      <td style={{ padding: "11px 16px", color: "#475569" }}>{(emp as any).officeLocation || "—"}</td>
                      <td style={{ padding: "11px 16px" }}>
                        {(emp as any).workMode ? (
                          <span style={{ fontSize: 11, fontWeight: 600, color: workModeColor((emp as any).workMode), background: workModeColor((emp as any).workMode) + "15", padding: "2px 8px", borderRadius: 99 }}>
                            {(emp as any).workMode}
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Edit Drawer */}
      {editEmp && (
        <>
          <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(15, 23, 42, 0.4)", zIndex: 100, backdropFilter: "blur(2px)" }} onClick={() => setEditEmp(null)} />
          <div style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 400, maxWidth: "90vw", background: "#fff", zIndex: 101, boxShadow: "-4px 0 24px rgba(0,0,0,0.1)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "20px 24px", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0f172a" }}>Edit Employee</h2>
              <button onClick={() => setEditEmp(null)} style={{ background: "none", border: "none", fontSize: 24, cursor: "pointer", color: "#64748b" }}>×</button>
            </div>
            <div style={{ padding: 24, flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16 }}>
              {editSaveErr && <ErrBanner msg={editSaveErr} onClose={() => setEditSaveErr(null)} />}
              {[
                { label: "Full Name", key: "fullName" },
                { label: "Email", key: "email" },
                { label: "Department", key: "department" },
                { label: "Job Title", key: "jobTitle" },
                { label: "Phone", key: "phone" },
                { label: "Manager", key: "managerName" },
                { label: "Location", key: "officeLocation" },
                { label: "Work Mode", key: "workMode" },
                { label: "Status", key: "employmentStatus" },
                { label: "Employee ID", key: "employeeId" },
              ].map(f => (
                <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>{f.label}</span>
                  <input
                    value={(editForm as any)[f.key] || ""}
                    onChange={e => setEditForm({ ...editForm, [f.key]: e.target.value })}
                    style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14 }}
                  />
                </label>
              ))}
            </div>
            <div style={{ padding: 24, borderTop: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", background: "#f8fafc" }}>
              <button onClick={deleteEmp} disabled={editSaving} style={{ padding: "10px 16px", borderRadius: 8, background: "#fef2f2", color: "#dc2626", border: "1px solid #fecaca", fontWeight: 600, cursor: "pointer", opacity: editSaving ? 0.5 : 1 }}>Delete</button>
              <div style={{ display: "flex", gap: 12 }}>
                <button onClick={() => setEditEmp(null)} style={{ padding: "10px 16px", borderRadius: 8, background: "#fff", color: "#475569", border: "1px solid #cbd5e1", fontWeight: 600, cursor: "pointer" }}>Cancel</button>
                <button onClick={saveEdit} disabled={editSaving} style={{ padding: "10px 20px", borderRadius: 8, background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", border: "none", fontWeight: 700, cursor: "pointer", opacity: editSaving ? 0.5 : 1 }}>Save</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── TAB: Documents ───────────────────────────────────────────────────────────
function DocumentsTab({ companyId }: { companyId: string }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [uploadOk, setUploadOk] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  async function fetchDocs() {
    try {
      const d = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents`);
      setDocs(d.documents); setErr(null);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    fetchDocs();
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, [companyId]);

  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === "processing");
    if (hasProcessing && !pollingRef.current) {
      pollingRef.current = setInterval(fetchDocs, 3000);
    } else if (!hasProcessing && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, [docs]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true); setUploadErr(null); setUploadOk(null);
    try {
      const form = new FormData(); form.append("file", file);
      const doc = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents`, { method: "POST", body: form });
      setDocs(prev => [doc, ...prev]);
      setUploadOk(`"${file.name}" uploaded — chunked & indexed in Pinecone with your company_id.`);
      setFile(null);
    } catch (e: any) { setUploadErr(e.message); }
    finally { setUploading(false); }
  }

  async function handleDelete(docId: string) {
    try {
      await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/documents/${docId}`, { method: "DELETE" });
      setDocs(prev => prev.filter(d => d.id !== docId));
    } catch (e: any) { setErr(e.message); }
  }

  const fileIcon = (name: string) => name.endsWith(".pdf") ? "📕" : name.endsWith(".docx") ? "📘" : "📄";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <p style={{ margin: "0 0 4px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Upload Policy Document</p>
          <p style={{ margin: 0, fontSize: 12, color: "#64748b" }}>
            Documents are automatically chunked (~1500 chars) and indexed in Pinecone with your <strong>company_id</strong> for RAG retrieval.
          </p>
        </div>
        {uploadErr && <ErrBanner msg={uploadErr} onClose={() => setUploadErr(null)} />}
        {uploadOk && <SuccessBanner msg={uploadOk} />}
        <DropZone accept=".pdf,.docx,.txt" label="PDF, DOCX, or TXT — HR policy documents" onFile={setFile} file={file} icon="📄" />
        <button
          onClick={handleUpload} disabled={!file || uploading}
          style={{ padding: "11px 0", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: (!file || uploading) ? 0.5 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
        >
          {uploading ? <><Spinner size={14} color="#fff" /> Uploading & Indexing in Pinecone…</> : "Upload & Index Document"}
        </button>
      </Card>

      <Card style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Policy Documents <span style={{ color: "#94a3b8", fontWeight: 400, fontSize: 13 }}>({docs.length})</span></p>
          <span style={{ fontSize: 11, color: "#94a3b8", background: "#f8fafc", padding: "3px 10px", borderRadius: 99, border: "1px solid #e2e8f0" }}>
            🔒 Pinecone namespace: policies
          </span>
        </div>
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}><Spinner size={28} /></div>
        ) : err ? (
          <div style={{ padding: 16 }}><ErrBanner msg={err} /></div>
        ) : docs.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 14 }}>No documents uploaded yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {docs.map((doc, i) => (
              <div key={doc.id} style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 20px", borderTop: i === 0 ? "none" : "1px solid #f1f5f9" }}>
                <span style={{ fontSize: 24, flexShrink: 0 }}>{fileIcon(doc.filename)}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ margin: 0, fontWeight: 600, color: "#0f172a", fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{doc.filename}</p>
                  <p style={{ margin: 0, fontSize: 12, color: "#94a3b8", marginTop: 2 }}>{fmtBytes(doc.size_bytes)} · {fmtDate(doc.uploaded_at)}</p>
                </div>
                <StatusBadge status={doc.status} />
                <button
                  onClick={() => handleDelete(doc.id)} title="Delete document"
                  style={{ width: 30, height: 30, borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#94a3b8", transition: "all 0.15s", flexShrink: 0 }}
                  onMouseEnter={e => { e.currentTarget.style.background = "#fef2f2"; e.currentTarget.style.color = "#dc2626"; e.currentTarget.style.borderColor = "#fecaca"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "#fff"; e.currentTarget.style.color = "#94a3b8"; e.currentTarget.style.borderColor = "#e2e8f0"; }}
                >✕</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── TAB: Vector DB Status ────────────────────────────────────────────────────
function VectorDbTab({ companyId }: { companyId: string }) {
  const [health, setHealth] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);
  const [activeNs, setActiveNs] = useState<"policies" | "employees">("policies");

  useEffect(() => {
    apiFetch(`${BACKEND_URL}/api/v1/vectordb/health`)
      .then(setHealth)
      .catch(() => setHealth({ status: "unhealthy", vector_db_connected: false }))
      .finally(() => setHealthLoading(false));
  }, []);

  async function runSearch() {
    if (!searchQuery.trim()) return;
    setSearchLoading(true); setSearchErr(null); setSearchResults(null);
    try {
      const params = new URLSearchParams({ query: searchQuery, top_k: "5", score_threshold: "0.2" });
      const endpoint = activeNs === "policies" ? "policies/search" : "employees/search";
      const d = await apiFetch(`${BACKEND_URL}/api/v1/vectordb/${endpoint}?${params}`);
      setSearchResults(d);
    } catch (e: any) { setSearchErr(e.message); }
    finally { setSearchLoading(false); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Connection Status */}
      <Card>
        <p style={{ margin: "0 0 16px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>🔌 Pinecone Connection</p>
        {healthLoading ? (
          <Spinner />
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "10px 18px",
              borderRadius: 10, background: health?.vector_db_connected ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${health?.vector_db_connected ? "#bbf7d0" : "#fecaca"}`,
              color: health?.vector_db_connected ? "#16a34a" : "#dc2626", fontWeight: 600,
            }}>
              <span style={{ fontSize: 18 }}>{health?.vector_db_connected ? "✓" : "✕"}</span>
              {health?.vector_db_connected ? "Connected to Pinecone" : "Pinecone not connected"}
            </div>
            {health?.index_name && (
              <div style={{ fontSize: 13, color: "#64748b" }}>
                Index: <code style={{ background: "#f1f5f9", padding: "2px 8px", borderRadius: 6 }}>{health.index_name}</code>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Isolation Explanation */}
      <Card style={{ background: "#0f172a", border: "1px solid #1e293b" }}>
        <p style={{ margin: "0 0 12px", fontWeight: 700, fontSize: 14, color: "#f1f5f9" }}>🔒 How Company Isolation Works</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          {[
            { step: "1", title: "HR Uploads Data", desc: "Policies & employees are stored in Pinecone with company_id metadata tag", color: "#3b82f6" },
            { step: "2", title: "Employee Asks Question", desc: "JWT token carries company_id — passed to Pinecone search", color: "#8b5cf6" },
            { step: "3", title: "Filtered Retrieval", desc: "Pinecone returns ONLY vectors where company_id matches — zero cross-tenant leakage", color: "#16a34a" },
          ].map(item => (
            <div key={item.step} style={{ padding: "14px 16px", borderRadius: 12, background: "#1e293b", border: `1px solid ${item.color}30` }}>
              <div style={{ width: 28, height: 28, borderRadius: "50%", background: item.color + "20", border: `1px solid ${item.color}40`, display: "flex", alignItems: "center", justifyContent: "center", color: item.color, fontWeight: 700, fontSize: 13, marginBottom: 10 }}>{item.step}</div>
              <p style={{ margin: "0 0 4px", fontWeight: 600, color: "#f1f5f9", fontSize: 13 }}>{item.title}</p>
              <p style={{ margin: 0, fontSize: 12, color: "#64748b", lineHeight: 1.5 }}>{item.desc}</p>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8, background: "#0f172a", fontFamily: "monospace", fontSize: 11, color: "#475569" }}>
          <span style={{ color: "#60a5fa" }}>// Pinecone query filter applied on every search</span><br/>
          filter{': { "company_id": { "$eq": "'}<span style={{ color: "#34d399" }}>{companyId}</span>{'" } }'}
        </div>
      </Card>

      {/* Semantic Search Test */}
      <Card>
        <p style={{ margin: "0 0 14px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>🔍 Test Semantic Search (your company only)</p>

        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {(["policies", "employees"] as const).map(ns => (
            <button
              key={ns}
              onClick={() => { setActiveNs(ns); setSearchResults(null); }}
              style={{ padding: "6px 16px", borderRadius: 8, border: `1px solid ${activeNs === ns ? "#3b82f6" : "#e2e8f0"}`, background: activeNs === ns ? "#eff6ff" : "#fff", color: activeNs === ns ? "#1d4ed8" : "#64748b", fontWeight: activeNs === ns ? 700 : 500, fontSize: 13, cursor: "pointer" }}
            >
              {ns === "policies" ? "📄 Policies" : "👥 Employees"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runSearch()}
            placeholder={activeNs === "policies" ? "e.g. sick leave days, salary policy…" : "e.g. Data Analyst, Remote worker in Hyderabad…"}
            style={{ flex: 1, padding: "9px 14px", borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 13, outline: "none", background: "#f8fafc" }}
          />
          <button
            onClick={runSearch} disabled={!searchQuery.trim() || searchLoading}
            style={{ padding: "9px 20px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer", opacity: (!searchQuery.trim() || searchLoading) ? 0.5 : 1 }}
          >
            {searchLoading ? <Spinner size={14} color="#fff" /> : "Search"}
          </button>
        </div>

        {searchErr && <div style={{ marginTop: 12 }}><ErrBanner msg={searchErr} /></div>}

        {searchResults && (
          <div style={{ marginTop: 16 }}>
            <p style={{ margin: "0 0 10px", fontSize: 13, color: "#64748b" }}>
              <strong>{searchResults.count ?? (searchResults.results?.length ?? 0)}</strong> results for "<em>{searchQuery}</em>" — filtered to <code style={{ background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, fontSize: 11 }}>company_id: {companyId.slice(0, 8)}…</code>
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(searchResults.results ?? []).map((r: any, i: number) => (
                <div key={i} style={{ padding: "12px 16px", borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#0f172a" }}>
                      {r.metadata?.name || r.metadata?.section || r.metadata?.filename || r.id}
                    </span>
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 99, background: "#eff6ff", color: "#1d4ed8", fontWeight: 600 }}>
                      {(r.score * 100).toFixed(1)}% match
                    </span>
                  </div>
                  {r.metadata?.content_preview && (
                    <p style={{ margin: 0, fontSize: 12, color: "#64748b", lineHeight: 1.5 }}>
                      {r.metadata.content_preview.slice(0, 200)}…
                    </p>
                  )}
                  {r.metadata?.department && (
                    <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                      {r.metadata.department && <span style={{ fontSize: 11, background: "#f1f5f9", color: "#475569", padding: "1px 8px", borderRadius: 99 }}>{r.metadata.department}</span>}
                      {r.metadata.designation && <span style={{ fontSize: 11, background: "#eff6ff", color: "#1d4ed8", padding: "1px 8px", borderRadius: 99 }}>{r.metadata.designation}</span>}
                      {r.metadata.location && <span style={{ fontSize: 11, background: "#fefce8", color: "#854d0e", padding: "1px 8px", borderRadius: 99 }}>{r.metadata.location}</span>}
                    </div>
                  )}
                </div>
              ))}
              {(searchResults.results ?? []).length === 0 && (
                <div style={{ padding: "24px", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
                  No results found. Upload documents or import employees first, then try again.
                </div>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── TAB: Analytics ───────────────────────────────────────────────────────────
function AnalyticsTab({ companyId }: { companyId: string }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/stats`)
      .then(setStats)
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={32} /></div>;
  if (err) return <ErrBanner msg={err} />;
  if (!stats) return null;

  const maxCount = Math.max(...(stats.departments.map(d => d.count)), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 16 }}>
        <StatCard label="Total Employees" value={stats.total_employees} icon="👥" color="#3b82f6" />
        <StatCard label="Documents" value={stats.total_documents} icon="📁" color="#6366f1" />
        <StatCard label="Ready for AI" value={stats.ready_documents} icon="✅" color="#16a34a" />
        <StatCard label="Departments" value={stats.department_count} icon="🏢" color="#d97706" />
      </div>

      {stats.departments.length > 0 && (
        <Card>
          <p style={{ margin: "0 0 20px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Headcount by Department</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {stats.departments.map(d => {
              const pct = Math.round((d.count / maxCount) * 100);
              const empPct = stats.total_employees > 0 ? Math.round((d.count / stats.total_employees) * 100) : 0;
              return (
                <div key={d.department} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ width: 140, fontSize: 13, color: "#475569", fontWeight: 500, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.department}</span>
                  <div style={{ flex: 1, height: 10, borderRadius: 99, background: "#f1f5f9", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${pct}%`, borderRadius: 99, background: "linear-gradient(90deg,#3b82f6,#6366f1)", transition: "width 0.8s ease" }} />
                  </div>
                  <span style={{ width: 60, textAlign: "right", fontSize: 12, color: "#94a3b8", flexShrink: 0 }}>{d.count} ({empPct}%)</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card>
        <p style={{ margin: "0 0 16px", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>AI Knowledge Base</p>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {[
            { label: "Total Documents", value: stats.total_documents, color: "#6366f1" },
            { label: "Ready for AI (Pinecone)", value: stats.ready_documents, color: "#16a34a" },
            { label: "Employees in Vector DB", value: stats.total_employees, color: "#3b82f6" },
            { label: "Processing / Error", value: stats.total_documents - stats.ready_documents, color: "#d97706" },
          ].map(s => (
            <div key={s.label} style={{ flex: 1, minWidth: 120, padding: "16px 20px", borderRadius: 12, background: s.color + "0d", border: `1px solid ${s.color}28` }}>
              <p style={{ margin: 0, fontSize: 26, fontWeight: 700, color: s.color }}>{s.value}</p>
              <p style={{ margin: 0, fontSize: 12, color: "#64748b", marginTop: 4 }}>{s.label}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── TAB: Query Logs ────────────────────────────────────────────────────────────
interface QueryLog {
  _id: string;
  user_id: string;
  question: string;
  answer: string;
  timestamp: string;
}

function QueryLogsTab({ companyId }: { companyId: string }) {
  const [logs, setLogs] = useState<QueryLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/query-logs`)
      .then(d => setLogs(d.logs || d.items || []))
      .catch(e => setErr(e.message))
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={32} /></div>;
  if (err) return <ErrBanner msg={err} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <InfoBanner msg="Query logs only store questions and AI answers. No sensitive passwords or PII are logged beyond what was typed in the chat." />
      <Card style={{ padding: 0, overflow: "hidden" }}>
        {logs.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 14 }}>No queries have been made yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead style={{ background: "#f8fafc" }}>
                <tr>
                  <th style={{ padding: "11px 16px", textAlign: "left", fontWeight: 600, color: "#64748b" }}>Time</th>
                  <th style={{ padding: "11px 16px", textAlign: "left", fontWeight: 600, color: "#64748b" }}>Question</th>
                  <th style={{ padding: "11px 16px", textAlign: "left", fontWeight: 600, color: "#64748b" }}>Answer</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const isExp = expanded[log._id];
                  return (
                    <tr key={log._id} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "11px 16px", color: "#64748b", whiteSpace: "nowrap", verticalAlign: "top" }}>{fmtDate(log.timestamp)}</td>
                      <td style={{ padding: "11px 16px", color: "#0f172a", fontWeight: 500, verticalAlign: "top", minWidth: 200 }}>{log.question}</td>
                      <td style={{ padding: "11px 16px", color: "#475569", verticalAlign: "top" }}>
                        <div style={{ whiteSpace: isExp ? "pre-wrap" : "nowrap", overflow: isExp ? "visible" : "hidden", textOverflow: "ellipsis", maxWidth: isExp ? "100%" : 400 }}>
                          {log.answer}
                        </div>
                        <button onClick={() => setExpanded(p => ({...p, [log._id]: !isExp}))} style={{ background: "none", border: "none", color: "#3b82f6", fontSize: 11, fontWeight: 600, cursor: "pointer", padding: 0, marginTop: 4 }}>
                          {isExp ? "Show less" : "Show more"}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── TAB: Settings ────────────────────────────────────────────────────────────
function SettingsTab({ companyId }: { companyId: string }) {
  const [profile, setProfile] = useState<{ name: string; logo?: string; passkey?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copiedPk, setCopiedPk] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);
  const [passkey, setPasskey] = useState<string | null>(null);
  const [regenLoading, setRegenLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}`),
      apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey`)
    ]).then(([prof, pk]) => {
      setProfile(prof);
      setCompanyName(prof.name);
      setPasskey(pk.passkey);
    }).catch(e => setErr(e.message)).finally(() => setLoading(false));
  }, [companyId]);

  function copyId() { navigator.clipboard.writeText(companyId); setCopied(true); setTimeout(() => setCopied(false), 2000); }
  function copyPasskey() { if(passkey) { navigator.clipboard.writeText(passkey); setCopiedPk(true); setTimeout(() => setCopiedPk(false), 2000); } }

  async function handleRegenerate() {
    if (!confirm("Are you sure? Old passkey will stop working immediately.")) return;
    setRegenLoading(true); setErr(null);
    try {
      const data = await apiFetch(`${BACKEND_URL}/api/hr/companies/${companyId}/passkey/regenerate`, { method: "POST" });
      setPasskey(data.passkey);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setRegenLoading(false);
    }
  }

  async function handleSave() {
    if (!companyName.trim()) return;
    setSaving(true); setSaveErr(null); setSaveOk(false);
    try {
      const form = new FormData();
      form.append("companyName", companyName.trim());
      if (logoFile) form.append("logo", logoFile);
      await apiFetch(`${BACKEND_URL}/api/hr/companies`, { method: "POST", body: form });
      setSaveOk(true);
      if (logoFile) setLogoFile(null);
    } catch (e: any) { setSaveErr(e.message); }
    finally { setSaving(false); }
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 60 }}><Spinner size={28} /></div>;
  if (err) return <ErrBanner msg={err} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <Card style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Company Profile</p>
        {saveErr && <ErrBanner msg={saveErr} onClose={() => setSaveErr(null)} />}
        {saveOk && <SuccessBanner msg="Profile updated successfully." />}
        {profile?.logo && (
          <div>
            <p style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 600, color: "#475569" }}>Current Logo</p>
            <img src={`data:image/png;base64,${profile.logo}`} alt="Company logo" style={{ height: 56, borderRadius: 8, border: "1px solid #e2e8f0", objectFit: "contain", background: "#f8fafc" }} />
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>Company Name</label>
          <input value={companyName} onChange={e => setCompanyName(e.target.value)} style={{ padding: "10px 14px", borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 13, color: "#0f172a", background: "#f8fafc", outline: "none" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#475569" }}>Logo {profile?.logo ? "(change)" : "(optional)"}</label>
          <DropZone accept="image/png,image/jpeg,image/svg+xml,image/webp" label="PNG, JPG, SVG — max 2 MB" onFile={setLogoFile} file={logoFile} icon="🖼️" />
        </div>
        <button
          onClick={handleSave} disabled={saving || !companyName.trim()}
          style={{ padding: "11px 0", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3b82f6,#6366f1)", color: "#fff", fontWeight: 700, fontSize: 14, cursor: "pointer", opacity: (saving || !companyName.trim()) ? 0.5 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
        >
          {saving ? <><Spinner size={14} color="#fff" /> Saving…</> : "Save Changes"}
        </button>
      </Card>

      <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Workspace Passkey</p>
        <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>Share this passkey with your employees. They will use this to join your workspace when signing up.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <code style={{ flex: 1, padding: "14px 20px", borderRadius: 12, background: "#f1f5f9", border: "2px dashed #94a3b8", fontSize: 24, color: "#0f172a", textAlign: "center", fontWeight: 700, letterSpacing: 2 }}>
            {passkey || "..."}
          </code>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <button
              onClick={copyPasskey}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #e2e8f0", background: copiedPk ? "#f0fdf4" : "#fff", color: copiedPk ? "#16a34a" : "#475569", fontWeight: 600, fontSize: 13, cursor: "pointer", transition: "all 0.2s" }}
            >
              {copiedPk ? "Copied ✓" : "Copy"}
            </button>
            <button
              onClick={handleRegenerate} disabled={regenLoading}
              style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid #fecaca", background: "#fef2f2", color: "#dc2626", fontWeight: 600, fontSize: 13, cursor: "pointer", transition: "all 0.2s", opacity: regenLoading ? 0.5 : 1 }}
            >
              {regenLoading ? "Regenerating..." : "Regenerate"}
            </button>
          </div>
        </div>
      </Card>
      
      <Card style={{ display: "flex", flexDirection: "column", gap: 12, opacity: 0.6 }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Company ID (Legacy)</p>
        <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>This is the internal ID used for Pinecone tenant isolation.</p>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <code style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: "#f1f5f9", border: "1px solid #e2e8f0", fontSize: 13, color: "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{companyId}</code>
          <button
            onClick={copyId}
            style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid #e2e8f0", background: copied ? "#f0fdf4" : "#fff", color: copied ? "#16a34a" : "#475569", fontWeight: 600, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap", transition: "all 0.2s" }}
          >
            {copied ? "Copied ✓" : "Copy ID"}
          </button>
        </div>
      </Card>
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────────
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview",   label: "Overview",       icon: "📊" },
  { id: "knowledge",  label: "AI Chat",         icon: "🤖" },
  { id: "employees",  label: "Employees",       icon: "👥" },
  { id: "documents",  label: "Documents",       icon: "📄" },
  { id: "querylogs",  label: "Query Logs",      icon: "📜" },
  { id: "vectordb",   label: "Vector DB",       icon: "🔮" },
  { id: "analytics",  label: "Analytics",       icon: "📈" },
  { id: "settings",   label: "Settings",        icon: "⚙️" },
];

export default function HrDashboard() {
  const router = useRouter();
  const [companyId, setCompanyId] = useState("");
  const [companyName, setCompanyName] = useState("HR Admin");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("token");
    const role = localStorage.getItem("role");
    const cId = localStorage.getItem("companyId");
    if (!t || role !== "hr_admin") { router.push("/login"); return; }
    if (!cId) { router.push("/login"); return; }
    setCompanyId(cId);
    setReady(true);
    apiFetch(`${BACKEND_URL}/api/hr/companies/${cId}`)
      .then(d => { if (d.name) setCompanyName(d.name); })
      .catch(() => {});
  }, [router]);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("companyId");
    router.push("/login");
  }

  if (!ready) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f8fafc" }}>
        <Spinner size={36} />
      </div>
    );
  }

  const tabDescriptions: Record<Tab, string> = {
    overview:   "Real-time snapshot of your HR workspace with multi-tenant status.",
    knowledge:  "Test your RAG-powered AI assistant against your policy documents.",
    employees:  "Import, view and manage your employee directory.",
    documents:  "Upload HR policy documents — auto-chunked and indexed in Pinecone.",
    querylogs:  "View questions employees have asked the AI.",
    vectordb:   "Verify that your data is correctly stored in Pinecone with company isolation.",
    analytics:  "Headcount and knowledge base insights.",
    settings:   "Manage company profile and workspace settings.",
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", fontFamily: "system-ui,-apple-system,sans-serif" }}>
      {/* Header */}
      <header style={{ background: "#0f172a", borderBottom: "1px solid #1e293b", position: "sticky", top: 0, zIndex: 50 }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "0 24px", height: 60, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "linear-gradient(135deg,#3b82f6,#6366f1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>🏢</div>
            <div>
              <p style={{ margin: 0, fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 2, lineHeight: 1 }}>HR Studio</p>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#f1f5f9", lineHeight: 1.4 }}>{companyName}</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 11, color: "#4ade80", background: "#16a34a18", padding: "4px 12px", borderRadius: 99, border: "1px solid #16a34a30", fontWeight: 600 }}>
              🔒 Multi-tenant
            </span>
            <button
              onClick={logout}
              style={{ padding: "7px 16px", borderRadius: 8, border: "1px solid #334155", background: "transparent", color: "#94a3b8", fontSize: 13, cursor: "pointer", fontWeight: 500 }}
              onMouseEnter={e => { e.currentTarget.style.background = "#1e293b"; e.currentTarget.style.color = "#f1f5f9"; }}
              onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#94a3b8"; }}
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 24px", display: "flex", gap: 24 }}>
        {/* Sidebar */}
        <aside style={{ width: 210, flexShrink: 0 }}>
          <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {TABS.map(tab => {
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  id={`tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 14px", borderRadius: 10, border: "none",
                    background: active ? "linear-gradient(135deg,#3b82f618,#6366f118)" : "transparent",
                    color: active ? "#3b82f6" : "#64748b",
                    fontWeight: active ? 700 : 500, fontSize: 13, cursor: "pointer",
                    textAlign: "left", width: "100%",
                    borderLeft: active ? "3px solid #3b82f6" : "3px solid transparent",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = "#f1f5f9"; }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.background = "transparent"; }}
                >
                  <span style={{ fontSize: 16 }}>{tab.icon}</span>
                  {tab.label}
                  {tab.id === "vectordb" && <span style={{ marginLeft: "auto", width: 6, height: 6, borderRadius: "50%", background: "#16a34a", flexShrink: 0 }} />}
                </button>
              );
            })}
          </nav>

          {/* Company ID chip */}
          <div style={{ marginTop: 24, padding: "10px 12px", borderRadius: 10, background: "#fff", border: "1px solid #e2e8f0" }}>
            <p style={{ margin: "0 0 4px", fontSize: 10, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1 }}>Company ID</p>
            <p style={{ margin: 0, fontSize: 11, color: "#64748b", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{companyId.slice(0, 18)}…</p>
          </div>
        </aside>

        {/* Main content */}
        <main style={{ flex: 1, minWidth: 0 }}>
          <div style={{ marginBottom: 20 }}>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
              {TABS.find(t => t.id === activeTab)?.icon} {TABS.find(t => t.id === activeTab)?.label}
            </h1>
            <p style={{ margin: 0, fontSize: 13, color: "#64748b", marginTop: 4 }}>{tabDescriptions[activeTab]}</p>
          </div>

          {activeTab === "overview"  && <OverviewTab  companyId={companyId} />}
          {activeTab === "knowledge" && <KnowledgeTab companyId={companyId} />}
          {activeTab === "employees" && <EmployeesTab companyId={companyId} />}
          {activeTab === "documents" && <DocumentsTab companyId={companyId} />}
          {activeTab === "querylogs" && <QueryLogsTab companyId={companyId} />}
          {activeTab === "vectordb"  && <VectorDbTab  companyId={companyId} />}
          {activeTab === "analytics" && <AnalyticsTab companyId={companyId} />}
          {activeTab === "settings"  && <SettingsTab  companyId={companyId} />}
        </main>
      </div>
    </div>
  );
}
