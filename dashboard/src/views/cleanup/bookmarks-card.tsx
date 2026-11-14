/**
 * CLNP-18: the bookmarks section and the small bookmark toggle used on scan,
 * results and history rows.
 *
 * Bookmarks are catalog-entry references (the engine refuses raw paths); the
 * section orders them by priority, toggles the quick-clean flag and the
 * Trash-only auto-clean hook, edits the size-alert threshold and starts the
 * quick cleanup — which runs the normal plan → confirm → run flow, so the
 * confirmation dialog the caller already owns opens on the returned plan job.
 */
import { useState } from "react";
import { BookmarkIcon, BookmarkSimpleIcon, FolderPlusIcon } from "@phosphor-icons/react";
import { Badge, Empty, Section, Status } from "../../components/ui";
import { api, message, type BookmarksPayload, type BookmarkRecord, type CleanupJob } from "../../lib/api";
import { riskTone } from "./format";

/** A small bookmark toggle for rows that already know their entry id. */
export function BookmarkToggle({
  entryId, bookmarked, busy, onToggle, title = "Bookmark this item"
}: {
  entryId: string; bookmarked: boolean; busy?: boolean; onToggle: (entryId: string) => void; title?: string;
}) {
  return <button type="button" className="iux-btn" data-variant="ghost" title={title} disabled={busy}
    onClick={(event) => { event.preventDefault(); event.stopPropagation(); onToggle(entryId); }}
    onMouseDown={(event) => event.preventDefault()}>
    {bookmarked ? <BookmarkSimpleIcon size={14} weight="fill" className="text-[#f36c21]" /> : <BookmarkIcon size={14} />}
  </button>;
}

export function BookmarksSection({
  bookmarks, reload, onQuickClean, onCatalogChanged
}: {
  bookmarks: BookmarksPayload | null; reload: () => void; onQuickClean: (job: CleanupJob) => void;
  onCatalogChanged: () => void;
}) {
  const [error, setError] = useState("");
  const [refusals, setRefusals] = useState<{ entryId: string; reason: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customPath, setCustomPath] = useState("");

  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try {
      await action();
      reload();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  function move(entry: BookmarkRecord, direction: -1 | 1) {
    const ordered = [...(bookmarks?.bookmarks ?? [])].sort((a, b) => a.priority - b.priority);
    const index = ordered.findIndex((item) => item.entryId === entry.entryId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    const swapped = ordered[target];
    void act(async () => {
      await api.cleanupBookmarkUpdate(entry.entryId, { priority: swapped.priority });
      await api.cleanupBookmarkUpdate(swapped.entryId, { priority: entry.priority });
    });
  }

  const items = [...(bookmarks?.bookmarks ?? [])].sort((a, b) => a.priority - b.priority);

  /** CLNP-20: add a custom folder, validate it once, and bookmark it. */
  async function addCustomFolder() {
    if (!customName.trim() || !customPath.trim()) return;
    setBusy(true); setError(""); setRefusals([]);
    try {
      const created = await api.cleanupCustomAdd(customName.trim(), customPath.trim());
      if (created.error) throw new Error(created.error);
      const entry = created.entries[created.entries.length - 1];
      if (entry) await api.cleanupBookmarkAdd(entry.id);
      setCustomName(""); setCustomPath(""); setAdding(false);
      reload();
      onCatalogChanged();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  /** CLNP-20: removing a custom entry clears its bookmark with it. */
  async function removeCustomEntry(entryId: string) {
    setBusy(true); setError("");
    try {
      const removed = await api.cleanupCustomRemove(entryId);
      if (removed.error) throw new Error(removed.error);
      reload();
      onCatalogChanged();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  return <Section id="cleanup-bookmarks" title="Bookmarks" description="Your cleanup favourites, in the order they are cleaned. Quick cleanup still confirms before anything moves.">
    {bookmarks?.error && <Status value={{ ok: false, text: bookmarks.error }} />}
    {error && <Status value={{ ok: false, text: error }} />}
    {refusals.length > 0 && <Status value={{ ok: false, text: refusals.map((item) => item.reason).join(" ") }} />}
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className="iux-btn" data-variant="primary" disabled={busy || !items.some((item) => item.quickClean)}
        onClick={() => void act(async () => {
          const response = await api.cleanupBookmarkQuickClean();
          setRefusals(response.refusals);
          onQuickClean(response.job);
        })}>
        Quick clean bookmarks
      </button>
      <button type="button" className="iux-btn" disabled={busy} onClick={() => setAdding((value) => !value)}>
        <FolderPlusIcon size={14} className="inline" /> Add a folder
      </button>
      <span className="text-xs text-(--iux-muted-foreground)">
        {items.filter((item) => item.quickClean).length} of {items.length} included in quick cleanup
      </span>
    </div>
    {adding && <div className="mt-3 rounded-md border border-(--iux-border) p-3 text-sm">
      <p className="text-xs text-(--iux-muted-foreground)">
        The folder is checked once (it must exist, be a real folder, and never be a protected or system directory), then it joins the scan like any catalog entry.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input type="text" className="iux-input w-44" placeholder="Name" value={customName} disabled={busy}
          onChange={(event) => setCustomName(event.target.value)} />
        <input type="text" className="iux-input min-w-0 flex-1" placeholder="/absolute/path/to/folder" dir="ltr" translate="no" value={customPath} disabled={busy}
          onChange={(event) => setCustomPath(event.target.value)} />
        <button type="button" className="iux-btn" data-variant="primary" disabled={busy || !customName.trim() || !customPath.trim()}
          onClick={() => void addCustomFolder()}>Add and bookmark</button>
        <button type="button" className="iux-btn" onClick={() => setAdding(false)}>Cancel</button>
      </div>
    </div>}
    {items.length ? <div className="mt-3 divide-y divide-(--iux-border)">
      {items.map((item, index) => <div key={item.entryId} className="flex flex-wrap items-center gap-2 py-2 text-sm">
        <span className="tabular-nums text-xs text-(--iux-muted-foreground)" aria-label={`Priority ${item.priority}`}>{item.priority}</span>
        <button type="button" className="iux-btn" data-variant="ghost" title="Move up" disabled={busy || index === 0} onClick={() => move(item, -1)}>↑</button>
        <button type="button" className="iux-btn" data-variant="ghost" title="Move down" disabled={busy || index === items.length - 1} onClick={() => move(item, 1)}>↓</button>
        <span className="min-w-0 flex-1 truncate font-medium">{item.entry?.name ?? item.entryId}</span>
        {item.entryId.startsWith("custom.") && <Badge>Your folder</Badge>}
        {item.entry && <Badge tone={riskTone(item.entry.risk)}>{item.entry.risk}</Badge>}
        <label className="text-xs" title="Include in quick cleanup">
          <input type="checkbox" className="iux-touch-target mr-1 size-3.5 accent-[#f36c21]" checked={item.quickClean} disabled={busy}
            onChange={(event) => void act(() => api.cleanupBookmarkUpdate(item.entryId, { quickClean: event.target.checked }))} />
          quick clean
        </label>
        <label className="text-xs" title="Clean automatically (Trash only) when the free-space hook fires">
          <input type="checkbox" className="iux-touch-target mr-1 size-3.5 accent-[#f36c21]" checked={item.autoCleanHook.enabled} disabled={busy}
            onChange={(event) => void act(() => api.cleanupBookmarkUpdate(item.entryId, { autoCleanHook: { enabled: event.target.checked } }))} />
          auto-clean
        </label>
        <label className="text-xs" title="Notify when this item grows above the threshold">
          <input type="checkbox" className="iux-touch-target mr-1 size-3.5 accent-[#f36c21]" checked={item.sizeAlert.enabled} disabled={busy}
            onChange={(event) => void act(() => api.cleanupBookmarkUpdate(item.entryId, { sizeAlert: { ...item.sizeAlert, enabled: event.target.checked } }))} />
          alert over{" "}
          <input type="number" className="iux-input w-16" min={0} dir="ltr" disabled={busy || !item.sizeAlert.enabled} defaultValue={Math.round(item.sizeAlert.thresholdBytes / (1024 * 1024 * 1024) * 10) / 10}
            onBlur={(event) => void act(() => api.cleanupBookmarkUpdate(item.entryId, { sizeAlert: { ...item.sizeAlert, thresholdBytes: Math.max(0, Number(event.target.value) * 1024 * 1024 * 1024) } }))} />{" "}GiB
        </label>
        <button type="button" className="iux-btn" data-variant="ghost" disabled={busy} title="Remove bookmark"
          onClick={() => void act(() => api.cleanupBookmarkRemove(item.entryId))}>Remove</button>
        {item.entryId.startsWith("custom.") &&
          <button type="button" className="iux-btn" data-variant="ghost" disabled={busy} title="Delete this custom folder from the catalog (its bookmark goes with it)"
            onClick={() => void removeCustomEntry(item.entryId)}>Delete folder</button>}
      </div>)}
    </div> : <Empty>No bookmarks yet. Use the bookmark button on any scan result or history item.</Empty>}
    <p className="mt-2 text-xs text-(--iux-muted-foreground)">
      Auto-clean runs only while the background monitor is enabled, moves items to Trash (never deletes), skips high-risk, privacy and credential entries, and records every run in the audit history.
    </p>
  </Section>;
}
