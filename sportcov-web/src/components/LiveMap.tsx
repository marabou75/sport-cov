
"use client";
import { useEffect, useRef } from "react";

type Props = {
  wsUrl: string;
  driverName: string;
  isDriver: boolean;
};

export default function LiveMap({ wsUrl, driverName, isDriver }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const markerRef = useRef<any>(null);
  const mapInstanceRef = useRef<any>(null);
  const watchRef = useRef<number | null>(null);

  useEffect(() => {
    if (!mapRef.current) return;
    let map: any;

    async function init() {
      const L = (await import("leaflet")).default;

      // Fix icônes Leaflet en Next.js
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      map = L.map(mapRef.current!).setView([47.4, 0.9], 12);
      mapInstanceRef.current = map;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap",
      }).addTo(map);

      const role = isDriver ? "driver" : "passenger";
      const ws = new WebSocket(`${wsUrl}?role=${role}`);
      wsRef.current = ws;

      if (isDriver) {
        ws.onopen = () => {
          watchRef.current = navigator.geolocation.watchPosition(
            (pos) => {
              const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
              ws.send(JSON.stringify(loc));
              if (!markerRef.current) {
                markerRef.current = L.marker([loc.lat, loc.lng])
                  .addTo(map)
                  .bindPopup("📍 Votre position")
                  .openPopup();
              } else {
                markerRef.current.setLatLng([loc.lat, loc.lng]);
              }
              map.setView([loc.lat, loc.lng], 15);
            },
            (err) => console.error("GPS:", err),
            { enableHighAccuracy: true, maximumAge: 5000 }
          );
        };
      } else {
        ws.onmessage = (e) => {
          const data = JSON.parse(e.data);
          if (data.ping) return;
          const L2 = (window as any).L || L;
          if (!markerRef.current) {
            markerRef.current = L2.marker([data.lat, data.lng], {
              icon: L2.divIcon({
                html: `<div style="background:#4ade80;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3)">🚗</div>`,
                iconSize: [32, 32], iconAnchor: [16, 16],
              })
            }).addTo(map).bindPopup(`🚗 ${driverName}`).openPopup();
          } else {
            markerRef.current.setLatLng([data.lat, data.lng]);
          }
          map.setView([data.lat, data.lng], 15);
        };
      }
    }

    init();
    return () => {
      if (watchRef.current !== null) navigator.geolocation.clearWatch(watchRef.current);
      wsRef.current?.close();
      mapInstanceRef.current?.remove();
    };
  }, [wsUrl, isDriver, driverName]);

  return <div ref={mapRef} className="w-full h-64 rounded-xl overflow-hidden border border-gray-200" />;
}
