import { Activity, BatteryMedium, CheckCircle2, CirclePause, CirclePlay, Download, RadioTower, RefreshCw, ShieldAlert, Signal, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EdgeRiskMap } from "../components/EdgeRiskMap";
import { PageHeader } from "../components/ui";
import { api, resolveApiUrl } from "../lib/api";
import { titleCase } from "../lib/format";
import type { EdgeCatalog, EdgeDevice, EdgeRiskEvent, EdgeSnapshot } from "../types";

type History = Array<{ timestamp: string; measurements: Record<string, { value: number; unit: string }> }>;
const empty: EdgeSnapshot = { notice: "SIMULATED / DEMO ONLY", cursor: "", transport: "polling", suggestedPollSeconds: 2, devices: [], risks: [], events: [], simulations: [] };

function MiniChart({ history, property }: { history: History; property: string }) {
  const points = history.flatMap((item, index) => item.measurements[property] ? [{ x: index, y: item.measurements[property].value }] : []);
  if (points.length < 2) return <div className="edge-chart-empty">Waiting for enough observations…</div>;
  const min = Math.min(...points.map((item) => item.y)); const max = Math.max(...points.map((item) => item.y));
  const polyline = points.map((item) => `${(item.x / Math.max(1, history.length - 1)) * 100},${92 - ((item.y - min) / Math.max(0.001, max - min)) * 78}`).join(" ");
  return <div className="edge-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${property} recent trend`}><polyline points={polyline} fill="none" vectorEffect="non-scaling-stroke" /></svg><span>{min.toFixed(2)}</span><strong>{max.toFixed(2)}</strong></div>;
}

export function EdgeEarlyWarningPage() {
  const [snapshot, setSnapshot] = useState(empty);
  const [catalog, setCatalog] = useState<EdgeCatalog | null>(null);
  const [selected, setSelected] = useState<EdgeDevice | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EdgeRiskEvent | null>(null);
  const [history, setHistory] = useState<History>([]);
  const [scenario, setScenario] = useState("flood-gradual-001");
  const [region, setRegion] = useState("visakhapatnam");
  const [hazard, setHazard] = useState("all");
  const [deviceType, setDeviceType] = useState("all");
  const [deviceStatus, setDeviceStatus] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try { setSnapshot(await api.edgeSnapshot()); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to reach the API"); }
  }, []);
  useEffect(() => { void Promise.all([refresh(), api.edgeCatalog().then(setCatalog).catch(() => undefined)]); const id = window.setInterval(() => void refresh(), 2000); return () => window.clearInterval(id); }, [refresh]);
  useEffect(() => { if (!selected && snapshot.devices.length) setSelected(snapshot.devices[0]); }, [selected, snapshot.devices]);
  useEffect(() => { if (!selected) return; void api.edgeDeviceHistory(selected.deviceId).then(setHistory).catch(() => setHistory([])); }, [selected, snapshot.cursor]);

  const filteredDevices = useMemo(() => snapshot.devices.filter((device) => {
    const risks = snapshot.risks.filter((item) => item.deviceId === device.deviceId);
    return (hazard === "all" || device.installedPurposes.includes(hazard as never)) && (deviceType === "all" || device.deviceType === deviceType) && (deviceStatus === "all" || device.status === deviceStatus) && (riskFilter === "all" || risks.some((item) => item.riskLevel === riskFilter));
  }), [deviceStatus, deviceType, hazard, riskFilter, snapshot.devices, snapshot.risks]);
  const deviceRisks = snapshot.risks.filter((risk) => risk.deviceId === selected?.deviceId).sort((a, b) => b.probability - a.probability);
  const chartProperties = selected?.deviceType === "river_gauge" ? ["waterLevelM", "rainfallMmH"] : selected?.deviceType === "hillslope_station" ? ["poreWaterPressureKpa", "groundTiltXDeg"] : ["seaLevelAnomalyM", "bottomPressureKpa"];
  const run = snapshot.simulations[0];

  const start = async () => { setBusy(true); try { await api.startEdgeSimulation({ scenario, region, numberOfDevices: 6, seed: 20260902, speedMultiplier: 60, timestepSeconds: 60 }); await refresh(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not start simulation"); } finally { setBusy(false); } };
  const control = async (action: "pause" | "resume" | "stop" | "reset") => { if (!run) return; await api.controlEdgeSimulation(run.runId, action); await refresh(); };
  const openEvent = async (event: EdgeRiskEvent) => setSelectedEvent(await api.edgeEvent(event.id));
  const review = async (action: "acknowledge" | "promote_to_incident") => { if (!selectedEvent) return; const confirmed = action !== "promote_to_incident" || window.confirm("This creates an unverified SIMULATED / DEMO ONLY incident. No notification is sent. Continue?"); if (!confirmed) return; setSelectedEvent(await api.reviewEdgeEvent(selectedEvent.id, action, "Demo operator", action === "promote_to_incident")); await refresh(); };

  return <div className="content page-space edge-page">
    <PageHeader eyebrow="Multi-hazard research prototype" title="Edge Early Warning" description="Explore estimated flood, landslide and tsunami risk from synthetic device telemetry. Probabilities are decision-support estimates—not predictions of certainty." />
    <div className="edge-demo-banner"><ShieldAlert size={20} /><strong>SIMULATED / DEMO ONLY</strong><span>No real emergency notification or public-warning channel is connected.</span></div>
    {error && <div className="edge-error">{error}</div>}

    <section className="edge-controls glass-panel">
      <label>Scenario<select value={scenario} onChange={(event) => setScenario(event.target.value)}>{catalog?.scenarios.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <label>Region<select value={region} onChange={(event) => setRegion(event.target.value)}>{catalog?.regions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <button className="button primary" disabled={busy || run?.status === "running"} onClick={() => void start()}><CirclePlay size={16} /> Start 2–4 min demo</button>
      {run?.status === "running" && <button className="button secondary" onClick={() => void control("pause")}><CirclePause size={16} /> Pause</button>}
      {run?.status === "paused" && <button className="button secondary" onClick={() => void control("resume")}><CirclePlay size={16} /> Resume</button>}
      {run && <button className="button ghost" onClick={() => void control("reset")}><RefreshCw size={16} /> Reset</button>}
      {run && <div className="edge-run-progress"><span>{titleCase(run.status)} · {run.cursorStep}/{run.totalSteps}</span><progress max={run.totalSteps || 1} value={run.cursorStep} /></div>}
    </section>

    <div className="edge-stats">
      {(["WATCH", "WARNING", "CRITICAL"] as const).map((state) => <article className={`glass-panel state-${state.toLowerCase()}`} key={state}><TriangleAlert size={20} /><div><strong>{snapshot.events.filter((item) => item.active && item.state === state).length}</strong><span>{state} events</span></div></article>)}
      <article className="glass-panel"><RadioTower size={20} /><div><strong>{snapshot.devices.length}</strong><span>virtual devices</span></div></article>
    </div>

    <div className="edge-filter-row"><label>Hazard<select value={hazard} onChange={(event) => setHazard(event.target.value)}><option value="all">All hazards</option><option value="flood">Flood</option><option value="landslide">Landslide</option><option value="tsunami">Tsunami</option></select></label><label>Device type<select value={deviceType} onChange={(event) => setDeviceType(event.target.value)}><option value="all">All devices</option><option value="river_gauge">River gauge</option><option value="hillslope_station">Hillslope station</option><option value="coastal_buoy">Coastal buoy</option></select></label><label>Status<select value={deviceStatus} onChange={(event) => setDeviceStatus(event.target.value)}><option value="all">All statuses</option><option value="online">Online</option><option value="degraded">Degraded</option><option value="registered">Registered</option></select></label><label>Risk<select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}><option value="all">All levels</option><option>WATCH</option><option>WARNING</option><option>CRITICAL</option><option>RECOVERY</option><option>NORMAL</option></select></label><button className="button ghost" onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</button></div>
    <div className="edge-workspace">
      <section className="glass-panel edge-map-panel"><EdgeRiskMap devices={filteredDevices} risks={snapshot.risks} selectedId={selected?.deviceId} onSelect={setSelected} /><div className="edge-map-legend"><i className="normal" /> Normal <i className="watch" /> Watch <i className="warning" /> Warning <i className="critical" /> Critical</div></section>
      <aside className="glass-panel edge-device-panel">
        {selected ? <><p className="eyebrow"><span />Virtual device</p><h2>{selected.name}</h2><div className="edge-health"><span><BatteryMedium size={16} /> {Math.round(selected.batteryPct)}%</span><span><Signal size={16} /> {Math.round(selected.signalQualityPct)}%</span><span><CheckCircle2 size={16} /> quality {Math.round((deviceRisks[0]?.dataQuality || selected.trustScore) * 100)}%</span></div><p>{titleCase(selected.deviceType)} · {selected.capabilities.length} observed properties</p>{deviceRisks.map((risk) => <div className={`edge-risk-card state-${risk.riskLevel.toLowerCase()}`} key={risk.hazard}><div><strong>Estimated {risk.hazard} risk</strong><b>{Math.round(risk.probability * 100)}%</b></div><progress max={1} value={risk.probability} /><small>{risk.riskLevel} · confidence {Math.round(risk.confidence * 100)}% · {risk.nearbyAgreement} nearby sensor(s) agree</small><h4>Why this risk?</h4>{risk.topContributors.slice(0, 3).map((item) => <p key={item.feature}>{titleCase(item.feature)} <span>{item.contribution >= 0 ? "+" : ""}{item.contribution.toFixed(2)}</span></p>)}</div>)}{chartProperties.map((property) => <div key={property}><h3>{titleCase(property)} trend</h3><MiniChart history={history} property={property} /></div>)}</> : <p>Start a scenario to create devices.</p>}
        {selected && <small className="edge-last-seen">Last seen {selected.lastSeenAt ? new Date(selected.lastSeenAt).toLocaleTimeString() : "never"}</small>}
      </aside>
    </div>

    <section className="glass-panel edge-timeline"><div className="panel-title"><div><p className="eyebrow"><span />Evidence trail</p><h2>Simulated event timeline</h2></div><Activity size={20} /></div>{snapshot.events.length ? snapshot.events.map((event) => <button key={event.id} onClick={() => void openEvent(event)}><span className={`event-dot state-${event.state.toLowerCase()}`} /><span><strong>{event.notice}: estimated {event.hazard} risk</strong><small>{event.regionId} · {event.state} · {Math.round(event.probability * 100)}% · {new Date(event.updatedAt).toLocaleTimeString()}</small></span><b>{event.reviewStatus}</b></button>) : <p>No event yet. Risk policy requires consecutive abnormal windows or nearby agreement.</p>}</section>

    {selectedEvent && <div className="edge-modal-backdrop" role="presentation" onClick={() => setSelectedEvent(null)}><section className="edge-modal glass-panel" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}><div className="panel-title"><div><p className="eyebrow"><span />Risk evidence bundle</p><h2>{selectedEvent.notice}</h2></div><button className="icon-button" onClick={() => setSelectedEvent(null)}>×</button></div><h3>Estimated {selectedEvent.hazard} risk: {selectedEvent.state}</h3><p>{Math.round(selectedEvent.probability * 100)}% probability, {Math.round(selectedEvent.confidence * 100)}% confidence, {selectedEvent.contributingDeviceIds.length} contributing device(s).</p><div className="edge-transitions">{selectedEvent.transitions?.map((item) => <p key={item.id}><strong>{item.fromState} → {item.toState}</strong><span>{item.reason}</span></p>)}</div><div className="edge-modal-actions"><button className="button secondary" onClick={() => void review("acknowledge")}>Acknowledge demo</button><button className="button primary" onClick={() => void review("promote_to_incident")}>Create simulated incident</button><a className="button ghost" href={resolveApiUrl(`/api/edge/events/${selectedEvent.id}/cap`)}><Download size={15} /> CAP 1.2 test export</a></div>{selectedEvent.incidentId && <p className="edge-success">Linked to incident #{selectedEvent.incidentId}; it remains unverified and simulated.</p>}</section></div>}
  </div>;
}
