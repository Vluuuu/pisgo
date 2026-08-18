"use client";

import dynamic from "next/dynamic";
import type { LocationSuggestion, RouteData } from "@/types/location";

const RouteMap = dynamic(() => import("./route-map").then((module) => module.RouteMap), {
  ssr: false,
  loading: () => <div className="map-loading" aria-label="Memuat peta"><span>Memuat peta</span></div>,
});

export function RouteMapLoader(props: {
  origin: LocationSuggestion | null;
  destination: LocationSuggestion | null;
  route: RouteData | null;
}) {
  return <RouteMap {...props} />;
}
