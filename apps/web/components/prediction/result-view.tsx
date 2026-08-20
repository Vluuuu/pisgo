"use client";

import { CheckCircleIcon, FlaskIcon, TruckIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { RouteMapLoader } from "@/components/map/route-map-loader";
import { formatDecisionDate, formatDistance, formatDuration, formatMaturity } from "@/lib/format";
import { MATURITY_SPECTRUM, MaturityInstrumentDisplay } from "./maturity-instrument";
import { ROUTING_VEHICLE_MODES } from "@/types/location";
import type { LocationSuggestion, RouteData, RoutingVehicleMode } from "@/types/location";
import type { OptimizerResult, PredictionResponse } from "@/types/prediction";

type ResultViewProps = {
  prediction: PredictionResponse;
  schedule: OptimizerResult;
  route: RouteData;
  origin: LocationSuggestion;
  destination: LocationSuggestion;
  targetMaturity: number;
  vehicleMode?: RoutingVehicleMode;
};

const statusCopy = {
  on_target: "Diperkirakan tiba sesuai target",
  under_target: "Diperkirakan tiba lebih hijau dari target",
  over_target: "Diperkirakan tiba lebih matang dari target",
};

export function ResultView({ prediction, schedule, route, origin, destination, targetMaturity, vehicleMode }: ResultViewProps) {
  const current = prediction.current_maturity;
  const arrival = schedule.expectedArrivalMaturity;
  const statusOnTarget = schedule.status === "on_target";

  const arrivalInfo = MATURITY_SPECTRUM.find((m) => m.level === Math.round(arrival)) ?? MATURITY_SPECTRUM[4];
  const targetInfo = MATURITY_SPECTRUM.find((m) => m.level === targetMaturity) ?? MATURITY_SPECTRUM[3];
  const currentInfo = MATURITY_SPECTRUM.find((m) => m.level === Math.round(current)) ?? MATURITY_SPECTRUM[2];
  const vehicleInfo = ROUTING_VEHICLE_MODES.find((v) => v.mode === vehicleMode) ?? ROUTING_VEHICLE_MODES[1];

  return (
    <section className="result-workspace" id="recommendation" aria-labelledby="recommendation-title">
      <section className="recommendation">
        <header className="recommendation-header">
          <div className="rec-badge-row">
            <span className="section-label">REKOMENDASI PENGIRIMAN</span>
            <p className="recommendation-status" data-status={schedule.status}>
              {statusOnTarget ? (
                <CheckCircleIcon aria-hidden="true" size={18} weight="fill" />
              ) : (
                <WarningCircleIcon aria-hidden="true" size={18} weight="fill" />
              )}
              <span>{statusCopy[schedule.status]}</span>
            </p>
          </div>

          <div className="recommendation-hero">
            <span className="hero-sub">Kirim pada</span>
            <h2 id="recommendation-title">{formatDecisionDate(schedule.recommendedShippingDate)}</h2>
          </div>
        </header>

        {/* Unified 3-Marker Shared Maturity Instrument */}
        <div className="result-maturity-section">
          <div className="result-maturity-header">
            <div>
              <span className="res-mat-title">Skala kematangan Cavendish</span>
              <p className="res-mat-subtitle">Sebaran titik: Saat Ini (Kini) → Target → Saat Tiba</p>
            </div>
            <span className="res-mat-badge" style={{ backgroundColor: arrivalInfo.color }}>
              Tiba: Tingkat {formatMaturity(arrival)} / 7
            </span>
          </div>

          <div className="result-instrument-track-wrapper">
            <MaturityInstrumentDisplay
              current={current}
              target={targetMaturity}
              arrival={arrival}
              size="large"
            />

            <div className="result-maturity-legend">
              <div className="legend-chip">
                <span className="chip-symbol current">▼</span>
                <span>Saat ini: <strong>Tingkat {formatMaturity(current)}/7</strong> ({currentInfo.shortLabel})</span>
              </div>
              <div className="legend-chip">
                <span className="chip-symbol target">■</span>
                <span>Target: <strong>Tingkat {targetMaturity}/7</strong> ({targetInfo.shortLabel})</span>
              </div>
              <div className="legend-chip">
                <span className="chip-symbol arrival">◆</span>
                <span>Saat tiba: <strong>Tingkat {formatMaturity(arrival)}/7</strong> ({arrivalInfo.shortLabel})</span>
              </div>
            </div>
          </div>
        </div>

        {/* Decision Timeline */}
        <div className="schedule-timeline" aria-label="Tanggal panen, kirim, dan tiba yang direkomendasikan">
          <ScheduleStep label="Panen di kebun" date={schedule.recommendedHarvestDate} tag="Panen" />
          <div className="timeline-connector">
            <span className="connector-arrow" />
            <span className="connector-label">Jeda kebun</span>
          </div>
          <ScheduleStep label="Kirim muatan" date={schedule.recommendedShippingDate} primary tag="Kirim" />
          <div className="timeline-connector">
            <span className="connector-arrow" />
            <span className="connector-label">Transit</span>
          </div>
          <ScheduleStep label="Tiba di tujuan" date={schedule.expectedArrivalDate} tag="Tiba" />
        </div>

        <div className="arrival-maturity-footer">
          <div className="arrival-text">
            <span>Kondisi buah saat tiba di tujuan:</span>
            <strong>{arrivalInfo.label}</strong>
          </div>
          <div className="arrival-score" style={{ color: arrivalInfo.color }}>
            <span>Tingkat</span> <strong>{formatMaturity(arrival)}</strong> <small>/ 7</small>
          </div>
        </div>
      </section>

      {/* Route & Map Section */}
      <section className="route-result" aria-labelledby="route-map-title">
        <header className="route-summary">
          <div className="route-title-row">
            <h2 id="route-map-title">
              <span className="loc-badge origin">{shortLocation(origin)}</span>
              <i aria-hidden="true">→</i>
              <span className="loc-badge dest">{shortLocation(destination)}</span>
            </h2>
          </div>
          <div className="route-metrics">
            <span className="metric-item">
              <TruckIcon size={16} weight="bold" />
              <strong>{formatDistance(route.distanceMeters)}</strong>
            </span>
            <span className="metric-separator">·</span>
            <span className="metric-item">
              <strong>{formatDuration(route.durationSeconds)}</strong> estimasi ({vehicleInfo.label})
            </span>
          </div>
        </header>
        <div className="map-area">
          <RouteMapLoader origin={origin} destination={destination} route={route} />
        </div>
      </section>

      {/* Evidence & Technical Data */}
      <section className="evidence-section" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Data pendukung</h3>
        <dl className="evidence-list">
          <Evidence label="Hari setelah berbunga" value={`${prediction.days_after_flowering} hari`} />
          <Evidence label="Kematangan saat ini" value={`Tingkat ${formatMaturity(current)} / 7`} />
          <Evidence label="Target kematangan" value={`Tingkat ${formatMaturity(targetMaturity)} / 7`} />
          <Evidence label="Tingkat keyakinan model" value={`${Math.round(prediction.confidence * 100)}%`} />
        </dl>
      </section>

      <footer className="recommendation-meta">
        <p>
          <FlaskIcon aria-hidden="true" size={16} weight="regular" /> Model baseline {prediction.model_version} · Prototipe pengembangan
        </p>
      </footer>
    </section>
  );
}

function ScheduleStep({ label, date, primary = false, tag }: { label: string; date: string; primary?: boolean; tag?: string }) {
  return (
    <div className="schedule-step" data-primary={primary}>
      {tag && <span className="step-tag">{tag}</span>}
      <time dateTime={date}>{formatDecisionDate(date)}</time>
      <span className="step-title">{label}</span>
    </div>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return (
    <div className="evidence-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function shortLocation(location: LocationSuggestion): string {
  return location.city || location.state || location.label.split(",")[0];
}
