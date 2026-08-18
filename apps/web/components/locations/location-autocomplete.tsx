"use client";

import { MapPinIcon, SpinnerGapIcon } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState } from "react";
import type { LocationSuggestion } from "@/types/location";

type LocationAutocompleteProps = {
  label: string;
  value: LocationSuggestion | null;
  onChange: (value: LocationSuggestion | null) => void;
  placeholder: string;
};

export function LocationAutocomplete({ label, value, onChange, placeholder }: LocationAutocompleteProps) {
  const inputId = useId();
  const listboxId = useId();
  const [query, setQuery] = useState(value?.label ?? "");
  const [results, setResults] = useState<LocationSuggestion[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "empty" | "error">("idle");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (value?.label === query || query.trim().length < 3) return;

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading");
      setOpen(true);
      try {
        const response = await fetch(`/api/geoapify/autocomplete?q=${encodeURIComponent(query.trim())}`, { signal: controller.signal });
        const data = (await response.json()) as { results?: LocationSuggestion[]; error?: string };
        if (!response.ok) throw new Error(data.error ?? "Location search failed.");
        const nextResults = data.results ?? [];
        setResults(nextResults);
        setStatus(nextResults.length ? "ready" : "empty");
        setActiveIndex(nextResults.length ? 0 : -1);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setResults([]);
        setStatus("error");
      }
    }, 350);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, value?.label]);

  function select(suggestion: LocationSuggestion) {
    if (blurTimer.current) clearTimeout(blurTimer.current);
    setQuery(suggestion.label);
    onChange(suggestion);
    setOpen(false);
    setStatus("idle");
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (event.key === "ArrowDown" && results.length) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? results.length - 1 : index - 1));
    } else if (event.key === "Enter" && open && activeIndex >= 0) {
      event.preventDefault();
      select(results[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="location-field">
      <label htmlFor={inputId}>{label}</label>
      <div className="location-input-wrap">
        <MapPinIcon aria-hidden="true" size={18} weight="regular" />
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-activedescendant={open && activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
          autoComplete="off"
          className="field location-input"
          placeholder={placeholder}
          value={query}
          onChange={(event) => {
            const nextQuery = event.target.value;
            setQuery(nextQuery);
            onChange(null);
            setOpen(nextQuery.trim().length >= 3);
            if (nextQuery.trim().length < 3) {
              setResults([]);
              setStatus("idle");
              setActiveIndex(-1);
            }
          }}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 150); }}
          onKeyDown={handleKeyDown}
        />
        {status === "loading" && <SpinnerGapIcon aria-label="Searching locations" className="location-spinner" size={19} />}
      </div>
      {open && status !== "idle" && (
        <div className="location-results">
          {status === "ready" ? (
            <ul id={listboxId} role="listbox">
              {results.map((result, index) => (
                <li
                  id={`${listboxId}-${index}`}
                  key={result.id}
                  role="option"
                  aria-selected={index === activeIndex}
                  data-active={index === activeIndex}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => select(result)}
                >
                  <span>{result.label}</span>
                  {(result.city || result.state) && <small>{[result.city, result.state].filter(Boolean).join(", ")}</small>}
                </li>
              ))}
            </ul>
          ) : (
            <p role="status" className="location-status">
              {status === "loading" ? "Mencari lokasi…" : status === "empty" ? "Tidak ada lokasi ditemukan. Coba pencarian lain." : "Pencarian lokasi gagal. Periksa koneksi dan coba lagi."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
