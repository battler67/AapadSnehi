import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("trained model API", () => {
  it("uses versioned allowlisted catalog and prediction routes", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ apiVersion: "v1", notice: "demo", models: [], unavailableModels: [], supportedSources: [], futureSources: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "prediction", modelId: "flood-random-forest-v2" }) });
    vi.stubGlobal("fetch", fetchMock);

    await api.mlModels();
    await api.mlPredict({ modelId: "flood-random-forest-v2", source: "manual", features: { row: {} }, unitsConfirmed: true });

    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/ml/models");
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/ml/predict");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "POST", signal: expect.any(AbortSignal) }));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(expect.objectContaining({ modelId: "flood-random-forest-v2", unitsConfirmed: true }));
  });

  it("loads synthetic data through the separate scenario route", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ source: "synthetic", features: {}, unitsConfirmed: true }) });
    vi.stubGlobal("fetch", fetchMock);
    await api.mlScenario("wildfire-unet-v1", "high");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/ml/models/wildfire-unet-v1/scenarios/high");
  });

  it("translates browser timeouts into a hosted-service recovery message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("signal timed out", "TimeoutError")));

    await expect(api.mlModels()).rejects.toThrow(
      "The hosted service took too long to respond. It may be waking from sleep; please retry.",
    );
  });
});
