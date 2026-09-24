import { useEffect, useRef, useState } from "react";
import { FloodMap } from "../components/FloodMap";
import { photoLocation } from "../lib/photo-location";
import {
  compressPhoto,
  draftStore,
  floodRequest,
  newDraft,
  uploadPhoto,
  type Draft,
  type Photo,
  type Receipt,
  type Submission,
} from "../lib/flood";

const addressLabels = {
  state: "State",
  city: "District / city",
  locality: "Locality",
  ward: "Ward",
  street: "Street name",
  street_number: "Street number",
  building: "Building / apartment",
  door: "Door / house number",
  floor: "Floor",
  landmark: "Nearby landmark",
  directions: "Directions from landmark / access notes",
};
const human = (s: string) => s.replaceAll("_", " ");

function Preview({ photo }: { photo: Photo }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const next = URL.createObjectURL(photo.file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [photo.file]);
  return <img src={url} alt={`Selected photo ${photo.name}`} />;
}

export function FloodReportPage() {
  const [draft, setDraft] = useState<Draft>(newDraft);
  const [loaded, setLoaded] = useState(false);
  const [step, setStep] = useState(0);
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [addressResults, setAddressResults] = useState<{ label: string; location: Submission["location"] }[]>([]);
  const [lookupReference, setLookupReference] = useState("");
  const [lookupToken, setLookupToken] = useState("");
  const saving = useRef(Promise.resolve());
  const p = draft.payload;
  useEffect(() => {
    draftStore("get")
      .then((d) => {
        if (d) {
          setDraft(d);
          setMessage("Recovered report from this device.");
        }
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
        setMessage(
          "Device storage unavailable. Keep this page open until submission succeeds.",
        );
      });
  }, []);
  useEffect(() => {
    if (!loaded) return;
    saving.current = saving.current
      .then(() =>
        draft.receipt && draft.photos.every((photo) => photo.attached)
          ? draftStore("delete")
          : draftStore("put", draft),
      )
      .then(() => {
        setSaved(
          draft.state === "queued"
            ? "Waiting to upload — saved on this device"
            : draft.receipt
              ? "Received by the platform — completed local draft removed"
              : "Saved on this device — not received by the platform",
        );
      })
      .catch(() => setSaved("Could not save on this device"));
  }, [draft, loaded]);
  function patch(fields: Partial<Submission>) {
    setDraft((d) => ({ ...d, payload: { ...d.payload, ...fields } }));
  }
  async function photos(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    try {
      const prepared: Photo[] = [];
      for (const file of Array.from(files).slice(0, 4 - draft.photos.length)) {
        prepared.push({
          id: crypto.randomUUID(),
          file: await compressPhoto(file),
          name: file.name,
        });
        if (p.location.latitude === null) {
          const suggestion = photoLocation(await file.arrayBuffer());
          if (suggestion) {
            patch({ location: { latitude: suggestion[0], longitude: suggestion[1], source: "photo_metadata", confirmed: false, accuracy: null, precision: "unknown" } });
            setMessage("Photo GPS suggested a location. Confirm where the photo was taken before using the pin.");
          }
        }
      }
      setDraft((d) => ({
        ...d,
        photos: [...d.photos, ...prepared].slice(0, 4),
      }));
      if (files.length + draft.photos.length > 4)
        setMessage("Only four photos can be attached.");
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }
  function locate() {
    if (!navigator.geolocation) {
      setMessage("GPS unavailable. Enter an address or move the pin.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        patch({
          location: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            source: "device_gps",
            accuracy: position.coords.accuracy,
            confirmed: false,
            precision: position.coords.accuracy > 50 ? "street" : "unknown",
          },
        });
        setMessage(
          "Device position suggested. Confirm where the photo was taken; you may be somewhere else.",
        );
      },
      () =>
        setMessage(
          "GPS denied or unavailable. You can use a pin or textual address.",
        ),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }
  async function submit() {
    setBusy(true);
    setMessage("");
    let current = { ...draft, state: "queued" as Draft["state"] };
    try {
      await saving.current;
      await draftStore("put", current).catch(() =>
        setSaved("Device storage unavailable; attempting direct submission"),
      );
      setDraft(current);
      const receipt =
        draft.receipt ||
        (await floodRequest<Receipt>("/reports", "", p, "POST"));
      current = { ...current, state: "received", receipt };
      await draftStore("put", current);
      setDraft(current);
      for (const photo of current.photos) {
        if (photo.attached) continue;
        try {
          const uploaded = await uploadPhoto(
            receipt.reportId,
            photo,
            p.reporter_token,
            (percent) => setProgress((v) => ({ ...v, [photo.id]: percent })),
          );
          current = {
            ...current,
            photos: current.photos.map((item) =>
              item.id === photo.id
                ? { ...item, attached: uploaded.id, review: uploaded.review, error: undefined }
                : item,
            ),
          };
        } catch (e) {
          current = {
            ...current,
            photos: current.photos.map((item) =>
              item.id === photo.id ? { ...item, error: String(e) } : item,
            ),
          };
        }
        await draftStore("put", current);
        setDraft(current);
      }
      if (current.photos.every((photo) => photo.attached)) {
        await saving.current;
        await draftStore("delete");
      }
      setMessage(
        "Text and location received. Check each photograph's attachment status below.",
      );
    } catch (e) {
      setMessage(
        `${String(e)}. Your draft remains on this device. Correct any validation errors, then explicitly retry.`,
      );
    } finally {
      setBusy(false);
    }
  }
  async function clear() {
    await saving.current;
    await draftStore("delete");
    setDraft(newDraft());
    setStep(0);
    setMessage(
      "Submitted draft, photos and contact details removed from this device. Keep your reference and private access key if you need to update it.",
    );
  }
  const select = (
    key: "water_level" | "trend" | "access" | "count_quality" | "time_quality",
    label: string,
    options: string[],
  ) => (
    <label>
      {label}
      <select aria-label={label} value={p[key]} onChange={(e) => patch({ [key]: e.target.value })}>
        {options.map((v) => (
          <option key={v} value={v}>
            {human(v)}
          </option>
        ))}
      </select>
    </label>
  );
  if (!loaded) return <p>Recovering saved draft…</p>;
  return (
    <div className="content page-space flood-workspace">
      <header>
        <p className="eyebrow">Citizen flood reporting</p>
        <h1>Report flooding. Make the location clear.</h1>
        <p>
          Community observations need review. Submitting a report does not
          dispatch a rescue team.
        </p>
        <a href="/flood">View flood reports and rescue coordination →</a>
      </header>
      {!draft.receipt && <details className="glass-panel flood-card"><summary>View or update a received report</summary><p>Loading a receipt replaces the current draft. Save any unfinished report first.</p><label>Report reference<input value={lookupReference} onChange={e => setLookupReference(e.target.value)} /></label><label>Report access key<input type="password" value={lookupToken} onChange={e => setLookupToken(e.target.value)} /></label><button className="button" onClick={async () => {
        try {
          const received = await floodRequest<Receipt & { observation: Omit<Submission, "idempotency_key" | "reporter_token">; assignmentStates: string[] }>(`/receipt?reference=${encodeURIComponent(lookupReference)}`, "", undefined, "GET", lookupToken);
          setDraft({ ...newDraft(), state: "received", receipt: received, payload: { ...newDraft().payload, ...received.observation, reporter_token: lookupToken }, photos: [] });
          setLookupToken("");
          setMessage(`Current rescue progress: ${received.assignmentStates.map(human).join(", ") || "No rescue task"}. Receipt does not imply dispatch.`);
        } catch (e) { setMessage(String(e)); }
      }}>Load private receipt</button></details>}
      <p role="status" className="flood-notice">
        {saved}
      </p>
      {message && (
        <p role="alert" className="flood-notice">
          {message}
        </p>
      )}
      {draft.receipt ? (
        <section className="glass-panel flood-card">
          <h2>Received by the platform</h2>
          <p>
            Report reference: <strong>{draft.receipt.reference}</strong> ·
            Incident #{draft.receipt.incidentId}
          </p>
          <p>
            Server receipt:{" "}
            {new Date(draft.receipt.receivedAt).toLocaleString()}
          </p>
          <p>
            Review: {human(draft.receipt.reviewStatus)} · Location:{" "}
            {draft.receipt.locationStatus}
          </p>
          <p>{draft.receipt.message}</p>
          <p>
            Photos attached: {draft.photos.length ? draft.photos.filter((f) => f.attached).length : draft.receipt.mediaCount} of{" "}
            {draft.photos.length || draft.receipt.mediaCount}. Photos remain private.
          </p>
          <details>
            <summary>
              Save private access key to view or update your report
            </summary>
            <p>Keep this key private. It grants access to your report.</p>
            <code className="flood-secret">{p.reporter_token}</code>
          </details>
          {draft.photos.map((photo) => (
            <p key={photo.id}>
              {photo.name}:{" "}
              {photo.attached ? "Attached" : photo.error || "Not attached"}
              {photo.review && <span> — {photo.review.message} {photo.review.caption}</span>}
            </p>
          ))}
          {!draft.photos.length && draft.receipt.media?.map((media) => (
            <p key={media.id}>Photo screening: {media.review.message} {media.review.caption}</p>
          ))}
          {draft.photos.some((photo) => !photo.attached) && (
            <button className="button" disabled={busy} onClick={submit}>
              Retry unattached photos
            </button>
          )}
          <button
            className="button"
            disabled={busy}
            onClick={async () => {
              await saving.current;
              const next = newDraft();
              next.payload.reporter_token = p.reporter_token;
              next.payload.kind = "update";
              next.payload.update_incident_id = draft.receipt!.incidentId;
              next.payload.address = p.address;
              next.payload.location = p.location;
              setDraft(next);
              setStep(0);
            }}
          >
            Provide a new observation
          </button>
          <button className="button primary" disabled={busy} onClick={clear}>
            Finish and clear this device
          </button>
        </section>
      ) : (
        <>
          <nav className="flood-steps" aria-label="Reporting steps">
            {[
              "Report type",
              "Photographs",
              "Location",
              "Situation",
              "Review & send",
            ].map((label, index) => (
              <button
                type="button"
                className={step === index ? "button primary" : "button"}
                key={label}
                onClick={() => setStep(index)}
              >
                {index + 1}. {label}
              </button>
            ))}
          </nav>
          <section className="glass-panel flood-card">
            {step === 0 && (
              <>
                <h2>What would you like to report?</h2>
                <div className="flood-type-grid">
                  {[
                    ["rescue", "People need rescue"],
                    ["flood", "Flooding observed"],
                    ["blocked", "Road or access blocked"],
                    ["update", "Update an existing incident"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={p.kind === value}
                      className={p.kind === value ? "button primary" : "button"}
                      onClick={() => patch({ kind: value })}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {p.kind === "update" && (
                  <div className="flood-fields">
                    <label>
                      Incident reference number
                      <input
                        type="number"
                        min="1"
                        value={p.update_incident_id || ""}
                        onChange={(e) =>
                          patch({
                            update_incident_id: Number(e.target.value) || null,
                          })
                        }
                      />
                    </label>
                    <label>
                      Private reporter access key
                      <input
                        type="password"
                        value={p.reporter_token}
                        onChange={(e) =>
                          patch({ reporter_token: e.target.value })
                        }
                      />
                    </label>
                    <p>
                      Use the key from your receipt. Other witnesses should
                      submit a new observation for grouping review.
                    </p>
                  </div>
                )}
              </>
            )}
            {step === 1 && (
              <>
                <h2>Photographs are helpful, but optional</h2>
                <p>
                  Up to four JPEG, PNG or WebP photos, 8 MB each. Photos are
                  compressed and remain private. Uploaded photos are sent to OpenAI
                  for advisory image screening when configured; metadata is removed,
                  and contact/address fields are not sent. With no photos, no AI call
                  is made. AI cannot establish authenticity, depth or urgency and
                  never replaces human verification. You can skip this step.
                </p>
                <div className="flood-fields">
                  <label>
                    Take a photograph
                    <input
                      aria-label="Take a photograph"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      capture="environment"
                      disabled={busy}
                      onChange={(e) => {
                        void photos(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <label>
                    Choose from gallery
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      disabled={busy}
                      onChange={(e) => {
                        void photos(e.target.files);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                <div className="flood-photos">
                  {draft.photos.map((photo) => (
                    <figure key={photo.id}>
                      <Preview photo={photo} />
                      <figcaption>{photo.name}</figcaption>
                      <button
                        className="button"
                        onClick={() =>
                          setDraft((d) => ({
                            ...d,
                            photos: d.photos.filter((f) => f.id !== photo.id),
                          }))
                        }
                      >
                        Remove
                      </button>
                      {progress[photo.id] !== undefined && (
                        <progress max={100} value={progress[photo.id]} />
                      )}
                    </figure>
                  ))}
                </div>
              </>
            )}
            {step === 2 && (
              <>
                <h2>Where was this photo taken?</h2>
                <p>
                  Your current location may differ from the incident. Move the
                  pin and explicitly confirm it. A textual description is
                  accepted when mapping fails.
                </p>
                <button className="button" onClick={locate}>
                  Use my current location
                </button>
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      const results = await floodRequest<{ items: typeof addressResults }>(
                        `/geocode?q=${encodeURIComponent([p.address.street, p.address.locality, p.address.city].join(" ").trim() || "address")}`,
                      );
                      setAddressResults(results.items);
                      setMessage(results.items.length ? "Choose a suggested area, then correct and confirm the pin. Search sends the entered address to OpenStreetMap Nominatim." : "No address matches. Enter a textual description or manual pin.");
                    } catch (e) {
                      setMessage(String(e));
                    }
                  }}
                >
                  Search entered address
                </button>
                <p>Address search, when configured, sends the entered address to OpenStreetMap Nominatim. Results are suggestions, not building verification.</p>
                {addressResults.map(result => <button className="button" key={result.label} onClick={() => { patch({ location: result.location }); setAddressResults([]); }}>{result.label} ({result.location.precision} suggestion)</button>)}
                <FloodMap
                  pin={p.location}
                  onPin={(latitude, longitude) =>
                    patch({
                      location: {
                        latitude,
                        longitude,
                        source: "manual_pin",
                        accuracy: null,
                        confirmed: false,
                        precision: "unknown",
                      },
                    })
                  }
                />
                <div className="flood-fields">
                  <label>
                    Latitude (optional)
                    <input
                      type="number"
                      step="any"
                      min="-90"
                      max="90"
                      value={p.location.latitude ?? ""}
                      onChange={(e) =>
                        patch({
                          location: {
                            ...p.location,
                            latitude: e.target.value
                              ? Number(e.target.value)
                              : null,
                            source: "manual_pin",
                            confirmed: false,
                            accuracy: null,
                          },
                        })
                      }
                    />
                  </label>
                  <label>
                    Longitude (optional)
                    <input
                      type="number"
                      step="any"
                      min="-180"
                      max="180"
                      value={p.location.longitude ?? ""}
                      onChange={(e) =>
                        patch({
                          location: {
                            ...p.location,
                            longitude: e.target.value
                              ? Number(e.target.value)
                              : null,
                            source: "manual_pin",
                            confirmed: false,
                            accuracy: null,
                          },
                        })
                      }
                    />
                  </label>
                  <label>
                    Location precision
                    <select
                      value={p.location.precision}
                      onChange={(e) =>
                        patch({
                          location: {
                            ...p.location,
                            precision: e.target.value,
                          },
                        })
                      }
                    >
                      {["unknown", "locality", "street", "building"].map(
                        (v) => (
                          <option key={v}>{v}</option>
                        ),
                      )}
                    </select>
                  </label>
                </div>
                {p.location.accuracy != null && (
                  <p>
                    Device GPS accuracy: ±{Math.round(p.location.accuracy)}{" "}
                    metres.{" "}
                    {p.location.accuracy > 50 &&
                      "Poor accuracy: do not claim building precision."}
                  </p>
                )}
                <label className="flood-check">
                  <input
                    type="checkbox"
                    disabled={
                      p.location.latitude == null ||
                      p.location.longitude == null
                    }
                    checked={p.location.confirmed}
                    onChange={(e) =>
                      patch({
                        location: {
                          ...p.location,
                          confirmed: e.target.checked,
                        },
                      })
                    }
                  />
                  I confirm this pin marks where the photo was taken / help is
                  needed.
                </label>
                <h3>Address details</h3>
                <p>
                  Door numbers are text, for example 12-4/7A. Fill what you
                  know; precise details help responders.
                </p>
                <div className="flood-fields">
                  {Object.entries(addressLabels).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input
                        maxLength={key === "directions" ? 1000 : 120}
                        value={p.address[key as keyof typeof p.address]}
                        onChange={(e) =>
                          patch({
                            address: { ...p.address, [key]: e.target.value },
                          })
                        }
                      />
                    </label>
                  ))}
                </div>
              </>
            )}
            {step === 3 && (
              <>
                <h2>What did you observe?</h2>
                <div className="flood-fields">
                  {select("time_quality", "Observation time quality", [
                    "unknown",
                    "exact",
                    "approximate",
                  ])}
                  {p.time_quality !== "unknown" && (
                    <label>
                      Time observed
                      <input
                        type="datetime-local"
                        value={
                          p.observed_at
                            ? new Date(
                                new Date(p.observed_at).getTime() -
                                  new Date(p.observed_at).getTimezoneOffset() *
                                    60000,
                              )
                                .toISOString()
                                .slice(0, 16)
                            : ""
                        }
                        onChange={(e) =>
                          patch({
                            observed_at: e.target.value
                              ? new Date(e.target.value).toISOString()
                              : null,
                          })
                        }
                      />
                    </label>
                  )}
                  {select("water_level", "Water level — citizen estimate", [
                    "unknown",
                    "ankle",
                    "knee",
                    "waist",
                    "above_waist",
                  ])}
                  {select("trend", "Water trend", [
                    "unknown",
                    "rising",
                    "stable",
                    "receding",
                  ])}
                  {select("access", "Access as reported", [
                    "unknown",
                    "passable_reported",
                    "blocked",
                  ])}
                </div>
                <label>
                  Description (optional)
                  <textarea
                    maxLength={2000}
                    value={p.description}
                    onChange={(e) => patch({ description: e.target.value })}
                  />
                </label>
                {(p.kind === "rescue" || p.kind === "update") && (
                  <>
                    <h3>Assistance needed</h3>
                    <div className="flood-fields">
                      {select("count_quality", "People count quality", [
                        "unknown",
                        "exact",
                        "estimated",
                      ])}
                      {p.count_quality !== "unknown" && (
                        <label>
                          Reported people needing assistance
                          <input
                            type="number"
                            min="0"
                            max="100000"
                            value={p.people ?? ""}
                            onChange={(e) =>
                              patch({
                                people: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              })
                            }
                          />
                        </label>
                      )}
                      <label>
                        Building/floor or last known position
                        <input
                          value={p.position}
                          onChange={(e) => patch({ position: e.target.value })}
                        />
                      </label>
                      <label>
                        Contact number (optional, private)
                        <input
                          type="tel"
                          maxLength={40}
                          value={p.contact}
                          onChange={(e) => patch({ contact: e.target.value })}
                        />
                      </label>
                    </div>
                    {[
                      "limited_mobility",
                      "urgent_medical",
                      "children",
                      "transport",
                      "other",
                    ].map((need) => (
                      <label className="flood-check" key={need}>
                        <input
                          type="checkbox"
                          checked={p.assistance.includes(need)}
                          onChange={(e) =>
                            patch({
                              assistance: e.target.checked
                                ? [...p.assistance, need]
                                : p.assistance.filter((v) => v !== need),
                            })
                          }
                        />
                        {human(need)}
                      </label>
                    ))}
                    <label className="flood-check">
                      <input
                        type="checkbox"
                        checked={p.reporter_present}
                        onChange={(e) =>
                          patch({ reporter_present: e.target.checked })
                        }
                      />
                      I am at this location (uncheck if reporting for someone
                      else)
                    </label>
                  </>
                )}
              </>
            )}
            {step === 4 && (
              <>
                <h2>Review and send</h2>
                <p>
                  Report type: {human(p.kind)} · {draft.photos.length} optional
                  photographs
                </p>
                <p>
                  {Object.values(p.address).filter(Boolean).join(", ") ||
                    "No textual address"}
                </p>
                <p>
                  {p.location.confirmed
                    ? `Confirmed pin: ${p.location.latitude}, ${p.location.longitude}`
                    : "Location needs clarification — a usable text description is required."}
                </p>
                <p>
                  Observation time:{" "}
                  {p.time_quality === "unknown"
                    ? "Unknown"
                    : p.observed_at || "Not entered"}
                </p>
                <p>
                  Water level: {human(p.water_level)} (citizen estimate) ·
                  Reported people:{" "}
                  {p.count_quality === "unknown"
                    ? "Unknown"
                    : `${p.people ?? "not entered"} (${p.count_quality})`}
                </p>
                <p>
                  Photos upload after the text report. If a photo fails, the
                  urgent request is still received. Retry is explicit and does
                  not create a duplicate.
                </p>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={submit}
                >
                  {busy
                    ? "Sending…"
                    : draft.state === "queued"
                      ? "Retry submission"
                      : "Submit report"}
                </button>
              </>
            )}
          </section>
          <div className="flood-actions">
            <button
              className="button"
              disabled={step === 0 || busy}
              onClick={() => setStep((s) => s - 1)}
            >
              Back
            </button>
            <button
              className="button primary"
              disabled={step === 4 || busy}
              onClick={() => setStep((s) => s + 1)}
            >
              Continue
            </button>
          </div>
        </>
      )}
    </div>
  );
}
