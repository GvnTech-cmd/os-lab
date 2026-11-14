/**
 * CLNP-21/22: the overview page pieces — the storage hero card and the
 * grouped capability card grids, in the reference screenshot's layout (big
 * available number, segmented used/available bar, CTA card, two-column card
 * grids) using the lab's own tokens. Behaviour is ported; Qleaner's colours,
 * code and known bugs are not.
 *
 * Every card states where it goes (a tab, or an on-page section anchor) and,
 * when the host does not support it, renders dimmed with the reason instead
 * of hiding silently.
 */
import {
  ArrowRightIcon, ArrowsClockwiseIcon, BroomIcon, BugIcon, CubeIcon, CubeTransparentIcon,
  HardDrivesIcon, MagnifyingGlassIcon, ShieldCheckIcon, SparkleIcon, TrayIcon, WrenchIcon,
  ArchiveIcon, PuzzlePieceIcon, PackageIcon
} from "@phosphor-icons/react";
import { Section } from "../../components/ui";
import { formatBytes, type CleanupStatus, type CleanupVolume } from "../../lib/api";

/** CLNP-22: the storage hero. Purgeable renders only when a probe proved it. */
export function StorageHero({
  volumes, onRefresh
}: {
  volumes: CleanupVolume[] | null; onRefresh: () => void;
}) {
  const measured = (volumes ?? []).filter((volume) => !volume.error && volume.totalBytes && volume.freeBytes != null);
  if (!measured.length) return null;
  const selected = measured.find((volume) => volume.isHome) ?? measured[0];
  const total = selected.totalBytes ?? 0;
  const free = selected.freeBytes ?? 0;
  const used = selected.usedBytes ?? Math.max(0, total - free);
  const purgeable = selected.purgeableBytes != null && selected.purgeableBytes <= used ? selected.purgeableBytes : null;
  const segments = [
    { key: "used", size: Math.max(0, used - (purgeable ?? 0)), className: "bg-[#7a7a72]" },
    ...(purgeable != null && purgeable > 0 ? [{ key: "purgeable", size: purgeable, className: "bg-(--iux-warning)" }] : []),
    { key: "available", size: free, className: "bg-[#f36c21]" },
  ];
  return <Section
    id="overview-storage"
    title={selected.isHome ? "This computer's storage" : "Storage"}
    action={<button type="button" className="iux-btn" data-variant="ghost" title="Re-measure" onClick={onRefresh}>
      <ArrowsClockwiseIcon size={16} />
    </button>}
    description={<span>
      {selected.usage != null && <span dir="ltr">{Math.round(selected.usage * 100)}% used · </span>}
      <span translate="no">{selected.mountPoint}</span>
      {selected.pressure === "warning" && <span className="text-(--iux-danger)"> · running low</span>}
    </span>}>
    <div className="flex flex-wrap items-baseline gap-2">
      <span dir="ltr" className="text-3xl font-bold tabular-nums">{formatBytes(free)}</span>
      <span className="text-sm text-(--iux-muted-foreground)">available</span>
      <span dir="ltr" className="ms-auto text-sm tabular-nums text-(--iux-muted-foreground)">{formatBytes(total)} total</span>
    </div>
    <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-(--iux-muted)" aria-hidden="true">
      {segments.filter((segment) => segment.size > 0).map((segment) =>
        <span key={segment.key} className={segment.className} style={{ width: `${(segment.size / total) * 100}%` }} />)}
    </div>
    <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
      <span className="flex items-center gap-1.5"><span aria-hidden="true" className="size-2 rounded-full bg-[#7a7a72]" />Used <span dir="ltr" className="tabular-nums">{formatBytes(used)}</span></span>
      {purgeable != null && purgeable > 0 && <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="size-2 rounded-full bg-(--iux-warning)" />Purgeable <span dir="ltr" className="tabular-nums">{formatBytes(purgeable)}</span>
      </span>}
      <span className="flex items-center gap-1.5"><span aria-hidden="true" className="size-2 rounded-full bg-[#f36c21]" />Available <span dir="ltr" className="tabular-nums">{formatBytes(free)}</span></span>
    </div>
    {purgeable == null && <p className="mt-1 text-xs text-(--iux-muted-foreground)">
      Purgeable space is managed by macOS and is only shown when the system probe reports it.
    </p>}
    {measured.length > 1 && <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-(--iux-muted-foreground)">Other volumes ({measured.length - 1})</summary>
      <ul className="mt-1 space-y-1">
        {measured.filter((volume) => volume.mountPoint !== selected.mountPoint).map((volume) => <li key={volume.mountPoint} className="flex gap-2" translate="no">
          <span className="truncate">{volume.mountPoint}</span>
          <span dir="ltr" className="ms-auto tabular-nums text-(--iux-muted-foreground)">
            {formatBytes(volume.freeBytes)} free · {volume.kind}
          </span>
        </li>)}
      </ul>
    </details>}
  </Section>;
}

export type OverviewCard = {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  /** A cleanup tab (navigated in place) or an on-page section anchor. */
  target: string;
  onTab: boolean;
  available?: boolean;
  note?: string;
};

const CARDS: { group: string; cards: OverviewCard[] }[] = [
  {
    group: "Storage & cleanup",
    cards: [
      { id: "scan-now", title: "Quick cleanup", description: "Scan all safe categories and review a plan", icon: <BroomIcon size={18} />, target: "overview-review", onTab: false },
      { id: "advanced-scan", title: "Advanced scan", description: "Choose individual items, modes and tools", icon: <MagnifyingGlassIcon size={18} />, target: "scan/", onTab: true },
      { id: "results", title: "Results", description: "The latest scan, by category and size", icon: <TrayIcon size={18} />, target: "results/", onTab: true },
      { id: "leftovers", title: "Leftovers", description: "Skipped, failed and unreadable items", icon: <BugIcon size={18} />, target: "leftovers/", onTab: true },
      { id: "history", title: "History", description: "Verified audit runs on this computer", icon: <ArchiveIcon size={18} />, target: "history/", onTab: true },
      { id: "bookmarks", title: "Bookmarks", description: "Your cleanup favourites, quick clean and hooks", icon: <SparkleIcon size={18} />, target: "cleanup-bookmarks", onTab: false },
      { id: "space", title: "Space Explorer", description: "Browse folders by size, like dua", icon: <HardDrivesIcon size={18} />, target: "space/", onTab: true },
    ],
  },
  {
    group: "System & maintenance",
    cards: [
      { id: "monitor", title: "Background monitor", description: "Warns when free space crosses a threshold", icon: <ShieldCheckIcon size={18} />, target: "cleanup-monitor", onTab: false },
      { id: "permissions", title: "Permissions", description: "Full Disk Access and hidden-folder grants", icon: <ShieldCheckIcon size={18} />, target: "cleanup-permissions", onTab: false },
      { id: "containers", title: "Containers & VMs", description: "Docker, Podman and virtual-machine inventories", icon: <CubeIcon size={18} />, target: "scan/", onTab: true },
      { id: "packages", title: "Package review", description: "Homebrew, pip and gem cleanup candidates", icon: <PackageIcon size={18} />, target: "scan/", onTab: true },
      { id: "privileged", title: "Privileged actions", description: "System maintenance through the desktop's own elevation", icon: <WrenchIcon size={18} />, target: "scan/", onTab: true, available: false, note: "Check availability on the Advanced scan page" },
      { id: "projects", title: "Projects deep scan", description: "Marker-verified build artifacts and projects", icon: <CubeTransparentIcon size={18} />, target: "scan/", onTab: true },
      { id: "simulators", title: "Simulators", description: "iOS and Android simulator inventories", icon: <PuzzlePieceIcon size={18} />, target: "scan/", onTab: true },
      { id: "relocation", title: "Relocation", description: "Move a cache to another volume behind a symlink", icon: <ArrowsClockwiseIcon size={18} />, target: "scan/", onTab: true },
      { id: "storage", title: "Volumes", description: "Every local volume, capacity and pressure", icon: <HardDrivesIcon size={18} />, target: "overview-storage", onTab: false },
    ],
  },
];

function CardTile({ card, go }: { card: OverviewCard; go: (card: OverviewCard) => void }) {
  const dimmed = card.available === false;
  const inner = <>
    <span className="mt-0.5 text-[#f36c21]">{card.icon}</span>
    <span className="min-w-0 flex-1">
      <span className="flex items-center gap-2 text-sm font-medium">{card.title}</span>
      <span className="mt-0.5 block truncate text-xs text-(--iux-muted-foreground)">
        {dimmed ? card.note : card.description}
      </span>
    </span>
    <ArrowRightIcon size={14} className="text-(--iux-muted-foreground)" />
  </>;
  const className = `flex w-full items-start gap-3 rounded-md border border-(--iux-border) p-3 text-start transition-colors hover:border-[#f36c21]/60 hover:bg-[#f36c21]/5 ${dimmed ? "opacity-60" : ""}`;
  return <button type="button" className={className} disabled={dimmed} onClick={() => go(card)}>{inner}</button>;
}

export function OverviewCards({ go }: { go: (card: OverviewCard) => void }) {
  return <>
    {CARDS.map(({ group, cards }) => <div key={group}>
      <h3 className="text-sm font-semibold">{group}</h3>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {cards.map((card) => <CardTile key={card.id} card={card} go={go} />)}
      </div>
    </div>)}
  </>;
}
