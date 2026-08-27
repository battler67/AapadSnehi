import { Activity, ArrowDown, Check, Database, FileJson, Globe2, Landmark, LoaderCircle, Newspaper, Plus, Radio, RefreshCw, Search, ShieldCheck, Workflow } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Notice, PageHeader } from "../components/ui";
import type { AppData } from "../hooks/useAppData";
import { timeAgo, titleCase } from "../lib/format";

const adapterIcon = (kind: string) => kind === "bluesky" ? Radio : ["government", "sachet"].includes(kind) ? Landmark : ["reliefweb", "google_news"].includes(kind) ? Newspaper : ["gdelt", "serper"].includes(kind) ? Search : kind === "seed" ? Database : Globe2;

export function PipelinePage({ data }: { data: AppData }) {
  const [running, setRunning] = useState(false);
  const [showSourceForm, setShowSourceForm] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const liveEnabled = data.dashboard.mode === "live-enabled";

  const run = async () => {
    setRunning(true); setMessage(""); setError("");
    try { const runs = await data.runPipeline(); setMessage(liveEnabled ? `Pipeline completed ${runs.length} source checks and refreshed external signals.` : `Pipeline completed ${runs.length} source checks. Live providers remained gated.`); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Pipeline run failed"); }
    finally { setRunning(false); }
  };

  const addSource = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    try {
      await data.addGovernmentSource({ name: String(form.get("name")), authority: String(form.get("authority")), endpoint: String(form.get("endpoint")), enabled: true });
      setMessage("Government source added to the approved adapter registry."); setShowSourceForm(false); event.currentTarget.reset();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not add source"); }
  };

  return (
    <div className="content page-space pipeline-page">
      <PageHeader eyebrow="Data ingestion" title="Many signals. One operational schema." description="Provider-specific adapters preserve raw provenance, while the normalizer creates reviewable portal incidents." actions={<div className="page-button-row"><button className="button secondary" type="button" onClick={() => setShowSourceForm((visible) => !visible)}><Plus size={16} /> Government source</button><button className="button primary" type="button" onClick={() => void run()} disabled={running}>{running ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}{running ? "Running checks…" : liveEnabled ? "Refresh live signals" : "Run demo pipeline"}</button></div>} />
      {message && <Notice tone="success"><Check size={17} />{message}</Notice>}
      {error && <Notice tone="danger">{error}</Notice>}
      {showSourceForm && <form className="glass-panel source-form" onSubmit={addSource}><div><p className="eyebrow"><span />Approved institution</p><h2>Add a government feed</h2><p>Only allowlisted HTTPS hosts are accepted. JSON, GeoJSON, RSS and CAP XML are normalized by the same adapter.</p></div><label className="field"><span>Display name</span><input required name="name" placeholder="State warning feed" /></label><label className="field"><span>Legal authority</span><input required name="authority" placeholder="Institution name" /></label><label className="field wide"><span>HTTPS endpoint</span><input required name="endpoint" type="url" placeholder="https://mausam.imd.gov.in/…" /></label><button className="button primary" type="submit"><ShieldCheck size={16} /> Validate and add</button></form>}

      <section className="pipeline-flow glass-panel">
        <div className="flow-node"><span><Globe2 size={21} /></span><strong>Provider adapters</strong><small>Fetch bounded payloads</small></div><ArrowDown className="flow-arrow" />
        <div className="flow-node"><span><FileJson size={21} /></span><strong>Raw envelopes</strong><small>Keep provider identity</small></div><ArrowDown className="flow-arrow" />
        <div className="flow-node featured"><span><Workflow size={21} /></span><strong>Portal normalizer</strong><small>Hazard, place, time, needs</small></div><ArrowDown className="flow-arrow" />
        <div className="flow-node"><span><ShieldCheck size={21} /></span><strong>Trust + dedupe</strong><small>Official ≠ community</small></div><ArrowDown className="flow-arrow" />
        <div className="flow-node"><span><Activity size={21} /></span><strong>Priority features</strong><small>Explainable 0–100 score</small></div><ArrowDown className="flow-arrow" />
        <div className="flow-node"><span><Database size={21} /></span><strong>Incident store</strong><small>Map and dispatch ready</small></div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><p className="eyebrow"><span />Adapter registry</p><h2>{data.sources.length} configured sources</h2><p>Each source fails independently and records its last run state.</p></div></div>
        <div className="adapter-grid">{data.sources.map((source) => { const Icon = adapterIcon(source.adapterType); return <article className="adapter-card glass-panel" key={source.id}><div className="adapter-head"><span className={`adapter-icon adapter-${source.adapterType}`}><Icon size={20} /></span><span className={`run-status ${source.status}`}>{titleCase(source.status)}</span></div><h3>{source.name}</h3><p>{source.authority}</p><div className="adapter-meta"><span>TYPE <strong>{titleCase(source.adapterType)}</strong></span><span>TRUST <strong>{titleCase(source.sourceKind)}</strong></span></div><div className="endpoint-line"><Globe2 size={13} /><span>{source.endpoint || "Internal deterministic fixture"}</span></div><small>{source.lastRunAt ? `Last checked ${timeAgo(source.lastRunAt)}` : "Not run in this environment"}</small></article>; })}</div>
      </section>

      <section className="schema-section glass-panel">
        <div><p className="eyebrow"><span />Normalizer contract</p><h2>Portal-ready incident</h2><p>Only records with a hazard, trustworthy time and usable coordinates reach the operational map.</p></div>
        <pre><code>{`{
  "externalId": "provider-stable-id",
  "disasterType": "flood",
  "severity": 1..5,
  "geometry": { "lat": 26.20, "lon": 92.94 },
  "verificationStatus": "official | corroborated | unverified",
  "needs": ["food", "shelter", "medical"],
  "priority": { "score": 0..100, "breakdown": { ... } },
  "provenance": { "source", "authority", "url", "observedAt" }
}`}</code></pre>
      </section>

      <section className="glass-panel assignment-table-card">
        <div className="panel-title"><div><p className="eyebrow"><span />Run history</p><h2>Recent ingestion checks</h2></div><span>{data.runs.length} records</span></div>
        {data.runs.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Source</th><th>Status</th><th>Fetched</th><th>Accepted</th><th>Duplicates</th><th>Started</th></tr></thead><tbody>{data.runs.map((run) => <tr key={run.id}><td>{run.sourceName}</td><td><span className={`run-status ${run.status}`}>{titleCase(run.status)}</span></td><td>{run.fetchedCount}</td><td>{run.acceptedCount}</td><td>{run.duplicateCount}</td><td>{timeAgo(run.startedAt)}</td></tr>)}</tbody></table></div> : <div className="empty-inline"><Workflow size={20} />Run the pipeline to verify adapters and idempotent deduplication.</div>}
      </section>
    </div>
  );
}
