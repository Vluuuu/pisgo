export type PredictionRequest = {
  floweringDate: string;
  photoDate: string;
  targetMaturity: number;
  image: File;
};

export type PredictionResponse = {
  banana_detected: boolean;
  cultivar: "cavendish";
  days_after_flowering: number;
  current_maturity: number;
  confidence: number;
  days_to_target: number | null;
  model_version: string;
};

export type OptimizerInput = {
  photoDate: string;
  targetMaturity: number;
  currentMaturity: number;
  daysToTarget: number | null;
  travelDurationSeconds: number;
};

export type OptimizerResult = {
  recommendedHarvestDate: string;
  recommendedShippingDate: string;
  expectedArrivalDate: string;
  expectedArrivalMaturity: number;
  status: "on_target" | "under_target" | "over_target";
};
