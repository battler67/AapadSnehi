import {
  ArrowUpRight,
  BadgeCheck,
  Bot,
  CircleAlert,
  Clock3,
  MapPin,
  Radio,
  ShieldQuestion,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { compactNumber, timeAgo, titleCase } from "../lib/format";
import type { Incident, VerificationStatus } from "../types";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <p className="eyebrow"><span />{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function MetricCard({ icon: Icon, label, value, detail, tone = "cyan" }: { icon: LucideIcon; label: string; value: string | number; detail: string; tone?: "cyan" | "violet" | "orange" | "green" }) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-top"><span className="metric-icon"><Icon size={19} /></span><span className="live-tick"><Radio size={12} /> live</span></div>
      <strong>{value}</strong>
      <p>{label}</p>
      <small>{detail}</small>
    </article>
  );
}

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const Icon = status === "official" ? BadgeCheck : status === "corroborated" ? ShieldQuestion : status === "community_reviewed" ? UserCheck : status === "ai_screened" ? Bot : CircleAlert;
  return <span className={`verification-badge ${status}`}><Icon size={13} />{titleCase(status)}</span>;
}

export function SeverityBadge({ severity, intensity }: Pick<Incident, "severity" | "intensity">) {
  return <span className={`severity-badge severity-${severity}`}><span />{titleCase(intensity)} · S{severity}</span>;
}

export function IncidentCard({ incident, compact = false, onSelect }: { incident: Incident; compact?: boolean; onSelect?: (incident: Incident) => void }) {
  return (
    <article className={compact ? "incident-card compact" : "incident-card"}>
      <div className="incident-card-head">
        <SeverityBadge severity={incident.severity} intensity={incident.intensity} />
        <span className="priority-number">P{Math.round(incident.priorityScore)}</span>
      </div>
      <h3>{incident.title}</h3>
      <p className="incident-location"><MapPin size={14} /> {incident.locationName}</p>
      {!compact && <p className="incident-description">{incident.description}</p>}
      <div className="need-row">
        {incident.needs.slice(0, compact ? 2 : 4).map((need) => <span key={need}>{titleCase(need)}</span>)}
      </div>
      <div className="incident-meta">
        <VerificationBadge status={incident.verificationStatus} />
        <span><Radio size={13} />{incident.sourceName}</span>
        <span><Clock3 size={13} />{timeAgo(incident.occurredAt)}</span>
        {incident.affectedEstimate > 0 && <span><Users size={13} />{compactNumber(incident.affectedEstimate)}</span>}
      </div>
      {onSelect && <button className="text-button" type="button" onClick={() => onSelect(incident)}>Inspect response priority <ArrowUpRight size={15} /></button>}
    </article>
  );
}

export function EmptyState({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return <div className="empty-state"><span><Icon size={22} /></span><h3>{title}</h3><p>{text}</p></div>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <div className={`notice ${tone}`}>{children}</div>;
}
