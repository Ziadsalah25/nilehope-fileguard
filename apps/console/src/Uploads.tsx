import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDownToLine, Check, RefreshCw, Upload, X } from "lucide-react";
import { api, clock, type Row } from "./api";

export default function Uploads({ enabled }: { enabled: boolean }) {
  const [items, setItems] = useState<Row[]>([]);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const load = useCallback(async () => {
    if (!enabled) return;
    try { setItems((await api("/uploads")).items); setError(""); }
    catch (e) { setError((e as Error).message); }
  }, [enabled]);
  useEffect(() => { void load(); const timer = setInterval(load, 10000); return () => clearInterval(timer); }, [load]);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setNotice("");
    const body = new FormData(e.currentTarget), file = body.get("file");
    if (!(file instanceof File) || file.size === 0 || file.size > 10 * 1024 * 1024) {
      setError("Choose a nonempty file up to 10 MiB."); return;
    }
    setBusy(true);
    try {
      await api("/uploads", { method: "POST", body });
      form.current?.reset(); setNotice("Submitted for review. Download becomes available after approval.");
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function decide(id: number, decision: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      await api(`/uploads/${id}/${decision}`, { method: "POST", body: "{}" });
      setNotice(decision === "approve" ? "Approved. An administrator can now download and place this file on the share." : "Rejected. This file cannot be downloaded.");
      await load();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <>
    <div className="page-heading"><div><div className="eyebrow">REVIEW BEFORE RELEASE</div>
      <h1>Upload approvals</h1><p>Review submitted files before an administrator places them on a share.</p></div>
      {enabled && <button className="btn secondary" onClick={load} disabled={busy}><RefreshCw size={15} />Refresh</button>}
    </div>
    <div className="recovery-intro"><div className="recovery-intro-icon"><Upload size={26} /></div>
      <div><h2>A separate approval queue</h2><p>Pending and rejected files cannot be downloaded. Approval releases a file for administrator download; placement on the file server is manual.</p></div>
      <span className="badge blue">Administrator pilot</span>
    </div>
    {!enabled ? <section className="panel recovery-empty"><h3>Upload approval is not enabled</h3><p>Contact the console administrator to enable this feature for your installation.</p></section> : <>
      {error && <div className="form-error" role="alert">{error}</div>}
      {notice && <p className="upload-notice" role="status">{notice}</p>}
      <form className="panel upload-form" onSubmit={submit} ref={form}>
        <h2>Submit a file</h2><p>Files up to 10 MiB. Submission and review use the existing administrator sign-in.</p>
        <label>File<input type="file" name="file" required disabled={busy} /></label>
        <label>Reason for upload<textarea name="reason" required maxLength={1000} rows={3} placeholder="Describe where this file is needed and why." disabled={busy} /></label>
        <button className="btn primary" type="submit" disabled={busy}><Upload size={15} />Submit for review</button>
      </form>
      <section className="panel"><div className="panel-heading"><div><h2>Upload queue</h2><p>The latest 200 submissions. Approval checks the request; it does not scan files for malware.</p></div></div>
        <div className="recovery-table-scroll"><table className="recovery-table"><thead><tr><th>File / reason</th><th>Submitted</th><th>Status</th><th>Review / release</th></tr></thead>
          <tbody>{items.map(row => <tr key={row.id}><td><strong className="upload-name">{row.file_name}</strong><small>{row.bytes.toLocaleString()} bytes</small><small>{row.reason}</small><code title={row.sha256}>SHA-256 {row.sha256.slice(0, 12)}…</code></td>
            <td>{row.submitted_by}<small>{clock(row.created_at)}</small></td>
            <td><span className={`badge ${row.status === "approved" ? "green" : row.status === "rejected" ? "orange" : "blue"}`}>{row.status}</span>{row.decided_by && <small>{row.decided_by} · {clock(row.decided_at)}</small>}</td>
            <td><div className="upload-actions">{row.status === "pending" ? <><button className="btn secondary" disabled={busy} onClick={() => decide(row.id, "approve")}><Check size={14} />Approve</button><button className="btn secondary" disabled={busy} onClick={() => decide(row.id, "reject")}><X size={14} />Reject</button></> : row.status === "approved" ? <a className="btn secondary" href={`/api/console/uploads/${row.id}/download`}><ArrowDownToLine size={14} />Download approved file</a> : <span className="muted">Download unavailable</span>}</div></td></tr>)}</tbody>
        </table></div>
        {items.length === 0 && <div className="recovery-empty"><Upload size={28} /><h3>No uploads submitted</h3><p>Choose a disposable test file to try the review workflow.</p></div>}
      </section>
    </>}
  </>;
}
