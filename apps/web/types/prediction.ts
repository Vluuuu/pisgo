export type MaturityClass =
  | "unripe"
  | "half_ripe"
  | "ripe"
  | "overripe";

export type MaturityClassValues = {
  unripe: number;
  half_ripe: number;
  ripe: number;
  overripe: number;
};

export type PredictionRequest = {
  floweringDate: string;
  photoDate: string;
  targetMaturity: number;
  image: File | Blob;
};

export type PredictionDebugInfo = {
  predicted_class: MaturityClass | null;
  class_probabilities: MaturityClassValues | null;
  maturity_class_scale: MaturityClassValues | null;
  detector_model_version: string;
  detection_score: number | null;
  detection_count: number;
  detection_threshold: number;
  detection_method: "yolo11n-class-0";
  detector_inference_milliseconds: number | null;
  inference_milliseconds: number | null;
};

export type CommonPredictionFields = {
  cultivar: "cavendish";
  days_after_flowering: number;
  model_version: string;
  adapter_version: string;
  debug: PredictionDebugInfo;
};

export type DetectedPredictionResponse = CommonPredictionFields & {
  banana_detected: true;
  current_maturity: number;
  confidence: number;
  days_to_target: number | null;
};

export type NoBananaPredictionResponse = CommonPredictionFields & {
  banana_detected: false;
  current_maturity: null;
  confidence: null;
  days_to_target: null;
};

export type PredictionResponse = DetectedPredictionResponse | NoBananaPredictionResponse;

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
