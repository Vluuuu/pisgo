import assert from "node:assert/strict";
import test from "node:test";
import { optimizeSchedule } from "./baseline.ts";

test("ships early enough for the target maturity", () => {
  const result = optimizeSchedule({
    photoDate: "2026-08-17",
    targetMaturity: 4,
    currentMaturity: 2.7,
    daysToTarget: 3.4,
    travelDurationSeconds: 86_400,
  });

  assert.equal(result.recommendedHarvestDate, "2026-08-18");
  assert.equal(result.recommendedShippingDate, "2026-08-19");
  assert.equal(result.expectedArrivalDate, "2026-08-20");
  assert.equal(result.status, "on_target");
});

test("ships immediately when travel already exceeds ripening time", () => {
  const result = optimizeSchedule({
    photoDate: "2026-08-17",
    targetMaturity: 3,
    currentMaturity: 2.7,
    daysToTarget: 0.8,
    travelDurationSeconds: 172_800,
  });

  assert.equal(result.recommendedShippingDate, "2026-08-17");
  assert.equal(result.expectedArrivalDate, "2026-08-19");
  assert.equal(result.status, "over_target");
});
