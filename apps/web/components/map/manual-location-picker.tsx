"use client";

import { CheckIcon, CrosshairIcon, NavigationArrowIcon, SpinnerGapIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";
import { Circle, CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { Coordinates, LocationSuggestion } from "@/types/location";

const GEOAPIFY_ATTRIBUTION = 'Powered by <a href="https://www.geoapify.com/" target="_blank" rel="noopener noreferrer">Geoapify</a> | © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';
const INDONESIA_CENTER: [number, number] = [-2.5, 118];

// Leaflet custom pin icon for precise manual placement
const customPinIcon = L.divIcon({
  className: "manual-picker-custom-pin",
  html: `<div class="manual-picker-pin-inner"><svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 0C6.268 0 0 6.268 0 14C0 24.5 14 36 14 36C14 36 28 24.5 28 14C28 6.268 21.732 0 14 0Z" fill="#215437"/>
    <circle cx="14" cy="14" r="6" fill="#FBF9F4"/>
    <circle cx="14" cy="14" r="3" fill="#215437"/>
  </svg></div>`,
  iconSize: [28, 36],
  iconAnchor: [14, 36],
});

type ManualLocationPickerProps = {
  isOpen: boolean;
  fieldLabel: "Asal" | "Tujuan";
  initialLocation: LocationSuggestion | null;
  initialQuery?: string;
  onConfirm: (location: LocationSuggestion) => void;
  onClose: () => void;
};

function MapClickHandler({ onSelect }: { onSelect: (coords: Coordinates) => void }) {
  useMapEvents({
    click(e) {
      onSelect({ lat: Number(e.latlng.lat.toFixed(6)), lon: Number(e.latlng.lng.toFixed(6)) });
    },
  });
  return null;
}

function MapViewController({ targetCenter, targetZoom }: { targetCenter: [number, number]; targetZoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(targetCenter, targetZoom);
  }, [targetCenter, targetZoom, map]);
  return null;
}

export function ManualLocationPicker({
  isOpen,
  fieldLabel,
  initialLocation,
  initialQuery,
  onConfirm,
  onClose,
}: ManualLocationPickerProps) {
  const titleId = useId();
  const descriptionId = useId();

  const [selectedCoords, setSelectedCoords] = useState<Coordinates | null>(
    initialLocation ? { lat: initialLocation.lat, lon: initialLocation.lon } : null,
  );
  const [deviceAccuracy, setDeviceAccuracy] = useState<number | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [mapTarget, setMapTarget] = useState<{ center: [number, number]; zoom: number }>({
    center: initialLocation ? [initialLocation.lat, initialLocation.lon] : INDONESIA_CENTER,
    zoom: initialLocation ? 13 : 5,
  });

  const [prevInitialLocation, setPrevInitialLocation] = useState<LocationSuggestion | null>(initialLocation);
  const [prevIsOpen, setPrevIsOpen] = useState(isOpen);

  if (isOpen !== prevIsOpen || initialLocation !== prevInitialLocation) {
    setPrevIsOpen(isOpen);
    setPrevInitialLocation(initialLocation);
    if (isOpen) {
      setSelectedCoords(initialLocation ? { lat: initialLocation.lat, lon: initialLocation.lon } : null);
      setDeviceAccuracy(null);
      setLocationNotice(null);
      setLocating(false);
      setMapTarget({
        center: initialLocation ? [initialLocation.lat, initialLocation.lon] : INDONESIA_CENTER,
        zoom: initialLocation ? 13 : 5,
      });
    }
  }

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  function handleLocateDevice() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocationNotice("Geolokasi tidak didukung oleh browser Anda.");
      return;
    }

    setLocating(true);
    setLocationNotice(null);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = Number(position.coords.latitude.toFixed(6));
        const lon = Number(position.coords.longitude.toFixed(6));
        const accuracy = Math.round(position.coords.accuracy);

        setSelectedCoords({ lat, lon });
        setDeviceAccuracy(accuracy);
        setMapTarget({ center: [lat, lon], zoom: 15 });
        setLocating(false);
      },
      (geoError) => {
        setLocating(false);
        if (geoError.code === geoError.PERMISSION_DENIED) {
          setLocationNotice("Izin lokasi perangkat ditolak. Anda dapat tetap memilih manual di peta.");
        } else if (geoError.code === geoError.TIMEOUT) {
          setLocationNotice("Permintaan lokasi perangkat kedaluwarsa. Coba lagi atau pilih manual di peta.");
        } else {
          setLocationNotice("Lokasi perangkat tidak dapat diperoleh. Pilih manual di peta.");
        }
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  }

  function handleSelectCoordinates(coords: Coordinates) {
    setSelectedCoords(coords);
    setDeviceAccuracy(null); // Clear device accuracy circle when user manually picks another point
    setLocationNotice(null);
  }

  function handleConfirm() {
    if (!selectedCoords) return;
    const trimmedTyped = initialQuery?.trim();
    const label = trimmedTyped && trimmedTyped.length > 0
      ? trimmedTyped
      : initialLocation?.label && initialLocation.provider === "manual"
        ? initialLocation.label
        : "Titik pilihan di peta";

    const manualSuggestion: LocationSuggestion = {
      id: `manual-${Date.now()}-${selectedCoords.lat.toFixed(4)}-${selectedCoords.lon.toFixed(4)}`,
      label,
      lat: selectedCoords.lat,
      lon: selectedCoords.lon,
      provider: "manual",
    };

    onConfirm(manualSuggestion);
    onClose();
  }

  const dialogAriaLabel = `Pilih titik ${fieldLabel.toLowerCase()} di peta`;

  return (
    <div className="manual-picker-backdrop" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId}>
      <div className="manual-picker-modal">
        <header className="manual-picker-header">
          <div className="manual-picker-title-group">
            <span className="manual-picker-badge">Peta Manual</span>
            <h2 id={titleId} className="manual-picker-title">{dialogAriaLabel}</h2>
            <p id={descriptionId} className="manual-picker-desc">
              Klik pada peta untuk menempatkan titik koordinat presisi. Untuk perhitungan rute, pilih titik di jalan atau dekat akses kendaraan.
            </p>
          </div>
          <button
            type="button"
            className="manual-picker-close-btn"
            onClick={onClose}
            aria-label="Tutup dialog pilih di peta"
          >
            <XIcon size={20} weight="bold" />
          </button>
        </header>

        <div className="manual-picker-map-container">
          <MapContainer
            center={mapTarget.center}
            zoom={mapTarget.zoom}
            scrollWheelZoom={true}
            className="manual-picker-leaflet-map"
          >
            {/* Richer OSM-Bright style for manual picker orientation */}
            <TileLayer
              url="/api/geoapify/tiles/{z}/{x}/{y}?style=osm-bright"
              maxZoom={20}
              attribution={GEOAPIFY_ATTRIBUTION}
            />
            <MapClickHandler onSelect={handleSelectCoordinates} />
            <MapViewController targetCenter={mapTarget.center} targetZoom={mapTarget.zoom} />

            {/* Subtle Leaflet accuracy circle when acquired via device geolocation */}
            {selectedCoords && deviceAccuracy !== null && (
              <Circle
                center={[selectedCoords.lat, selectedCoords.lon]}
                radius={deviceAccuracy}
                pathOptions={{
                  color: "#215437",
                  fillColor: "#215437",
                  fillOpacity: 0.12,
                  weight: 1,
                  dashArray: "4, 4",
                }}
              />
            )}

            {selectedCoords && (
              <Marker position={[selectedCoords.lat, selectedCoords.lon]} icon={customPinIcon}>
                <Tooltip direction="top" offset={[0, -36]} permanent>
                  {initialQuery?.trim() || "Titik pilihan"}
                </Tooltip>
              </Marker>
            )}

            {/* If there's an existing point and user hasn't moved it or wants reference */}
            {initialLocation && (
              <CircleMarker
                center={[initialLocation.lat, initialLocation.lon]}
                radius={6}
                pathOptions={{ color: "#215437", weight: 2, fillColor: "#dbe7dc", fillOpacity: 0.8 }}
              />
            )}
          </MapContainer>

          {/* Map Control: Device Geolocation Button */}
          <div className="manual-picker-locate-ctrl">
            <button
              type="button"
              className="manual-picker-locate-btn"
              onClick={handleLocateDevice}
              disabled={locating}
              aria-label="Gunakan lokasi perangkat"
              title="Gunakan lokasi perangkat"
            >
              {locating ? (
                <SpinnerGapIcon className="spin" size={18} weight="bold" />
              ) : (
                <NavigationArrowIcon size={18} weight="bold" />
              )}
            </button>
          </div>
        </div>

        {locationNotice && (
          <div role="status" className="manual-picker-notice" aria-live="polite">
            <span>{locationNotice}</span>
          </div>
        )}

        <footer className="manual-picker-footer">
          <div className="manual-picker-coords-box" aria-live="polite">
            <CrosshairIcon size={16} weight="bold" className="coords-icon" aria-hidden="true" />
            {selectedCoords ? (
              <div className="coords-display-group">
                <span className="coords-text">
                  Koordinat: <strong>{selectedCoords.lat.toFixed(5)}, {selectedCoords.lon.toFixed(5)}</strong>
                </span>
                {deviceAccuracy !== null && (
                  <span className="coords-accuracy">
                    (Akurasi perangkat ±{deviceAccuracy} m)
                  </span>
                )}
              </div>
            ) : (
              <span className="coords-placeholder">Belum ada titik dipilih. Klik peta untuk memilih.</span>
            )}
          </div>

          <div className="manual-picker-actions">
            <button
              type="button"
              className="manual-picker-cancel-btn"
              onClick={onClose}
            >
              Batal
            </button>
            <button
              type="button"
              className="manual-picker-confirm-btn"
              disabled={!selectedCoords}
              onClick={handleConfirm}
            >
              <CheckIcon size={16} weight="bold" aria-hidden="true" />
              <span>Gunakan titik ini</span>
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
