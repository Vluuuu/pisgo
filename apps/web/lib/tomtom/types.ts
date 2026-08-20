export type TomTomPosition = {
  type: "Point";
  coordinates: number[];
};

export type TomTomAddress = {
  street?: string;
  houseNumber?: string;
  municipality?: string;
  municipalitySubdivision?: string;
  countrySubdivision?: string;
  countrySecondarySubdivision?: string;
  countryTertiarySubdivision?: string;
  municipalitySecondarySubdivision?: string;
  neighborhood?: string;
  country?: string;
  countryCodeIso2?: string;
  postalCode?: string;
};

export type TomTomPoiType = {
  id?: string;
  name?: string;
  groupId?: string;
  role?: string;
};

export type TomTomFlowLinkage = {
  operation?: string;
  pathParameters?: Array<{
    parameter?: string;
    argument?: string;
  }>;
  queryParameters?: Record<string, string | number | boolean | string[] | undefined>;
  requestBody?: unknown;
};

export type TomTomSuggestItem = {
  id?: string;
  type?: string;
  title?: string;
  subtitles?: string[];
  address?: TomTomAddress;
  poiTypes?: TomTomPoiType[];
  poiBrands?: TomTomPoiType[];
  more?: TomTomFlowLinkage;
};

export type TomTomSuggestResponse = {
  results?: TomTomSuggestItem[];
};

export type TomTomDiscoverItem = {
  id?: string;
  type?: string;
  title?: string;
  subtitles?: string[];
  position?: TomTomPosition;
  address?: TomTomAddress;
  poiTypes?: TomTomPoiType[];
  poiBrands?: TomTomPoiType[];
  distanceInMeters?: number;
};

export type TomTomDiscoverResponse = {
  results?: TomTomDiscoverItem[];
};

export type TomTomGeocodeItem = {
  id?: string;
  type?: string;
  areaType?: string;
  title?: string;
  subtitles?: string[];
  position?: TomTomPosition;
  address?: TomTomAddress;
};

export type TomTomGeocodeResponse = {
  results?: TomTomGeocodeItem[];
};

export type LocationSearchSuggestion =
  | {
      status: "resolved";
      location: import("@/types/location").LocationSuggestion;
    }
  | {
      status: "pending";
      id: string;
      label: string;
      subtitles?: string;
      more: TomTomFlowLinkage;
    };
