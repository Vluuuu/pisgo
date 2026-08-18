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
  1: "Hijau matang",
  2: "Matang hijau",
  3: "Kuning hijau",
  4: "Lebih hijau",
  5: "Kuning",
  6: "Kuning bintik",
  7: "Terlalu matang",
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
    if (!floweringDate) next.floweringDate = "Tanggal berbunga wajib diisi.";
    if (!photoDate) next.photoDate = "Tanggal foto wajib diisi.";
    if (floweringDate && photoDate && daysBetweenSafe(floweringDate, photoDate) < 0) next.floweringDate = "Tanggal berbunga harus sebelum tanggal foto.";
    if (photoDate > today) next.photoDate = "Tanggal foto tidak boleh di masa depan.";
    if (!image) next.image = "Unggah foto pisang untuk melanjutkan.";
    else if (image.size > 10 * 1024 * 1024) next.image = "Ukuran foto tidak boleh lebih dari 10 MB.";
    else if (!image.type.startsWith("image/")) next.image = "File harus berupa gambar.";
    if (targetMaturity < 1 || targetMaturity > 7) next.targetMaturity = "Pilih target kematangan dari 1 sampai 7.";
    if (!origin) next.origin = "Pilih lokasi asal dari hasil pencarian.";
    if (!destination) next.destination = "Pilih lokasi tujuan dari hasil pencarian.";
    if (origin && destination && origin.lat === destination.lat && origin.lon === destination.lon) next.destination = "Tujuan harus berbeda dari asal.";
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
      if (!routeResponse.ok) throw new Error(routeData.error ?? "Rute tidak dapat dihitung.");

      setPhase("predicting");
      const form = new FormData();
      form.set("flowering_date", floweringDate);
      form.set("photo_date", photoDate);
      form.set("target_maturity", String(targetMaturity));
      form.set("image", image);
      const predictionResponse = await fetch("/api/predict", { method: "POST", body: form });
      const prediction = (await predictionResponse.json()) as PredictionResponse & { error?: string };
      if (!predictionResponse.ok) throw new Error(prediction.error ?? "Prediksi tidak dapat dibuat.");
      if (!prediction.banana_detected) throw new Error("Pisang tidak terdeteksi di foto. Gunakan foto lain.");

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
      setError(caught instanceof Error ? caught.message : "Analisis gagal. Coba lagi.");
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
    <section className="workspace" aria-label="Workspace analisis panen dan pengiriman">
      <form noValidate onSubmit={handleSubmit} className="control-rail" id="controls">
        <header className="rail-header">
          <h1>Rencana panen baru</h1>
          <p>Tentukan data buah, target kematangan, dan rute pengiriman.</p>
        </header>

        <fieldset className="control-group fruit-controls">
          <legend>Data buah</legend>
          <DateField
            id="flowering-date"
            label="Tanggal berbunga"
            value={floweringDate}
            max={photoDate || today}
            onChange={(value) => { setFloweringDate(value); setResult(null); setErrors((current) => ({ ...current, floweringDate: undefined })); }}
            error={errors.floweringDate}
          />

          {daf !== null && daf >= 0 && (
            <p className="daf-inline" aria-live="polite">
              <span>Usia buah</span><strong>{daf}</strong><small>hari setelah berbunga</small>
            </p>
          )}

          <ImageUpload value={image} onChange={(file) => { setImage(file); setResult(null); setErrors((current) => ({ ...current, image: undefined })); }} error={errors.image} />

          <DateField
            id="photo-date"
            label="Tanggal foto"
            value={photoDate}
            max={today}
            secondary
            onChange={(value) => { setPhotoDate(value); setResult(null); setErrors((current) => ({ ...current, photoDate: undefined })); }}
            error={errors.photoDate}
          />
        </fieldset>

        <fieldset className="control-group maturity-group">
          <legend className="sr-only">Target kematangan</legend>
          <div className="maturity-heading">
            <label htmlFor="target-maturity">Target kematangan</label>
            <output htmlFor="target-maturity">{targetMaturity}<small>/7</small></output>
          </div>
          <div className="maturity-extremes" aria-hidden="true"><span>Lebih hijau</span><span>Lebih kuning</span></div>
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
          <legend>Rute</legend>
          <div className="route-stack">
            <div className="route-field"><LocationAutocomplete label="Asal" value={origin} onChange={changeOrigin} placeholder="Kebun, rumah kemas, atau kota" />{errors.origin && <p role="alert" className="field-error">{errors.origin}</p>}</div>
            <div className="route-line-input" aria-hidden="true" />
            <div className="route-field"><LocationAutocomplete label="Tujuan" value={destination} onChange={changeDestination} placeholder="Pasar, pelabuhan, atau kota" />{errors.destination && <p role="alert" className="field-error">{errors.destination}</p>}</div>
          </div>
          <p className="transport-mode">Truk ringan <span aria-hidden="true">·</span> Estimasi tanpa kemacetan</p>
        </fieldset>

        {error && <div role="alert" className="analysis-error">{error}</div>}

        <div className="analysis-command">
          <p className={busy ? "analysis-status" : "sr-only"} aria-live="polite">{phase === "routing" ? "Menghitung rute…" : phase === "predicting" ? "Menganalisis buah…" : ""}</p>
          <button type="submit" disabled={busy} className="analyze-button">
            {busy ? <><SpinnerGapIcon className="spin" aria-hidden="true" size={19} />{phase === "routing" ? "Menghitung rute" : "Menganalisis buah"}</> : "Analisis rencana panen"}
          </button>
        </div>
      </form>

      {result && <ResultView {...result} />}
    </section>
  );
}

function DateField({ id, label, value, max, onChange, error, secondary = false }: { id: string; label: string; value: string; max: string; onChange: (value: string) => void; error?: string; secondary?: boolean }) {
  function handleInputClick(event: React.MouseEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    try {
      input.showPicker?.();
    } catch {
      // showPicker can throw (e.g. missing user activation); native click behavior remains.
    }
  }

  return (
    <div className="date-field" data-secondary={secondary}>
      <label htmlFor={id}>{label}</label>
      <div className="date-input-wrap">
        <CalendarBlankIcon aria-hidden="true" size={18} />
        <input id={id} type="date" value={value} max={max} onClick={handleInputClick} onChange={(event) => onChange(event.target.value)} className="field" data-error={Boolean(error)} />
      </div>
      {error && <p role="alert" className="field-error">{error}</p>}
    </div>
  );
}

function daysBetweenSafe(start: string, end: string): number {
  try { return daysBetween(start, end); } catch { return -1; }
}
