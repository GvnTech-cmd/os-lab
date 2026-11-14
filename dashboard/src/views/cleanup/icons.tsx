/** Monoline icon maps for cleanup categories and item statuses. */
import type { ReactNode } from "react";
import {
  CheckCircleIcon,
  CodeIcon,
  GearIcon,
  GlobeSimpleIcon,
  HardDrivesIcon,
  LockIcon,
  MinusCircleIcon,
  PauseIcon,
  TrashIcon,
  WarningCircleIcon,
  XIcon
} from "@phosphor-icons/react";

/** Category icon: system → gear, browsers → globe, developer → code; unknown → hard drives. */
export function CategoryIcon({ category, size = 14 }: { category: string; size?: number }) {
  const icon =
    category === "system" ? <GearIcon size={size} /> :
    category === "browser" ? <GlobeSimpleIcon size={size} /> :
    category === "developer" ? <CodeIcon size={size} /> :
    <HardDrivesIcon size={size} />;
  return <span className="text-(--iux-muted-foreground)" aria-hidden="true">{icon}</span>;
}

/** Status icon for plan and clean items; unknown statuses get a neutral dash. */
export function StatusIcon({ status, size = 13 }: { status: string; size?: number }) {
  const icon: ReactNode =
    status === "ready" ? <CheckCircleIcon size={size} /> :
    status === "trashed" ? <TrashIcon size={size} /> :
    status === "deleted" ? <XIcon size={size} weight="bold" /> :
    status === "skipped" ? <PauseIcon size={size} /> :
    status === "failed" ? <WarningCircleIcon size={size} /> :
    <MinusCircleIcon size={size} />;
  const tone =
    status === "ready" || status === "trashed" ? "text-(--iux-success)" :
    status === "deleted" ? "text-(--iux-muted-foreground)" :
    status === "failed" ? "text-(--iux-danger)" :
    "text-(--iux-muted-foreground)";
  return <span aria-hidden="true" className={tone}>{icon}</span>;
}

/** Small marker for entries that need administrator privileges to clean. */
export function PrivilegeMarker({ size = 12 }: { size?: number }) {
  return <span aria-hidden="true" className="text-(--iux-muted-foreground)" title="Requires administrator privileges"><LockIcon size={size} /></span>;
}
