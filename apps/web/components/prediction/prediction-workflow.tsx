"use client";

import { CalendarBlankIcon, CameraIcon, ShieldCheckIcon, SpinnerGapIcon, TruckIcon } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { LocationAutocomplete } from "@/components/locations/location-autocomplete";
import { ManualLocationPickerLoader } from "@/components/map/manual-location-picker-loader";
import { VehicleModeIcon } from "@/components/vehicles/vehicle-mode-icon";
import { ImageUpload } from "./image-upload";
import { ResultView } from "./result-view";
import { MATURITY_SPECTRUM, MaturityInstrumentControl, MaturityInstrumentDisplay } from "./maturity-instrument";
import { daysBetween, todayIso } from "@/lib/dates";
import { optimizeSchedule } from "@/lib/optimizer/baseline";
import {
  DEFAULT_ROUTING_VEHICLE_MODE,
  ROUTING_VEHICLE_MODES,
} from "@/types/location";
import type {
  LocationSuggestion,
  RouteData,
  RoutingVehicleMode,
} from "@/types/location";
import type {
  DetectedPredictionResponse,
  OptimizerResult,
  PredictionResponse,
} from "@/types/prediction";

type WorkflowResult = {
  prediction: DetectedPredictionResponse;
  route: RouteData;
  schedule: OptimizerResult;
  origin: LocationSuggestion;
  destination: LocationSuggestion;
  targetMaturity: number;
  vehicleMode: RoutingVehicleMode;
};

type FormErrors = Partial<Record<"floweringDate" | "photoDate" | "image" | "targetMaturity" | "origin" | "destination", string>>;

export const maturityLabels: Record<number, string> = Object.fromEntries(
  MATURITY_SPECTRUM.map((item) => [item.level, item.label])
);

export function PredictionWorkflow() {
  const today = todayIso();
  const [floweringDate, setFloweringDate] = useState("");
  const [photoDate, setPhotoDate] = useState(today);
  const [image, setImage] = useState<File | null>(null);
  const [targetMaturity, setTargetMaturity] = useState(4);
  const [origin, setOrigin] = useState<LocationSuggestion | null>(null);
  const [destination, setDestination] = useState<LocationSuggestion | null>(null);
  const [vehicleMode, setVehicleMode] = useState<RoutingVehicleMode>(DEFAULT_ROUTING_VEHICLE_MODE);
  const [pickerTarget, setPickerTarget] = useState<"origin" | "destination" | null>(null);
  const [pickerQuery, setPickerQuery] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "routing" | "predicting">("idle");
  const [result, setResult] = useState<WorkflowResult | null>(null);

  const requestGenerationRef = useRef(0);
  const lastPredictionRef = useRef<{
    prediction: DetectedPredictionResponse;
    origin: LocationSuggestion;
    destination: LocationSuggestion;
    photoDate: string;
    targetMaturity: number;
  } | null>(null);

  const daf = floweringDate && photoDate ? daysBetweenSafe(floweringDate, photoDate) : null;
  const busy = phase !== "idle";
  const selectedMaturityInfo = MATURITY_SPECTRUM.find((m) => m.level === targetMaturity) ?? MATURITY_SPECTRUM[3];

  function invalidateInFlight() {
    requestGenerationRef.current++;
    setPhase("idle");
    setResult(null);
    lastPredictionRef.current = null;
  }

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
    lastPredictionRef.current = null;
    if (Object.keys(nextErrors).length || !image || !origin || !destination) return;

    const requestGeneration = ++requestGenerationRef.current;

    try {
      setPhase("routing");
      const currentOrigin = origin;
      const currentDestination = destination;
      const currentVehicleMode = vehicleMode;
      const currentTargetMaturity = targetMaturity;
      const currentPhotoDate = photoDate;

      const routeResponse = await fetch("/api/geoapify/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: { lat: currentOrigin.lat, lon: currentOrigin.lon },
          destination: { lat: currentDestination.lat, lon: currentDestination.lon },
          vehicleMode: currentVehicleMode,
        }),
      });
      const routeData = (await routeResponse.json()) as RouteData & { error?: string };
      if (!routeResponse.ok) throw new Error(routeData.error ?? "Rute tidak dapat dihitung.");
      if (requestGeneration !== requestGenerationRef.current) return;

      setPhase("predicting");
      const form = new FormData();
      form.set("flowering_date", floweringDate);
      form.set("photo_date", currentPhotoDate);
      form.set("target_maturity", String(currentTargetMaturity));
      form.set("image", image);
      const predictionResponse = await fetch("/api/predict", { method: "POST", body: form });
      const prediction = (await predictionResponse.json()) as PredictionResponse & { error?: string };
      if (!predictionResponse.ok) throw new Error(prediction.error ?? "Prediksi tidak dapat dibuat.");
      if (!prediction.banana_detected) throw new Error("Pisang tidak terdeteksi di foto. Gunakan foto lain.");
      if (requestGeneration !== requestGenerationRef.current) return;

      const schedule = optimizeSchedule({
        photoDate: currentPhotoDate,
        targetMaturity: currentTargetMaturity,
        currentMaturity: prediction.current_maturity,
        daysToTarget: prediction.days_to_target,
        travelDurationSeconds: routeData.durationSeconds,
      });

      lastPredictionRef.current = {
        prediction,
        origin: currentOrigin,
        destination: currentDestination,
        photoDate: currentPhotoDate,
        targetMaturity: currentTargetMaturity,
      };

      setResult({
        prediction,
        route: routeData,
        schedule,
        origin: currentOrigin,
        destination: currentDestination,
        targetMaturity: currentTargetMaturity,
        vehicleMode: currentVehicleMode,
      });
      requestAnimationFrame(() => document.getElementById("recommendation")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (caught) {
      if (requestGeneration === requestGenerationRef.current) {
        setError(caught instanceof Error ? caught.message : "Analisis gagal. Coba lagi.");
      }
    } finally {
      if (requestGeneration === requestGenerationRef.current) {
        setPhase("idle");
      }
    }
  }

  function changeOrigin(location: LocationSuggestion | null) {
    invalidateInFlight();
    setOrigin(location);
    setErrors((current) => ({ ...current, origin: undefined }));
  }

  function changeDestination(location: LocationSuggestion | null) {
    invalidateInFlight();
    setDestination(location);
    setErrors((current) => ({ ...current, destination: undefined }));
  }

  async function changeVehicleMode(mode: RoutingVehicleMode) {
    const requestGeneration = ++requestGenerationRef.current;
    setVehicleMode(mode);

    const prev = lastPredictionRef.current;
    // Rule A: Before first analysis or if locations missing: changing vehicle only changes vehicle state.
    if (!prev || !origin || !destination) {
      setResult(null);
      setPhase("idle");
      return;
    }

    // Rule B: After a successful analysis exists: trigger fresh recalculation with new vehicle mode
    const currentOrigin = origin;
    const currentDestination = destination;

    setResult(null);
    setError(null);
    setPhase("routing");

    try {
      const routeResponse = await fetch("/api/geoapify/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: { lat: currentOrigin.lat, lon: currentOrigin.lon },
          destination: { lat: currentDestination.lat, lon: currentDestination.lon },
          vehicleMode: mode,
        }),
      });
      const routeData = (await routeResponse.json()) as RouteData & { error?: string };
      if (!routeResponse.ok) throw new Error(routeData.error ?? "Rute tidak dapat dihitung.");
      if (requestGeneration !== requestGenerationRef.current) return;

      const schedule = optimizeSchedule({
        photoDate: prev.photoDate,
        targetMaturity: prev.targetMaturity,
        currentMaturity: prev.prediction.current_maturity,
        daysToTarget: prev.prediction.days_to_target,
        travelDurationSeconds: routeData.durationSeconds,
      });

      setResult({
        prediction: prev.prediction,
        route: routeData,
        schedule,
        origin: currentOrigin,
        destination: currentDestination,
        targetMaturity: prev.targetMaturity,
        vehicleMode: mode,
      });
    } catch (caught) {
      if (requestGeneration === requestGenerationRef.current) {
        setError(caught instanceof Error ? caught.message : "Analisis rute gagal. Coba lagi.");
      }
    } finally {
      if (requestGeneration === requestGenerationRef.current) {
        setPhase("idle");
      }
    }
  }

  function openOriginPicker(query: string) {
    setPickerTarget("origin");
    setPickerQuery(query);
  }

  function openDestinationPicker(query: string) {
    setPickerTarget("destination");
    setPickerQuery(query);
  }

  function handleManualLocationConfirm(location: LocationSuggestion) {
    if (pickerTarget === "origin") {
      changeOrigin(location);
    } else if (pickerTarget === "destination") {
      changeDestination(location);
    }
  }

  return (
    <section className="workspace" aria-label="Workspace analisis panen dan pengiriman">
      <form noValidate onSubmit={handleSubmit} className="control-rail" id="controls">
        <header className="rail-header">
          <div className="rail-header-eyebrow">
            <span className="eyebrow-badge">Alur Kerja Keputusan</span>
            <span className="eyebrow-rule" />
          </div>
          <h1>Rencana Panen Baru</h1>
          <p>Tentukan parameter buah, target kematangan saat tiba di tujuan, dan rute pengiriman.</p>
        </header>

        <fieldset className="control-group fruit-controls">
          <legend><span className="section-number" aria-hidden="true">01</span>Data buah</legend>
          <DateField
            id="flowering-date"
            label="Tanggal berbunga"
            value={floweringDate}
            max={photoDate || today}
            onChange={(value) => { setFloweringDate(value); setResult(null); setErrors((current) => ({ ...current, floweringDate: undefined })); }}
            error={errors.floweringDate}
          />

          {daf !== null && daf >= 0 && (
            <div className="daf-inline" aria-live="polite">
              <span className="daf-label">Usia buah terhitung:</span>
              <strong className="daf-value">{daf}</strong>
              <small className="daf-unit">hari setelah berbunga</small>
            </div>
          )}
        </fieldset>

        <fieldset className="control-group specimen-controls">
          <legend><span className="section-number" aria-hidden="true">02</span>Foto pisang</legend>
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
          <legend><span className="section-number" aria-hidden="true">03</span>Target</legend>

          <MaturityInstrumentControl
            id="target-maturity"
            value={targetMaturity}
            onChange={(val) => {
              setTargetMaturity(val);
              setResult(null);
            }}
          />

          {errors.targetMaturity && <p role="alert" className="field-error">{errors.targetMaturity}</p>}
        </fieldset>

        <fieldset className="control-group route-controls">
          <legend><span className="section-number" aria-hidden="true">04</span>Perjalanan</legend>
          <div className="route-stack">
            <div className="route-field">
              <LocationAutocomplete
                label="Asal"
                value={origin}
                onChange={changeOrigin}
                placeholder="Kebun, rumah kemas, atau kota asal"
                onOpenMapPicker={openOriginPicker}
              />
              {errors.origin && <p role="alert" className="field-error">{errors.origin}</p>}
            </div>
            <div className="route-connector-line" aria-hidden="true">
              <span className="connector-dot origin" />
              <span className="connector-line" />
              <span className="connector-dot dest" />
            </div>
            <div className="route-field">
              <LocationAutocomplete
                label="Tujuan"
                value={destination}
                onChange={changeDestination}
                placeholder="Pasar induk, pelabuhan, atau kota tujuan"
                onOpenMapPicker={openDestinationPicker}
              />
              {errors.destination && <p role="alert" className="field-error">{errors.destination}</p>}
            </div>
          </div>

          <div className="vehicle-selector-group">
            <label htmlFor="vehicle-mode-select" className="vehicle-select-label">Kendaraan</label>
            <div className="vehicle-select-wrap">
              <VehicleModeIcon mode={vehicleMode} size={18} weight="bold" aria-hidden="true" />
              <select
                id="vehicle-mode-select"
                value={vehicleMode}
                onChange={(e) => changeVehicleMode(e.target.value as RoutingVehicleMode)}
                className="field vehicle-select"
                aria-label="Pilih jenis kendaraan pengiriman"
              >
                {ROUTING_VEHICLE_MODES.map((opt) => (
                  <option key={opt.mode} value={opt.mode}>
                    {opt.label} ({opt.description})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </fieldset>

        {error && <div role="alert" className="analysis-error">{error}</div>}

        <div className="analysis-command">
          <p className={busy ? "analysis-status" : "sr-only"} aria-live="polite">
            {phase === "routing" ? "Menghitung jarak dan durasi rute…" : phase === "predicting" ? "Menganalisis kematangan tandan buah…" : ""}
          </p>
          <button type="submit" disabled={busy} className="analyze-button">
            {busy ? (
              <>
                <SpinnerGapIcon className="spin" aria-hidden="true" size={20} />
                <span>{phase === "routing" ? "Menghitung Rute Logistik…" : "Menganalisis Kematangan Buah…"}</span>
              </>
            ) : (
              <>
                <ShieldCheckIcon size={20} weight="bold" aria-hidden="true" />
                <span>Analisis Rencana Panen</span>
              </>
            )}
          </button>
        </div>
      </form>

      {/* Reusable Manual Location Picker modal */}
      <ManualLocationPickerLoader
        isOpen={pickerTarget !== null}
        fieldLabel={pickerTarget === "origin" ? "Asal" : "Tujuan"}
        initialLocation={pickerTarget === "origin" ? origin : destination}
        initialQuery={pickerQuery}
        onConfirm={handleManualLocationConfirm}
        onClose={() => setPickerTarget(null)}
      />

      {!result && (
        <aside className="standby-instrument" aria-label="Perencanaan kematangan & pengiriman">
          <div className="standby-canvas">
            <header className="standby-header">
              <div className="standby-tag">
                <span className="tag-pulse" />
                <span>PERENCANAAN KEMATANGAN & PENGIRIMAN</span>
              </div>
              <h2>Alur Kematangan & Logistik</h2>
              <p className="standby-lead">
                PisGo membaca kematangan pisang dari foto spesimen kebun, memetakan posisinya pada skala kematangan Cavendish (1–7), lalu memproyeksikan durasi transit untuk menetapkan jadwal panen dan pengiriman yang tepat.
              </p>
            </header>

            {/* Standby Coherent Flow Process */}
            <div className="standby-process-flow">
              <div className="process-step">
                <span className="process-step-num">01</span>
                <div className="process-step-body">
                  <span className="process-label">FOTO PISANG</span>
                  <strong className="process-value empty">—</strong>
                  <small className="process-note">Spesimen di pohon</small>
                </div>
              </div>

              <div className="process-arrow" aria-hidden="true">→</div>

              <div className="process-step">
                <span className="process-step-num">02</span>
                <div className="process-step-body">
                  <span className="process-label">KEMATANGAN SAAT INI</span>
                  <strong className="process-value empty">—</strong>
                  <small className="process-note">Perkiraan dari foto</small>
                </div>
              </div>

              <div className="process-arrow" aria-hidden="true">→</div>

              <div className="process-step">
                <span className="process-step-num">03</span>
                <div className="process-step-body">
                  <span className="process-label">DURASI PERJALANAN</span>
                  <strong className="process-value empty">—</strong>
                  <small className="process-note">Rute logistik darat</small>
                </div>
              </div>

              <div className="process-arrow" aria-hidden="true">→</div>

              <div className="process-step active">
                <span className="process-step-num">04</span>
                <div className="process-step-body">
                  <span className="process-label">KEMATANGAN SAAT TIBA</span>
                  <strong className="process-value" style={{ color: selectedMaturityInfo.color }}>
                    Tingkat {targetMaturity}
                  </strong>
                  <small className="process-note" style={{ color: selectedMaturityInfo.color }}>
                    Target: {selectedMaturityInfo.shortLabel}
                  </small>
                </div>
              </div>
            </div>

            {/* Dominant Visual Signature: Standby Maturity Instrument */}
            <div className="standby-instrument-block">
              <div className="instrument-block-header">
                <div>
                  <h3 className="instrument-block-title">Skala kematangan Cavendish</h3>
                  <p className="instrument-block-sub">Skala pembacaan kematangan 1–7 untuk perencanaan panen dan pengiriman</p>
                </div>
                <div className="instrument-active-pill" style={{ borderColor: selectedMaturityInfo.color }}>
                  <span className="pill-dot" style={{ backgroundColor: selectedMaturityInfo.color }} />
                  <span className="pill-text">Target: Tingkat {targetMaturity} / 7</span>
                </div>
              </div>

              <div className="standby-track-wrap">
                <MaturityInstrumentDisplay
                  target={targetMaturity}
                  size="large"
                />
              </div>
            </div>

            {/* Flattened Operational Guidance Band */}
            <div className="operational-guidance-band">
              <div className="guidance-col">
                <div className="guidance-col-header">
                  <CameraIcon size={18} weight="bold" className="guidance-icon-flat" />
                  <h4>Panduan Foto Pisang</h4>
                </div>
                <p>Ambil foto 1 tandan utuh di pohon dengan pencahayaan alami siang hari. Hindari bayangan pekat atau sudut terlalu gelap untuk pembacaan terbaik.</p>
              </div>

              <div className="guidance-col-divider" aria-hidden="true" />

              <div className="guidance-col">
                <div className="guidance-col-header">
                  <TruckIcon size={18} weight="bold" className="guidance-icon-flat" />
                  <h4>Faktor Rute & Kematangan</h4>
                </div>
                <p>Durasi perjalanan truk langsung memengaruhi laju kematangan buah selama transit. PisGo menyesuaikan tanggal kirim agar buah tiba pada tingkat kematangan yang ditargetkan.</p>
              </div>
            </div>

            <div className="standby-footer-tip">
              <span>Lengkapi data formulir di sebelah kiri, kemudian klik <strong>Analisis Rencana Panen</strong> untuk memunculkan rekomendasi tanggal panen, pengiriman, dan verifikasi rute.</span>
            </div>
          </div>
        </aside>
      )}

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
      // showPicker fallback
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
