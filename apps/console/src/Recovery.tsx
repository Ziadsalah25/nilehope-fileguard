import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, CheckCircle2, FileClock, RefreshCw, Search, ShieldCheck, TriangleAlert } from "lucide-react";
import { api, clock, type Row } from "./api";

const labels: Record<string, string> = {
  version_captured: "Version preserved", restored: "Restored & verified",
  restore_failed: "Restore failed", restore_conflict: "Conflict preserved",
  loop_suppressed: "Restore limit reached", delete_observed: "Deletion observed", scan_failed: "Scan paused",
};

export default function Recovery() {
  const [data, setData] = useState<any>(null), [query, setQuery] = useState("");
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setBusy(true);
    try { setData(await api(`/recovery?q=${encodeURIComponent(query)}`)); setError(""); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }, [query]);
  useEffect(() => { const debounce = setTimeout(load, 200), interval = setInterval(load, 5000); return () => { clearTimeout(debounce); clearInterval(interval); }; }, [load]);
  return <>
    <div className="page-heading"><div><div className="eyebrow">FILEGUARD RECOVERY LAB</div>
      <h1>Every version. A way back.</h1><p>Follow protected copies, deleted-file recovery, and integrity results.</p></div>
      <button className="btn secondary" onClick={load} disabled={busy}><RefreshCw size={15} className={busy ? "spin" : ""} />Refresh</button>
    </div>
    <div className="recovery-intro"><div className="recovery-intro-icon"><ShieldCheck size={28} /></div>
      <div><h2>Recover after deletion</h2><p>The lab agent preserves stable file content and checks SHA-256 before and after restoration. Existing destinations are never silently overwritten.</p></div>
      <span className="badge blue">Disposable lab data</span>
    </div>
    {error && <div className="form-error" role="alert">{error}</div>}
    <div className="recovery-metrics">
      {[
        { label: "Protected versions", value: data?.stats.versions, icon: FileClock, detail: "Stable copies reported by agents" },
        { label: "Verified restores", value: data?.stats.restored, icon: CheckCircle2, detail: "Content hash verified by the agent" },
        { label: "Review events", value: data?.stats.issues, icon: TriangleAlert, detail: "Failures, conflicts, and paused scans" },
      ].map(metric => <div className="panel recovery-metric" key={metric.label}><metric.icon size={21} /><span>{metric.label}</span>
        <strong>{metric.value ?? "—"}</strong><small>{metric.detail}</small></div>)}
    </div>
    <section className="panel"><div className="panel-heading"><div><h2>Recovery & version history</h2><p>The latest 200 matching reports. Copies remain in each agent’s separate repository.</p></div>
      <div className="recovery-search"><Search size={16} /><input aria-label="Search recovery history" placeholder="Search file or agent…" value={query} onChange={e => setQuery(e.target.value)} /></div>
    </div>
      <div className="recovery-table-scroll"><table className="recovery-table"><thead><tr><th>File / agent</th><th>Outcome</th><th>Integrity / version</th><th>Time</th></tr></thead>
        <tbody>{data?.items.map((row: Row) => <tr key={row.id}><td><button className="recovery-file" onClick={() => setQuery(row.relative_path)}>{row.relative_path || "Agent scan"}</button><small>{row.device}</small></td>
          <td><span className={`badge ${row.kind === "restored" ? "green" : row.kind === "version_captured" ? "blue" : "orange"}`}>{labels[row.kind] || row.kind}</span><small className="recovery-message">{row.message}</small></td>
          <td>{row.sha256 ? <><code title={row.sha256}>SHA-256 {row.sha256.slice(0, 12)}…</code><small title={row.version_id}>{row.bytes?.toLocaleString()} bytes · {row.version_id?.slice(0, 8)}</small></> : <span className="muted">No version</span>}</td><td><span>{clock(row.ts)}</span></td></tr>)}</tbody>
      </table></div>
      {!data && !error && <div className="recovery-empty">Loading recovery reports…</div>}
      {data?.items.length === 0 && <div className="recovery-empty"><FileClock size={30} /><h3>{query ? "No matching recovery reports" : "Your recovery history starts here"}</h3><p>Start the lab recovery agent to preserve a first version. This page shows actual agent reports.</p></div>}
    </section>
    <div className="recovery-footnotes"><div><ArrowDownToLine size={19} /><p><strong>Local policy, centrally visible.</strong> Automatic restore is configured on the lab agent. This console does not send restore or retention commands.</p></div>
      <div><TriangleAlert size={19} /><p><strong>Content recovery MVP.</strong> It does not block deletion. Windows Service installation, NTFS ACLs, user attribution, large-volume performance, and production backup hardening need separate validation.</p></div></div>
  </>;
}
