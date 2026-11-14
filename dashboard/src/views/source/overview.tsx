import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, Field, Section, Skeleton, Status } from "../../components/ui";
import { hostStore } from "../../lib/api";
import { SourceAction } from "./action";
import { useSource } from "./client";
import { sourceHref } from "./pages";

interface MatrixRow { name: string; count: number; slugs: string[]; category?: string; mvStatus?: string; mv2?: number; mv3?: number; specNote?: string; migrationNote?: string; risk?: string; sections?: string[] }
interface Extension { slug: string; repo: string; name: string; manifestVersion: string; version: string; description: string; riskLevel: string; heuristicScore: number | null; backgroundType: string; dependenciesCount: number; permissions: string[] }
interface OverviewData { stats: Record<string, number>; propsMatrix: MatrixRow[]; depsMatrix: MatrixRow[]; permsMatrix: MatrixRow[]; swGroups: Record<string, string[]>; extensions: Extension[]; truncated: boolean }
const statLabels: Record<string, string> = { totalAnalyzed: "Analyzed targets", mv2Count: "MV2", mv3Count: "MV3", uniquePropsCount: "Manifest properties", uniqueDepsCount: "Dependencies", uniquePermsCount: "Permissions", serviceWorkerCount: "Service workers", persistentScriptCount: "Background scripts", backgroundPageCount: "Background pages", noneCount: "No background" };
const backgroundLabels: Record<string, string> = { serviceWorker: "Service workers", persistentScript: "Background scripts", backgroundPage: "Background pages", none: "No background" };
const catalogLabels = { mergedExtensions: "Merged", curated: "Curated", monitored: "Monitored" };
const tabs = { props: "Properties", workers: "Backgrounds", deps: "Dependencies", perms: "Permissions", inspector: "Inspector" };
type Tab = keyof typeof tabs;
const input = "iux-input w-full";
const table = "w-full text-start text-sm [&_th]:p-2 [&_td]:p-2 [&_th]:text-start [&_tr]:border-b [&_tr]:border-(--iux-border)";
function useQueryValue(key: string, value: string) {
  useEffect(() => {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    window.history.replaceState(null, "", url);
  }, [key, value]);
}
function Links({ slugs }: { slugs: string[] }) {
  return <ul className="flex flex-col gap-2">{slugs.map(slug => <li key={slug}>
    <a className="underline" data-no-translate href={sourceHref("deep-analysis", `?repo=${encodeURIComponent(slug.replace("__", "/"))}`)}>{slug}</a>{" · "}
    <a className="underline" href={sourceHref("evidence", `?slug=${encodeURIComponent(slug)}`)}>Evidence</a>
  </li>)}</ul>;
}
export function SourceOverview() {
  const { data, error, loading, refresh } = useSource<OverviewData>("analyzer/merged");
  const params = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
  const [tab, setTab] = useState<Tab>(((params.get("tab") ?? "") in tabs ? params.get("tab") : "props") as Tab);
  const [filter, setFilter] = useState(params.get("q") ?? "");
  const [category, setCategory] = useState("");
  const [version, setVersion] = useState("");
  const [selected, setSelected] = useState<MatrixRow | Extension>();
  const dialog = useRef<HTMLDialogElement>(null);
  useQueryValue("tab", tab); useQueryValue("q", filter);
  useEffect(() => { if (selected) dialog.current?.showModal(); }, [selected]);
  if (loading) return <Skeleton />;
  if (error) return <Section title="Overview"><Status value={{ ok: false, text: error }} /><button className="iux-btn" onClick={refresh}>Retry</button></Section>;
  if (!data) return null;
  const rows = tab === "props" ? data.propsMatrix : tab === "deps" ? data.depsMatrix : tab === "perms" ? data.permsMatrix : [];
  const matchingSlugs = new Set(data.extensions.filter(ext => !version || ext.manifestVersion === version).map(ext => ext.slug));
  const visible = rows.filter(row => row.slugs.some(s => matchingSlugs.has(s)) && (!category || row.category === category || row.risk === category) && JSON.stringify(row).toLowerCase().includes(filter.toLowerCase()));
  const categories = [...new Set(rows.map(row => row.category ?? row.risk).filter(Boolean))] as string[];
  const targets = data.extensions.filter(ext => matchingSlugs.has(ext.slug) && JSON.stringify(ext).toLowerCase().includes(filter.toLowerCase()));
  return <>
    <Section title="Analysis summary" action={<button className="iux-btn" onClick={refresh}>Refresh</button>}>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">{Object.entries(data.stats).map(([key, value]) => <div key={key}><dt className="break-words text-xs" >{statLabels[key] ?? key}</dt><dd className="text-xl font-semibold">{value}</dd></div>)}</dl>
      {data.truncated && <p role="status">Results are capped. Refine the private workspace before comparing totals.</p>}
      <div className="mt-3 flex flex-wrap gap-3"><a className="underline" href="/api/source/analyzer/merged?export=csv">Download CSV</a><a className="underline" href="/api/source/analyzer/merged?export=json" download="source-overview.json">Download JSON</a><a className="underline" href={sourceHref("sources")}>Sources</a></div>
    </Section>
    <Section title="Comparison matrices">
      <div role="tablist" aria-label="Overview matrices" className="mb-4 flex flex-wrap gap-2">{Object.entries(tabs).map(([key, label]) => <button key={key} id={`source-tab-${key}`} role="tab" aria-selected={tab === key} aria-controls="source-matrix-panel" tabIndex={tab === key ? 0 : -1} className="iux-btn" data-variant={tab === key ? "default" : "outline"} onClick={() => { setTab(key as Tab); setCategory(""); }} onKeyDown={event => {
        if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
        event.preventDefault(); const keys = Object.keys(tabs); const index = keys.indexOf(key);
        const next = event.key === "Home" ? 0 : event.key === "End" ? keys.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + keys.length) % keys.length;
        setTab(keys[next] as Tab); setCategory(""); document.getElementById(`source-tab-${keys[next]}`)?.focus();
      }}>{label}</button>)}</div>
      <div className="mb-4 grid gap-3 sm:grid-cols-3"><Field label="Filter results"><input className={input} value={filter} onChange={e => setFilter(e.target.value)} /></Field>
        <Field label="Category or risk"><select className={input} value={category} onChange={e => setCategory(e.target.value)}><option value="">All</option>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select></Field>
        <Field label="Manifest version"><select className={input} value={version} onChange={e => setVersion(e.target.value)}><option value="">All</option><option value="2">MV2</option><option value="3">MV3</option></select></Field></div>
      <div id="source-matrix-panel" role="tabpanel" aria-labelledby={`source-tab-${tab}`} className="overflow-x-auto">
        {tab === "workers" ? Object.entries(data.swGroups).map(([group, slugs]) => <details className="mb-3 rounded border border-(--iux-border) p-3" key={group}><summary><span>{backgroundLabels[group] ?? group}</span> ({slugs.filter(s => targets.some(t => t.slug === s)).length})</summary><Links slugs={slugs.filter(s => targets.some(t => t.slug === s))} /></details>) : tab === "inspector" ? targets.length ? <table className={table}><thead><tr><th>Target</th><th>Manifest version</th><th>Risk</th><th>Details</th></tr></thead><tbody>{targets.map(ext => <tr key={ext.slug}><td data-no-translate>{ext.name}<br />{ext.repo}</td><td>{ext.manifestVersion}</td><td data-no-translate>{ext.riskLevel}</td><td><button className="iux-btn" onClick={() => setSelected(ext)}>Inspect</button></td></tr>)}</tbody></table> : <Empty>No matching targets.</Empty> : visible.length ? <table className={table}><thead><tr><th>Name</th><th>Category or risk</th><th>Count</th>{tab === "props" && <th>MV2 / MV3</th>}<th>Details</th></tr></thead><tbody>{visible.map(row => <tr key={row.name}><td data-no-translate>{row.name}</td><td data-no-translate>{row.category ?? row.risk}</td><td>{row.count}</td>{tab === "props" && <td>{row.mv2} / {row.mv3}</td>}<td><button className="iux-btn" onClick={() => setSelected(row)}>Inspect</button></td></tr>)}</tbody></table> : <Empty>No matching results. Add authorized targets or adjust filters.</Empty>}
      </div>
    </Section>
    <dialog ref={dialog} className="iux iux-dialog max-h-[80dvh] w-full max-w-2xl overflow-auto p-5" aria-label="Source inspector" onClose={() => setSelected(undefined)}>
      <div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold" data-no-translate>{selected?.name}</h2><button autoFocus className="iux-btn" onClick={() => dialog.current?.close()}>Close</button></div>
      {selected && ("slugs" in selected ? <div className="space-y-3"><p data-no-translate>{selected.mvStatus}</p><p data-no-translate>{selected.specNote}</p><p data-no-translate>{selected.migrationNote}</p>{selected.sections && <p data-no-translate>{selected.sections.join(", ")}</p>}<Links slugs={selected.slugs} /></div> : <div className="space-y-3"><p data-no-translate>{selected.description}</p><pre className="overflow-auto text-xs">{JSON.stringify(selected, null, 2)}</pre><Links slugs={[selected.slug]} /></div>)}
    </dialog>
  </>;
}
interface SourceData { stats: Record<string, number>; files: { name: string; type: string; size: number }[]; mergedExtensions: Record<string, unknown>[]; curated: Record<string, unknown>[]; monitored: Record<string, unknown>[] }
export function SourceCatalogs() {
  const [origin, setOrigin] = useState("resources");
  const { data: host, error: hostError } = hostStore.use();
  const { data, error, loading, refresh } = useSource<SourceData>(`sources?origin=${origin}`);
  const joined = useCallback(() => { setOrigin("generated"); refresh(); }, [refresh]);
  const [tab, setTab] = useState<"mergedExtensions" | "curated" | "monitored">("mergedExtensions");
  const [filter, setFilter] = useState("");
  if (loading) return <Skeleton />;
  if (error) return <Section title="Sources"><Status value={{ ok: false, text: error }} /><button className="iux-btn" onClick={refresh}>Retry</button></Section>;
  const rows = (data?.[tab] ?? []).filter(row => JSON.stringify(row).toLowerCase().includes(filter.toLowerCase()));
  const keys = [...new Set(rows.flatMap(row => Object.keys(row)))];
  return <Section title="Source catalogs" description="Only operator-provided catalogs are shown. No dataset is bundled.">
    <Field label="Source"><select className="iux-input" value={origin} onChange={e => setOrigin(e.target.value)}><option value="resources">Resources</option><option value="generated">Generated catalogs</option></select></Field>
    <SourceAction endpoint="sources" options={{}} ready={Boolean(!hostError && host?.labs.find(l => l.id === "source")?.state === "ready" && ["browser-extensions.csv", "browser-extension-repos.csv"].every(name => data?.files.some(f => f.name === name)))} onFinished={joined} />
    <div className="mb-4 flex flex-wrap gap-3">{data?.files.map(file => <a className="underline" key={file.name} href={`/api/source/sources?origin=${origin}&download=${encodeURIComponent(file.name)}`} data-no-translate>{file.name} ({file.size} B)</a>)}</div>
    <div className="mb-3 flex flex-wrap gap-2">{(["mergedExtensions", "curated", "monitored"] as const).map(key => <button className="iux-btn" aria-pressed={tab === key} key={key} onClick={() => setTab(key)}><span>{catalogLabels[key]}</span> ({data?.[key].length ?? 0})</button>)}</div>
    <Field label="Filter sources"><input className={input} value={filter} onChange={e => setFilter(e.target.value)} /></Field>
    <div className="mt-4 overflow-x-auto">{rows.length ? <table className={table}><thead><tr>{keys.map(key => <th key={key} data-no-translate>{key}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={i}>{keys.map(key => <td key={key} data-no-translate>{String(row[key] ?? "")}</td>)}</tr>)}</tbody></table> : <Empty>No matching sources.</Empty>}</div>
  </Section>;
}
