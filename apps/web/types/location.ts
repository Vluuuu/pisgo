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
  provider?: "tomtom" | "foursquare" | "geoapify";
};

export type RouteData = {
  distanceMeters: number;
  durationSeconds: number;
  path: [number, number][];
};
