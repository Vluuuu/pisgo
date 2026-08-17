export type Coordinates = {
  lat: number;
  lon: number;
};

export type LocationSuggestion = Coordinates & {
  id: string;
  label: string;
  city?: string;
  state?: string;
  country?: string;
};

export type RouteData = {
  distanceMeters: number;
  durationSeconds: number;
  path: [number, number][];
};
