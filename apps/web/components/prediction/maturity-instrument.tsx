"use client";

import React, { useRef } from "react";

export type MaturityItem = {
  level: number;
  label: string;
  shortLabel: string;
  color: string;
  desc: string;
};

export const MATURITY_SPECTRUM: MaturityItem[] = [
  { level: 1, label: "Hijau matang", shortLabel: "Hijau matang", color: "#34683a", desc: "Kulit hijau pekat merata, baru siap dipetik." },
  { level: 2, label: "Matang hijau", shortLabel: "Matang hijau", color: "#4f833b", desc: "Hijau muda dengan garis sudut buah mulai melunak." },
  { level: 3, label: "Kuning hijau", shortLabel: "Kuning hijau", color: "#759d33", desc: "Mulai menguning, lebih dominan hijau." },
  { level: 4, label: "Lebih hijau dari kuning", shortLabel: "Lebih hijau dari kuning", color: "#9eb52d", desc: "Kuning merata namun ujung dan pangkal masih hijau." },
  { level: 5, label: "Kuning ujung hijau", shortLabel: "Kuning ujung hijau", color: "#c7a726", desc: "Kuning segar cerah dengan sedikit hijau di ujung." },
  { level: 6, label: "Kuning penuh", shortLabel: "Kuning penuh", color: "#d6981f", desc: "Kuning sempurna siap konsumsi langsung." },
  { level: 7, label: "Kuning bintik cokelat", shortLabel: "Kuning bintik cokelat", color: "#c48e18", desc: "Kematangan puncak dengan bintik gula alami." },
];

export function levelToPercent(level: number): number {
  return ((level - 1) / 6) * 100;
}

export function percentToLevel(percent: number): number {
  const clamped = Math.max(0, Math.min(100, percent));
  const raw = 1 + (clamped / 100) * 6;
  return Math.max(1, Math.min(7, Math.round(raw)));
}

type InteractiveProps = {
  value: number;
  onChange: (level: number) => void;
  id?: string;
  size?: "default" | "large";
};

type ResultProps = {
  current?: number;
  target: number;
  arrival?: number;
  size?: "default" | "large";
};

export function MaturityInstrumentControl({
  value,
  onChange,
  id = "target-maturity",
  size = "default",
}: InteractiveProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const selectedInfo = MATURITY_SPECTRUM.find((m) => m.level === value) ?? MATURITY_SPECTRUM[3];

  function handleTrackInteraction(clientX: number) {
    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const offsetX = clientX - rect.left;
    const percent = (offsetX / rect.width) * 100;
    const newLevel = percentToLevel(percent);
    if (newLevel !== value) {
      onChange(newLevel);
    }
  }

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const track = trackRef.current;
    if (!track) return;
    track.setPointerCapture(e.pointerId);
    handleTrackInteraction(e.clientX);

    function onPointerMove(moveEvent: PointerEvent) {
      handleTrackInteraction(moveEvent.clientX);
    }

    function onPointerUp(upEvent: PointerEvent) {
      track?.releasePointerCapture(upEvent.pointerId);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  const targetPercent = levelToPercent(value);

  return (
    <div className="maturity-instrument-card" data-size={size}>
      <div className="maturity-instrument-header">
        <label htmlFor={id} className="instrument-title">
          Target kematangan saat tiba
        </label>
        <output htmlFor={id} className="instrument-badge" style={{ borderColor: selectedInfo.color }}>
          <span className="badge-dot" style={{ backgroundColor: selectedInfo.color }} aria-hidden="true" />
          <span className="badge-value">Tingkat {value} <small>/ 7</small></span>
        </output>
      </div>

      <p className="maturity-instrument-desc">
        <span className="maturity-desc-name" style={{ color: selectedInfo.color }}>{selectedInfo.shortLabel}</span>
        <span className="maturity-desc-sep">·</span>
        <span className="maturity-desc-text">{selectedInfo.desc}</span>
      </p>

      {/* Unified Ripeness Track */}
      <div className="maturity-track-container" data-size={size}>
        <div
          ref={trackRef}
          className="maturity-continuous-track interactive"
          onPointerDown={handlePointerDown}
          role="presentation"
        >
          {/* 7 Semantic Numbers and Tick Dividers */}
          <div className="track-ticks-layer" aria-hidden="true">
            {MATURITY_SPECTRUM.map((item) => {
              const pct = levelToPercent(item.level);
              return (
                <div
                  key={item.level}
                  className="track-tick-node"
                  style={{ left: `${pct}%` }}
                >
                  <span className="tick-mark" />
                  <span className="tick-number">{item.level}</span>
                </div>
              );
            })}
          </div>

          {/* Active Target Indicator Marker */}
          <div
            className="track-target-marker"
            style={{ left: `${targetPercent}%` }}
            aria-hidden="true"
          >
            <div className="target-marker-tag">
              <span className="target-marker-glyph">■</span>
              <span className="target-marker-label">TARGET</span>
            </div>
            <div className="target-marker-pointer" />
            <div className="target-marker-thumb" style={{ backgroundColor: selectedInfo.color }} />
          </div>
        </div>

        {/* Fully accessible native range input */}
        <input
          id={id}
          type="range"
          min="1"
          max="7"
          step="1"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="maturity-native-range-slider"
          aria-valuetext={`Tingkat ${value}, ${selectedInfo.shortLabel}`}
          aria-label="Target kematangan buah saat tiba"
        />
      </div>

      <div className="maturity-track-labels" aria-hidden="true">
        <span className="track-side-label start">
          <span className="side-dot" style={{ backgroundColor: MATURITY_SPECTRUM[0].color }} />
          <span>Hijau</span>
        </span>
        <span className="track-center-label">
          <span>Pematangan</span>
        </span>
        <span className="track-side-label end">
          <span>Kuning</span>
          <span className="side-dot" style={{ backgroundColor: MATURITY_SPECTRUM[6].color }} />
        </span>
      </div>
    </div>
  );
}

export function MaturityInstrumentDisplay({
  current,
  target,
  arrival,
  size = "default",
}: ResultProps) {
  const currentLevel = current !== undefined ? Math.max(1, Math.min(7, current)) : undefined;
  const targetLevel = Math.max(1, Math.min(7, target));
  const arrivalLevel = arrival !== undefined ? Math.max(1, Math.min(7, arrival)) : undefined;

  const currentPct = currentLevel !== undefined ? levelToPercent(currentLevel) : undefined;
  const targetPct = levelToPercent(targetLevel);
  const arrivalPct = arrivalLevel !== undefined ? levelToPercent(arrivalLevel) : undefined;

  return (
    <div className="maturity-track-container display-mode" data-size={size}>
      <div className="maturity-continuous-track display-track" role="presentation">
        <div className="track-ticks-layer" aria-hidden="true">
          {MATURITY_SPECTRUM.map((item) => {
            const pct = levelToPercent(item.level);
            return (
              <div
                key={item.level}
                className="track-tick-node"
                style={{ left: `${pct}%` }}
              >
                <span className="tick-mark" />
                <span className="tick-number">{item.level}</span>
              </div>
            );
          })}
        </div>

        {/* Semantic markers on fixed lanes prevent overlap without runtime layout logic. */}
        {currentPct !== undefined && (
          <div
            className="track-display-marker current"
            style={{ left: `${currentPct}%` }}
            title={`Saat Ini: Tingkat ${currentLevel?.toFixed(1)}`}
          >
            <div className="display-marker-tag current">
              <span className="marker-icon">▼</span>
              <span className="marker-txt">SAAT INI</span>
            </div>
            <div className="display-marker-line current" />
          </div>
        )}

        <div
          className="track-display-marker target"
          style={{ left: `${targetPct}%` }}
          title={`Target: Tingkat ${targetLevel}`}
        >
          <div className="display-marker-tag target">
            <span className="marker-icon">■</span>
            <span className="marker-txt">TARGET</span>
          </div>
          <div className="display-marker-line target" />
        </div>

        {arrivalPct !== undefined && (
          <div
            className="track-display-marker arrival"
            style={{ left: `${arrivalPct}%` }}
            title={`Saat Tiba: Tingkat ${arrivalLevel?.toFixed(1)}`}
          >
            <div className="display-marker-tag arrival">
              <span className="marker-icon">◆</span>
              <span className="marker-txt">SAAT TIBA</span>
            </div>
            <div className="display-marker-line arrival" />
          </div>
        )}
      </div>

      <div className="maturity-track-labels" aria-hidden="true">
        <span className="track-side-label start">
          <span className="side-dot" style={{ backgroundColor: MATURITY_SPECTRUM[0].color }} />
          <span>Hijau</span>
        </span>
        <span className="track-center-label">
          <span>Pematangan</span>
        </span>
        <span className="track-side-label end">
          <span>Kuning</span>
          <span className="side-dot" style={{ backgroundColor: MATURITY_SPECTRUM[6].color }} />
        </span>
      </div>
    </div>
  );
}
