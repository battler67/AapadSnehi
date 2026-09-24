import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, api } from "./api";

describe("edge early-warning API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("starts a deterministic simulation without auth or a public dispatch call", async () => {
    const response = { runId: "run-1", scenario: "flood-gradual-001", region: "visakhapatnam", status: "running", cursorStep: 0, totalSteps: 75, emittedCount: 0, rejectedCount: 0, error: "" };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const payload = { scenario: "flood-gradual-001", numberOfDevices: 6, seed: 42, region: "visakhapatnam", speedMultiplier: 60, timestepSeconds: 60 };
    await api.startEdgeSimulation(payload);
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE}/api/edge/simulations`);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", body: JSON.stringify(payload), headers: expect.not.objectContaining({ Authorization: expect.anything() }) });
  });

  it("requires the UI to explicitly carry demo confirmation for incident promotion", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 2 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await api.reviewEdgeEvent(2, "promote_to_incident", "Demo operator", true);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ action: "promote_to_incident", confirmDemoOnly: true });
  });
});
