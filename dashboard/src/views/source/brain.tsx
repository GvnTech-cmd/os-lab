import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Empty, Field, Section, Skeleton, Status } from "../../components/ui";
import { ArtifactDetails } from "./evidence";
import { useSource } from "./client";
import { compareLines, graphWindow, normalizeGraph, type BrainGraph, type BrainManifest, type BrainNode } from "./brain-model";
import { useBrainProvider } from "./brain-data";
const views = { graph: "Graph", usages: "Usages", source: "Source", history: "History", diff: "Diff", flow: "Flowchart", sequence: "Sequence", aiRules: "AI rules", complexity: "Complexity", risk: "Risk", stress: "Stress", export: "Export" };
type View = keyof typeof views;
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function text(value: unknown) { return typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2); }
function Flow({ steps }: { steps: unknown }) {
  const budget = { left: 300 };
  const render = (value: unknown, depth: number): ReactNode => !Array.isArray(value) || depth > 8 ? null : <ol className="space-y-2 border-s border-(--iux-border) ps-3">{value.slice(0, 300).map((raw, index) => {
    if (--budget.left < 0) return null;
    const step = record(raw);
    return <li key={index} data-no-translate><p>{String(step.type ?? "step")} → {String(step.label ?? "")}</p>{render(step.then, depth + 1)}{render(step.else, depth + 1)}{render(step.body, depth + 1)}</li>;
  })}</ol>;
  return render(steps, 0);
}
function GraphCanvas({ graph, offset, query, types, onSelect }: { graph: BrainGraph; offset: number; query: string; types: string[]; onSelect: (id: string) => void }) {
  const window = graphWindow(graph, query, types, offset);
  const positions = new Map(window.nodes.map((node, index) => [node.id, { x: 110 + index % 5 * 190, y: 50 + Math.floor(index / 5) * 90 }]));
  return <div className="max-h-[36rem] overflow-auto rounded border border-(--iux-border)"><svg aria-label="Snapshot graph" role="group" viewBox={`0 0 1000 ${Math.max(180, Math.ceil(window.nodes.length / 5) * 90 + 30)}`} className="min-w-[40rem] text-(--iux-foreground)">
    <defs><marker id="source-brain-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="currentColor" /></marker></defs>
    {window.edges.slice(0, 2000).map((edge, index) => { const a = positions.get(edge.source)!; const b = positions.get(edge.target)!; return <line key={`${edge.id}-${index}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="currentColor" opacity="0.25" markerEnd="url(#source-brain-arrow)" />; })}
    {window.nodes.map(node => { const p = positions.get(node.id)!; return <g key={node.id} role="button" aria-label={node.label} tabIndex={0} onClick={() => onSelect(node.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(node.id); } }} className="cursor-pointer outline-none focus:text-[#f36c21]"><title>{node.label}</title><rect x={p.x - 85} y={p.y - 23} width="170" height="46" rx="6" fill="var(--iux-card)" stroke="currentColor" /><text x={p.x} y={p.y - 2} textAnchor="middle" fill="currentColor" fontSize="11" data-no-translate>{node.label.slice(0, 25)}</text><text x={p.x} y={p.y + 13} textAnchor="middle" fill="currentColor" fontSize="9" data-no-translate>{node.type}</text></g>; })}
  </svg></div>;
}
export function SourceBrain() {
  const params = new URLSearchParams(location.search);
  const manifest = useSource<{ data: { manifest: BrainManifest } }>("brain");
  const [tab, setTab] = useState(params.get("tab") ?? ""); const [selectedId, setSelectedId] = useState(params.get("node") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? ""); const [mode, setMode] = useState<View>((Object.hasOwn(views, params.get("view") ?? "") ? params.get("view") : "graph") as View);
  const [types, setTypes] = useState<string[]>([]); const [offset, setOffset] = useState(0); const [revisionA, setRevisionA] = useState(0); const [revisionB, setRevisionB] = useState(1);
  const rulesDialog = useRef<HTMLDialogElement>(null);
  const info = manifest.data?.data?.manifest; const tabs = info?.tabs ?? []; const active = tabs.find(t => t.id === tab) ?? tabs[0];
  const raw = useBrainProvider(active?.file);
  const source = useBrainProvider(info?.providers?.source); const history = useBrainProvider(info?.providers?.history);
  const flow = useBrainProvider(info?.providers?.flow); const sequence = useBrainProvider(info?.providers?.sequence); const rules = useBrainProvider(info?.providers?.aiRules);
  const parsed = useMemo(() => { try { return { graph: raw.data ? normalizeGraph(raw.data) : undefined }; } catch (error) { return { error: String(error) }; } }, [raw.data]);
  const graph = parsed.graph;
  const selected = graph?.nodes.find(node => node.id === selectedId);
  const file = String(selected?.data.file ?? selected?.data.filePath ?? selected?.data.path ?? "");
  const related = graph?.edges.filter(edge => edge.source === selectedId || edge.target === selectedId) ?? [];
  const revisions = (Array.isArray(history.data?.[file]) ? history.data[file] as unknown[] : []).map(record).filter(item => typeof item.content === "string").slice(0, 200);
  const diff = useMemo(() => compareLines(text(revisions[revisionA]?.content), text(revisions[revisionB]?.content)), [history.data, file, revisionA, revisionB]);
  const flowSteps = selected?.data.flowSteps ?? record(flow.data?.[selectedId]).flowSteps ?? flow.data?.[selectedId];
  const sequenceSteps = sequence.data?.[selectedId] ?? related;
  const aiRules = rules.data?.[selectedId] ?? rules.data?.global;
  useEffect(() => { const url = new URL(location.href); for (const [key, value] of Object.entries({ tab: active?.id ?? "", node: selectedId, q: query, view: mode })) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); } historyWindow(url); }, [active?.id, selectedId, query, mode]);
  function historyWindow(url: URL) { window.history.replaceState(null, "", url); }
  function select(id: string) { setSelectedId(id); setRevisionA(0); setRevisionB(1); }
  const windowed = graph ? graphWindow(graph, query, types, offset) : undefined;
  const nodeTypes = [...new Set(graph?.nodes.map(node => node.type) ?? [])];
  function metric(node: BrainNode) { const metrics = record(node.data.metrics); const value = mode === "risk" ? node.data.riskScore ?? metrics.cyclomaticComplexity : metrics.cyclomaticComplexity; return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
  const ranking = graph?.nodes.filter(node => metric(node) !== undefined).sort((a, b) => metric(b)! - metric(a)!).slice(0, 100) ?? [];
  function exportGraph() { if (!graph) return; const blob = new Blob([JSON.stringify(graph, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `source-brain-${(active?.id ?? "graph").replace(/[^A-Za-z0-9_.-]/g, "-").slice(0, 80)}.json`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 0); }
  const activeProvider = mode === "source" ? source : mode === "history" || mode === "diff" ? history : mode === "flow" ? flow : mode === "sequence" ? sequence : mode === "aiRules" ? rules : undefined;
  const providerError = activeProvider?.error;
  const needsNode = ["source", "history", "diff", "flow", "sequence", "aiRules"].includes(mode);
  return <>
    <Section title="Brain" description="Operator-provided graph snapshots stay local. No live application provider is configured automatically." action={<button className="iux-btn" onClick={manifest.refresh}>Refresh</button>}>
      {manifest.loading && <Skeleton />}{manifest.error && <Status value={{ ok: false, text: manifest.error }} />}
      <div className="flex flex-wrap gap-2">{tabs.map(t => <button key={t.id} className="iux-btn" aria-pressed={active?.id === t.id} data-no-translate onClick={() => { setTab(t.id); setSelectedId(""); setTypes([]); setOffset(0); }}>{t.label}</button>)}</div>
      {raw.loading && <Skeleton />}{raw.error && <Status value={{ ok: false, text: raw.error }} />}{parsed.error && <Status value={{ ok: false, text: parsed.error }} />}
      {graph ? <><p className="mt-3" data-no-translate>{graph.nodes.length} nodes · {graph.edges.length} edges · {String(graph.meta.analyzedAt ?? info?.date ?? "unknown date")}</p>{graph.omittedEdges > 0 && <p role="status">Dangling edges omitted: <span>{graph.omittedEdges}</span></p>}
        <div className="my-4 flex flex-wrap gap-2">{Object.entries(views).map(([id, title]) => <button className="iux-btn" key={id} aria-pressed={mode === id} onClick={() => setMode(id as View)}>{title}</button>)}</div>
        <div className="my-4 grid gap-4 sm:grid-cols-[2fr_1fr]"><Field label="Filter results"><input className="iux-input" value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} /></Field><details><summary>Legend</summary>{nodeTypes.map(type => <label key={type} className="m-1 inline-flex gap-1" data-no-translate><input type="checkbox" checked={!types.length || types.includes(type)} onChange={e => { setTypes(previous => { const activeTypes = previous.length ? previous.filter(t => t !== "__none__") : nodeTypes; const next = e.target.checked ? [...activeTypes.filter(t => t !== type), type] : activeTypes.filter(t => t !== type); return next.length ? next : ["__none__"]; }); setOffset(0); }} />{type}</label>)}</details></div>
        {mode === "graph" && <><p>Only the current graph window is drawn. Filters and export use the full snapshot.</p><GraphCanvas graph={graph} offset={offset} query={query} types={types} onSelect={select} /><div className="my-3 flex gap-3"><button className="iux-btn" disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 100))}>Previous</button><span>{windowed?.total}</span><button className="iux-btn" disabled={offset + 100 >= (windowed?.total ?? 0)} onClick={() => setOffset(n => n + 100)}>Next</button></div></>}
        {(mode === "complexity" || mode === "risk") && <><p>Recorded metrics rank review priorities; they are not security findings.</p><ol>{ranking.map(node => <li key={node.id}><button className="underline" data-no-translate onClick={() => select(node.id)}>{node.label} · {metric(node)}</button></li>)}</ol>{!ranking.length && <Empty>No recorded metrics.</Empty>}</>}
        {mode === "stress" && <Empty>Live stress testing is unavailable without an application provider.</Empty>}
        {mode === "export" && <button className="iux-btn" onClick={exportGraph}>Download JSON</button>}
        {mode === "usages" && (selected ? <ul>{related.map((edge, index) => <li key={index}><button className="underline" data-no-translate onClick={() => select(edge.source === selectedId ? edge.target : edge.source)}>{edge.source} → {edge.target} · {edge.label}</button></li>)}</ul> : <Empty>Select a graph node.</Empty>)}
        {needsNode && !selected && <Empty>Select a graph node.</Empty>}
        {mode === "source" && selected && (source.loading ? <Skeleton /> : source.unavailable || !source.data?.[file] ? <Empty>This provider is unavailable. Configure an authorized local snapshot.</Empty> : <pre className="max-h-[40rem] overflow-auto whitespace-pre-wrap break-all text-xs" data-no-translate>{typeof source.data[file] === "string" ? source.data[file] as string : text(record(source.data[file]).content)}</pre>)}
        {(mode === "history" || mode === "diff") && selected && (history.loading ? <Skeleton /> : revisions.length ? <><div className="my-3 grid gap-3 sm:grid-cols-2"><Field label="Revision A"><select className="iux-input" value={revisionA} onChange={e => setRevisionA(Number(e.target.value))}>{revisions.map((item, index) => <option value={index} key={index}>{String(item.revision ?? index)}</option>)}</select></Field><Field label="Revision B"><select className="iux-input" value={revisionB} onChange={e => setRevisionB(Number(e.target.value))}>{revisions.map((item, index) => <option value={index} key={index}>{String(item.revision ?? index)}</option>)}</select></Field></div><div className="grid gap-3 sm:grid-cols-2">{[revisions[revisionA], revisions[revisionB]].map((item, index) => <pre key={index} className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded border border-(--iux-border) p-3 text-xs" data-no-translate>{mode === "diff" ? diff.rows.map((row, line) => <span key={line} className={row.kind === "equal" ? "block" : index === 0 ? "block bg-red-500/15" : "block bg-green-500/15"}>{(index === 0 ? row.before : row.after) ?? " "}</span>) : text(item?.content)}</pre>)}</div>{mode === "diff" && diff.truncated && <p>Diff is capped at 1,000 lines per revision.</p>}</> : <Empty>This provider is unavailable. Configure an authorized local snapshot.</Empty>)}
        {mode === "flow" && selected && (flow.loading && !flowSteps ? <Skeleton /> : Array.isArray(flowSteps) ? <Flow steps={flowSteps} /> : <Empty>This provider is unavailable. Configure an authorized local snapshot.</Empty>)}
        {mode === "sequence" && selected && <><p>Snapshot relationships are not a runtime trace.</p><ArtifactDetails title="Sequence" value={sequenceSteps} /></>}
        {mode === "aiRules" && selected && (rules.loading ? <Skeleton /> : aiRules ? <button className="iux-btn" onClick={() => rulesDialog.current?.showModal()}>AI rules</button> : <Empty>This provider is unavailable. Configure an authorized local snapshot.</Empty>)}
        {providerError && <Status value={{ ok: false, text: providerError }} />}
        {selected && <aside className="mt-4 space-y-3 rounded border border-(--iux-border) p-3"><h3 className="font-semibold" data-no-translate>{selected.label}</h3><p data-no-translate>{selected.type} · {file}</p><ArtifactDetails title="Details" value={selected.data} /></aside>}
        <details className="mt-3"><summary>Nodes</summary><ul>{windowed?.nodes.map(node => <li key={node.id}><button className="underline" data-no-translate onClick={() => select(node.id)}>{node.label}</button></li>)}</ul></details>
      </> : !manifest.loading && <Empty>No graph provider is available.</Empty>}
    </Section>
    <dialog ref={rulesDialog} className="iux iux-dialog max-h-[80dvh] w-full max-w-3xl overflow-auto p-5" aria-label="AI rules"><button className="iux-btn" autoFocus onClick={() => rulesDialog.current?.close()}>Close</button><pre className="mt-3 whitespace-pre-wrap break-all text-xs" data-no-translate>{text(aiRules)}</pre></dialog>
  </>;
}
