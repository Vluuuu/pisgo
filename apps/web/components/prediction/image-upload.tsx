"use client";

import Image from "next/image";
import { CameraIcon, UploadSimpleIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useId, useState } from "react";

type ImageUploadProps = {
  value: File | null;
  onChange: (file: File | null) => void;
  error?: string;
};

export function ImageUpload({ value, onChange, error }: ImageUploadProps) {
  const inputId = useId();
  const [isDragging, setIsDragging] = useState(false);

  function handleDrop(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      return;
    }
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
        handleDrop(event.dataTransfer.files?.[0] ?? null);
      }}
    >
      <div className="field-heading">
        <label id={`${inputId}-label`} htmlFor={inputId}>Foto tandan</label>
        <span>JPG, PNG, WebP · maks. 10 MB</span>
      </div>

      <div className="photo-stage" data-error={Boolean(error)} data-dragging={isDragging}>
        {value ? (
          <ImagePreview file={value} inputId={inputId} onRemove={() => onChange(null)} />
        ) : (
          <label className="photo-prompt" htmlFor={inputId}>
            <CameraIcon aria-hidden="true" size={24} weight="regular" />
            <span>
              <strong>{isDragging ? "Lepaskan foto di sini" : "Seret foto tandan ke sini"}</strong>
              <small>Pilih foto atau seret ke area ini</small>
            </span>
          </label>
        )}

        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          aria-labelledby={`${inputId}-label`}
          onClick={(event) => { event.currentTarget.value = ""; }}
          onChange={(event) => onChange(event.target.files?.[0] ?? null)}
        />
      </div>

      {error && <p role="alert" className="field-error">{error}</p>}
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
      {preview && <Image src={preview} alt="Foto tandan pisang Cavendish terpilih" fill unoptimized className="photo-preview" sizes="(max-width: 860px) 100vw, 400px" />}
      <div className="photo-caption">
        <span><strong>{file.name}</strong><small>{formatFileSize(file.size)}</small></span>
        <span className="photo-actions">
          <label htmlFor={inputId}><UploadSimpleIcon aria-hidden="true" size={15} /> Ganti</label>
          <button type="button" onClick={onRemove}><XIcon aria-hidden="true" size={15} /> Hapus</button>
        </span>
      </div>
    </>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return "< 1 KB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 }).format(bytes / 1024 / 1024)} MB`;
}
