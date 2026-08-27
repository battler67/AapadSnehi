import { Activity, ArrowRight, BadgeCheck, Bot, Check, ChevronRight, ClipboardCheck, Clock3, Image, LoaderCircle, MapPin, Route, ShieldCheck, ThumbsDown, ThumbsUp, UserCheck, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AutomaticDistributionPanel } from "../components/AutomaticDistributionPanel";
import { IncidentCard, Notice, PageHeader, SeverityBadge, VerificationBadge } from "../components/ui";
import type { AppData } from "../hooks/useAppData";
import { api, resolveApiUrl } from "../lib/api";
import { titleCase } from "../lib/format";
import type { Incident, Volunteer } from "../types";

export function AdminPage({ data }: { data: AppData }) {
  const ordered = useMemo(() => [...data.incidents].sort((a, b) => b.priorityScore - a.priorityScore), [data.incidents]);
  const [selected, setSelected] = useState<Incident | null>(ordered[0] || null);
  const [suggestions, setSuggestions] = useState<Volunteer[]>([]);
  const [volunteerId, setVolunteerId] = useState<number>(0);
  const [service, setService] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!selected) return;
    const local = data.volunteers.map((volunteer) => {
      const overlap = selected.needs.filter((need) => volunteer.services.includes(need)).length;
      return { ...volunteer, fitScore: Math.min(98, 35 + overlap * 22 + (volunteer.verified ? 8 : 0)) };
    }).sort((a, b) => (b.fitScore || 0) - (a.fitScore || 0));
    setSuggestions(local);
    setVolunteerId(local[0]?.id || 0);
    setService(selected.needs.find((need) => local[0]?.services.includes(need)) || selected.needs[0] || "general support");
    if (data.connection === "api") api.suggestions(selected.id).then((items) => { setSuggestions(items); setVolunteerId(items[0]?.id || 0); }).catch(() => undefined);
  }, [data.connection, data.volunteers, selected]);

  const chosenVolunteer = suggestions.find((item) => item.id === volunteerId);
  const chooseVolunteer = (volunteer: Volunteer) => {
    setVolunteerId(volunteer.id);
    setService(selected?.needs.find((need) => volunteer.services.includes(need)) || volunteer.services[0] || "general support");
  };

  const assign = async () => {
    if (!selected || !volunteerId || !service) { setError("Select an incident, volunteer and service."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const assignment = await data.createAssignment({ incident_id: selected.id, volunteer_id: volunteerId, service, note });
      setMessage(`${assignment.volunteerName} assigned to ${assignment.incidentTitle}.`);
      setNote("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not create assignment"); }
    finally { setBusy(false); }
  };

  const reviewReport = async (trackingId: string, decision: "approve" | "reject") => {
    setReviewBusy(trackingId); setError(""); setMessage("");
    try {
      const updated = await data.moderateReport(trackingId, decision, "Administrator reviewer");
      setMessage(`${updated.trackingId} ${decision === "approve" ? "approved for the response queue" : "rejected and kept off the dashboard"}.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not review report"); }
    finally { setReviewBusy(""); }
  };

  return (
    <div className="content page-space admin-page">
      <PageHeader eyebrow="Administrator workspace" title="Allocate people with context, not guesswork" description="Inspect the score, compare suitable volunteers and make the final dispatch decision." actions={<span className="demo-admin-badge"><ShieldCheck size={15} /> Demonstration admin console</span>} />
      {message && <Notice tone="success"><Check size={17} />{message}</Notice>}
      {error && <Notice tone="danger">{error}</Notice>}

      <AutomaticDistributionPanel data={data} />

      <div className="admin-grid">
        <section className="queue-panel glass-panel">
          <div className="panel-title"><div><p className="eyebrow"><span />Priority queue</p><h2>{ordered.length} active incidents</h2></div><span className="queue-live"><Activity size={14} /> scored live</span></div>
          <div className="admin-queue">{ordered.map((incident, index) => <button key={incident.id} type="button" className={selected?.id === incident.id ? "queue-item active" : "queue-item"} onClick={() => setSelected(incident)}><span className="queue-rank">{String(index + 1).padStart(2, "0")}</span><div><div><SeverityBadge severity={incident.severity} intensity={incident.intensity} /><VerificationBadge status={incident.verificationStatus} /></div><strong>{incident.title}</strong><small><MapPin size={12} />{incident.locationName}</small></div><span className="queue-score"><strong>{Math.round(incident.priorityScore)}</strong><small>priority</small></span><ChevronRight size={17} /></button>)}</div>
        </section>

        <section className="allocation-panel">
          {selected && <>
            <IncidentCard incident={selected} />
            <div className="glass-panel allocation-card">
              <div className="panel-title"><div><p className="eyebrow"><span />Recommended responders</p><h2>Fit for this mission</h2></div><Users size={22} /></div>
              <p className="muted">Fit combines registered capability, availability and approximate distance. Verification is shown separately.</p>
              <div className="suggestion-list">{suggestions.slice(0, 5).map((volunteer, index) => <button key={volunteer.id} type="button" className={volunteerId === volunteer.id ? "suggestion active" : "suggestion"} onClick={() => chooseVolunteer(volunteer)}><span className="volunteer-mini-avatar">{volunteer.name.split(" ").map((part) => part[0]).join("").slice(0, 2)}</span><div><strong>{volunteer.name}{volunteer.verified && <BadgeCheck size={14} />}</strong><small><MapPin size={11} />{volunteer.homeLocation}</small><small className="preferred-places"><Route size={11} />Preferred: {volunteer.preferredPlaces.join(" · ")}</small><div className="need-row">{volunteer.services.slice(0, 3).map((item) => <span key={item}>{item}</span>)}</div></div><span className="fit-score"><small>FIT</small><strong>{Math.round(volunteer.fitScore || 0)}</strong><i style={{ width: `${volunteer.fitScore || 0}%` }} /></span>{index === 0 && <em>best match</em>}</button>)}</div>
            </div>
            <div className="glass-panel dispatch-card">
              <div className="form-card-head"><span><ClipboardCheck size={20} /></span><div><h2>Prepare assignment</h2><p>The volunteer still receives instructions and must accept safely.</p></div></div>
              <div className="dispatch-summary"><div><UserCheck size={18} /><span>Responder</span><strong>{chosenVolunteer?.name || "Choose a volunteer"}</strong></div><ArrowRight size={18} /><div><Route size={18} /><span>Destination</span><strong>{selected.locationName}</strong></div></div>
              <div className="field-grid two"><label className="field"><span>Assigned service</span><select value={service} onChange={(event) => setService(event.target.value)}>{Array.from(new Set([...selected.needs, ...(chosenVolunteer?.services || [])])).map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label><label className="field"><span>Response status</span><input value="Assigned · awaiting acceptance" disabled /></label></div>
              <label className="field"><span>Coordinator note</span><textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Meeting point, supplies, safety constraints…" /></label>
              <button className="button primary full" type="button" onClick={() => void assign()} disabled={busy || !chosenVolunteer}>{busy ? <LoaderCircle className="spin" size={17} /> : <UserCheck size={17} />}{busy ? "Creating assignment…" : "Assign volunteer"}</button>
            </div>
          </>}
        </section>
      </div>

      <section className="glass-panel report-review-panel">
        <div className="panel-title"><div><p className="eyebrow"><span />Image evidence triage</p><h2>Citizen report review</h2></div><span className="queue-live"><Bot size={14} />{data.reports.filter((report) => report.moderationStatus === "needs_volunteer_review").length} need review</span></div>
        <p className="muted">AI image screening and an independent disaster-keyword check assess visible evidence only. They do not prove location, recency or authenticity; uncertainty or disagreement stays off the dashboard until a person approves it.</p>
        {data.reports.length ? <div className="report-review-list">{data.reports.map((report) => <article className="report-review-item" key={report.trackingId}>
          <div className="report-review-head"><span className="report-image-icon"><Image size={18} /></span><div><strong>{report.incident.title}</strong><small><MapPin size={11} />{report.incident.locationName} <Clock3 size={11} />{new Date(report.createdAt).toLocaleString("en-IN")}</small></div><span className={`run-status ${report.moderationStatus}`}>{titleCase(report.moderationStatus)}</span></div>
          {report.imageAvailable && <img className="report-review-image" src={resolveApiUrl(report.imageUrl)} alt={`Submitted evidence for ${report.incident.locationName}`} loading="lazy" />}
          <p><Bot size={14} /><span><strong>OpenAI description</strong>{report.aiCaption || "Description unavailable"}</span></p>
          <small>{report.aiReason}</small>
          {(report.aiProvider || report.aiModel) && <small>Provider/model: {[report.aiProvider, report.aiModel].filter(Boolean).join(" · ")}</small>}
          {report.aiAnalysis.disasterEvidence && <small>Visible disaster evidence: {titleCase(report.aiAnalysis.disasterEvidence)}{report.aiAnalysis.hazards?.length ? ` · Hazards: ${report.aiAnalysis.hazards.map(titleCase).join(", ")}` : ""}</small>}
          {report.aiAnalysis.observations?.length ? <small>Visible observations: {report.aiAnalysis.observations.join(" · ")}</small> : null}
          {report.aiPromptVersion && <small>Screening policy: {report.aiPromptVersion}</small>}
          {report.reviewedAt && <small>Reviewed by {report.reviewedBy} on {new Date(report.reviewedAt).toLocaleString("en-IN")}</small>}
          {report.moderationStatus === "needs_volunteer_review" && <div className="report-review-actions"><button className="button secondary" type="button" disabled={reviewBusy === report.trackingId} onClick={() => void reviewReport(report.trackingId, "approve")}><ThumbsUp size={15} />Approve</button><button className="button danger" type="button" disabled={reviewBusy === report.trackingId} onClick={() => void reviewReport(report.trackingId, "reject")}><ThumbsDown size={15} />Reject</button></div>}
        </article>)}</div> : <div className="empty-inline"><Image size={20} />Citizen image screening results will appear here.</div>}
      </section>

      <section className="glass-panel assignment-table-card">
        <div className="panel-title"><div><p className="eyebrow"><span />Dispatch log</p><h2>Current assignments</h2></div><span>{data.assignments.length} records</span></div>
        {data.assignments.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Responder</th><th>Incident</th><th>Service</th><th>Status</th><th>Assigned</th></tr></thead><tbody>{data.assignments.map((assignment) => <tr key={assignment.id}><td>{assignment.volunteerName}</td><td>{assignment.incidentTitle}</td><td>{titleCase(assignment.service)}</td><td><span className={`run-status ${assignment.status}`}>{titleCase(assignment.status)}</span></td><td>{new Date(assignment.assignedAt).toLocaleString("en-IN")}</td></tr>)}</tbody></table></div> : <div className="empty-inline"><ClipboardCheck size={20} />Assignments will appear here after dispatch.</div>}
      </section>
    </div>
  );
}
