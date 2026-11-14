/**
 * macOS Lab app mirror: a live, draggable view of one real app window on this Mac, with its
 * accessibility tree as numbered hotspots. Mirror and hotspot clicks preview a macos-click
 * action; arming control mode lets clicks land immediately. Everything stays localhost-only
 * and the underlying endpoints are read-only except the armed click.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwiseIcon, CircleNotchIcon, EyeIcon, HandIcon, PushPinIcon, XIcon } from "@phosphor-icons/react";
import { Badge, Empty, Field, Skeleton, Status } from "../components/ui";
import { api, message, usePoll, type LabRequest, type MacElement } from "../lib/api";

/** The mirror refreshes faster than the simulator screen; each frame is one screencapture. */
const MIRROR_INTERVAL = 1500;
const ELEMENTS_INTERVAL = 5000;
const MIN_WIDTH = 280;
const MIN_HEIGHT = 240;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

function hotspotStyle(element: MacElement, bounds: { width: number; height: number }) {
  return {
    left: `${(element.x / bounds.width) * 100}%`,
    top: `${(element.y / bounds.height) * 100}%`,
    width: `${(element.w / bounds.width) * 100}%`,
    height: `${(element.h / bounds.height) * 100}%`
  };
}

export function MacAppPanel({ onPreview, onHide }: { onPreview: (action: string, extra?: Partial<LabRequest>) => void; onHide: () => void }) {
  const { data, error } = usePoll(() => api.macosApps(), 5000);
  const control = usePoll(() => api.macosControl(), 15000);
  const [windowId, setWindowId] = useState(0);
  const [float, setFloat] = useState(true);
  const [pos, setPos] = useState({ left: 0, top: 0, width: 440, height: 420 });
  const [showElements, setShowElements] = useState(false);
  const [shot, setShot] = useState<string | null>(null);
  const [shotError, setShotError] = useState<string | null>(null);
  const [clickError, setClickError] = useState<string | null>(null);
  const mirrorRef = useRef<HTMLDivElement | null>(null);
  const shotRef = useRef<string | null>(null);

  const windows = data?.windows ?? [];
  const selected = windows.find((w) => w.windowId === windowId) ?? windows[0] ?? null;
  const armed = control.data?.armed ?? false;

  useEffect(() => {
    // First placement: near the panel's corner without covering the page head.
    setPos((p) => (p.left === 0 && p.top === 0 && typeof window !== "undefined"
      ? { ...p, left: Math.max(16, window.innerWidth - 480), top: 220 } : p));
  }, []);

  // Pick the first window when the selection disappears (app quit, window closed).
  useEffect(() => {
    if (selected && selected.windowId !== windowId) setWindowId(selected.windowId);
  }, [selected, windowId]);

  const grab = useCallback(async () => {
    if (!selected) return;
    try {
      const res = await fetch(api.macosAppScreenshotUrl(selected.windowId), { cache: "no-store" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error || `${res.status} ${res.statusText}`);
      }
      const url = URL.createObjectURL(await res.blob());
      if (shotRef.current) URL.revokeObjectURL(shotRef.current);
      shotRef.current = url;
      setShot(url);
      setShotError(null);
    } catch (e) {
      setShot(null);
      setShotError(message(e));
    }
  }, [selected?.windowId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => {
    if (shotRef.current) URL.revokeObjectURL(shotRef.current);
  }, []);
  useEffect(() => {
    if (!selected) {
      setShot(null);
      setShotError(null);
      return;
    }
    void grab();
    const timer = setInterval(() => {
      if (!document.hidden) void grab();
    }, MIRROR_INTERVAL);
    return () => clearInterval(timer);
  }, [selected?.windowId, grab]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: elementsData, reload: reloadElements } = usePoll(
    () => (showElements && selected ? api.macosElements(selected.windowId) : Promise.resolve(null)),
    showElements ? ELEMENTS_INTERVAL : 0,
    [showElements, selected?.windowId]
  );
  const elements = elementsData?.elements ?? [];
  const bounds = elementsData?.bounds ?? (selected ? { x: selected.x, y: selected.y, width: selected.width, height: selected.height } : null);

  const clickAt = (pid: number, gx: number, gy: number) => {
    setClickError(null);
    if (armed) {
      void api.macosClick(pid, Math.round(gx), Math.round(gy))
        .then(() => void grab())
        .catch((e) => {
          setClickError(message(e));
          void control.reload();
        });
    } else {
      onPreview("macos-click", { clickPid: pid, clickX: Math.round(gx), clickY: Math.round(gy) });
    }
  };

  const mirrorClick = (e: React.PointerEvent) => {
    if (!selected || !mirrorRef.current) return;
    const rect = mirrorRef.current.getBoundingClientRect();
    const scale = selected.width / rect.width;
    clickAt(selected.pid, selected.x + (e.clientX - rect.left) * scale, selected.y + (e.clientY - rect.top) * scale);
  };

  const startDrag = (e: React.PointerEvent) => {
    if (!float) return;
    e.preventDefault();
    const origin = { x: e.clientX, y: e.clientY, left: pos.left, top: pos.top };
    const move = (ev: PointerEvent) => {
      setPos((p) => ({
        ...p,
        left: clamp(origin.left + ev.clientX - origin.x, 0, window.innerWidth - MIN_WIDTH),
        top: clamp(origin.top + ev.clientY - origin.y, 0, window.innerHeight - 120)
      }));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const startResize = (e: React.PointerEvent) => {
    if (!float) return;
    e.preventDefault();
    e.stopPropagation();
    const origin = { x: e.clientX, y: e.clientY, width: pos.width, height: pos.height };
    const move = (ev: PointerEvent) => {
      setPos((p) => ({
        ...p,
        width: clamp(origin.width + ev.clientX - origin.x, MIN_WIDTH, window.innerWidth - 24),
        height: clamp(origin.height + ev.clientY - origin.y, MIN_HEIGHT, window.innerHeight - 24)
      }));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className="iux-btn" data-variant="outline" onClick={() => void grab()} disabled={!selected}>
        <ArrowClockwiseIcon size={14} /> Refresh
      </button>
      <button type="button" className="iux-btn" data-variant="outline" aria-pressed={showElements}
        onClick={() => setShowElements((s) => !s)} disabled={!selected}>
        <EyeIcon size={14} /> Elements
      </button>
      <button
        type="button"
        className={armed ? "iux-btn bg-[#f36c21] text-white hover:bg-[#fa7b32]" : "iux-btn"}
        data-variant={armed ? undefined : "outline"}
        aria-pressed={armed}
        onClick={() => void api.macosControlArm(!armed).then(() => control.reload())}
      >
        <HandIcon size={14} /> {armed ? "Disarm" : "Arm control"}
      </button>
    </div>
  );

  const mirror = bounds ? (
    <div className="flex flex-col gap-2">
      <div
        ref={mirrorRef}
        className="relative w-full cursor-crosshair overflow-hidden rounded-xl border border-(--iux-border) bg-black"
        style={{ aspectRatio: `${bounds.width} / ${bounds.height}` }}
        onPointerDown={mirrorClick}
      >
        {shot ? (
          <img src={shot} alt={`Mirror of ${selected?.app ?? "the app"}`} className="absolute inset-0 h-full w-full object-fill" draggable={false} />
        ) : shotError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center">
            <p className="text-xs text-zinc-400">{shotError}</p>
            <button type="button" className="iux-btn" data-variant="outline" onClick={() => void grab()}>Retry</button>
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center" aria-busy="true">
            <CircleNotchIcon size={22} className="animate-spin text-zinc-500" aria-hidden />
          </div>
        )}
        {showElements && shot
          ? elements.map((element, i) => (
              <button
                key={`${element.role}-${element.x}-${element.y}-${i}`}
                type="button"
                className="absolute flex items-center justify-center rounded-md border border-[#f36c21]/70 bg-[#f36c21]/15 text-[10px] font-semibold text-[#ffb27a] hover:bg-[#f36c21]/35"
                style={hotspotStyle(element, bounds)}
                title={`${element.role}${element.label ? `: ${element.label}` : ""}`}
                aria-label={`${i + 1}${element.label ? `: ${element.label}` : `: ${element.role}`}`}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  clickAt(selected?.pid ?? 0, bounds.x + element.x + element.w / 2, bounds.y + element.y + element.h / 2);
                }}
              >
                {element.w > 24 && element.h > 14 ? i + 1 : null}
              </button>
            ))
          : null}
      </div>
      {showElements && !elements.length ? (
        <p className="text-xs text-(--iux-muted-foreground)">No UI elements found for this window yet.</p>
      ) : null}
    </div>
  ) : null;

  const body = (
    <div className="flex flex-col gap-3">
      {error ? <Status value={{ ok: false, text: error }} /> : null}
      {clickError ? <Status value={{ ok: false, text: clickError }} /> : null}
      {data && !data.available ? (
        <Empty>{data.reason ?? "The app mirror is not available here."}</Empty>
      ) : !data ? (
        <Skeleton rows={2} />
      ) : (
        <>
          {data.screenRecording ? null : (
            <p className="text-xs text-(--iux-warning)">
              Window titles and captures need Screen Recording permission for the console
              (System Settings › Privacy & Security).
            </p>
          )}
          {windows.length ? (
            <>
              <Field label="Window">
                <select
                  className="iux-input"
                  value={selected?.windowId ?? 0}
                  onChange={(e) => setWindowId(Number(e.target.value))}
                  aria-label="Window"
                >
                  {windows.map((w) => (
                    <option key={w.windowId} value={w.windowId}>
                      {w.app}{w.title ? ` — ${w.title.slice(0, 40)}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              {mirror}
              {toolbar}
              {armed ? (
                <p className="text-xs text-(--iux-warning)">
                  Armed — mirror clicks run immediately on this Mac. Control disarms itself after ten minutes.
                </p>
              ) : (
                <p className="text-xs text-(--iux-muted-foreground)">
                  Clicks on the mirror preview a macos-click action first.
                </p>
              )}
            </>
          ) : (
            <Empty>No visible app windows right now.</Empty>
          )}
        </>
      )}
    </div>
  );

  const header = (
    <div
      className={`flex items-center gap-2 border-b border-(--iux-border) px-4 py-2.5 ${float ? "cursor-move touch-none select-none" : ""}`}
      onPointerDown={startDrag}
    >
      <EyeIcon size={15} className="text-[#f36c21]" aria-hidden />
      <span className="text-sm font-semibold">App mirror</span>
      {armed ? <Badge tone="warning">Armed</Badge> : null}
      <span className="ml-auto flex items-center gap-1">
        <button
          type="button"
          className="iux-btn" data-variant="ghost"
          title={float ? "Dock the panel" : "Float the panel"}
          aria-label={float ? "Dock the app mirror panel" : "Float the app mirror panel"}
          onClick={() => setFloat((f) => !f)}
        >
          <PushPinIcon size={14} />
        </button>
        <button
          type="button"
          className="iux-btn" data-variant="ghost"
          title="Hide the app mirror"
          aria-label="Hide the app mirror"
          onClick={onHide}
        >
          <XIcon size={14} />
        </button>
      </span>
    </div>
  );

  if (!float) {
    return (
      <section className="iux-card gap-3 py-4">
        {header}
        <div className="px-4">{body}</div>
      </section>
    );
  }
  return (
    <div
      className="iux-card fixed z-40 flex flex-col overflow-hidden shadow-[0_18px_50px_-12px_rgba(0,0,0,0.55)]"
      style={{ left: pos.left, top: pos.top, width: pos.width, height: pos.height }}
    >
      {header}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{body}</div>
      <div
        className="absolute right-0 bottom-0 h-5 w-5 cursor-nwse-resize touch-none"
        onPointerDown={startResize}
        aria-hidden
      />
    </div>
  );
}

/** Reopen affordance shown where the floating panel used to sit. */
export function MacAppMirrorTeaser({ onOpen }: { onOpen: () => void }) {
  return (
    <section className="iux-card items-start gap-3 py-4">
      <div className="flex items-center gap-2 px-4">
        <EyeIcon size={15} className="text-[#f36c21]" aria-hidden />
        <span className="text-sm font-semibold">App mirror</span>
      </div>
      <div className="px-4">
        <button type="button" className="iux-btn" data-variant="outline" onClick={onOpen}>
          Show the app mirror
        </button>
      </div>
    </section>
  );
}
