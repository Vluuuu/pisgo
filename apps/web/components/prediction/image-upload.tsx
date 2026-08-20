"use client";

import Image from "next/image";
import { CameraIcon, UploadSimpleIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";

type ImageUploadProps = {
  value: File | null;
  onChange: (file: File | null) => void;
  error?: string;
};

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

export function ImageUpload({ value, onChange, error }: ImageUploadProps) {
  const inputId = useId();
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

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

      <div className="specimen-frame-stage" data-error={Boolean(error)} data-dragging={isDragging}>
        {/* Inspection Corner Marks */}
        <span className="frame-corner top-left" aria-hidden="true" />
        <span className="frame-corner top-right" aria-hidden="true" />
        <span className="frame-corner bottom-left" aria-hidden="true" />
        <span className="frame-corner bottom-right" aria-hidden="true" />

        {value ? (
          <ImagePreview file={value} inputId={inputId} onRemove={() => onChange(null)} />
        ) : (
          <label className="photo-prompt" htmlFor={inputId}>
            <div className="prompt-icon-ring">
              <CameraIcon aria-hidden="true" size={26} weight="bold" />
            </div>
            <div className="prompt-text-group">
              <strong>{isDragging ? "Lepaskan foto pisang di sini" : "Pilih atau Tarik Foto Pisang"}</strong>
              <small>Foto 1 tandan penuh, pencahayaan alami terang di kebun</small>
            </div>
          </label>
        )}

        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-labelledby={`${inputId}-label`}
          onClick={(event) => { event.currentTarget.value = ""; setValidationError(null); }}
          onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
        />
      </div>

      {(error ?? validationError) && <p role="alert" className="field-error">{error ?? validationError}</p>}
    </div>
  );
}

function ImagePreview({ file, inputId, onRemove }: { file: File; inputId: string; onRemove: () => void }) {
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
          <label htmlFor={inputId} className="action-btn replace">
            <UploadSimpleIcon aria-hidden="true" size={14} weight="bold" />
            <span>Ganti</span>
          </label>
          <button type="button" onClick={onRemove} className="action-btn remove">
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
