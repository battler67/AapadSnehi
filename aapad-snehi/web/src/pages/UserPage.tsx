import { Camera, CheckCircle2, Clock3, Crosshair, FileImage, Info, LoaderCircle, MapPin, ShieldCheck, SignalLow, Upload, X, XCircle } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Notice, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import { queueCitizenReport } from "../lib/offline-queue";

const needs = ["food", "water", "shelter", "medical", "rescue", "transport"];
const hazards = ["flood", "landslide", "cyclone", "earthquake", "wildfire", "heatwave", "infrastructure", "other"];

export function UserPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [locating, setLocating] = useState(false);
  const [selectedNeeds, setSelectedNeeds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{
    id: string;
    queued: boolean;
    status?: "accepted" | "rejected" | "needs_volunteer_review";
    message?: string;
    caption?: string;
  } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const locate = () => {
    if (!navigator.geolocation) { setError("Location is not supported on this device."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLatitude(position.coords.latitude.toFixed(6));
        setLongitude(position.coords.longitude.toFixed(6));
        setLocating(false);
      },
      () => { setError("Location permission was not granted. You can enter coordinates manually."); setLocating(false); },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (!file) { setError("Add a recent photo before submitting the report."); return; }
    const form = new FormData(event.currentTarget);
    form.set("image", file);
    form.set("needs", JSON.stringify(selectedNeeds));
    setSubmitting(true);
    try {
      const response = await api.submitReport(form);
      setResult({
        id: response.trackingId,
        queued: false,
        status: response.moderationStatus,
        message: response.message,
        caption: response.caption,
      });
    } catch {
      try {
        const queueId = await queueCitizenReport(form);
        setResult({ id: queueId, queued: true });
      } catch {
        setError("The report could not be sent or saved offline. Please try again when connected.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    const accepted = result.status === "accepted";
    const rejected = result.status === "rejected";
    const ResultIcon = result.queued || accepted ? CheckCircle2 : rejected ? XCircle : Clock3;
    const eyebrow = result.queued
      ? "Stored safely on this device"
      : accepted
        ? "Disaster evidence detected"
        : rejected
          ? "Report rejected"
          : "Volunteer approval needed";
    const title = result.queued
      ? "Queued for reconnection"
      : accepted
        ? "The community signal is now visible."
        : rejected
          ? "The image did not show clear disaster evidence."
          : "The report is safely held for a person to review.";
    return (
      <div className="content page-space narrow-page">
        <div className="success-panel glass-panel">
          <span className={`success-icon ${rejected ? "rejected" : !accepted && !result.queued ? "review" : ""}`}><ResultIcon size={34} /></span>
          <p className="eyebrow"><span />{eyebrow}</p>
          <h1>{title}</h1>
          <p>{result.queued ? "AapadSnehi will retry this evidence when your connection returns." : result.message}</p>
          {result.caption && <Notice tone="info"><Info size={17} /><span><strong>Image caption:</strong> {result.caption}</span></Notice>}
          <div className="tracking-code"><small>Tracking reference</small><strong>{result.id}</strong></div>
          <Notice tone={rejected ? "danger" : "warning"}><Info size={17} /> This submission is community evidence, not an official alert. If life is in immediate danger, contact emergency services.</Notice>
          <button className="button primary" type="button" onClick={() => { setResult(null); setFile(null); setSelectedNeeds([]); }}>Submit another report</button>
        </div>
      </div>
    );
  }

  return (
    <div className="content page-space">
      <PageHeader eyebrow="Community users" title="Report an incident from the ground" description="Capture recent evidence, preserve its location, and tell response teams what people need." />
      <form className="report-layout" onSubmit={submit}>
        <div className="form-stack">
          <section className="glass-panel form-card">
            <div className="form-card-head"><span><Camera size={20} /></span><div><h2>1. Add recent evidence</h2><p>The backend securely sends a metadata-stripped copy to the configured hosted AI image-screening service.</p></div></div>
            {preview ? (
              <div className="image-preview"><img src={preview} alt="Selected incident evidence" /><button type="button" onClick={() => setFile(null)} aria-label="Remove selected photo"><X size={17} /></button><span><FileImage size={14} />{file?.name}</span></div>
            ) : (
              <label className="camera-drop">
                <span><Camera size={27} /></span><strong>Capture or choose a photo</strong><small>JPEG, PNG or WebP · maximum 6 MB</small><input type="file" name="image" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
            )}
          </section>

          <section className="glass-panel form-card">
            <div className="form-card-head"><span><MapPin size={20} /></span><div><h2>2. Pin the incident</h2><p>Precise coordinates help the nearest suitable team respond.</p></div></div>
            <div className="field-grid two">
              <label className="field"><span>Latitude</span><input required name="latitude" inputMode="decimal" value={latitude} onChange={(event) => setLatitude(event.target.value)} placeholder="26.144500" /></label>
              <label className="field"><span>Longitude</span><input required name="longitude" inputMode="decimal" value={longitude} onChange={(event) => setLongitude(event.target.value)} placeholder="91.736200" /></label>
            </div>
            <button className="button secondary location-button" type="button" onClick={locate} disabled={locating}>{locating ? <LoaderCircle className="spin" size={17} /> : <Crosshair size={17} />}{locating ? "Getting location…" : "Use my current location"}</button>
            <label className="field"><span>Place or landmark</span><input required name="location_name" placeholder="Village, ward, road or nearby landmark" /></label>
          </section>

          <section className="glass-panel form-card">
            <div className="form-card-head"><span><ShieldCheck size={20} /></span><div><h2>3. Describe the situation</h2><p>State only what you can observe directly.</p></div></div>
            <div className="field-grid two">
              <label className="field"><span>Incident type</span><select name="disaster_type" defaultValue="flood">{hazards.map((hazard) => <option key={hazard} value={hazard}>{hazard[0].toUpperCase() + hazard.slice(1)}</option>)}</select></label>
              <label className="field"><span>Observed severity</span><select name="severity" defaultValue="3"><option value="1">1 · Minor</option><option value="2">2 · Low</option><option value="3">3 · Significant</option><option value="4">4 · Severe</option><option value="5">5 · Life threatening</option></select></label>
            </div>
            <label className="field"><span>What can you see?</span><textarea required minLength={8} maxLength={1800} name="description" rows={5} placeholder="Describe damage, access, people at risk and what changed recently…" /></label>
            <fieldset className="choice-field"><legend>What support appears necessary?</legend><div className="choice-grid">{needs.map((need) => <label key={need} className={selectedNeeds.includes(need) ? "choice active" : "choice"}><input type="checkbox" checked={selectedNeeds.includes(need)} onChange={() => setSelectedNeeds((current) => current.includes(need) ? current.filter((item) => item !== need) : [...current, need])} /><span>{need[0].toUpperCase() + need.slice(1)}</span></label>)}</div></fieldset>
          </section>
        </div>

        <aside className="submit-sidebar">
          <section className="glass-panel form-card sticky-card">
            <p className="eyebrow"><span />Reporter details</p>
            <h2>Help verifiers follow up</h2>
            <p className="muted">Contact details are operational evidence metadata and are not shown on the public map.</p>
            <label className="field"><span>Name <small>optional</small></span><input name="reporter_name" placeholder="Your name" /></label>
            <label className="field"><span>Phone or email <small>optional</small></span><input name="contact" placeholder="For verification only" /></label>
            <label className="consent-row"><input required type="checkbox" name="consent" value="true" /><span>I confirm this is recent, unaltered evidence and consent to secure transfer of a processed copy to the hosted AI service for incident screening.</span></label>
            {error && <Notice tone="danger"><Info size={16} />{error}</Notice>}
            <button className="button primary full" type="submit" disabled={submitting}>{submitting ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}{submitting ? "Sending report…" : "Submit for verification"}</button>
            <div className="offline-note"><SignalLow size={16} /><span><strong>Low connectivity?</strong>Your report is queued on-device if the API cannot be reached.</span></div>
          </section>
        </aside>
      </form>
    </div>
  );
}
