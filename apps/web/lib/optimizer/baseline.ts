import { addCalendarDays } from "../dates.ts";
import type { OptimizerInput, OptimizerResult } from "@/types/prediction";

const SECONDS_PER_DAY = 86_400;
const BASELINE_RIPENING_PER_DAY = 0.38;
const TARGET_TOLERANCE = 0.35;

const round = (value: number) => Number(value.toFixed(1));

/** Baseline schedule heuristic. Replace after validating the maturity forecast model. */
export function optimizeSchedule(input: OptimizerInput): OptimizerResult {
  if (input.travelDurationSeconds <= 0) throw new Error("Travel duration must be positive.");
  if (input.targetMaturity < 1 || input.targetMaturity > 7) throw new Error("Target maturity must be between 1 and 7.");

  const transitDays = input.travelDurationSeconds / SECONDS_PER_DAY;
  const delayUntilShipping = Math.max(0, Math.floor((input.daysToTarget ?? 0) - transitDays));
  const delayUntilHarvest = Math.max(0, delayUntilShipping - 1);
  const ripeningRate = input.daysToTarget && input.targetMaturity > input.currentMaturity
    ? (input.targetMaturity - input.currentMaturity) / input.daysToTarget
    : BASELINE_RIPENING_PER_DAY;
  const expectedArrivalMaturity = round(Math.min(7, input.currentMaturity + ripeningRate * (delayUntilShipping + transitDays)));
  const difference = expectedArrivalMaturity - input.targetMaturity;

  return {
    recommendedHarvestDate: addCalendarDays(input.photoDate, delayUntilHarvest),
    recommendedShippingDate: addCalendarDays(input.photoDate, delayUntilShipping),
    expectedArrivalDate: addCalendarDays(input.photoDate, delayUntilShipping + Math.ceil(transitDays)),
    expectedArrivalMaturity,
    status: Math.abs(difference) <= TARGET_TOLERANCE ? "on_target" : difference < 0 ? "under_target" : "over_target",
  };
}
