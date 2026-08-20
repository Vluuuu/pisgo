export type FoursquareLocation = {
  address?: string;
  locality?: string;
  region?: string;
  postcode?: string;
  country?: string;
  formatted_address?: string;
};

export type FoursquarePlace = {
  fsq_place_id?: string;
  name?: string;
  latitude?: number;
  longitude?: number;
  distance?: number;
  location?: FoursquareLocation;
};

export type FoursquareSearchResponse = {
  results?: FoursquarePlace[];
};
