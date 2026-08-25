"use client";

import Image from "next/image";
import {
  ArrowClockwiseIcon,
  ArrowCounterClockwiseIcon,
  CameraIcon,
  CheckIcon,
  ImageIcon,
  SpinnerGapIcon,
  UploadSimpleIcon,
  WarningCircleIcon,
  XIcon,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { getLocalDateString } from "@/lib/dates";

type ImageUploadProps = {
  value: File | null;
  onChange: (file: File | null) => void;
  onPhotoDateChange?: (dateString: string) => void;
  error?: string;
};

type CameraStatus = "idle" | "requesting" | "live" | "captured" | "error";

const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function validateImageFile(file: File): string | null {
  if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
    return "Format foto harus JPG, PNG, atau WebP.";
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return "Ukuran foto maksimal 10 MB.";
  }
  return null;
}

export function ImageUpload({ value, onChange, onPhotoDateChange, error }: ImageUploadProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Bottom Sheet & Camera State
  const [isSheetOpen, setIsSheetOpen] = useState(false);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("idle");
  const [cameraErrorMessage, setCameraErrorMessage] = useState<string | null>(null);

  // Live Camera stream & Captured frame state
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [capturedBlob, setCapturedBlob] = useState<Blob | null>(null);
  const [capturedPreviewUrl, setCapturedPreviewUrl] = useState<string | null>(null);
  const [capturedAt, setCapturedAt] = useState<Date | null>(null);

  // Stop camera tracks cleanly
  const stopCameraStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  // Cleanup object URLs when discarded
  const clearCapturedState = useCallback(() => {
    if (capturedPreviewUrl) {
      URL.revokeObjectURL(capturedPreviewUrl);
      setCapturedPreviewUrl(null);
    }
    setCapturedBlob(null);
    setCapturedAt(null);
  }, [capturedPreviewUrl]);

  // Clean unmount safety
  useEffect(() => {
    return () => {
      stopCameraStream();
      if (capturedPreviewUrl) {
        URL.revokeObjectURL(capturedPreviewUrl);
      }
    };
  }, [stopCameraStream, capturedPreviewUrl]);

  function handleFile(file: File | null) {
    if (!file) return;
    const message = validateImageFile(file);
    if (message) {
      setValidationError(message);
      return;
    }
    setValidationError(null);
    onChange(file);
  }

  // Open Gallery File Picker
  function handleOpenGallery() {
    setIsSheetOpen(false);
    fileInputRef.current?.click();
  }

  // Open and initialize Camera
  const startCamera = useCallback(async () => {
    setCameraStatus("requesting");
    setCameraErrorMessage(null);
    clearCapturedState();
    stopCameraStream();

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("error");
      setCameraErrorMessage("Kamera tidak didukung oleh browser Anda. Silakan pilih foto dari Galeri.");
      return;
    }

    try {
      // 1st priority: Mobile rear camera (environment)
      let mediaStream: MediaStream;
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });
      } catch {
        // Fallback: generic video stream
        mediaStream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: false,
        });
      }

      streamRef.current = mediaStream;
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        await videoRef.current.play().catch(() => {});
      }
      setCameraStatus("live");
    } catch (err: unknown) {
      const errorObj = err as { name?: string };
      setCameraStatus("error");
      if (errorObj?.name === "NotAllowedError" || errorObj?.name === "PermissionDeniedError") {
        setCameraErrorMessage("Akses kamera tidak diberikan. Izinkan akses kamera atau pilih foto dari Galeri.");
      } else if (errorObj?.name === "NotFoundError" || errorObj?.name === "DevicesNotFoundError") {
        setCameraErrorMessage("Kamera tidak tersedia pada perangkat ini. Silakan pilih foto dari Galeri.");
      } else {
        setCameraErrorMessage("Kamera tidak dapat dibuka. Silakan coba lagi atau pilih foto dari Galeri.");
      }
    }
  }, [clearCapturedState, stopCameraStream]);

  // Handle camera option click from bottom sheet
  function handleSelectCamera() {
    setIsSheetOpen(false);
    setIsCameraOpen(true);
    startCamera();
  }

  // Close Camera modal completely
  function handleCloseCamera() {
    stopCameraStream();
    clearCapturedState();
    setIsCameraOpen(false);
    setCameraStatus("idle");
    setCameraErrorMessage(null);
  }

  // Capture frame from active video
  function handleCapturePhoto() {
    const video = videoRef.current;
    if (!video || cameraStatus !== "live") return;

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");

    if (!ctx) return;
    ctx.drawImage(video, 0, 0, width, height);

    const now = new Date();
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        // Pause live camera stream temporarily while previewing
        stopCameraStream();
        const previewUrl = URL.createObjectURL(blob);
        setCapturedBlob(blob);
        setCapturedPreviewUrl(previewUrl);
        setCapturedAt(now);
        setCameraStatus("captured");
      },
      "image/jpeg",
      0.92
    );
  }

  // Retake photo: discard temporary capture and restart live camera
  function handleRetakePhoto() {
    clearCapturedState();
    startCamera();
  }

  // Use captured photo: convert Blob -> File, pass into existing upload pipeline, and auto-set photoDate
  function handleUseCapturedPhoto() {
    if (!capturedBlob || !capturedAt) return;

    const timestamp = capturedAt.getTime();
    const cameraFile = new File([capturedBlob], `pisgo-camera-${timestamp}.jpg`, {
      type: "image/jpeg",
      lastModified: timestamp,
    });

    // Auto set photo date to local device date when taken via camera
    const localDateStr = getLocalDateString(capturedAt);
    if (onPhotoDateChange) {
      onPhotoDateChange(localDateStr);
    }

    // Pass into standard existing image handler
    handleFile(cameraFile);

    // Clean up and close modal
    handleCloseCamera();
  }

  // Handle tap on photo container box
  function handleStageClick(event: React.MouseEvent) {
    const target = event.target as HTMLElement;
    if (target.closest(".action-btn.remove")) {
      return;
    }
    event.preventDefault();
    setIsSheetOpen(true);
  }

  return (
    <div
      className="upload-field"
      onDragEnter={(event) => { event.preventDefault(); event.stopPropagation(); setIsDragging(true); }}
      onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); setIsDragging(true); }}
      onDragLeave={(event) => { event.preventDefault(); event.stopPropagation(); setIsDragging(false); }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(false);
        handleFile(event.dataTransfer.files?.[0] ?? null);
      }}
    >
      <div className="field-heading">
        <label id={`${inputId}-label`} htmlFor={inputId}>Foto Pisang di Pohon</label>
        <span className="upload-spec-hint">JPG, PNG, WebP · maks. 10 MB</span>
      </div>

      <div
        className="specimen-frame-stage"
        data-error={Boolean(error)}
        data-dragging={isDragging}
        onClick={handleStageClick}
        role="button"
        tabIndex={0}
        aria-haspopup="dialog"
        aria-expanded={isSheetOpen || isCameraOpen}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setIsSheetOpen(true);
          }
        }}
      >
        {/* Inspection Corner Marks */}
        <span className="frame-corner top-left" aria-hidden="true" />
        <span className="frame-corner top-right" aria-hidden="true" />
        <span className="frame-corner bottom-left" aria-hidden="true" />
        <span className="frame-corner bottom-right" aria-hidden="true" />

        {value ? (
          <ImagePreview
            file={value}
            onOpenSheet={() => setIsSheetOpen(true)}
            onRemove={(e) => {
              e.stopPropagation();
              onChange(null);
            }}
          />
        ) : (
          <div className="photo-prompt">
            <div className="prompt-icon-ring">
              <CameraIcon aria-hidden="true" size={26} weight="bold" />
            </div>
            <div className="prompt-text-group">
              <strong>{isDragging ? "Lepaskan foto pisang di sini" : "Pilih atau Tarik Foto Pisang"}</strong>
              <small>Foto 1 tandan penuh, pencahayaan alami terang di kebun</small>
            </div>
          </div>
        )}

        {/* Existing Hidden File Input for Gallery / Drag & Drop */}
        <input
          id={inputId}
          ref={fileInputRef}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-labelledby={`${inputId}-label`}
          onClick={(event) => { event.currentTarget.value = ""; setValidationError(null); }}
          onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
        />
      </div>

      {(error ?? validationError) && <p role="alert" className="field-error">{error ?? validationError}</p>}

      {/* -------------------------------------------------------------
          SOURCE PICKER BOTTOM SHEET (Native Android Style)
          ------------------------------------------------------------- */}
      {isSheetOpen && (
        <div
          className="bottom-sheet-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Pilih sumber foto"
          onClick={() => setIsSheetOpen(false)}
        >
          <div
            className="bottom-sheet-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sheet-handle-bar" aria-hidden="true" />
            <header className="sheet-header">
              <h3 className="sheet-title">Pilih sumber foto</h3>
            </header>

            <div className="sheet-options-grid">
              <button
                type="button"
                className="sheet-option-card"
                onClick={handleSelectCamera}
              >
                <div className="sheet-option-icon camera">
                  <CameraIcon size={24} weight="bold" aria-hidden="true" />
                </div>
                <div className="sheet-option-text">
                  <strong>Kamera</strong>
                  <small>Ambil foto langsung di kebun</small>
                </div>
              </button>

              <button
                type="button"
                className="sheet-option-card"
                onClick={handleOpenGallery}
              >
                <div className="sheet-option-icon gallery">
                  <ImageIcon size={24} weight="bold" aria-hidden="true" />
                </div>
                <div className="sheet-option-text">
                  <strong>Galeri</strong>
                  <small>Pilih dari penyimpanan perangkat</small>
                </div>
              </button>
            </div>

            <button
              type="button"
              className="sheet-cancel-btn"
              onClick={() => setIsSheetOpen(false)}
            >
              Batal
            </button>
          </div>
        </div>
      )}

      {/* -------------------------------------------------------------
          CAMERA VIEW MODAL (LIVE CAPTURE & PREVIEW)
          ------------------------------------------------------------- */}
      {isCameraOpen && (
        <div
          className="camera-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="Kamera PisGo"
        >
          <div className="camera-modal-content">
            <header className="camera-modal-header">
              <div className="camera-header-info">
                <span className="camera-badge">Inspeksi Kamera</span>
                <h3 className="camera-modal-title">
                  {cameraStatus === "captured" ? "Pratinjau Hasil Foto" : "Arahkan ke Tandan Pisang"}
                </h3>
              </div>
              <button
                type="button"
                className="camera-modal-close-btn"
                onClick={handleCloseCamera}
                aria-label="Tutup kamera"
              >
                <XIcon size={20} weight="bold" />
              </button>
            </header>

            {/* Camera Stage Container */}
            <div className="camera-stage-box">
              {/* Video Element for live preview */}
              <video
                ref={videoRef}
                playsInline
                muted
                autoPlay
                className={`camera-video-stream ${cameraStatus === "captured" ? "hidden" : ""}`}
              />

              {/* Inspection corner overlay */}
              <div className="camera-inspection-reticle" aria-hidden="true">
                <span className="reticle-corner top-left" />
                <span className="reticle-corner top-right" />
                <span className="reticle-corner bottom-left" />
                <span className="reticle-corner bottom-right" />
              </div>

              {/* Status Overlay: Requesting */}
              {cameraStatus === "requesting" && (
                <div className="camera-state-overlay" aria-live="polite">
                  <SpinnerGapIcon className="spin" size={36} weight="bold" />
                  <p>Menyiapkan kamera...</p>
                </div>
              )}

              {/* Status Overlay: Error / Permission Denied */}
              {cameraStatus === "error" && (
                <div className="camera-state-overlay error" role="alert">
                  <WarningCircleIcon size={40} weight="bold" />
                  <p className="error-text">{cameraErrorMessage ?? "Kamera tidak dapat diakses."}</p>
                  <div className="camera-error-actions">
                    <button
                      type="button"
                      className="camera-btn-retry"
                      onClick={() => startCamera()}
                    >
                      <ArrowClockwiseIcon size={16} weight="bold" />
                      <span>Coba Lagi</span>
                    </button>
                    <button
                      type="button"
                      className="camera-btn-gallery-fallback"
                      onClick={() => {
                        handleCloseCamera();
                        fileInputRef.current?.click();
                      }}
                    >
                      <ImageIcon size={16} weight="bold" />
                      <span>Pilih dari Galeri</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Status Overlay: Captured Frame Preview */}
              {cameraStatus === "captured" && capturedPreviewUrl && (
                <div className="camera-captured-preview-wrap">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={capturedPreviewUrl}
                    alt="Hasil jepretan kamera spesimen pisang"
                    className="captured-img-preview"
                  />
                  {capturedAt && (
                    <div className="captured-timestamp-badge">
                      <span>Waktu foto: {getLocalDateString(capturedAt)}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Bottom Actions Bar */}
            <footer className="camera-modal-footer">
              {cameraStatus === "live" && (
                <div className="camera-live-controls">
                  <button
                    type="button"
                    className="camera-cancel-text-btn"
                    onClick={handleCloseCamera}
                  >
                    Batal
                  </button>

                  <button
                    type="button"
                    className="camera-shutter-btn"
                    onClick={handleCapturePhoto}
                    aria-label="Ambil Foto"
                    title="Ambil Foto"
                  >
                    <div className="shutter-inner-ring" />
                  </button>

                  <div className="camera-placeholder-spacer" aria-hidden="true" />
                </div>
              )}

              {cameraStatus === "captured" && (
                <div className="camera-preview-controls">
                  <button
                    type="button"
                    className="camera-action-retake-btn"
                    onClick={handleRetakePhoto}
                  >
                    <ArrowCounterClockwiseIcon size={18} weight="bold" />
                    <span>Foto Ulang</span>
                  </button>
                  <button
                    type="button"
                    className="camera-action-use-btn"
                    onClick={handleUseCapturedPhoto}
                  >
                    <CheckIcon size={18} weight="bold" />
                    <span>Pakai Foto Ini</span>
                  </button>
                </div>
              )}

              {(cameraStatus === "requesting" || cameraStatus === "error") && (
                <div className="camera-live-controls">
                  <button
                    type="button"
                    className="camera-cancel-text-btn"
                    onClick={handleCloseCamera}
                  >
                    Tutup
                  </button>
                </div>
              )}
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function ImagePreview({
  file,
  onOpenSheet,
  onRemove,
}: {
  file: File;
  onOpenSheet: () => void;
  onRemove: (e: React.MouseEvent) => void;
}) {
  const [preview, setPreview] = useState("");

  useEffect(() => {
    const reader = new FileReader();
    reader.addEventListener("load", () => setPreview(typeof reader.result === "string" ? reader.result : ""));
    reader.readAsDataURL(file);
    return () => reader.abort();
  }, [file]);

  return (
    <>
      {preview && (
        <Image
          src={preview}
          alt="Foto tandan pisang Cavendish terpilih"
          fill
          unoptimized
          className="photo-preview"
          sizes="(max-width: 860px) 100vw, 420px"
        />
      )}
      <div className="photo-caption">
        <div className="caption-meta">
          <span className="meta-tag">FOTO PISANG</span>
          <strong className="meta-filename">{file.name}</strong>
          <small className="meta-size">{formatFileSize(file.size)}</small>
        </div>
        <div className="photo-actions">
          <button
            type="button"
            className="action-btn replace"
            onClick={(e) => {
              e.stopPropagation();
              onOpenSheet();
            }}
          >
            <UploadSimpleIcon aria-hidden="true" size={14} weight="bold" />
            <span>Ganti</span>
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="action-btn remove"
          >
            <XIcon aria-hidden="true" size={14} weight="bold" />
            <span>Hapus</span>
          </button>
        </div>
      </div>
    </>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return "< 1 KB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024)} MB`;
}
