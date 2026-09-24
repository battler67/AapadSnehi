import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { EdgeDevice, EdgeRiskAssessment } from "../types";

const colors = { NORMAL: "#49d6c8", WATCH: "#ffd45f", WARNING: "#ff844b", CRITICAL: "#ff4560", RECOVERY: "#8ba9ff" };

export function EdgeRiskMap({ devices, risks, selectedId, onSelect }: { devices: EdgeDevice[]; risks: EdgeRiskAssessment[]; selectedId?: string; onSelect: (device: EdgeDevice) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const layers = useRef<L.Layer[]>([]);
  useEffect(() => {
    if (!root.current || map.current) return;
    map.current = L.map(root.current, { center: [22.8, 80.2], zoom: 4, zoomControl: false });
    L.control.zoom({ position: "bottomright" }).addTo(map.current);
    L.tileLayer(import.meta.env.VITE_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map.current);
    return () => { map.current?.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    if (!map.current) return;
    layers.current.forEach((item) => item.removeFrom(map.current!));
    layers.current = [];
    devices.forEach((device) => {
      const deviceRisks = risks.filter((risk) => risk.deviceId === device.deviceId);
      const risk = deviceRisks.sort((a, b) => b.probability - a.probability)[0];
      const level = risk?.riskLevel || "NORMAL";
      const marker = L.circleMarker([device.location.latitude, device.location.longitude], {
        radius: selectedId === device.deviceId ? 12 : 8,
        color: selectedId === device.deviceId ? "white" : colors[level],
        weight: selectedId === device.deviceId ? 3 : 2,
        fillColor: colors[level], fillOpacity: 0.88,
      }).addTo(map.current!);
      marker.bindTooltip(`<strong>${device.name.replace(/[<>]/g, "")}</strong><br/>${risk ? `${risk.hazard}: ${Math.round(risk.probability * 100)}% estimated risk` : "Awaiting telemetry"}<br/>SIMULATED / DEMO ONLY`);
      marker.on("click", () => onSelect(device));
      layers.current.push(marker);
    });
    if (devices.length && devices.length < 20) {
      const bounds = L.latLngBounds(devices.map((item) => [item.location.latitude, item.location.longitude]));
      map.current.fitBounds(bounds.pad(0.35), { maxZoom: 10 });
    }
  }, [devices, onSelect, risks, selectedId]);
  return <div ref={root} className="edge-map" aria-label="Simulated edge device risk map" />;
}
