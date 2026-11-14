/* oxlint-disable jsx-a11y/prefer-tag-over-role, jsx-a11y/no-noninteractive-element-interactions -- ARIA combobox/listbox pattern (as in the prompt menu); the dialog takes arrow keys for the list and a backdrop click to close, Escape is native */
/**
 * Spotlight — the ⌘K / Ctrl+K command palette, ported from the iQ-iUX studio (src/components/spotlight.tsx):
 * ranked search, `scope: text` narrowing, Tab to drill into a section, Backspace to leave it.
 *
 * Results are laid out like the sidebar: group → section → part, with records nested under the section
 * they belong to on a guide line. Sections come from the same `SidebarGroup[]` the sidebar renders;
 * records (MCP servers, tools, prompts…) are already in the browser, so they are passed in and filtered here.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  KeyReturnIcon,
  MagnifyingGlassIcon,
  TerminalWindowIcon
} from "@phosphor-icons/react";
import { cn, type SidebarGroup } from "./sidebar";

export interface SpotlightRecord {
  id: string;
  href?: string;
  /** Id of the sidebar section this record belongs to. */
  section: string;
  title: string;
  description?: string | null;
  badge?: string | null;
  /** Replaces the section's icon for this record, such as an agent's avatar. */
  icon?: ReactNode;
}

export interface SpotlightCommand {
  id: string;
  label: string;
  description?: string;
  aliases?: string[];
  icon?: ReactNode;
  run: () => void;
}

/** A `scope:` prefix shown under "Search tips" while the query is empty. */
export interface SpotlightTip {
  scope: string;
  description: string;
  icon?: ReactNode;
}

export interface SpotlightMeta {
  description?: string;
  aliases?: string[];
}

interface SpotlightProps {
  open: boolean;
  onQueryChange?: (query: string) => void;
  searchError?: string;
  onOpenChange: (open: boolean) => void;
  groups: SidebarGroup[];
  /** Descriptions and aliases per section id, so "connector" finds MCP servers. */
  meta?: Record<string, SpotlightMeta>;
  commands?: SpotlightCommand[];
  records: SpotlightRecord[];
  tips?: SpotlightTip[];
  onNavigate: (section: string, record?: SpotlightRecord) => void;
}

// ---------------------------------------------------------------------------
// Recents — the last picks, remembered per browser
// ---------------------------------------------------------------------------

type Recent =
  | { type: "section"; section: string }
  | { type: "record"; section: string; id: string }
  | { type: "command"; id: string };

const RECENTS_KEY = "oslab.spotlight.recents";
const RECENTS_MAX = 5;

function loadRecents(): Recent[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(RECENTS_KEY) ?? "[]");
    return Array.isArray(raw) ? (raw as Recent[]) : [];
  } catch {
    return [];
  }
}

function saveRecent(recent: Recent) {
  const same = (r: Recent) => JSON.stringify(r) === JSON.stringify(recent);
  const next = [recent, ...loadRecents().filter((r) => !same(r))].slice(
    0,
    RECENTS_MAX
  );
  try {
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable: no recents
  }
}

// ---------------------------------------------------------------------------
// Ranking — same ladder as iQ-iBone's SpotlightScorer
// ---------------------------------------------------------------------------

export function scoreText(
  text: string,
  title: string,
  aliases: string[] = [],
  description = ""
): number {
  const t = text.toLowerCase().trim();
  if (!t) return 1;
  const name = title.toLowerCase();
  const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (name === t) return 100;
  if (new RegExp(`^${esc}(\\s|-|_|$)`).test(name)) return 90;
  if (name.startsWith(t)) return 80;
  if (new RegExp(`(^|\\s|-|_)${esc}`).test(name)) return 70;
  if (name.includes(t)) return 60;
  for (const alias of aliases) {
    const a = alias.toLowerCase().trim();
    if (a === t) return 55;
    if (a.includes(t)) return 50;
  }
  return description.toLowerCase().includes(t) ? 30 : 0;
}

/** `tools: search` → scope "tools", text "search". */
export function parseScope(raw: string): {
  scope: string | null;
  text: string;
} {
  const m = /^([a-z][a-z0-9 _-]*):\s*(.*)$/i.exec(raw.trim());
  return m
    ? { scope: m[1].trim().toLowerCase(), text: m[2].trim() }
    : { scope: null, text: raw.trim() };
}

// ---------------------------------------------------------------------------
// Tree rows
// ---------------------------------------------------------------------------

type Row =
  | { key: string; type: "group"; label: string }
  | {
      key: string;
      type: "section";
      label: string;
      icon?: ReactNode;
      /** The item a leaf sits under, shown after an em dash. */
      parent?: string;
      depth: 0 | 1;
      section: string;
      score: number;
      description?: string;
    }
  | {
      key: string;
      type: "record";
      depth: 1 | 2;
      record: SpotlightRecord;
      icon?: ReactNode;
      parent: string;
      score: number;
    }
  | { key: string; type: "command"; command: SpotlightCommand; score: number }
  | { key: string; type: "tip"; tip: SpotlightTip; score: number };

const isSelectable = (r: Row) =>
  r.type === "section" ||
  r.type === "record" ||
  r.type === "command" ||
  r.type === "tip";

export function buildRows(
  groups: SidebarGroup[],
  meta: Record<string, SpotlightMeta>,
  commands: SpotlightCommand[],
  records: SpotlightRecord[],
  rawQuery: string,
  drill: string | null
): Row[] {
  const { scope, text } = parseScope(rawQuery);
  const byParts = new Map<string, SpotlightRecord[]>();
  for (const r of records)
    byParts.set(r.section, [...(byParts.get(r.section) ?? []), r]);
  const searching = text !== "" || drill !== null;
  const rows: Row[] = [];

  const recordRows = (
    section: string,
    depth: 1 | 2,
    icon: ReactNode,
    parent: string
  ): Row[] =>
    (byParts.get(section) ?? []).map((record) => ({
      key: `r:${section}:${record.id}`,
      type: "record" as const,
      depth,
      record,
      icon: record.icon ?? icon,
      parent,
      score: scoreText(text, record.title, [], record.description ?? "")
    }));

  // `chats:` finds the "Chat" section as well as `chat:`
  const inScope = (labels: string[]) =>
    !scope ||
    labels.some((l) => {
      const label = l.toLowerCase();
      return label.includes(scope) || scope.startsWith(label);
    });
  const sectionRow = (
    id: string,
    label: string,
    icon: ReactNode | undefined,
    depth: 0 | 1,
    parent?: string
  ) => ({
    key: `s:${id}`,
    type: "section" as const,
    label,
    icon,
    parent,
    depth,
    section: id,
    score: scoreText(text, label, meta[id]?.aliases, meta[id]?.description),
    description: meta[id]?.description
  });

  for (const group of groups) {
    const block: Row[] = [];
    for (const item of group.items) {
      const kids = item.children ?? [];
      if (kids.length === 0) {
        if (drill && drill !== item.id) continue;
        if (!inScope([item.label, group.label])) continue;
        const self = sectionRow(item.id, item.label, item.icon, 0);
        const recs = recordRows(item.id, 1, item.icon, item.label);
        if (!text || self.score > 0 || recs.length > 0)
          block.push(self, ...recs);
        continue;
      }
      const parentHit = scoreText(text, item.label) > 0;
      const kidRows: Row[] = [];
      for (const leaf of kids) {
        if (drill && drill !== leaf.id) continue;
        if (!inScope([leaf.label, item.label, group.label])) continue;
        const self = sectionRow(leaf.id, leaf.label, item.icon, 1, item.label);
        const recs = recordRows(leaf.id, 2, item.icon, leaf.label);
        if (!text || self.score > 0 || parentHit || recs.length > 0)
          kidRows.push(self, ...recs);
      }
      block.push(...kidRows);
    }
    if (block.length > 0)
      rows.push(
        { key: `g:${group.label}`, type: "group", label: group.label },
        ...block
      );
  }

  if (!drill && !scope) {
    const cmds = commands
      .map((command) => ({
        key: `c:${command.id}`,
        type: "command" as const,
        command,
        score: scoreText(
          text,
          command.label,
          command.aliases,
          command.description
        )
      }))
      .filter((c) => !searching || c.score > 0);
    if (cmds.length > 0)
      rows.push(
        { key: "g:Commands", type: "group", label: "Commands" },
        ...cmds
      );
  }
  return rows;
}

/** Records under a section, or matching the text once it is two characters long; a `scope:` lists them all. */
function matchRecords(
  records: SpotlightRecord[],
  text: string,
  drill: string | null,
  scoped: boolean
) {
  if (text.length < 2 && !drill && !scoped) return [];
  return records.filter(
    (r) =>
      (!drill || r.section === drill) &&
      (!text || scoreText(text, r.title, [], r.description ?? "") > 0)
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Spotlight({
  open,
  onOpenChange,
  groups,
  meta = {},
  commands = [],
  records,
  tips = [],
  onNavigate, onQueryChange, searchError
}: SpotlightProps) {
  const [query, setQuery] = useState("");
  useEffect(() => { onQueryChange?.(query); }, [query, onQueryChange]);
  const [drill, setDrill] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [recents, setRecents] = useState<Recent[]>([]);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const { scope, text } = parseScope(query);

  // ⌘K / Ctrl+K toggles the palette from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setRecents(loadRecents());
      dialog.showModal();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const reset = () => {
    setQuery("");
    setDrill(null);
    setPicked(null);
  };
  const close = () => {
    onOpenChange(false);
    reset();
  };

  const matched = useMemo(
    () => matchRecords(records, text, drill, scope !== null),
    [records, text, drill, scope]
  );
  const idle = query.trim() === "" && drill === null;

  const rows = useMemo(() => {
    const found = buildRows(groups, meta, commands, matched, query, drill);
    if (!idle) return found;

    // Empty query: Recents and Search tips lead, then every section and command
    const lead: Row[] = [];
    const all = buildRows(groups, meta, commands, records, "", null);
    const recentRows = recents
      .map((r): Row | undefined => {
        const hit = all.find((row) =>
          r.type === "section"
            ? row.type === "section" && row.section === r.section
            : r.type === "record"
              ? row.type === "record" &&
                row.record.section === r.section &&
                row.record.id === r.id
              : row.type === "command" && row.command.id === r.id
        );
        return hit && { ...hit, key: `recent:${hit.key}` };
      })
      .filter((r): r is Row => r !== undefined);
    if (recentRows.length > 0)
      lead.push(
        { key: "g:Recents", type: "group", label: "Recents" },
        ...recentRows
      );
    if (tips.length > 0)
      lead.push(
        { key: "g:Tips", type: "group", label: "Search tips" },
        ...tips.map((tip) => ({
          key: `t:${tip.scope}`,
          type: "tip" as const,
          tip,
          score: 1
        }))
      );
    return [...lead, ...found];
  }, [
    groups,
    meta,
    commands,
    matched,
    records,
    query,
    drill,
    idle,
    recents,
    tips
  ]);
  const selectable = rows.filter(isSelectable);

  // The best match leads, unless the user already moved the highlight
  const best = useMemo(() => {
    let top: Row | undefined;
    for (const r of selectable)
      if (!top || ("score" in r && "score" in top && r.score > top.score))
        top = r;
    return top?.key ?? null;
  }, [selectable]);
  const active =
    picked && selectable.some((r) => r.key === picked) ? picked : best;

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const sectionLabel = (id: string) => {
    for (const g of groups)
      for (const i of g.items) {
        if (i.id === id) return i.label;
        const leaf = i.children?.find((c) => c.id === id);
        if (leaf) return leaf.label;
      }
    return id;
  };

  const run = (row: Row) => {
    if (row.type === "tip") {
      setQuery(`${row.tip.scope}: `);
      setPicked(null);
      return;
    }
    if (row.type === "command") {
      saveRecent({ type: "command", id: row.command.id });
      close();
      row.command.run();
    } else if (row.type === "section") {
      saveRecent({ type: "section", section: row.section });
      close();
      onNavigate(row.section);
    } else if (row.type === "record") {
      saveRecent({
        type: "record",
        section: row.record.section,
        id: row.record.id
      });
      close();
      onNavigate(row.record.section, row.record);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const index = selectable.findIndex((r) => r.key === active);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next =
        selectable[
          (index + (e.key === "ArrowDown" ? 1 : -1) + selectable.length) %
            selectable.length
        ];
      if (next) setPicked(next.key);
    } else if (e.key === "Enter") {
      const row = selectable[index];
      if (row) {
        e.preventDefault();
        run(row);
      }
    } else if (e.key === "Tab") {
      const row = selectable[index];
      if (row?.type === "section") {
        e.preventDefault();
        setDrill(row.section);
        setQuery("");
        setPicked(null);
      }
    } else if (e.key === "Backspace" && query === "" && drill) {
      e.preventDefault();
      setDrill(null);
      setPicked(null);
    }
  };

  const empty = selectable.length === 0;
  const kbd =
    "inline-flex h-5 min-w-5 items-center justify-center rounded border border-(--iux-border) bg-(--iux-muted) px-1 text-[11px] text-(--iux-muted-foreground)";

  /** Icon, then "Title — Context" on one line, as in the Cloudflare dashboard's search. */
  const line = (
    icon: ReactNode,
    title: string,
    context?: string | null,
    mono = false
  ) => (
    <>
      <span className="flex size-4 shrink-0 items-center justify-center text-(--iux-muted-foreground)">
        {icon}
      </span>
      <span className="flex min-w-0 flex-1 items-baseline gap-2">
        <span
          className={cn("shrink-0 truncate", mono && "font-mono text-[13px]")}
        >
          {title}
        </span>
        {context && (
          <>
            <span className="shrink-0 text-(--iux-muted-foreground)">—</span>
            <span className="truncate text-(--iux-muted-foreground)">
              {context}
            </span>
          </>
        )}
      </span>
    </>
  );

  return (
    <dialog
      ref={dialogRef}
      aria-label="Spotlight"
      className="iux iux-dialog iux-spotlight"
      onKeyDown={onKeyDown}
      // Escape closes the native dialog; keep React state in step
      onClose={() => {
        if (open) close();
      }}
      // A click on the backdrop lands on the dialog element itself
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      {open && (
        <>
          {drill && (
            <div
              className="flex items-center gap-1 px-4 pt-2 text-xs text-(--iux-muted-foreground)"
              aria-label="Search scope"
            >
              <span>Search in</span>
              <span className="font-medium text-(--iux-foreground)">
                {sectionLabel(drill)}
              </span>
              <span className="ml-auto">Backspace to leave</span>
            </div>
          )}
          <div className="flex items-center gap-3 border-b border-(--iux-border) px-4">
            <MagnifyingGlassIcon
              size={18}
              className="shrink-0 text-(--iux-muted-foreground)"
            />
            <input
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPicked(null);
              }}
              placeholder={
                drill
                  ? `Search ${sectionLabel(drill)}…`
                  : "Search chats, agents, tools, pages and commands…"
              }
              aria-label="Spotlight search"
              role="combobox"
              aria-expanded
              aria-controls="spotlight-list"
              aria-activedescendant={active ? `sp-${active}` : undefined}
              className="h-12 w-full bg-transparent text-[15px] outline-none placeholder:text-(--iux-muted-foreground)"
            />
            <kbd className={kbd}>Esc</kbd>
          </div>

          {searchError && <p role="status" className="px-4 py-2 text-sm">{searchError}</p>}
          <div
            ref={listRef}
            id="spotlight-list"
            role="listbox"
            className="iux-scroll max-h-[26rem] overflow-y-auto p-2"
          >
            {empty && (
              <p className="px-3 py-6 text-center text-sm text-(--iux-muted-foreground)">
                {drill && !text
                  ? "Nothing here yet."
                  : scope
                    ? `No results in “${scope}”.`
                    : "No results."}
              </p>
            )}
            {rows.map((row) => {
              if (row.type === "group") {
                return (
                  <div
                    key={row.key}
                    className="px-3 pt-3 pb-1.5 text-xs font-medium text-(--iux-muted-foreground)"
                  >
                    {row.label}
                  </div>
                );
              }
              const isActive = row.key === active;
              const body =
                row.type === "section"
                  ? line(row.icon, row.label, row.parent ?? row.description)
                  : row.type === "record"
                    ? line(
                        row.icon,
                        row.record.title,
                        row.record.badge
                          ? `${row.parent} · ${row.record.badge}`
                          : row.parent
                      )
                    : row.type === "tip"
                      ? line(
                          row.tip.icon,
                          `${row.tip.scope}:`,
                          row.tip.description
                        )
                      : line(
                          row.command.icon ?? <TerminalWindowIcon size={16} />,
                          row.command.label,
                          row.command.description
                        );
              return (
                <button
                  key={row.key}
                  type="button"
                  id={`sp-${row.key}`}
                  role="option"
                  aria-selected={isActive}
                  data-active={isActive}
                  title={
                    row.type === "record"
                      ? (row.record.description ?? undefined)
                      : undefined
                  }
                  onMouseMove={() => setPicked(row.key)}
                  onClick={() => run(row)}
                  className={cn(
                    "flex h-9 w-full items-center gap-3 rounded-md px-3 text-left text-sm outline-none transition-colors",
                    isActive
                      ? "bg-(--iux-accent) text-(--iux-foreground)"
                      : "text-(--iux-foreground)/90"
                  )}
                >
                  {body}
                  {isActive && row.type === "section" && !idle && (
                    <span className="shrink-0 text-[10px] text-(--iux-muted-foreground)">
                      Tab ›
                    </span>
                  )}
                  {isActive && (
                    <ArrowRightIcon
                      size={14}
                      className="shrink-0 text-(--iux-muted-foreground)"
                    />
                  )}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-4 border-t border-(--iux-border) bg-(--iux-muted)/40 px-4 py-2.5 text-xs text-(--iux-muted-foreground)">
            <span className="inline-flex items-center gap-1.5">
              <kbd className={kbd}>
                <ArrowUpIcon size={11} />
              </kbd>
              <kbd className={kbd}>
                <ArrowDownIcon size={11} />
              </kbd>
              to navigate
            </span>
            <span className="inline-flex items-center gap-1.5">
              <kbd className={kbd}>
                <KeyReturnIcon size={11} />
              </kbd>
              to select
            </span>
            <span className="ml-auto hidden items-center gap-1.5 sm:inline-flex">
              <kbd className={kbd}>Tab</kbd>
              search inside
            </span>
          </div>
        </>
      )}
    </dialog>
  );
}
