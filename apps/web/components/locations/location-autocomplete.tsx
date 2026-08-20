"use client";

import { MapPinIcon, SpinnerGapIcon } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState } from "react";
import type { LocationFlowLinkage, LocationSuggestion } from "@/types/location";

type SuggestionItem =
  | {
      status: "resolved";
      location: LocationSuggestion;
    }
  | {
      status: "pending";
      id: string;
      label: string;
      subtitles?: string;
      more: LocationFlowLinkage;
    };

type LocationAutocompleteProps = {
  label: string;
  value: LocationSuggestion | null;
  onChange: (value: LocationSuggestion | null) => void;
  placeholder: string;
};

function generateUUIDv4(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) => {
    const num = Number(c);
    return (num ^ (Math.floor(Math.random() * 16) >> (num / 4))).toString(16);
  });
}

export function LocationAutocomplete({ label, value, onChange, placeholder }: LocationAutocompleteProps) {
  const inputId = useId();
  const listboxId = useId();
  const [query, setQuery] = useState(value?.label ?? "");
  const [results, setResults] = useState<SuggestionItem[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "empty" | "error">("idle");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionIdRef = useRef<string>("");
  const requestGenerationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);

  function getSessionId(): string {
    if (!sessionIdRef.current) {
      sessionIdRef.current = generateUUIDv4();
    }
    return sessionIdRef.current;
  }

  function resetSessionId() {
    sessionIdRef.current = "";
  }

  useEffect(() => {
    if (value?.label === query || query.trim().length < 3) return;

    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const requestGeneration = ++requestGenerationRef.current;
    const sessionId = getSessionId();
    const typedQuery = query.trim();

    const timer = setTimeout(async () => {
      setStatus("loading");
      setOpen(true);
      try {
        const response = await fetch(
          `/api/locations?q=${encodeURIComponent(typedQuery)}&sessionId=${encodeURIComponent(sessionId)}`,
          { signal: controller.signal },
        );
        const data = (await response.json()) as { results?: SuggestionItem[]; error?: string };
        if (!response.ok) throw new Error(data.error ?? "Location search failed.");
        if (requestGeneration !== requestGenerationRef.current) return;
        const nextResults = data.results ?? [];
        setResults(nextResults);
        setStatus(nextResults.length ? "ready" : "empty");
        setActiveIndex(-1);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (requestGeneration !== requestGenerationRef.current) return;
        setResults([]);
        setStatus("error");
      }
    }, 350);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, value?.label]);

  async function searchCompleteQuery() {
    const typedQuery = query.trim();
    if (typedQuery.length < 3) return;

    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const requestGeneration = ++requestGenerationRef.current;
    setStatus("loading");
    setOpen(true);

    try {
      const response = await fetch(
        `/api/locations?mode=search&q=${encodeURIComponent(typedQuery)}&sessionId=${encodeURIComponent(getSessionId())}`,
        { signal: controller.signal },
      );
      const data = (await response.json()) as { results?: LocationSuggestion[]; error?: string };
      if (!response.ok) throw new Error(data.error ?? "Location search failed.");
      if (requestGeneration !== requestGenerationRef.current) return;
      const nextResults = (data.results ?? []).map((location): SuggestionItem => ({ status: "resolved", location }));
      setResults(nextResults);
      setStatus(nextResults.length ? "ready" : "empty");
      setActiveIndex(-1);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (requestGeneration !== requestGenerationRef.current) return;
      setResults([]);
      setStatus("error");
    }
  }

  async function select(suggestion: SuggestionItem) {
    if (blurTimer.current) clearTimeout(blurTimer.current);

    if (suggestion.status === "resolved") {
      setQuery(suggestion.location.label);
      onChange(suggestion.location);
      setOpen(false);
      setStatus("idle");
      resetSessionId();
      return;
    }

    if (suggestion.status === "pending" && suggestion.more) {
      setStatus("loading");
      try {
        const response = await fetch("/api/locations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            more: suggestion.more,
            sessionId: getSessionId(),
          }),
        });
        const data = (await response.json()) as { result?: LocationSuggestion; error?: string };
        if (!response.ok || !data.result) throw new Error(data.error ?? "Could not get location details.");

        setQuery(data.result.label);
        onChange(data.result);
        setOpen(false);
        setStatus("idle");
        resetSessionId();
        return;
      } catch {
        setStatus("error");
        return;
      }
    }

    setStatus("error");
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
    } else if (event.key === "Enter") {
      if (open && activeIndex >= 0 && results[activeIndex]) {
        event.preventDefault();
        void select(results[activeIndex]);
      } else if (query.trim().length >= 3) {
        event.preventDefault();
        void searchCompleteQuery();
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showFoursquareAttribution =
    value?.provider === "foursquare" ||
    results.some((r) => r.status === "resolved" && r.location.provider === "foursquare");

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
              resetSessionId();
            }
          }}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 150); }}
          onKeyDown={handleKeyDown}
        />
        {status === "loading" && <SpinnerGapIcon aria-label="Mencari lokasi" className="location-spinner" size={19} />}
      </div>
      {open && status !== "idle" && (
        <div className="location-results">
          {status === "ready" ? (
            <>
              <ul id={listboxId} role="listbox">
                {results.map((result, index) => {
                  const labelText = result.status === "resolved" ? result.location.label : result.label;
                  const subtitleText = result.status === "resolved"
                    ? [result.location.city, result.location.state].filter(Boolean).join(", ")
                    : result.subtitles;
                  const key = result.status === "resolved" ? result.location.id : result.id;

                  return (
                    <li
                      id={`${listboxId}-${index}`}
                      key={key}
                      role="option"
                      aria-selected={index === activeIndex}
                      data-active={index === activeIndex}
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => void select(result)}
                    >
                      <span>{labelText}</span>
                      {subtitleText && <small>{subtitleText}</small>}
                    </li>
                  );
                })}
              </ul>
              {showFoursquareAttribution && (
                <div className="foursquare-attribution">
                  <span>Powered by Foursquare</span>
                </div>
              )}
            </>
          ) : (
            <p role="status" className="location-status">
              {status === "loading" ? "Mencari lokasi…" : status === "empty" ? "Tidak ada lokasi ditemukan. Coba pencarian lain." : "Pencarian lokasi gagal. Periksa koneksi dan coba lagi."}
            </p>
          )}
        </div>
      )}
      {!open && value?.provider === "foursquare" && (
        <div className="foursquare-attribution-standalone">
          <span>Powered by Foursquare</span>
        </div>
      )}
    </div>
  );
}
