import { useCallback, useEffect, useState } from "react";
import { FloodMap } from "../components/FloodMap";
import { API_BASE } from "../lib/api";
import {
  floodRequest,
  type Incident,
  type Listing,
  type Task,
} from "../lib/flood";

const human = (s: string) =>
  s.replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2");
function PrivatePhoto({ id, token }: { id: string; token: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let live = true,
      objectUrl = "";
    fetch(`${API_BASE}/api/flood/media/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.blob();
      })
      .then((blob) => {
        if (live) {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch(() => setUrl(""));
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id, token]);
  return url ? (
    <img
      src={url}
      alt="Private citizen flood evidence; requires human review"
    />
  ) : (
    <p>Private photo unavailable</p>
  );
}

function TaskControls({
  task,
  token,
  coordinator,
  teams,
  changed,
}: {
  task: Task;
  token: string;
  coordinator: boolean;
  teams: { id: string; name: string }[];
  changed: () => void;
}) {
  const [state, setState] = useState("");
  const [team, setTeam] = useState("");
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("");
  const [remaining, setRemaining] = useState("");
  const [assisted, setAssisted] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const transitions: Record<string, string[]> = {
    needs_review: ["ready", "cancelled"],
    ready: ["assigned", "needs_review", "cancelled"],
    assigned: ["en_route", "ready", "assigned", "cancelled"],
    en_route: ["on_scene", "unable_to_reach", "ready", "cancelled"],
    on_scene: ["resolved", "unable_to_reach", "ready"],
    unable_to_reach: ["ready", "en_route", "cancelled"],
    resolved: ["needs_review"],
    cancelled: ["needs_review"],
  };
  const choices = (transitions[task.state] || []).filter(
    (s) =>
      coordinator ||
      ["en_route", "on_scene", "resolved", "unable_to_reach"].includes(s),
  );
  return (
    <section className="flood-task">
      <h3>Rescue task: {human(task.state)}</h3>
      <p>
        Team:{" "}
        {teams.find((t) => t.id === task.teamId)?.name ||
          task.teamId ||
          "Unassigned"}{" "}
        · Version {task.version}
      </p>
      {task.outcome && (
        <p>
          Outcome: {task.outcome} · Assisted: {task.assisted ?? "unknown"} ·
          Remaining: {task.remaining}
        </p>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await floodRequest(
              `/tasks/${task.id}`,
              token,
              {
                version: task.version,
                state,
                team_id: state === "assigned" ? team : null,
                note,
                outcome,
                remaining,
                assisted: assisted ? Number(assisted) : null,
              },
              "PATCH",
            );
            changed();
            setState("");
          } catch (e) {
            setError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="flood-fields">
          <label>
            Next rescue state
            <select
              aria-label="Next rescue state"
              required
              value={state}
              onChange={(e) => setState(e.target.value)}
            >
              <option value="">Choose transition</option>
              {choices.map((s) => (
                <option key={s} value={s}>
                  {s === "needs_review" &&
                  ["resolved", "cancelled"].includes(task.state)
                    ? "Reopen for review"
                    : s === "assigned" && task.state === "assigned"
                      ? "Reassign team"
                      : human(s)}
                </option>
              ))}
            </select>
          </label>
          {state === "assigned" && (
            <label>
              Assign team
              <select
                aria-label="Assign team"
                required
                value={team}
                onChange={(e) => setTeam(e.target.value)}
              >
                <option value="">Choose authorized team</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Progress / reason
            <textarea
              required
              minLength={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          {state === "resolved" && (
            <>
              <label>
                Resolution outcome
                <input
                  required
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                />
              </label>
              <label>
                Number assisted, if known
                <input
                  type="number"
                  min="0"
                  value={assisted}
                  onChange={(e) => setAssisted(e.target.value)}
                />
              </label>
              <label>
                Remaining needs (write none if none)
                <input
                  required
                  value={remaining}
                  onChange={(e) => setRemaining(e.target.value)}
                />
              </label>
            </>
          )}
        </div>
        <button className="button primary" disabled={busy || !state}>
          Record task transition
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  );
}

function IncidentPanel({
  incident,
  token,
  role,
  teams,
  changed,
}: {
  incident: Incident;
  token: string;
  role: string;
  teams: { id: string; name: string }[];
  changed: () => void;
}) {
  const [reason, setReason] = useState("");
  const [verification, setVerification] = useState(incident.verification);
  const [urgency, setUrgency] = useState(incident.urgency);
  const [status, setStatus] = useState(incident.status);
  const [canonical, setCanonical] = useState(
    String(incident.canonicalReportId || incident.reports?.[0]?.id || ""),
  );
  const [confirmed, setConfirmed] = useState("");
  const [target, setTarget] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<
    { incidentId: number; reasons: string[]; warning: string }[]
  >([]);
  const [lat, setLat] = useState(String(incident.point?.[0] ?? ""));
  const [lon, setLon] = useState(String(incident.point?.[1] ?? ""));
  const [precision, setPrecision] = useState("unknown");
  const coordinator = role === "coordinator";
  async function run(action: () => Promise<unknown>) {
    try {
      setError("");
      await action();
      changed();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <article
      className="glass-panel flood-card"
      aria-label={`Incident ${incident.id} detail`}
    >
      <h2>Incident #{incident.id}</h2>
      <p>
        {incident.demo && "SYNTHETIC DEMO · "}
        {incident.status} flooding · {human(incident.verification)} ·{" "}
        {incident.urgency} priority
      </p>
      <p>
        {incident.locality} / {incident.street} · {incident.precision} ·{" "}
        {incident.locationStatus}
      </p>
      <p>
        Latest observation:{" "}
        {incident.lastObservation
          ? new Date(incident.lastObservation).toLocaleString()
          : "Unknown"}
      </p>
      <p>
        {incident.stale && "Stale — needs an updated observation. "}
        {incident.conflict && "Conflicting counts — review the evidence. "}
        {incident.reviewNeeded && "Review needed."}
      </p>
      <p>
        {incident.conditionBasis}: {human(incident.waterLevel)} water level
        (citizen estimate), {incident.trend}; access {human(incident.access)}.
      </p>
      {incident.address && (
        <>
          <p>
            {Object.entries(incident.address)
              .filter(([, v]) => v)
              .map(([k, v]) => `${human(k)}: ${v}`)
              .join(" · ")}
          </p>
          <p>
            Reported people:{" "}
            {incident.reportedPeople ?? "unknown / not reviewed"} (
            {incident.countQuality}) · Responder-confirmed:{" "}
            {incident.confirmedPeople ?? "unknown"}
          </p>
          <p>Urgency reason: {incident.urgencyReason}</p>
          {incident.point && (
            <a
              target="_blank"
              rel="noreferrer"
              href={`https://www.openstreetmap.org/directions?to=${incident.point.join(",")}`}
            >
              Open navigation (external service; ordinary directions are not a
              verified safe rescue route)
            </a>
          )}
        </>
      )}
      {incident.reports?.map((r) => (
        <details key={r.id} className="flood-report" open>
          <summary>
            Citizen observation {r.reference} · {r.kind}
          </summary>
          <p>
            Observed: {r.observed_at || "unknown"} ({r.time_quality}) ·
            Received: {new Date(r.receivedAt).toLocaleString()}
          </p>
          <p>{r.description}</p>
          <p>
            People: {r.people ?? "unknown"} ({r.count_quality}) · Position:{" "}
            {r.position || "unknown"} · Assistance:{" "}
            {r.assistance.map(human).join(", ") || "not specified"}
          </p>
          <p>
            Contact: {r.contact || "not provided"} · Reporter{" "}
            {r.reporter_present ? "at location" : "reporting for someone else"}
          </p>
          <p>Address: {Object.values(r.address).filter(Boolean).join(", ")}</p>
          <p>
            Location source: {human(r.location.source)} · Accuracy:{" "}
            {r.location.accuracy == null
              ? "unknown"
              : `${r.location.accuracy} metres`}{" "}
            · {r.locationStatus}
          </p>
          <div className="flood-photos">
            {r.media.map((m) => (
              <div key={m.id}>
                <PrivatePhoto id={m.id} token={token} />
                <p>{m.review?.message || "No AI screening recorded; human review required."}</p>
                {m.review?.caption && <p>AI observation: {m.review.caption}</p>}
                {m.review?.evidence && <p>Visible disaster evidence (AI): {m.review.evidence}. Not incident verification.</p>}
              </div>
            ))}
          </div>
          {!r.media.length && <p>No photographs attached.</p>}
        </details>
      ))}
      {coordinator && (
        <section>
          <h3>Coordinator review</h3>
          <div className="flood-fields">
            <label>
              Canonical observation
              <select
                value={canonical}
                onChange={(e) => setCanonical(e.target.value)}
              >
                {incident.reports?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.reference} — {r.people ?? "unknown"} people (
                    {r.count_quality})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Verification
              <select
                value={verification}
                onChange={(e) => setVerification(e.target.value)}
              >
                {[
                  "unverified",
                  "corroborated",
                  "responder_verified",
                  "disputed",
                ].map((v) => (
                  <option key={v} value={v}>
                    {human(v)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Operational urgency
              <select
                value={urgency}
                onChange={(e) => setUrgency(e.target.value)}
              >
                {["review", "routine", "high", "critical"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Flood incident status
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                {["active", "monitoring", "closed"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Responder-confirmed people (if verified)
              <input
                type="number"
                min="0"
                value={confirmed}
                onChange={(e) => setConfirmed(e.target.value)}
              />
            </label>
            <label>
              Evidence and reason
              <textarea
                minLength={5}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain reviewed evidence, conflicts and priority"
              />
            </label>
          </div>
          <button
            className="button primary"
            onClick={() =>
              run(() =>
                floodRequest(
                  `/incidents/${incident.id}/review`,
                  token,
                  {
                    version: incident.version,
                    report_id: Number(canonical),
                    verification,
                    urgency,
                    reason,
                    confirmed_people: confirmed ? Number(confirmed) : null,
                    status,
                  },
                  "PATCH",
                ),
              )
            }
          >
            Save reviewed situation
          </button>
          {!incident.tasks?.some(task => !["resolved", "cancelled"].includes(task.state)) && <button className="button" onClick={() => run(() => floodRequest(`/incidents/${incident.id}/task`, token, { version: incident.version, reason }, "POST"))}>Create rescue task for reviewed need</button>}
          <details>
            <summary>
              Confirm / correct location or request clarification
            </summary>
            <p>
              Applies to the selected canonical observation. Pin confirmation
              does not verify flood conditions.
            </p>
            <div className="flood-fields">
              <label>
                Correct latitude
                <input
                  type="number"
                  step="any"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                />
              </label>
              <label>
                Correct longitude
                <input
                  type="number"
                  step="any"
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                />
              </label>
              <label>
                Corrected precision
                <select
                  value={precision}
                  onChange={(e) => setPrecision(e.target.value)}
                >
                  {["unknown", "locality", "street", "building"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
            </div>
            <button
              className="button"
              onClick={() =>
                run(() =>
                  floodRequest(
                    `/reports/${canonical}/location`,
                    token,
                    {
                      version: incident.version,
                      location: {
                        latitude: lat ? Number(lat) : null,
                        longitude: lon ? Number(lon) : null,
                        source: "manual_pin",
                        accuracy: null,
                        precision,
                        confirmed: true,
                      },
                      reason,
                    },
                    "PATCH",
                  ),
                )
              }
            >
              Confirm corrected coordinates
            </button>
            <button
              className="button"
              onClick={() =>
                run(() =>
                  floodRequest(
                    `/reports/${canonical}/location`,
                    token,
                    {
                      version: incident.version,
                      location: {
                        latitude: null,
                        longitude: null,
                        source: "text",
                        accuracy: null,
                        precision: "unknown",
                        confirmed: false,
                      },
                      reason,
                    },
                    "PATCH",
                  ),
                )
              }
            >
              Request location clarification
            </button>
          </details>
          <details>
            <summary>Related reports and grouping</summary>
            <button
              className="button"
              onClick={async () => {
                try {
                  const s = await floodRequest<{ items: typeof suggestions }>(
                    `/reports/${canonical}/suggestions`,
                    token,
                  );
                  setSuggestions(s.items);
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              Find related incident candidates
            </button>
            {suggestions.map((s) => (
              <p key={s.incidentId}>
                #{s.incidentId}: {s.reasons.join("; ")} — {s.warning}
              </p>
            ))}
            <label>
              Target incident ID
              <input
                type="number"
                min="1"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </label>
            <p>
              Moving a report retains existing assignments at its source. Review
              them explicitly. A new rescue report grouping creates a task
              awaiting review.
            </p>
            <button
              className="button"
              onClick={() =>
                run(() =>
                  floodRequest(
                    `/reports/${canonical}/regroup`,
                    token,
                    {
                      version: incident.version,
                      target_incident_id: target ? Number(target) : null,
                      reason,
                    },
                    "POST",
                  ),
                )
              }
            >
              {target
                ? "Move selected report to target"
                : "Separate selected report into new incident"}
            </button>
            <label className="flood-check">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
              />
              Acknowledge all task relationships will move on merge; resolve
              conflicting tasks first.
            </label>
            <button
              className="button"
              disabled={!target}
              onClick={() =>
                run(async () => {
                  const dest = await floodRequest<Incident>(
                    `/incidents/${target}?private=true`,
                    token,
                  );
                  return floodRequest(
                    `/incidents/${incident.id}/merge`,
                    token,
                    {
                      version: incident.version,
                      target_incident_id: Number(target),
                      target_version: dest.version,
                      acknowledge_tasks: ack,
                      reason,
                    },
                    "POST",
                  );
                })
              }
            >
              Merge this incident into target
            </button>
          </details>
        </section>
      )}
      {incident.tasks?.map((task) => (
        <TaskControls
          key={`${task.id}-${task.version}`}
          task={task}
          token={token}
          coordinator={coordinator}
          teams={teams}
          changed={changed}
        />
      ))}
      {incident.timeline && (
        <section>
          <h3>Activity timeline</h3>
          <ol className="flood-timeline">
            {incident.timeline.map((event) => (
              <li key={event.id}>
                <time>{new Date(event.at).toLocaleString()}</time>
                <strong>{human(event.action)}</strong>
                <span>
                  {event.role} · {event.actor}
                </span>
                <details>
                  <summary>Recorded details</summary>
                  <pre>{JSON.stringify(event.details, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        </section>
      )}
      {error && (
        <p role="alert" className="flood-notice">
          {error}
        </p>
      )}
    </article>
  );
}

export function FloodOperationsPage() {
  const [token, setToken] = useState("");
  const [credential, setCredential] = useState("");
  const [role, setRole] = useState("public");
  const [name, setName] = useState("");
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<Incident | null>(null);
  const [teams, setTeams] = useState<{ id: string; name: string }[]>([]);
  const [revision, setRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const [group, setGroup] = useState("");
  const [bounds, setBounds] = useState("");
  const [viewport, setViewport] = useState(false);
  const changed = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    const id = setInterval(changed, 20000);
    return () => clearInterval(id);
  }, [changed]);
  useEffect(() => {
    let live = true;
    const query = new URLSearchParams({
      demo: String(demo),
      private: String(role !== "public"),
      offset: String(offset),
      limit: "50",
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      ...(viewport && bounds ? { bbox: bounds } : {}),
    });
    floodRequest<Listing>(`/incidents?${query}`, token)
      .then((data) => {
        if (live) {
          setListing(data);
          setError("");
        }
      })
      .catch((e) => {
        if (live) {
          setError(String(e));
          setListing(null);
        }
      });
    return () => {
      live = false;
    };
  }, [token, role, demo, filters, revision, offset, viewport, bounds]);
  useEffect(() => {
    setDetail(null);
  }, [selected, role]);
  useEffect(() => {
    let live = true;
    if (selected != null)
      floodRequest<Incident>(
        `/incidents/${selected}?private=${role !== "public"}`,
        token,
      )
        .then((d) => {
          if (live) setDetail(d);
        })
        .catch((e) => {
          if (live) setError(String(e));
        });
    return () => {
      live = false;
    };
  }, [selected, token, role, revision]);
  useEffect(() => {
    if (role !== "public")
      floodRequest<{ items: typeof teams }>("/teams", token)
        .then((d) => setTeams(d.items))
        .catch((e) => setError(String(e)));
    else setTeams([]);
  }, [token, role]);
  const visible =
    listing?.items.filter(
      (i) =>
        !group ||
        listing.groups.find((g) => g.id === group)?.incidentIds.includes(i.id),
    ) || [];
  const filter = (key: string, label: string, choices?: string[]) => (
    <label>
      {label}
      {choices ? (
        <select
          value={filters[key] || ""}
          onChange={(e) => {
            setFilters((v) => ({ ...v, [key]: e.target.value }));
            setOffset(0);
            setGroup("");
          }}
        >
          <option value="">All</option>
          {choices.map((v) => (
            <option key={v} value={v}>
              {human(v)}
            </option>
          ))}
        </select>
      ) : (
        <input
          value={filters[key] || ""}
          onChange={(e) => {
            setFilters((v) => ({ ...v, [key]: e.target.value }));
            setOffset(0);
            setGroup("");
          }}
        />
      )}
    </label>
  );
  return (
    <div className="content page-space flood-workspace">
      <header>
        <p className="eyebrow">
          Citizen observations · Human-reviewed coordination
        </p>
        <h1>Flood reports & rescue</h1>
        <p>
          Reported points are not validated flood extent. Flood conditions,
          verification and rescue progress are tracked separately.
        </p>
        <a className="button primary" href="/flood/report">
          People need rescue / submit a report
        </a>
      </header>
      <section className="glass-panel flood-card">
        <div className="flood-actions">
          <strong>
            {role === "public"
              ? "Public view — approximate locations"
              : `${name} · ${role}`}
          </strong>
          <label className="flood-check">
            <input
              type="checkbox"
              checked={demo}
              onChange={(e) => {
                setDemo(e.target.checked);
                setSelected(null);
                setGroup("");
              }}
            />
            Show isolated synthetic demo reports
          </label>
          <button className="button" onClick={changed}>
            Refresh
          </button>
        </div>
        {role === "public" ? (
          <details>
            <summary>Coordinator / responder access</summary>
            <p>
              Use a locally provisioned operational credential. Existing public
              Admin and Volunteer pages do not grant these permissions.
            </p>
            <form
              className="flood-actions"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const s = await floodRequest<{ role: string; name: string }>(
                    "/session",
                    credential,
                  );
                  setToken(credential);
                  setCredential("");
                  setRole(s.role);
                  setName(s.name);
                  setSelected(null);
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              <label>
                Operational credential
                <input
                  type="password"
                  autoComplete="off"
                  required
                  value={credential}
                  onChange={(e) => setCredential(e.target.value)}
                />
              </label>
              <button className="button">Unlock operational view</button>
            </form>
          </details>
        ) : (
          <button
            className="button"
            onClick={() => {
              setToken("");
              setRole("public");
              setDetail(null);
              setSelected(null);
              setFilters({});
              setListing(null);
            }}
          >
            Lock operational view
          </button>
        )}
      </section>
      {demo && (
        <p className="flood-notice">
          SYNTHETIC DEMO ONLY — fictional observations, not an emergency
          notification service.
        </p>
      )}
      {error && (
        <p className="flood-notice" role="alert">
          {error} No successful response is being simulated.
        </p>
      )}
      <details className="glass-panel flood-card" open>
        <summary>Filters — applied to map, list and statistics</summary>
        <div className="flood-fields">
          {filter("kind", "Report type", [
            "rescue",
            "flood",
            "blocked",
            "update",
          ])}
          {filter("status", "Incident status", [
            "active",
            "monitoring",
            "closed",
          ])}
          {filter("verification", "Verification", [
            "unverified",
            "corroborated",
            "responder_verified",
            "disputed",
          ])}
          {filter("urgency", "Urgency", [
            "review",
            "routine",
            "high",
            "critical",
          ])}
          {filter("assignment", "Assignment state", [
            "needs_review",
            "ready",
            "assigned",
            "en_route",
            "on_scene",
            "unable_to_reach",
            "resolved",
            "cancelled",
          ])}
          {filter("stale", "Stale observations", ["true", "false"])}
          {filter("resolution", "Location review queue", ["confirmed", "clarification"])}
          {filter("locality", "Locality")}
          {filter("street", "Street")}
          {filter("since", "Observed since (ISO timestamp)")}
          {role !== "public" && <>{filter("near_lat", "Known landmark latitude")}{filter("near_lon", "Known landmark longitude")}{filter("radius", "Landmark radius in metres (50–5000)")}</>}
          {role !== "public" &&
            filter("assistance", "Assistance needs", [
              "limited_mobility",
              "urgent_medical",
              "children",
              "transport",
              "other",
            ])}
          {filter(
            "group_by",
            "Group geography",
            role === "public"
              ? ["locality", "street"]
              : ["locality", "street", "building", "landmark"],
          )}
        </div>
      </details>
      {listing && (
        <>
          <div className="flood-stats">
            {Object.entries((group && listing.groups.find(g => g.id === group)?.summary) || listing.summary).map(([key, value]) => (
              <div
                className="glass-panel"
                key={key}
                title={listing.definitions[key] || human(key)}
              >
                <strong>
                  {value == null
                    ? "Unknown"
                    : key === "lastObservation"
                      ? new Date(String(value)).toLocaleString()
                      : value}
                </strong>
                <span>{human(key)}</span>
              </div>
            ))}
          </div>
          <label>
            Geographic drill-down
            <select value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">All matching groups</option>
              {listing.groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.label} — {g.incidentIds.length} incidents
                </option>
              ))}
            </select>
          </label>
          {group && (
            <p>
              Statistics and list show the selected group. Landmark groups mean the reported landmark text, not a verified
              access route.
            </p>
          )}
          <label className="flood-check">
            <input
              type="checkbox"
              checked={viewport}
              onChange={(e) => setViewport(e.target.checked)}
            />
            Limit results to map viewport (unresolved locations remain counted
            when unchecked)
          </label>
          <FloodMap
            incidents={visible}
            onSelect={setSelected}
            onBounds={setBounds}
          />
          <p>
            Map and list show this page of matching incidents. {listing.total}{" "}
            total. Unconfirmed locations stay in the list and are never plotted
            as precise buildings.
          </p>
          <div className="flood-operations-grid">
            <section aria-label="Matching incident list">
              {visible.map((i) => (
                <button
                  className={`flood-list-item ${selected === i.id ? "selected" : ""}`}
                  key={i.id}
                  onClick={() => setSelected(i.id)}
                >
                  <strong>
                    #{i.id} · {i.types.map(human).join(", ")} ·{" "}
                    {i.locality || "Location clarification"}
                  </strong>
                  <span>
                    {i.street} · {i.verification} · {i.urgency} ·{" "}
                    {i.assignmentStates.map(human).join(", ") ||
                      "No rescue task"}
                  </span>
                  <span>
                    {i.stale ? "Stale / time unknown" : "Recent observation"} ·{" "}
                    {i.locationStatus}
                    {i.conflict ? " · Conflicting evidence" : ""}
                  </span>
                </button>
              ))}
              {!visible.length && (
                <p>
                  No matching incidents. Textual reporting remains available.
                </p>
              )}
              <div className="flood-actions">
                <button
                  className="button"
                  disabled={offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - 50))}
                >
                  Previous
                </button>
                <button
                  className="button"
                  disabled={offset + 50 >= listing.total}
                  onClick={() => setOffset((v) => v + 50)}
                >
                  Next
                </button>
              </div>
            </section>
            <section>
              {detail ? (
                <IncidentPanel
                  key={`${detail.id}-${detail.version}`}
                  incident={detail}
                  token={token}
                  role={role}
                  teams={teams}
                  changed={changed}
                />
              ) : (
                <p>Select an incident to inspect evidence and progress.</p>
              )}
            </section>
          </div>
          <details>
            <summary>Statistic definitions</summary>
            {Object.entries(listing.definitions).map(([k, v]) => (
              <p key={k}>
                <strong>{human(k)}:</strong> {v}
              </p>
            ))}
          </details>
        </>
      )}
    </div>
  );
}
