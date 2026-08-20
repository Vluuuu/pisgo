"use client";

import dynamic from "next/dynamic";
import type { LocationSuggestion } from "@/types/location";

const ManualLocationPicker = dynamic(
  () => import("./manual-location-picker").then((module) => module.ManualLocationPicker),
  {
    ssr: false,
  },
);

type ManualLocationPickerLoaderProps = {
  isOpen: boolean;
  fieldLabel: "Asal" | "Tujuan";
  initialLocation: LocationSuggestion | null;
  initialQuery?: string;
  onConfirm: (location: LocationSuggestion) => void;
  onClose: () => void;
};

export function ManualLocationPickerLoader(props: ManualLocationPickerLoaderProps) {
  if (!props.isOpen) return null;
  return <ManualLocationPicker {...props} />;
}
