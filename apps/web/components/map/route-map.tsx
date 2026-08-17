"use client";

import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { useEffect } from "react";
import type { LocationSuggestion, RouteData } from "@/types/location";

const GEOAPIFY_ATTRIBUTION = 'Powered by <a href="https://www.geoapify.com/">Geoapify</a> | © OpenStreetMap contributors';
const INDONESIA_CENTER: [number, number] = [-2.5, 118];

type RouteMapProps = {
  origin: LocationSuggestion | null;
  destination: LocationSuggestion | null;
  route: RouteData | null;
};

function FitSelection({ origin, destination, route }: RouteMapProps) {
  const map = useMap();

  useEffect(() => {
    if (route?.path.length) {
      map.fitBounds(route.path, { padding: [42, 42], maxZoom: 12 });
    } else if (origin && destination) {
      map.fitBounds([[origin.lat, origin.lon], [destination.lat, destination.lon]], { padding: [52, 52], maxZoom: 11 });
    } else if (origin || destination) {
      const point = origin ?? destination;
      if (point) map.setView([point.lat, point.lon], 10);
    }
  }, [destination, map, origin, route]);

  return null;
}

export function RouteMap({ origin, destination, route }: RouteMapProps) {
  const label = origin && destination
    ? `Route map from ${origin.label} to ${destination.label}`
    : "Route planning map";

  return (
    <div className="map-shell">
      <MapContainer center={INDONESIA_CENTER} zoom={5} scrollWheelZoom={false} className="route-map" aria-label={label}>
        <TileLayer url="/api/geoapify/tiles/{z}/{x}/{y}" maxZoom={20} attribution={GEOAPIFY_ATTRIBUTION} />
        {route && <Polyline positions={route.path} pathOptions={{ color: "#285b3a", weight: 5, opacity: 0.92, lineCap: "round", lineJoin: "round", className: "route-line" }} />}
        {origin && (
          <CircleMarker center={[origin.lat, origin.lon]} radius={8} pathOptions={{ color: "#fbfaf6", weight: 3, fillColor: "#285b3a", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}>Origin: {origin.label}</Tooltip>
          </CircleMarker>
        )}
        {destination && (
          <CircleMarker center={[destination.lat, destination.lon]} radius={8} pathOptions={{ color: "#fbfaf6", weight: 3, fillColor: "#172019", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}>Destination: {destination.label}</Tooltip>
          </CircleMarker>
        )}
        <FitSelection origin={origin} destination={destination} route={route} />
      </MapContainer>
      {!route && (
        <p className="map-instruction">
          {origin || destination ? "Select both endpoints to calculate the route." : "Search for an origin and destination to begin route planning."}
        </p>
      )}
    </div>
  );
}
