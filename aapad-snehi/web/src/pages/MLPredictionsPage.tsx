import {
  AlertTriangle,
  Beaker,
  BrainCircuit,
  CheckCircle2,
  Database,
  Gauge,
  LoaderCircle,
  Play,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../components/ui";
import { api } from "../lib/api";
import type {
  MLFeatureDefinition,
  MLModelCatalog,
  MLModelInfo,
  MLPredictionResult,
} from "../types";

type FeatureValues = Record<string, unknown>;

function FireScoreGrid({ scores, cutoff }: { scores: number[][]; cutoff: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || scores.length !== 64) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const image = context.createImageData(64, 64);
    scores.forEach((row, y) => row.forEach((score, x) => {
      const offset = (y * 64 + x) * 4;
      const normalized = Math.max(0, Math.min(1, score));
      image.data[offset] = Math.round(255 * normalized);
      image.data[offset + 1] = Math.round(95 + 150 * normalized);
      image.data[offset + 2] = normalized >= cutoff ? 45 : Math.round(175 - 120 * normalized);
      image.data[offset + 3] = 255;
    }));
    context.putImageData(image, 0, 0);
  }, [cutoff, scores]);
  return <canvas ref={ref} className="ml-score-map" width={64} height={64} role="img" aria-label="Uncalibrated 64 by 64 next-day active-fire score grid" />;
}

function ProbabilityBars({ values }: { values: Record<string, number> }) {
  return <div className="ml-probabilities" aria-label="Class score comparison">
    {Object.entries(values).map(([name, value]) => <div key={name}>
      <span>{name.replace(/([A-Z])/g, " $1")}</span>
      <progress max={1} value={value} />
      <strong>{(value * 100).toFixed(2)}%</strong>
    </div>)}
  </div>;
}

function FeatureField({ definition, value, onChange }: { definition: MLFeatureDefinition; value: unknown; onChange: (value: string) => void }) {
  return <label className="ml-field">
    <span>{definition.label}<small>{definition.unit}</small></span>
    <input
      type={definition.type === "number" ? "number" : "text"}
      value={value === undefined || value === null ? "" : String(value)}
      min={definition.minimum ?? undefined}
      max={definition.maximum ?? undefined}
      step={definition.type === "number" ? "any" : undefined}
      required
      onChange={(event) => onChange(event.target.value)}
      aria-describedby={`help-${definition.name.replace(/[^a-z0-9]/gi, "-")}`}
    />
    <small id={`help-${definition.name.replace(/[^a-z0-9]/gi, "-")}`}>{definition.helperText}</small>
  </label>;
}

export function MLPredictionsPage() {
  const [catalog, setCatalog] = useState<MLModelCatalog | null>(null);
  const [modelId, setModelId] = useState("");
  const [mode, setMode] = useState<"manual" | "synthetic">("synthetic");
  const [scenarioId, setScenarioId] = useState("low");
  const [features, setFeatures] = useState<FeatureValues>({});
  const [gridJson, setGridJson] = useState("");
  const [scenarioNotes, setScenarioNotes] = useState<string[]>([]);
  const [result, setResult] = useState<MLPredictionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [error, setError] = useState("");

  const selected = catalog?.models.find((model) => model.id === modelId) ?? null;
  const groupedFeatures = useMemo(() => {
    const groups = new Map<string, MLFeatureDefinition[]>();
    for (const feature of selected?.features ?? []) {
      groups.set(feature.group, [...(groups.get(feature.group) ?? []), feature]);
    }
    return [...groups.entries()];
  }, [selected]);

  const loadScenario = useCallback(async (nextModelId: string, nextScenarioId: string) => {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const scenario = await api.mlScenario(nextModelId, nextScenarioId);
      setFeatures(scenario.features);
      setScenarioNotes(scenario.notes);
      setGridJson(JSON.stringify(scenario.features));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load the synthetic scenario");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    setLoadingCatalog(true);
    setError("");
    api.mlModels()
      .then((response) => {
        if (!active) return;
        setCatalog(response);
        const first = response.models.find((model) => model.availability.available) ?? response.models[0];
        if (first) {
          setModelId(first.id);
          setScenarioId(first.scenarios[0]?.id ?? "low");
          void loadScenario(first.id, first.scenarios[0]?.id ?? "low");
        }
      })
      .catch((caught) => active && setError(caught instanceof Error ? caught.message : "Unable to load model catalog"))
      .finally(() => active && setLoadingCatalog(false));
    return () => { active = false; };
  }, [catalogAttempt, loadScenario]);

  const selectModel = (nextModelId: string) => {
    const model = catalog?.models.find((item) => item.id === nextModelId);
    const nextScenario = model?.scenarios[0]?.id ?? "low";
    setModelId(nextModelId);
    setScenarioId(nextScenario);
    setMode("synthetic");
    void loadScenario(nextModelId, nextScenario);
  };

  const updateFloodFeature = (name: string, value: string) => {
    setMode("manual");
    setResult(null);
    setFeatures((current) => ({
      ...current,
      row: { ...((current.row as Record<string, unknown> | undefined) ?? {}), [name]: value },
    }));
  };

  const submit = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      let payloadFeatures = features;
      if (selected.inputMode === "spatial_grid") {
        const parsed = JSON.parse(gridJson) as FeatureValues;
        payloadFeatures = parsed;
      } else {
        const row = { ...((features.row as Record<string, unknown> | undefined) ?? {}) };
        for (const definition of selected.features) {
          if (definition.type === "number") row[definition.name] = Number(row[definition.name]);
        }
        payloadFeatures = { row };
      }
      setResult(await api.mlPredict({ modelId: selected.id, source: mode, features: payloadFeatures, unitsConfirmed: true }));
    } catch (caught) {
      setError(caught instanceof SyntaxError ? "The spatial JSON is invalid." : caught instanceof Error ? caught.message : "Prediction failed");
    } finally {
      setBusy(false);
    }
  };

  return <div className="content page-space ml-page">
    <PageHeader
      eyebrow="Historical research models"
      title="Test disaster predictions"
      description="Run trusted saved flood and wildfire models with manual or clearly labelled synthetic inputs. This page is isolated from warning and dispatch workflows."
    />

    <div className="ml-demo-banner" role="note">
      <AlertTriangle size={20} />
      <div><strong>RESEARCH DEMO — NOT AN OFFICIAL WARNING</strong><span>Inputs are manual or synthetic, not live sensors, weather feeds, satellites, or government APIs.</span></div>
    </div>
    {error && <div className="ml-error" role="alert">
      <span>{error}</span>
      {!catalog && !loadingCatalog && <button className="button secondary" type="button" onClick={() => setCatalogAttempt((attempt) => attempt + 1)}>Retry model catalog</button>}
    </div>}

    {loadingCatalog ? <div className="glass-panel ml-loading"><LoaderCircle className="spin" /> Loading trusted model registry; a sleeping free demo may take up to two minutes to wake…</div> : <>
      <section className="ml-model-grid" aria-label="Available trained models">
        {catalog?.models.map((model) => <button
          key={model.id}
          type="button"
          className={`glass-panel ml-model-card ${model.id === modelId ? "active" : ""}`}
          onClick={() => selectModel(model.id)}
          aria-pressed={model.id === modelId}
          disabled={!model.availability.available}
        >
          <span className="ml-model-icon">{model.disaster === "wildfire" ? <BrainCircuit /> : <Gauge />}</span>
          <span><strong>{model.name}</strong><small>{model.target}</small></span>
          <em className={model.availability.available ? "available" : "unavailable"}>{model.availability.available ? "Ready" : model.availability.status}</em>
        </button>)}
      </section>

      {selected && <div className="ml-workspace">
        <section className="glass-panel ml-input-panel">
          <div className="panel-title"><div><p className="eyebrow"><span />Input configuration</p><h2>{selected.name}</h2></div><Database size={20} /></div>
          <p className="ml-description">{selected.description}</p>
          <div className="ml-mode-tabs" role="tablist" aria-label="Prediction input mode">
            <button type="button" className={mode === "manual" ? "active" : ""} onClick={() => setMode("manual")}><Database size={15} /> Manual input</button>
            <button type="button" className={mode === "synthetic" ? "active" : ""} onClick={() => setMode("synthetic")}><Beaker size={15} /> Synthetic test data</button>
          </div>

          <div className="ml-scenario-row">
            <label>Test scenario
              <select value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>
                {selected.scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.label}</option>)}
              </select>
            </label>
            <button className="button secondary" type="button" disabled={busy} onClick={() => { setMode("synthetic"); void loadScenario(selected.id, scenarioId); }}><Beaker size={15} /> Load synthetic scenario</button>
          </div>
          {scenarioNotes.length > 0 && <div className="ml-notes">{scenarioNotes.map((note) => <p key={note}>{note}</p>)}</div>}

          {selected.inputMode === "engineered_row" ? <div className="ml-feature-groups">
            {groupedFeatures.map(([group, definitions]) => <details key={group} open={group !== "Static catchment attributes"}>
              <summary>{group}<span>{definitions.length} required fields</span></summary>
              <div className="ml-field-grid">
                {definitions.map((definition) => <FeatureField
                  key={definition.name}
                  definition={definition}
                  value={(features.row as Record<string, unknown> | undefined)?.[definition.name]}
                  onChange={(value) => updateFloodFeature(definition.name, value)}
                />)}
              </div>
            </details>)}
          </div> : <div className="ml-json-input">
            <label htmlFor="ml-grid-json">Twelve aligned 64×64 channel grids as JSON</label>
            <textarea id="ml-grid-json" rows={12} value={gridJson} onChange={(event) => { setGridJson(event.target.value); setMode("manual"); setResult(null); }} spellCheck={false} />
            <small>Expected object: <code>{`{"channels":{"elevation":[64 rows],...,"PrevFireMask":[64 rows]}}`}</code>. A camera image is not a valid input.</small>
          </div>}

          <button className="button primary ml-run-button" type="button" disabled={busy || !selected.availability.available} onClick={() => void submit()}>
            {busy ? <><LoaderCircle className="spin" size={17} /> Running saved model…</> : <><Play size={17} /> Run research prediction</>}
          </button>
        </section>

        <aside className="glass-panel ml-model-info">
          <p className="eyebrow"><span />Model card</p>
          <h2>{selected.target}</h2>
          <dl><div><dt>Version</dt><dd>{selected.version}</dd></div><div><dt>Input</dt><dd>{selected.features.length} {selected.inputMode === "spatial_grid" ? "aligned grids" : "ordered features"}</dd></div><div><dt>Output</dt><dd>{selected.supportedOutput}</dd></div><div><dt>Operational validation</dt><dd>No</dd></div></dl>
        </aside>
      </div>}

      {result && <section className="glass-panel ml-result" aria-live="polite">
        <div className="panel-title"><div><p className="eyebrow"><span />Real saved-model output</p><h2>Prediction result</h2></div><CheckCircle2 size={22} /></div>
        <div className="ml-result-summary">
          <div><span>Predicted outcome</span><strong>{result.predictedOutcome}</strong></div>
          <div><span>Research review state</span><strong className={`risk-${result.riskLevel}`}>{result.riskLevel.replaceAll("_", " ")}</strong></div>
          <div><span>Processing time</span><strong>{result.inferenceTimeMs.toFixed(2)} ms</strong></div>
          <div><span>Input source</span><strong>{result.synthetic ? "Synthetic demonstration" : "Manual demonstration"}</strong></div>
        </div>
        {result.classProbabilities && <ProbabilityBars values={result.classProbabilities} />}
        {result.outputDetails.scoreMap && <div className="ml-map-result"><FireScoreGrid scores={result.outputDetails.scoreMap} cutoff={result.outputDetails.validationAlertCutoff ?? 0.5} /><div><strong>Uncalibrated activity score grid</strong><p>{result.outputDetails.cellsAboveCutoff} cells are above the validation cutoff; {result.outputDetails.newlyActiveCandidateCells} were previously inactive in the supplied mask.</p><small>No coordinates are available. This is not a mapped fire perimeter.</small></div></div>}
        {result.outputDetails.scoreMeaning && <p className="ml-score-meaning">{result.outputDetails.scoreMeaning}</p>}
        {result.validationWarnings.length > 0 && <div className="ml-warning-list"><strong>Validation warnings</strong>{result.validationWarnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
        <details className="ml-input-summary"><summary>Input summary used by the model</summary><pre>{JSON.stringify(result.inputDataUsed, null, 2)}</pre></details>
      </section>}
    </>}
  </div>;
}
