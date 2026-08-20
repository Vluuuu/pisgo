"use client";

import {
  MotorcycleIcon,
  ShippingContainerIcon,
  TruckIcon,
  TruckTrailerIcon,
  VanIcon,
} from "@phosphor-icons/react";
import type { ComponentType } from "react";
import type { RoutingVehicleMode } from "@/types/location";

type IconProps = {
  size?: number | string;
  weight?: "thin" | "light" | "regular" | "bold" | "fill" | "duotone";
  className?: string;
  "aria-hidden"?: boolean | "true" | "false";
};

export const VEHICLE_ICON_MAP: Record<RoutingVehicleMode, ComponentType<IconProps>> = {
  motorcycle: MotorcycleIcon,
  light_truck: VanIcon,
  medium_truck: TruckIcon,
  truck: TruckTrailerIcon,
  heavy_truck: ShippingContainerIcon,
};

export function VehicleModeIcon({
  mode,
  size = 18,
  weight = "bold",
  className,
  "aria-hidden": ariaHidden = true,
}: {
  mode: RoutingVehicleMode;
  size?: number | string;
  weight?: "thin" | "light" | "regular" | "bold" | "fill" | "duotone";
  className?: string;
  "aria-hidden"?: boolean | "true" | "false";
}) {
  const IconComponent = VEHICLE_ICON_MAP[mode] ?? TruckIcon;
  return <IconComponent size={size} weight={weight} className={className} aria-hidden={ariaHidden} />;
}
