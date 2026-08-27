import { CalendarRange, Filter, Layers3, MapPinned, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { IncidentMap } from "../components/IncidentMap";
import { IncidentCard, PageHeader } from "../components/ui";
import { titleCase } from "../lib/format";
import type { AppData } from "../hooks/useAppData";
import type { Incident } from "../types";

const windows = [
  { label: "24 hours", days: 1 },
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
];

export function MapPage({ data }: { data: AppData }) {
  const [days, setDays] = useState(30);
  const [type, setType] = useState("all");
  const [trust, setTrust] = useState("all");
  const [selected, setSelected] = useState<Incident | null>(null);
  const types = useMemo(() => ["all", ...Array.from(new Set(data.incidents.map((item) => item.disasterType)))], [data.incidents]);
  const filtered = useMemo(() => data.incidents.filter((incident) => {
    const recentEnough = Date.now() - new Date(incident.occurredAt).getTime() <= days * 86_400_000;
    return recentEnough && (type === "all" || incident.disasterType === type) && (trust === "all" || incident.verificationStatus === trust);
  }), [data.incidents, days, trust, type]);

  return (
    <div className="content page-space">
      <PageHeader eyebrow="Time-aware intelligence" title="Disaster intensity map" description="Explore recent incident clusters without losing source trust, severity or response context." actions={<button className="button secondary" type="button" onClick={() => { setDays(30); setType("all"); setTrust("all"); }}><RotateCcw size={16} /> Reset filters</button>} />

      <div className="filter-bar glass-panel">
        <div className="filter-group"><span><CalendarRange size={15} /> Window</span><div className="segmented">{windows.map((item) => <button className={days === item.days ? "active" : ""} type="button" key={item.days} onClick={() => setDays(item.days)}>{item.label}</button>)}</div></div>
        <label><Filter size={15} /><span>Hazard</span><select value={type} onChange={(event) => setType(event.target.value)}>{types.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label>
        <label><Layers3 size={15} /><span>Trust layer</span><select value={trust} onChange={(event) => setTrust(event.target.value)}><option value="all">All signals</option><option value="official">Official only</option><option value="corroborated">Corroborated</option><option value="unverified">Unverified</option></select></label>
      </div>

      <div className="map-workspace">
        <div className="map-stage glass-panel">
          <IncidentMap incidents={filtered} onSelect={setSelected} className="large-map" />
          <div className="map-count"><MapPinned size={16} /><strong>{filtered.length}</strong> incidents in view</div>
          <div className="map-legend"><strong>Response intensity</strong><div><span className="legend-dot low" />Low<span className="legend-dot medium" />Medium<span className="legend-dot high" />High<span className="legend-dot critical" />Critical</div><small>Heat weight uses the explainable priority score.</small></div>
        </div>
        <aside className="map-side-panel">
          {selected ? (
            <>
              <div className="panel-title"><div><p className="eyebrow"><span />Selected signal</p><h2>Response detail</h2></div><button type="button" className="icon-button" onClick={() => setSelected(null)} aria-label="Close selected incident">×</button></div>
              <IncidentCard incident={selected} />
              <div className="score-breakdown glass-panel">
                <h3>Why priority {Math.round(selected.priorityScore)}?</h3>
                {Object.entries(selected.priorityBreakdown).map(([label, value]) => <div key={label}><span>{titleCase(label)}</span><span className="score-track"><i style={{ width: `${Math.min(100, value * 2.5)}%` }} /></span><strong>{value}</strong></div>)}
                <p>Decision support only. Dispatch remains an administrator action.</p>
              </div>
            </>
          ) : (
            <div className="map-list">
              <div><p className="eyebrow"><span />Ranked view</p><h2>{filtered.length} signals</h2></div>
              {filtered.slice(0, 6).map((incident) => <IncidentCard key={incident.id} incident={incident} compact onSelect={setSelected} />)}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
