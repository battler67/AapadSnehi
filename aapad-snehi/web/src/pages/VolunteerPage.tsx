import { BadgeCheck, Bot, Check, Clock3, Crosshair, HandHeart, Image, Languages, LoaderCircle, MapPin, Medal, Phone, Route, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, UserPlus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { IncidentCard, Notice, PageHeader } from "../components/ui";
import type { AppData } from "../hooks/useAppData";
import { resolveApiUrl } from "../lib/api";
import { titleCase } from "../lib/format";
import type { Volunteer } from "../types";

const serviceOptions = ["food", "water", "shelter", "medical", "rescue", "transport", "verification"];

export function VolunteerPage({ data }: { data: AppData }) {
  const storedId = Number(localStorage.getItem("aapad-volunteer-id") || 0);
  const [activeVolunteer, setActiveVolunteer] = useState<Volunteer | null>(data.volunteers.find((item) => item.id === storedId) || null);
  const [services, setServices] = useState<string[]>(["food", "shelter"]);
  const [latitude, setLatitude] = useState("26.1445");
  const [longitude, setLongitude] = useState("91.7362");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const matchingMissions = useMemo(() => data.incidents.filter((incident) => {
    if (!activeVolunteer) return incident.severity >= 3;
    return incident.needs.some((need) => activeVolunteer.services.includes(need));
  }).slice(0, 6), [activeVolunteer, data.incidents]);
  const pendingReports = useMemo(
    () => data.reports.filter((report) => report.moderationStatus === "needs_volunteer_review"),
    [data.reports],
  );

  const reviewReport = async (trackingId: string, decision: "approve" | "reject") => {
    setReviewBusy(trackingId); setError(""); setMessage("");
    try {
      const reviewer = activeVolunteer?.name || "Volunteer reviewer";
      const updated = await data.moderateReport(trackingId, decision, reviewer);
      setMessage(`${updated.trackingId} ${decision === "approve" ? "approved for response coordination" : "rejected; its stored image was removed"}.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not review report"); }
    finally { setReviewBusy(""); }
  };

  const register = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const preferredPlaces = String(form.get("preferred_places")).split(";").map((item) => item.trim()).filter(Boolean);
    if (!preferredPlaces.length || preferredPlaces.length > 5 || preferredPlaces.some((place) => place.length > 120)) {
      setError("Provide one to five preferred work areas, separated by semicolons.");
      return;
    }
    setBusy(true); setError(""); setMessage("");
    try {
      const volunteer = await data.createVolunteer({
        name: String(form.get("name")), phone: String(form.get("phone")), email: String(form.get("email")),
        home_location: String(form.get("home_location")), preferred_places: preferredPlaces, latitude: Number(latitude), longitude: Number(longitude),
        services, skills: String(form.get("skills")).split(",").map((item) => item.trim()).filter(Boolean),
        languages: String(form.get("languages")).split(",").map((item) => item.trim()).filter(Boolean), availability: "available",
      });
      localStorage.setItem("aapad-volunteer-id", String(volunteer.id));
      setActiveVolunteer(volunteer);
      setMessage("Profile created. Verification remains pending, but you can inspect suitable missions now.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not register this profile");
    } finally { setBusy(false); }
  };

  const claim = async (incidentId: number, incidentNeeds: string[]) => {
    if (!activeVolunteer) { setError("Create a volunteer profile before claiming a mission."); return; }
    const service = incidentNeeds.find((need) => activeVolunteer.services.includes(need));
    if (!service) { setError("This mission does not match your registered services."); return; }
    setBusy(true); setError("");
    try {
      await data.claimTask(incidentId, activeVolunteer.id, service);
      setMessage(`Mission claimed for ${service}. Await coordinator instructions before travelling.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to claim mission"); }
    finally { setBusy(false); }
  };

  const locate = () => navigator.geolocation?.getCurrentPosition((position) => {
    setLatitude(position.coords.latitude.toFixed(6)); setLongitude(position.coords.longitude.toFixed(6));
  });

  return (
    <div className="content page-space">
      <PageHeader eyebrow="Volunteer network" title="Put your skills where they matter most" description="Register the services you can safely provide, then receive missions matched to need and distance." actions={activeVolunteer && <div className="profile-chip"><span>{activeVolunteer.name.split(" ").map((part) => part[0]).join("").slice(0, 2)}</span><div><strong>{activeVolunteer.name}</strong><small>{activeVolunteer.verified ? "Verified volunteer" : "Verification pending"}</small></div></div>} />

      {message && <Notice tone="success"><Check size={17} />{message}</Notice>}
      {error && <Notice tone="danger">{error}</Notice>}

      <div className="volunteer-layout">
        {!activeVolunteer ? (
          <form className="glass-panel form-card volunteer-form" onSubmit={register}>
            <div className="form-card-head"><span><UserPlus size={20} /></span><div><h2>Create your responder profile</h2><p>Verification and training checks are separate from registration.</p></div></div>
            <div className="field-grid two"><label className="field"><span>Full name</span><input required name="name" placeholder="Your full name" /></label><label className="field"><span>Phone</span><input required name="phone" inputMode="tel" placeholder="+91…" /></label></div>
            <div className="field-grid two"><label className="field"><span>Email <small>optional</small></span><input name="email" type="email" placeholder="you@example.org" /></label><label className="field"><span>Home base</span><input required name="home_location" placeholder="City, district, state" /></label></div>
            <label className="field"><span>Preferred work areas <small>1-5 areas, separated by ;</small></span><input required name="preferred_places" placeholder="Guwahati, Assam; Nagaon, Assam" /></label>
            <div className="field-grid location-fields"><label className="field"><span>Latitude</span><input required value={latitude} onChange={(event) => setLatitude(event.target.value)} /></label><label className="field"><span>Longitude</span><input required value={longitude} onChange={(event) => setLongitude(event.target.value)} /></label><button className="button secondary" type="button" onClick={locate}><Crosshair size={16} /> Locate</button></div>
            <fieldset className="choice-field"><legend>Services you can provide</legend><div className="choice-grid services">{serviceOptions.map((service) => <label key={service} className={services.includes(service) ? "choice active" : "choice"}><input type="checkbox" checked={services.includes(service)} onChange={() => setServices((current) => current.includes(service) ? current.filter((item) => item !== service) : [...current, service])} /><span>{service[0].toUpperCase() + service.slice(1)}</span></label>)}</div></fieldset>
            <div className="field-grid two"><label className="field"><span>Skills</span><input name="skills" placeholder="First aid, logistics, driving" /></label><label className="field"><span>Languages</span><input name="languages" placeholder="Hindi, English, Assamese" /></label></div>
            <label className="consent-row"><input type="checkbox" required /><span>I will only accept tasks I am trained and equipped to perform, and will follow agency safety instructions.</span></label>
            <button className="button primary" type="submit" disabled={busy || !services.length}>{busy ? <LoaderCircle className="spin" size={17} /> : <HandHeart size={17} />}Register as a volunteer</button>
          </form>
        ) : (
          <aside className="glass-panel volunteer-profile">
            <div className="volunteer-avatar">{activeVolunteer.name.split(" ").map((part) => part[0]).join("").slice(0, 2)}</div>
            <h2>{activeVolunteer.name}</h2><p><MapPin size={14} />{activeVolunteer.homeLocation}</p>
            <span className={activeVolunteer.verified ? "verification-badge official" : "verification-badge unverified"}>{activeVolunteer.verified ? <BadgeCheck size={14} /> : <ShieldCheck size={14} />}{activeVolunteer.verified ? "Identity verified" : "Verification pending"}</span>
            <div className="profile-stat-grid"><div><Medal size={18} /><strong>{activeVolunteer.completedMissions}</strong><span>Missions</span></div><div><Sparkles size={18} /><strong>{activeVolunteer.services.length}</strong><span>Services</span></div></div>
            <div className="profile-list"><strong><HandHeart size={15} /> Services</strong><div className="need-row">{activeVolunteer.services.map((service) => <span key={service}>{service}</span>)}</div></div>
            <div className="profile-list"><strong><Route size={15} /> Preferred work areas</strong><p>{activeVolunteer.preferredPlaces.join(" · ")}</p></div>
            <div className="profile-list"><strong><Languages size={15} /> Languages</strong><p>{activeVolunteer.languages.join(", ") || "Not provided"}</p></div>
            <div className="profile-list"><strong><Phone size={15} /> Contact</strong><p>{activeVolunteer.phone}</p></div>
            <button className="button secondary full" type="button" onClick={() => { localStorage.removeItem("aapad-volunteer-id"); setActiveVolunteer(null); }}>Switch profile</button>
          </aside>
        )}

        <section className="mission-section">
          <div className="section-heading"><div><p className="eyebrow"><span />Suitable missions</p><h2>{activeVolunteer ? "Matched to your services" : "Urgent missions near the top"}</h2><p>Do not self-deploy. Claiming starts coordination with an administrator.</p></div></div>
          <div className="mission-grid">{matchingMissions.map((incident) => <div className="mission-wrap" key={incident.id}><IncidentCard incident={incident} compact /><button className="button secondary full" type="button" disabled={busy || !activeVolunteer || !incident.needs.some((need) => activeVolunteer.services.includes(need))} onClick={() => void claim(incident.id, incident.needs)}><HandHeart size={16} />{activeVolunteer ? "Claim suitable task" : "Register to claim"}</button></div>)}</div>
        </section>
      </div>

      <section className="glass-panel report-review-panel volunteer-review-panel">
        <div className="panel-title"><div><p className="eyebrow"><span />Community verification</p><h2>Reports needing volunteer review</h2></div><span className="queue-live"><Bot size={14} />{pendingReports.length} need review</span></div>
        <p className="muted">Review the submitted image and its short OpenAI description. Approve only when visible disaster evidence supports the reported incident; rejecting removes the stored image.</p>
        {pendingReports.length ? <div className="report-review-list">{pendingReports.map((report) => <article className="report-review-item" key={report.trackingId}>
          <div className="report-review-head"><span className="report-image-icon"><Image size={18} /></span><div><strong>{report.incident.title}</strong><small><MapPin size={11} />{report.incident.locationName} <Clock3 size={11} />{new Date(report.createdAt).toLocaleString("en-IN")}</small></div><span className={`run-status ${report.moderationStatus}`}>{titleCase(report.moderationStatus)}</span></div>
          {report.imageAvailable && <img className="report-review-image" src={resolveApiUrl(report.imageUrl)} alt={`Submitted evidence for ${report.incident.locationName}`} loading="lazy" />}
          <p><Bot size={14} /><span><strong>OpenAI description</strong>{report.aiCaption || "Description unavailable"}</span></p>
          <small>{report.aiReason}</small>
          {report.aiAnalysis.observations?.length ? <small>Visible observations: {report.aiAnalysis.observations.join(" · ")}</small> : null}
          <div className="report-review-actions"><button className="button secondary" type="button" disabled={reviewBusy === report.trackingId} onClick={() => void reviewReport(report.trackingId, "approve")}><ThumbsUp size={15} />Approve</button><button className="button danger" type="button" disabled={reviewBusy === report.trackingId} onClick={() => void reviewReport(report.trackingId, "reject")}><ThumbsDown size={15} />Reject</button></div>
        </article>)}</div> : <div className="empty-inline"><Check size={20} />No citizen images currently need volunteer review.</div>}
      </section>
    </div>
  );
}
