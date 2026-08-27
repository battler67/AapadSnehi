import L from "leaflet";
import "leaflet.heat";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { Incident } from "../types";

interface IncidentMapProps {
  incidents: Incident[];
  onSelect?: (incident: Incident) => void;
  className?: string;
}

const severityColor = (severity: number) =>
  severity >= 5 ? "#ff4560" : severity >= 4 ? "#ff844b" : severity >= 3 ? "#ffd45f" : "#5fe7df";

export function IncidentMap({ incidents, onSelect, className = "" }: IncidentMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const overlaysRef = useRef<L.Layer[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [22.8, 80.2],
      zoom: 4,
      zoomControl: false,
      attributionControl: true,
      minZoom: 3,
    });
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.tileLayer(
      import.meta.env.VITE_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      },
    ).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    overlaysRef.current.forEach((layer) => layer.removeFrom(map));
    overlaysRef.current = [];

    const heatPoints = incidents.map((incident) => [
      incident.latitude,
      incident.longitude,
      Math.max(0.2, incident.priorityScore / 100),
    ] as L.HeatLatLngTuple);
    if (heatPoints.length) {
      const heat = L.heatLayer(heatPoints, {
        radius: 38,
        blur: 32,
        maxZoom: 9,
        minOpacity: 0.35,
        gradient: { 0.2: "#5fe7df", 0.45: "#ffd45f", 0.7: "#ff844b", 1: "#ff4560" },
      }).addTo(map);
      overlaysRef.current.push(heat);
    }
    incidents.forEach((incident) => {
      const marker = L.circleMarker([incident.latitude, incident.longitude], {
        radius: 5 + incident.severity,
        color: "rgba(255,255,255,.92)",
        weight: 1.5,
        fillColor: severityColor(incident.severity),
        fillOpacity: 0.92,
      }).addTo(map);
      marker.bindTooltip(
        `<strong>${incident.title.replace(/[<>]/g, "")}</strong><br/>${incident.locationName.replace(/[<>]/g, "")} · P${Math.round(incident.priorityScore)}`,
        { direction: "top", className: "map-tooltip" },
      );
      if (onSelect) marker.on("click", () => onSelect(incident));
      overlaysRef.current.push(marker);
    });
  }, [incidents, onSelect]);

  return <div ref={containerRef} className={`incident-map ${className}`} aria-label="Disaster intensity heat map" />;
}
