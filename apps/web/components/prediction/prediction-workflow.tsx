"use client";

import { CalendarBlankIcon, SpinnerGapIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { LocationAutocomplete } from "@/components/locations/location-autocomplete";
import { ImageUpload } from "./image-upload";
import { ResultView } from "./result-view";
import { daysBetween, todayIso } from "@/lib/dates";
import { optimizeSchedule } from "@/lib/optimizer/baseline";
import type { LocationSuggestion, RouteData } from "@/types/location";
import type { OptimizerResult, PredictionResponse } from "@/types/prediction";

type WorkflowResult = {
  prediction: PredictionResponse;
  route: RouteData;
  schedule: OptimizerResult;
  origin: LocationSuggestion;
  destination: LocationSuggestion;
  targetMaturity: number;
};

type FormErrors = Partial<Record<"floweringDate" | "photoDate" | "image" | "targetMaturity" | "origin" | "destination", string>>;

const maturityLabels: Record<number, string> = {
  1: "Full green",
  2: "Mature green",
  3: "Turning",
  4: "More green than yellow",
  5: "Yellow",
  6: "Yellow with flecks",
  7: "Overripe",
};

export function PredictionWorkflow() {
  const today = todayIso();
  const [floweringDate, setFloweringDate] = useState("");
  const [photoDate, setPhotoDate] = useState(today);
  const [image, setImage] = useState<File | null>(null);
  const [targetMaturity, setTargetMaturity] = useState(4);
  const [origin, setOrigin] = useState<LocationSuggestion | null>(null);
  const [destination, setDestination] = useState<LocationSuggestion | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "routing" | "predicting">("idle");
  const [result, setResult] = useState<WorkflowResult | null>(null);

  const daf = floweringDate && photoDate ? daysBetweenSafe(floweringDate, photoDate) : null;
  const busy = phase !== "idle";

  function validate(): FormErrors {
    const next: FormErrors = {};
    if (!floweringDate) next.floweringDate = "Flowering date is required.";
    if (!photoDate) next.photoDate = "Photo date is required.";
    if (floweringDate && photoDate && daysBetweenSafe(floweringDate, photoDate) < 0) next.floweringDate = "Flowering must be before the photo date.";
    if (photoDate > today) next.photoDate = "Photo date cannot be in the future.";
    if (!image) next.image = "Upload a banana photo to continue.";
    else if (image.size > 10 * 1024 * 1024) next.image = "Photo size must not exceed 10 MB.";
    else if (!image.type.startsWith("image/")) next.image = "The file must be an image.";
    if (targetMaturity < 1 || targetMaturity > 7) next.targetMaturity = "Choose a target maturity from 1 to 7.";
    if (!origin) next.origin = "Select an origin from the search results.";
    if (!destination) next.destination = "Select a destination from the search results.";
    if (origin && destination && origin.lat === destination.lat && origin.lon === destination.lon) next.destination = "Destination must differ from origin.";
    return next;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validate();
    setErrors(nextErrors);
    setError(null);
    setResult(null);
    if (Object.keys(nextErrors).length || !image || !origin || !destination) return;

    try {
      setPhase("routing");
      const routeResponse = await fetch("/api/geoapify/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin: { lat: origin.lat, lon: origin.lon }, destination: { lat: destination.lat, lon: destination.lon } }),
      });
      const routeData = (await routeResponse.json()) as RouteData & { error?: string };
      if (!routeResponse.ok) throw new Error(routeData.error ?? "Route could not be calculated.");

      setPhase("predicting");
      const form = new FormData();
      form.set("flowering_date", floweringDate);
      form.set("photo_date", photoDate);
      form.set("target_maturity", String(targetMaturity));
      form.set("image", image);
      const predictionResponse = await fetch("/api/predict", { method: "POST", body: form });
      const prediction = (await predictionResponse.json()) as PredictionResponse & { error?: string };
      if (!predictionResponse.ok) throw new Error(prediction.error ?? "Prediction could not be created.");
      if (!prediction.banana_detected) throw new Error("No banana was detected in the photo. Use another photo.");

      const schedule = optimizeSchedule({
        photoDate,
        targetMaturity,
        currentMaturity: prediction.current_maturity,
        daysToTarget: prediction.days_to_target,
        travelDurationSeconds: routeData.durationSeconds,
      });
      setResult({ prediction, route: routeData, schedule, origin, destination, targetMaturity });
      requestAnimationFrame(() => document.getElementById("recommendation")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Analysis failed. Try again.");
    } finally {
      setPhase("idle");
    }
  }

  function changeOrigin(location: LocationSuggestion | null) {
    setOrigin(location);
    setResult(null);
    setErrors((current) => ({ ...current, origin: undefined }));
  }

  function changeDestination(location: LocationSuggestion | null) {
    setDestination(location);
    setResult(null);
    setErrors((current) => ({ ...current, destination: undefined }));
  }

  return (
    <section className="workspace" aria-label="Harvest and shipping analysis workspace">
      <form noValidate onSubmit={handleSubmit} className="control-rail" id="controls">
        <header className="rail-header">
          <h1>New harvest plan</h1>
          <p>Set the fruit, maturity target, and delivery route.</p>
        </header>

        <fieldset className="control-group fruit-controls">
          <legend>Fruit</legend>
          <DateField
            id="flowering-date"
            label="Flowering date"
            value={floweringDate}
            max={photoDate || today}
            onChange={(value) => { setFloweringDate(value); setResult(null); setErrors((current) => ({ ...current, floweringDate: undefined })); }}
            error={errors.floweringDate}
          />

          {daf !== null && daf >= 0 && (
            <p className="daf-inline" aria-live="polite">
              <span>DAF</span><strong>{daf} days</strong><small>after flowering</small>
            </p>
          )}

          <ImageUpload value={image} onChange={(file) => { setImage(file); setResult(null); setErrors((current) => ({ ...current, image: undefined })); }} error={errors.image} />

          <DateField
            id="photo-date"
            label="Photo date"
            value={photoDate}
            max={today}
            secondary
            onChange={(value) => { setPhotoDate(value); setResult(null); setErrors((current) => ({ ...current, photoDate: undefined })); }}
            error={errors.photoDate}
          />
        </fieldset>

        <fieldset className="control-group maturity-group">
          <legend className="sr-only">Target maturity</legend>
          <div className="maturity-heading">
            <label htmlFor="target-maturity">Target maturity</label>
            <output htmlFor="target-maturity">{targetMaturity}<small>/7</small></output>
          </div>
          <div className="maturity-extremes" aria-hidden="true"><span>More green</span><span>More yellow</span></div>
          <input
            id="target-maturity"
            type="range"
            min="1"
            max="7"
            step="1"
            value={targetMaturity}
            onChange={(event) => { setTargetMaturity(Number(event.target.value)); setResult(null); }}
            className="maturity-range"
            aria-valuetext={`${targetMaturity}, ${maturityLabels[targetMaturity]}`}
          />
          {errors.targetMaturity && <p role="alert" className="field-error">{errors.targetMaturity}</p>}
        </fieldset>

        <fieldset className="control-group route-controls">
          <legend>Route</legend>
          <div className="route-stack">
            <div className="route-field"><LocationAutocomplete label="Origin" value={origin} onChange={changeOrigin} placeholder="Farm, packhouse, or city" />{errors.origin && <p role="alert" className="field-error">{errors.origin}</p>}</div>
            <div className="route-line-input" aria-hidden="true" />
            <div className="route-field"><LocationAutocomplete label="Destination" value={destination} onChange={changeDestination} placeholder="Market, port, or city" />{errors.destination && <p role="alert" className="field-error">{errors.destination}</p>}</div>
          </div>
          <p className="transport-mode">Light truck <span aria-hidden="true">·</span> Free-flow routing</p>
        </fieldset>

        {error && <div role="alert" className="analysis-error">{error}</div>}

        <div className="analysis-command">
          <p className={busy ? "analysis-status" : "sr-only"} aria-live="polite">{phase === "routing" ? "Calculating light-truck route…" : phase === "predicting" ? "Estimating maturity…" : ""}</p>
          <button type="submit" disabled={busy} className="analyze-button">
            {busy ? <><SpinnerGapIcon className="spin" aria-hidden="true" size={19} />{phase === "routing" ? "Calculating route" : "Analyzing fruit"}</> : "Analyze harvest plan"}
          </button>
        </div>
      </form>

      {result && <ResultView {...result} />}
    </section>
  );
}

function DateField({ id, label, value, max, onChange, error, secondary = false }: { id: string; label: string; value: string; max: string; onChange: (value: string) => void; error?: string; secondary?: boolean }) {
  return (
    <div className="date-field" data-secondary={secondary}>
      <label htmlFor={id}>{label}</label>
      <div className="date-input-wrap"><CalendarBlankIcon aria-hidden="true" size={18} /><input id={id} type="date" value={value} max={max} onChange={(event) => onChange(event.target.value)} className="field" data-error={Boolean(error)} /></div>
      {error && <p role="alert" className="field-error">{error}</p>}
    </div>
  );
}

function daysBetweenSafe(start: string, end: string): number {
  try { return daysBetween(start, end); } catch { return -1; }
}
