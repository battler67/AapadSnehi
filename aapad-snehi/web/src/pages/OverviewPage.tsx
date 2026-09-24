import { Activity, ArrowRight, Camera, Clock3, HandHeart, RadioTower, ShieldAlert, Users } from "lucide-react";
import { IncidentMap } from "../components/IncidentMap";
import { IncidentCard, MetricCard } from "../components/ui";
import { titleCase } from "../lib/format";
import type { AppData } from "../hooks/useAppData";
import { APP_ROUTES } from "../routes";

export function OverviewPage({ data, navigate }: { data: AppData; navigate: (path: string) => void }) {
  const recent = data.incidents.filter((incident) => Date.now() - new Date(incident.occurredAt).getTime() <= 30 * 86_400_000);
  const healthySources = data.sources.filter((source) => ["healthy", "ready"].includes(source.status)).length;
  return (
    <div>
      <section className="hero-section grid-field">
        <div className="ambient ambient-one" />
        <div className="ambient ambient-two" />
        <div className="content hero-grid">
          <div className="hero-copy">
            <p className="eyebrow"><span />Community response operating system</p>
            <h1>Turn disaster signals into <span>coordinated relief.</span></h1>
            <p className="hero-lead">AapadSnehi brings official feeds, trusted reports and citizen evidence into one explainable priority queue—so the right volunteers reach the places that need them first.</p>
            <div className="hero-actions">
              <button type="button" className="button primary" onClick={() => navigate(APP_ROUTES.map)}>Open live risk map <ArrowRight size={17} /></button>
              <button type="button" className="button secondary" onClick={() => navigate(APP_ROUTES.users)}><Camera size={17} /> Report an incident</button>
            </div>
            <div className="trust-strip">
              <span><ShieldAlert size={16} /> Provenance retained</span>
              <span><Activity size={16} /> Explainable priority</span>
              <span><HandHeart size={16} /> Human dispatch control</span>
            </div>
          </div>
          <div className="hero-command glass-panel">
            <div className="command-head">
              <div><span className="pulse-dot" /><strong>Operations pulse</strong></div>
              <span>Last 30 days</span>
            </div>
            <IncidentMap incidents={recent.slice(0, 6)} className="hero-map" />
            <div className="map-overlay-card">
              <span className="risk-ring">{Math.round(recent[0]?.priorityScore || 0)}</span>
              <div><small>Highest response priority</small><strong>{recent[0]?.locationName || "No current events"}</strong></div>
            </div>
            <div className="command-foot">
              <span><RadioTower size={14} /> {healthySources}/{data.sources.length} feeds ready</span>
              <span><Clock3 size={14} /> rolling window</span>
            </div>
          </div>
        </div>
      </section>

      <section className="content section-block metrics-grid">
        <MetricCard icon={ShieldAlert} label="Active incidents" value={data.dashboard.metrics.activeIncidents} detail="Across the current operational window" tone="orange" />
        <MetricCard icon={Activity} label="High priority" value={data.dashboard.metrics.highPriority} detail="Severity four or above" tone="violet" />
        <MetricCard icon={Users} label="Volunteers available" value={data.dashboard.metrics.availableVolunteers} detail="Registered for rapid response" tone="green" />
        <MetricCard icon={HandHeart} label="Missions active" value={data.dashboard.metrics.activeAssignments} detail="Assigned or self-claimed" tone="cyan" />
      </section>

      <section className="content section-block callout-card edge-dashboard-callout">
        <div><p className="eyebrow"><span />SIMULATED / DEMO ONLY</p><h2>Multi-hazard edge early warning</h2><p>Run deterministic virtual river, hillslope and coastal sensors, then watch transparent risk estimates mature through persistence, quality and nearby agreement.</p></div>
        <button type="button" className="button primary" onClick={() => navigate(APP_ROUTES.edgeEarlyWarning)}>Open edge warning lab <ArrowRight size={17} /></button>
      </section>

      <section className="content section-block operations-grid">
        <div>
          <div className="section-heading">
            <div><p className="eyebrow"><span />Priority queue</p><h2>Where help is needed first</h2><p>Ranked from severity, recency, affected estimate, unmet needs, trust and current coverage.</p></div>
            <button className="text-button" type="button" onClick={() => navigate(APP_ROUTES.admin)}>Open allocation console <ArrowRight size={15} /></button>
          </div>
          <div className="priority-list">
            {recent.slice(0, 5).map((incident) => <IncidentCard key={incident.id} incident={incident} compact onSelect={() => navigate(APP_ROUTES.admin)} />)}
          </div>
        </div>
        <aside className="glass-panel signal-panel">
          <p className="eyebrow"><span />Signal fabric</p>
          <h2>{data.sources.length} adapters, one event language</h2>
          <p>Every provider enters through a bounded adapter, then passes validation, deduplication and trust classification.</p>
          <div className="source-mini-list">
            {data.sources.slice(0, 6).map((source) => (
              <div key={source.id}>
                <span className={`source-logo source-${source.adapterType}`}>{source.adapterType.slice(0, 2).toUpperCase()}</span>
                <div><strong>{source.name}</strong><small>{titleCase(source.sourceKind)} · {titleCase(source.status)}</small></div>
                <span className={`status-dot ${source.status}`} />
              </div>
            ))}
          </div>
          <button type="button" className="button secondary full" onClick={() => navigate(APP_ROUTES.pipeline)}>Inspect ingestion pipeline <ArrowRight size={16} /></button>
        </aside>
      </section>

      {data.dashboard.externalIncidents.length > 0 && (
        <section className="content section-block">
          <div className="section-heading">
            <div><p className="eyebrow"><span />Latest external signals</p><h2>India disaster signals from official CAP, search and news</h2><p>Up to five current results that passed source-specific hazard, location and lifecycle checks. Each card retains its official or unverified provenance.</p></div>
          </div>
          <div className="priority-list">
            {data.dashboard.externalIncidents.map((incident) => <IncidentCard key={incident.id} incident={incident} onSelect={() => navigate(APP_ROUTES.admin)} />)}
          </div>
        </section>
      )}

      <section className="content section-block callout-card">
        <div><p className="eyebrow"><span />Community eyes on the ground</p><h2>See something the feeds have not caught?</h2><p>Share the location and what people need. Photos are optional and receive advisory AI screening when available. Incident verification always requires human review.</p></div>
        <button type="button" className="button primary" onClick={() => navigate(APP_ROUTES.users)}><Camera size={17} /> Start a report</button>
      </section>
    </div>
  );
}
