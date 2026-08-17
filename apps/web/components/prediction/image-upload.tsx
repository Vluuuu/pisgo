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

  return (
    <div className="upload-field">
      <div className="field-heading">
        <label id={`${inputId}-label`} htmlFor={inputId}>Photo</label>
        <span>JPG, PNG, WebP · max. 10 MB</span>
      </div>

      <div className="photo-stage" data-error={Boolean(error)}>
        {value ? (
          <ImagePreview file={value} inputId={inputId} onRemove={() => onChange(null)} />
        ) : (
          <label className="photo-prompt" htmlFor={inputId}>
            <CameraIcon aria-hidden="true" size={24} weight="regular" />
            <span>
              <strong>Select photo</strong>
              <small>Clear banana bunch in even light</small>
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
      {preview && <Image src={preview} alt="Selected Cavendish banana bunch specimen" fill unoptimized className="photo-preview" sizes="(max-width: 860px) 100vw, 400px" />}
      <div className="photo-caption">
        <span><strong>{file.name}</strong><small>{formatFileSize(file.size)}</small></span>
        <span className="photo-actions">
          <label htmlFor={inputId}><UploadSimpleIcon aria-hidden="true" size={15} /> Replace</label>
          <button type="button" onClick={onRemove}><XIcon aria-hidden="true" size={15} /> Remove</button>
        </span>
      </div>
    </>
  );
}

function formatFileSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
