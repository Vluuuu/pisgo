"use client";

import { CheckCircleIcon, FlaskIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { RouteMapLoader } from "@/components/map/route-map-loader";
import { formatDate, formatDistance, formatDuration } from "@/lib/format";
import type { LocationSuggestion, RouteData } from "@/types/location";
import type { OptimizerResult, PredictionResponse } from "@/types/prediction";

type ResultViewProps = {
  prediction: PredictionResponse;
  schedule: OptimizerResult;
  route: RouteData;
  origin: LocationSuggestion;
  destination: LocationSuggestion;
  targetMaturity: number;
};

const statusCopy = {
  on_target: "Expected to arrive on target",
  under_target: "Expected to arrive below target",
  over_target: "Expected to arrive above target",
};

export function ResultView({ prediction, schedule, route, origin, destination, targetMaturity }: ResultViewProps) {
  const current = prediction.current_maturity;
  const arrival = schedule.expectedArrivalMaturity;
  const statusOnTarget = schedule.status === "on_target";

  return (
    <section className="result-workspace" id="recommendation" aria-labelledby="recommendation-title">
      <section className="recommendation">
        <header className="recommendation-header">
          <p className="section-label">Recommended plan</p>
          <h2 id="recommendation-title"><span>Ship on</span>{formatDecisionDate(schedule.recommendedShippingDate)}</h2>
          <p className="recommendation-status" data-status={schedule.status}>
            {statusOnTarget ? <CheckCircleIcon aria-hidden="true" size={18} weight="fill" /> : <WarningCircleIcon aria-hidden="true" size={18} weight="fill" />}
            {statusCopy[schedule.status]}
          </p>
        </header>

        <div className="schedule-timeline" aria-label="Recommended harvest, shipping, and arrival dates">
          <ScheduleStep label="Harvest" date={schedule.recommendedHarvestDate} />
          <span className="schedule-connector" aria-hidden="true" />
          <ScheduleStep label="Ship" date={schedule.recommendedShippingDate} primary />
          <span className="schedule-connector" aria-hidden="true" />
          <ScheduleStep label="Arrive" date={schedule.expectedArrivalDate} />
        </div>

        <p className="arrival-maturity"><span>Expected arrival maturity</span><strong>{arrival.toFixed(1)} <small>/ 7</small></strong></p>
      </section>

      <section className="route-result" aria-labelledby="route-map-title">
        <header className="route-summary">
          <h2 id="route-map-title"><span>{shortLocation(origin)}</span><i aria-hidden="true">→</i><span>{shortLocation(destination)}</span></h2>
          <p>{formatDistance(route.distanceMeters)} <span aria-hidden="true">·</span> {formatDuration(route.durationSeconds)}</p>
        </header>
        <div className="map-area"><RouteMapLoader origin={origin} destination={destination} route={route} /></div>
      </section>

      <section className="evidence-section" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Supporting evidence</h3>
        <dl className="evidence-list">
          <Evidence label="DAF" value={`${prediction.days_after_flowering} days`} />
          <Evidence label="Current maturity" value={`${current.toFixed(1)} / 7`} />
          <Evidence label="Target maturity" value={`${targetMaturity.toFixed(1)} / 7`} />
          <Evidence label="AI confidence" value={`${Math.round(prediction.confidence * 100)}%`} />
        </dl>
      </section>

      <footer className="recommendation-meta">
        <p><FlaskIcon aria-hidden="true" size={16} weight="regular" /> Model {prediction.model_version} · Development simulation</p>
      </footer>
    </section>
  );
}

function ScheduleStep({ label, date, primary = false }: { label: string; date: string; primary?: boolean }) {
  return (
    <div className="schedule-step" data-primary={primary}>
      <time dateTime={date}>{formatTimelineDate(date)}</time>
      <span>{label}</span>
    </div>
  );
}

function Evidence({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function shortLocation(location: LocationSuggestion): string {
  return location.city || location.state || location.label.split(",")[0];
}

function formatDecisionDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00.000Z`));
}

function formatTimelineDate(value: string): string {
  return formatDate(value).replace(/, \d{4}$/, "").toUpperCase();
}
