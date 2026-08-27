import {
  AlertTriangle,
  BadgeCheck,
  Check,
  ClipboardCheck,
  GitBranch,
  LoaderCircle,
  MapPin,
  Route,
  Sparkles,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { AppData } from "../hooks/useAppData";
import { api } from "../lib/api";
import { distributionSelectionError, groupDistributionAllocations } from "../lib/distribution";
import { titleCase } from "../lib/format";
import type { AllocationStrategyMetadata, DistributionPlan } from "../types";
import { Notice } from "./ui";

const defaultStrategy: AllocationStrategyMetadata = {
  key: "balanced-greedy-v1",
  name: "Balanced greedy distribution",
  version: "1.0.0",
};

export function AutomaticDistributionPanel({ data }: { data: AppData }) {
  const incidents = useMemo(
    () => [...data.incidents].filter((item) => item.active).sort((a, b) => b.priorityScore - a.priorityScore),
    [data.incidents],
  );
  const volunteers = useMemo(
    () => [...data.volunteers].sort((a, b) => Number(b.verified) - Number(a.verified) || a.name.localeCompare(b.name)),
    [data.volunteers],
  );
  const [incidentIds, setIncidentIds] = useState<number[]>([]);
  const [volunteerIds, setVolunteerIds] = useState<number[]>([]);
  const [strategies, setStrategies] = useState<AllocationStrategyMetadata[]>([defaultStrategy]);
  const [strategy, setStrategy] = useState(defaultStrategy.key);
  const [plan, setPlan] = useState<DistributionPlan | null>(null);
  const [busy, setBusy] = useState<"preview" | "commit" | "">("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (data.connection !== "api") return;
    api.allocationStrategies().then((items) => {
      if (!items.length) return;
      setStrategies(items);
      setStrategy((current) => items.some((item) => item.key === current) ? current : items[0]!.key);
    }).catch(() => undefined);
  }, [data.connection]);

  const invalidate = () => {
    setPlan(null);
    setMessage("");
    setError("");
  };

  const toggleIncident = (id: number) => {
    invalidate();
    setIncidentIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 10) { setError("Select at most ten incidents per distribution run."); return current; }
      return [...current, id];
    });
  };

  const toggleVolunteer = (id: number) => {
    invalidate();
    setVolunteerIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 50) { setError("Select at most fifty volunteers per distribution run."); return current; }
      return [...current, id];
    });
  };

  const distribute = async (commit: boolean) => {
    setError("");
    setMessage("");
    const selectionError = distributionSelectionError(incidentIds, volunteerIds);
    if (selectionError) { setError(selectionError); return; }
    if (data.connection !== "api") { setError("Start the API to generate and confirm an automatic distribution plan."); return; }
    setBusy(commit ? "commit" : "preview");
    try {
      const result = await data.distributeVolunteers({
        incident_ids: incidentIds,
        volunteer_ids: volunteerIds,
        strategy,
        commit,
        preview_token: commit ? plan?.previewToken || "" : "",
        note: "Confirmed through the automated distribution workspace.",
      });
      setPlan(result);
      if (result.committed) {
        setMessage(`${result.summary.allocatedVolunteers} volunteers assigned across ${result.summary.coveredIncidents} disaster places.`);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not generate the distribution plan.");
    } finally {
      setBusy("");
    }
  };

  const groupedAllocations = useMemo(() => {
    if (!plan) return [];
    return groupDistributionAllocations(incidentIds, incidents, plan.allocations);
  }, [incidentIds, incidents, plan]);

  return (
    <section className="glass-panel auto-distribution-card">
      <div className="panel-title">
        <div><p className="eyebrow"><span />Automatic distribution</p><h2>Build a multi-place response plan</h2></div>
        <span className="strategy-chip"><GitBranch size={14} />Replaceable strategy</span>
      </div>
      <p className="muted">Choose the exact disaster places and volunteer pool. The algorithm proposes one compatible destination per available volunteer; nothing is dispatched until you confirm the preview.</p>

      {data.connection !== "api" && <Notice tone="warning"><AlertTriangle size={16} />Automatic planning needs the API. The rest of the demonstration interface remains available offline.</Notice>}
      {message && <Notice tone="success"><Check size={16} />{message}</Notice>}
      {error && <Notice tone="danger"><AlertTriangle size={16} />{error}</Notice>}

      <div className="distribution-controls">
        <div className="distribution-picker">
          <div className="picker-heading"><div><MapPin size={17} /><strong>Disaster places</strong></div><span>{incidentIds.length}/10 selected</span></div>
          <div className="picker-list">
            {incidents.map((incident) => <label key={incident.id} className={incidentIds.includes(incident.id) ? "picker-option active" : "picker-option"}><input type="checkbox" checked={incidentIds.includes(incident.id)} onChange={() => toggleIncident(incident.id)} /><span className="picker-check"><Check size={12} /></span><div><strong>{incident.locationName}</strong><small>{incident.title}</small><span>P{Math.round(incident.priorityScore)} · {incident.needs.slice(0, 3).map(titleCase).join(" · ")}</span></div></label>)}
          </div>
        </div>

        <div className="distribution-picker">
          <div className="picker-heading"><div><Users size={17} /><strong>Volunteer pool</strong></div><span>{volunteerIds.length}/50 selected</span></div>
          <div className="picker-list">
            {volunteers.map((volunteer) => {
              const available = volunteer.availability === "available";
              return <label key={volunteer.id} className={`${volunteerIds.includes(volunteer.id) ? "picker-option active" : "picker-option"}${available ? "" : " disabled"}`}><input type="checkbox" checked={volunteerIds.includes(volunteer.id)} disabled={!available} onChange={() => toggleVolunteer(volunteer.id)} /><span className="picker-check"><Check size={12} /></span><div><strong>{volunteer.name}{volunteer.verified && <BadgeCheck size={13} />}</strong><small><Route size={10} />{volunteer.preferredPlaces.join(" · ")}</small><span>{volunteer.services.map(titleCase).join(" · ")} · {titleCase(volunteer.availability)}</span></div></label>;
            })}
          </div>
        </div>
      </div>

      <div className="distribution-action-bar">
        <label className="field"><span>Allocation strategy</span><select value={strategy} onChange={(event) => { invalidate(); setStrategy(event.target.value); }}>{strategies.map((item) => <option key={item.key} value={item.key}>{item.name} · v{item.version}</option>)}</select></label>
        <button className="button secondary" type="button" disabled={Boolean(busy) || data.connection !== "api"} onClick={() => void distribute(false)}>{busy === "preview" ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}{busy === "preview" ? "Building plan…" : "Preview distribution"}</button>
        <button className="button primary" type="button" disabled={Boolean(busy) || !plan || plan.committed || !plan.allocations.length} onClick={() => void distribute(true)}>{busy === "commit" ? <LoaderCircle className="spin" size={17} /> : <ClipboardCheck size={17} />}{busy === "commit" ? "Assigning…" : `Confirm ${plan?.allocations.length || 0} assignments`}</button>
      </div>

      {plan && <div className="distribution-plan">
        <div className="distribution-summary"><span><strong>{plan.summary.allocatedVolunteers}</strong> allocated</span><span><strong>{plan.summary.coveredIncidents}</strong> places covered</span><span><strong>{plan.summary.unassignedVolunteers}</strong> unassigned</span><small>{plan.strategy.name} · v{plan.strategy.version}</small></div>
        <div className="distribution-results">
          {groupedAllocations.map((group) => <article key={group.id} className="distribution-destination"><div><MapPin size={16} /><span><strong>{group.location}</strong><small>{group.title}</small></span><em>{group.allocations.length} responders</em></div>{group.allocations.length ? group.allocations.map((item) => <div key={item.volunteerId} className="distribution-person"><span className="volunteer-mini-avatar">{item.volunteerName.split(" ").map((part) => part[0]).join("").slice(0, 2)}</span><div><strong>{item.volunteerName}</strong><small>{titleCase(item.service)} · fit {Math.round(item.fitScore)} · allocation {Math.round(item.allocationScore)}</small></div></div>) : <p>No compatible selected volunteer was available.</p>}</article>)}
        </div>
        {plan.unassigned.length > 0 && <div className="unassigned-list"><strong>Not included in this plan</strong>{plan.unassigned.map((item) => <p key={item.volunteerId}><AlertTriangle size={13} /><span><b>{item.volunteerName}</b> — {item.reason}</span></p>)}</div>}
      </div>}
    </section>
  );
}
