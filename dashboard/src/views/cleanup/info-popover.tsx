/** Details popover for cleanup rows: hover (fine pointers), focus or click to open. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { InfoIcon } from "@phosphor-icons/react";

/**
 * Non-modal popover anchored to the trigger. Opens after a short hover intent on
 * fine pointers, immediately on keyboard focus, and closes on Escape, outside
 * interaction, or when unpinned hover leaves. A click pins it open so hover and
 * click never fight each other; a second click closes it again.
 */
export function InfoPopover({
  label = "Details",
  children,
  width = "w-72 max-w-[min(18rem,80vw)] max-h-72 overflow-auto iux-scroll"
}: {
  label?: string;
  children: ReactNode;
  width?: string;
}) {
  const wrap = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const pinned = useRef(false);
  const timer = useRef<number | null>(null);
  const finePointer = () => window.matchMedia("(hover: hover)").matches;
  const cancel = () => { if (timer.current) { window.clearTimeout(timer.current); timer.current = null; } };

  useEffect(() => cancel, []);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) {
        pinned.current = false;
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      pinned.current = false;
      setOpen(false);
      wrap.current?.querySelector("button")?.focus();
    };
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return <span ref={wrap} className="relative inline-flex"
    onMouseEnter={() => { if (!finePointer()) return; cancel(); timer.current = window.setTimeout(() => setOpen(true), 250); }}
    onMouseLeave={() => { if (!finePointer() || pinned.current) return; cancel(); timer.current = window.setTimeout(() => setOpen(false), 300); }}
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node) && !pinned.current) setOpen(false); }}>
    <button type="button"
      className="iux-touch-target flex size-6 items-center justify-center rounded-md text-(--iux-muted-foreground) transition-colors hover:bg-(--iux-muted) hover:text-(--iux-foreground)"
      aria-label={label} aria-expanded={open}
      onClick={() => {
        cancel();
        if (open && !pinned.current) pinned.current = true;
        else if (open) { pinned.current = false; setOpen(false); }
        else { pinned.current = true; setOpen(true); }
      }}
      onFocus={() => { cancel(); setOpen(true); }}>
      <InfoIcon size={14} weight="bold" />
    </button>
    {open && <div role="note" tabIndex={-1}
      className={`absolute end-0 top-full z-30 mt-1 ${width} rounded-md border border-(--iux-border) bg-(--iux-card) p-3 text-sm shadow-lg`}>
      {children}
    </div>}
  </span>;
}
