import { daysBetween } from "@/lib/dates";
import type { PredictionResponse } from "@/types/prediction";

type MockPredictionInput = {
  floweringDate: string;
  photoDate: string;
  targetMaturity: number;
};

const round = (value: number, decimals = 1) => Number(value.toFixed(decimals));

/** Development-only baseline. This does not inspect image pixels or represent an ML prediction. */
export async function predictWithMock(input: MockPredictionInput): Promise<PredictionResponse> {
  const daysAfterFlowering = daysBetween(input.floweringDate, input.photoDate);
  if (daysAfterFlowering < 0) throw new Error("Flowering date cannot be after the photo date.");

  const currentMaturity = round(Math.min(7, Math.max(1, 1.2 + (daysAfterFlowering - 55) * 0.06)));
  const daysToTarget = input.targetMaturity <= currentMaturity
    ? 0
    : round((input.targetMaturity - currentMaturity) / 0.38);

  return {
    banana_detected: true,
    cultivar: "cavendish",
    days_after_flowering: daysAfterFlowering,
    current_maturity: currentMaturity,
    confidence: 0.91,
    days_to_target: daysToTarget,
    model_version: "mock-v1",
  };
}
