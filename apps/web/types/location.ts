export type Coordinates = {
  lat: number;
  lon: number;
};

export type LocationFlowLinkage = {
  operation?: string;
  pathParameters?: Array<{
    parameter?: string;
    argument?: string;
  }>;
  queryParameters?: Record<string, string | number | boolean | string[] | undefined>;
  requestBody?: unknown;
};

export type LocationSuggestion = Coordinates & {
  id: string;
  label: string;
  city?: string;
  state?: string;
  country?: string;
  provider?: "tomtom" | "foursquare" | "geoapify" | "manual";
};

export type RoutingVehicleMode =
  | "motorcycle"
  | "light_truck"
  | "medium_truck"
  | "truck"
  | "heavy_truck";

export type VehicleModeOption = {
  mode: RoutingVehicleMode;
  label: string;
  description: string;
};

export const ROUTING_VEHICLE_MODES: VehicleModeOption[] = [
  { mode: "motorcycle", label: "Motor", description: "Pengiriman ringan" },
  { mode: "light_truck", label: "Pickup / Van", description: "< 3.5 t" },
  { mode: "medium_truck", label: "Truk Sedang", description: "< 7.5 t" },
  { mode: "truck", label: "Truk Besar", description: "< 22 t" },
  { mode: "heavy_truck", label: "Truk Berat", description: "< 40 t" },
];

export const DEFAULT_ROUTING_VEHICLE_MODE: RoutingVehicleMode = "light_truck";

export type RouteData = {
  distanceMeters: number;
  durationSeconds: number;
  path: [number, number][];
};
