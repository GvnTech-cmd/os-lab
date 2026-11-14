/** Shared formatting, labeling and ordering for the cleanup views. */

/** Human size, one decimal: 42 B, 3.5 KiB, 128.0 MiB, 2.4 GiB, 1.1 TiB. */
export function bytes(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let unit = 0;
  let size = value;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}

/** Badge tone for a catalog risk class. */
export function riskTone(risk: string): "success" | "warning" | "danger" | undefined {
  return risk === "low" ? "success" : risk === "medium" ? "warning" : risk === "high" ? "danger" : undefined;
}

/** Spoken label for a catalog risk class; unknown values fall back to "High risk". */
export function riskLabel(risk: string): string {
  const labels: Record<string, string> = {
    low: "Low risk", medium: "Medium risk", high: "High risk",
    credentials: "Credentials", privacy: "Private data"
  };
  return labels[risk] ?? "High risk";
}

/** Sort rank for risks: safe first, credentials and privacy last. */
export function riskRank(risk: string): number {
  const ranks: Record<string, number> = { low: 0, medium: 1, high: 2, credentials: 3, privacy: 3 };
  return ranks[risk] ?? 2;
}

/** Display label for a plan or clean item status; server values pass through. */
export function itemStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ready: "Ready", skipped: "Skipped", trashed: "Trashed", deleted: "Deleted", failed: "Failed"
  };
  return labels[status] ?? status;
}

export type SortOrder = "size" | "cleanable";

type Sortable = { id: string; name: string; risk: string; defaultSelected?: boolean };

/**
 * Sort entries for review: "size" puts measured entries first by descending size and
 * unmeasured ones after in cleanability order; "cleanable" puts likely-safe,
 * default-selected entries first. Ties fall back to risk, then name.
 */
export function sortEntries<T extends Sortable>(
  entries: readonly T[],
  sizes: ReadonlyMap<string, number> | null,
  order: SortOrder
): T[] {
  const safe = (a: T, b: T) =>
    Number(b.defaultSelected ?? false) - Number(a.defaultSelected ?? false)
    || riskRank(a.risk) - riskRank(b.risk)
    || a.name.localeCompare(b.name);
  if (order === "cleanable" || !sizes) return [...entries].sort(safe);
  return [...entries].sort((a, b) => {
    const sizeA = sizes.get(a.id);
    const sizeB = sizes.get(b.id);
    if (sizeA != null && sizeB != null) return sizeB - sizeA || safe(a, b);
    if (sizeA != null) return -1;
    if (sizeB != null) return 1;
    return safe(a, b);
  });
}

/** Sum of measured sizes per risk class, in stable risk order, zero classes dropped. */
export function totalsByRisk(
  entries: readonly { id: string; risk: string }[],
  sizes: ReadonlyMap<string, number>
): { risk: string; sizeBytes: number }[] {
  const totals = new Map<string, number>();
  for (const entry of entries) {
    const size = sizes.get(entry.id);
    if (size == null) continue;
    totals.set(entry.risk, (totals.get(entry.risk) ?? 0) + size);
  }
  return [...totals.entries()]
    .sort((a, b) => riskRank(a[0]) - riskRank(b[0]))
    .map(([risk, sizeBytes]) => ({ risk, sizeBytes }));
}

/** Friendly, accurate label for a container action id such as "containers.docker.dangling-images". */
export function containerActionLabel(actionId: string): string {
  const slugs: Record<string, string> = {
    "build-cache": "Build cache", "dangling-images": "Dangling images",
    "stopped-containers": "Stopped containers", "dangling-volumes": "Dangling volumes"
  };
  const slug = actionId.split(".").at(-1) ?? "";
  return slugs[slug] ?? actionId;
}
