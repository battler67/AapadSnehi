import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import type { Incident, Location } from "../lib/flood";

export function FloodMap({
  incidents = [],
  pin,
  onPin,
  onSelect,
  onBounds,
}: {
  incidents?: Incident[];
  pin?: Location;
  onPin?: (lat: number, lon: number) => void;
  onSelect?: (id: number) => void;
  onBounds?: (bounds: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const callbacks = useRef({ onPin, onSelect, onBounds });
  callbacks.current = { onPin, onSelect, onBounds };
  const [tileError, setTileError] = useState(false);
  const [zoom, setZoom] = useState(5);
  useEffect(() => {
    if (!container.current) return;
    const m = L.map(container.current).setView([17.4, 78.48], 5);
    map.current = m;
    L.tileLayer(
      import.meta.env.VITE_MAP_TILE_URL ||
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" },
    )
      .on("tileerror", () => setTileError(true))
      .addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) =>
      callbacks.current.onPin?.(e.latlng.lat, e.latlng.lng),
    );
    m.on("zoomend", () => setZoom(m.getZoom()));
    m.on("moveend", () => {
      const b = m.getBounds();
      callbacks.current.onBounds?.(
        [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(","),
      );
    });
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const layers = L.layerGroup().addTo(m);
    const groups = new Map<string, Incident[]>();
    const size = zoom < 10 ? 0.2 : zoom < 14 ? 0.01 : 0.0001;
    incidents
      .filter((i) => i.point)
      .forEach((i) => {
        const key = i.point!.map((n) => Math.floor(n / size)).join(":");
        groups.set(key, [...(groups.get(key) || []), i]);
      });
    groups.forEach((group) => {
      const point = group[0].point!;
      const marker = L.circleMarker(point, {
        radius: group.length > 1 ? 14 : 8,
        color: "#fff",
        fillColor: group.some((i) => i.types.includes("rescue"))
          ? "#ff844b"
          : "#5fe7df",
        fillOpacity: 0.85,
      }).addTo(layers);
      const label = document.createElement("span");
      label.textContent =
        group.length > 1
          ? `${group.length} incidents — select to zoom`
          : `#${group[0].id} ${group[0].urgency} · ${group[0].verification}`;
      marker.bindTooltip(label).on("click", () => {
        if (group.length > 1 && zoom < 18)
          m.setView(point, Math.min(18, zoom + 3));
        else if (group.length > 1) {
          const list = document.createElement("div");
          group.forEach(incident => {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = `Incident #${incident.id} · ${incident.urgency}`;
            button.style.display = "block";
            button.style.padding = "12px";
            button.onclick = () => callbacks.current.onSelect?.(incident.id);
            list.appendChild(button);
          });
          marker.bindPopup(list).openPopup();
        } else callbacks.current.onSelect?.(group[0].id);
      });
    });
    if (pin?.latitude != null && pin.longitude != null) {
      const p: [number, number] = [pin.latitude, pin.longitude];
      const marker = L.marker(p, {
        draggable: true,
        icon: L.divIcon({
          className: "flood-pin",
          html: "<span>📍</span>",
          iconSize: [30, 36],
        }),
      }).addTo(layers);
      marker.on("dragend", () => {
        const ll = marker.getLatLng();
        callbacks.current.onPin?.(ll.lat, ll.lng);
      });
      if (!m.getBounds().contains(p) || m.getZoom() < 13) m.setView(p, 15);
      if (pin.accuracy) L.circle(p, { radius: pin.accuracy }).addTo(layers);
    }
    return () => {
      layers.remove();
    };
  }, [incidents, pin, zoom]);
  return (
    <div>
      <div
        ref={container}
        className="flood-map"
        aria-label={
          onPin
            ? "Select or move the incident location pin"
            : "Reported flood points, not validated flood extent"
        }
      />
      {tileError && (
        <p role="status">
          Map tiles unavailable. Use the address fields and incident list.
        </p>
      )}
    </div>
  );
}
