import { useEffect, useRef, useState } from "react";
import type { RepoMapV1 } from "../../lib/source-contracts";
import { Empty, Field, Section, Skeleton, Status } from "../../components/ui";
import { ArtifactDetails } from "./evidence";
import { SourceCrawler } from "./crawler";
import { useSource } from "./client";
interface Bundle { slug: string; repo: string; manifestAnalysis: unknown; dependencies: unknown; metadata: unknown; fileTree: { path: string; type: string }[] | null; astIndex: { path: string; parser: string; file: string }[] | null; repoMap: RepoMapV1 | null }
export function SourceDeep() {
  const query = new URLSearchParams(window.location.search);
  const [repo, setRepo] = useState(query.get("repo") ?? ""); const [file, setFile] = useState(query.get("file") ?? "");
  const [filter, setFilter] = useState(""); const [view, setView] = useState("source");
  const [mapFilter, setMapFilter] = useState(""); const [mapPage, setMapPage] = useState(0);
  const [role, setRole] = useState(""); const [lang, setLang] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useSource<{ analyzedRepos: Bundle[]; availableRepos: { key: string; slug: string }[]; truncated: boolean }>("deep-analysis");
  const selected = useSource<Bundle>(repo ? `deep-analysis?repo=${encodeURIComponent(repo)}` : "");
  const contents = useSource<{ content?: string; ast?: unknown }>(repo && file ? `deep-analysis?repo=${encodeURIComponent(repo)}&file=${encodeURIComponent(file)}${view === "ast" ? "&view=ast" : ""}` : "");
  useEffect(() => { const url = new URL(location.href); for (const [key, value] of Object.entries({ repo, file })) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); } history.replaceState(null, "", url); }, [repo, file]);
  const data = repo ? selected.data : undefined;
  const map = data?.repoMap;
  const files = (Array.isArray(data?.fileTree) ? data.fileTree : []).filter(f => f && typeof f.path === "string" && f.type !== "tree" && f.path.toLowerCase().includes(filter.toLowerCase()));
  const mapFiles = Object.entries(map?.files ?? {}).filter(([path, info]) => info && info.role && (!role || info.role.kind === role) && (!lang || info.lang === lang) && `${path} ${JSON.stringify(info)}`.toLowerCase().includes(mapFilter.toLowerCase()));
  const targetKey = list.data?.availableRepos?.find(t => t.slug === data?.slug)?.key;
  return <>
    <Section title="Deep analysis" action={<button className="iux-btn" onClick={() => { list.refresh(); selected.refresh(); }}>Refresh</button>}>
      <Field label="Repository"><select className="iux-input" value={repo} onChange={e => { setRepo(e.target.value); setFile(""); }}><option value="">Select</option>{list.data?.analyzedRepos?.map(r => <option key={r.slug} value={r.repo}>{r.repo}</option>)}</select></Field>
      {list.loading && <Skeleton />}{list.error && <Status value={{ ok: false, text: list.error }} />}
      {list.data?.truncated && <p>Results are capped. Refine the private workspace before comparing totals.</p>}
      {selected.error && <Status value={{ ok: false, text: selected.error }} />}
      {!data && !selected.loading && <Empty>No matching results. Add authorized targets or adjust filters.</Empty>}
      {data && <div className="mt-4 space-y-3"><ArtifactDetails title="Manifest" value={data.manifestAnalysis} /><ArtifactDetails title="Dependencies" value={data.dependencies} /><ArtifactDetails title="Metadata" value={data.metadata} />
        {map?.schema_version === 1 ? <button className="iux-btn" onClick={() => dialog.current?.showModal()}>Structural map</button> : <Empty>Structural map is unavailable. Run the crawler with map generation enabled.</Empty>}
        <Field label="Filter results"><input className="iux-input" value={filter} onChange={e => setFilter(e.target.value)} /></Field>
        <Field label="File"><select className="iux-input" value={file} onChange={e => setFile(e.target.value)}><option value="">Select</option>{files.slice(0, 1000).map(f => <option key={f.path}>{f.path}</option>)}</select></Field>
        <div className="flex gap-2"><button className="iux-btn" aria-pressed={view === "source"} onClick={() => setView("source")}>Source</button><button className="iux-btn" aria-pressed={view === "ast"} onClick={() => setView("ast")}>AST</button></div>
        {contents.loading && file && <Skeleton />}{contents.error && file && <Status value={{ ok: false, text: contents.error }} />}
        {file && view === "source" && <pre className="max-h-[40rem] overflow-auto whitespace-pre-wrap break-all rounded bg-(--iux-muted) p-3 text-xs" data-no-translate>{contents.data?.content}</pre>}
        {file && view === "ast" && <ArtifactDetails title="AST" value={contents.data?.ast} />}
        <ArtifactDetails title="AST index" value={data.astIndex} />
      </div>}
    </Section>
    {targetKey && <SourceCrawler targetKey={targetKey} />}
    <dialog ref={dialog} className="iux iux-dialog max-h-[90dvh] w-full max-w-5xl overflow-auto p-5" aria-label="Structural map"><div className="mb-4 flex justify-between gap-3"><h2>Structural map</h2><button className="iux-btn" autoFocus onClick={() => dialog.current?.close()}>Close</button></div>
      <p>A structural map describes source structure, not observed behavior.</p>
      <div className="my-4 grid gap-3 sm:grid-cols-3"><Field label="Filter results"><input className="iux-input" value={mapFilter} onChange={e => { setMapFilter(e.target.value); setMapPage(0); }} /></Field><Field label="Role"><select className="iux-input" value={role} onChange={e => { setRole(e.target.value); setMapPage(0); }}><option value="">All</option>{[...new Set(Object.values(map?.files ?? {}).filter(f => f?.role).map(f => f.role.kind))].map(v => <option key={v}>{v}</option>)}</select></Field><Field label="Language"><select className="iux-input" value={lang} onChange={e => { setLang(e.target.value); setMapPage(0); }}><option value="">All</option>{[...new Set(Object.values(map?.files ?? {}).filter(Boolean).map(f => f.lang))].map(v => <option key={v}>{v}</option>)}</select></Field></div>
      <ArtifactDetails title="Statistics" value={map?.stats} /><ArtifactDetails title="Coverage" value={map?.coverage} /><ArtifactDetails title="Targets" value={map?.targets} /><ArtifactDetails title="Entrypoints" value={map?.entrypoints} />
      <div className="my-3 flex gap-3"><button className="iux-btn" disabled={!mapPage} onClick={() => setMapPage(n => n - 1)}>Previous</button><span>{mapFiles.length}</span><button className="iux-btn" disabled={(mapPage + 1) * 50 >= mapFiles.length} onClick={() => setMapPage(n => n + 1)}>Next</button></div>
      {mapFiles.slice(mapPage * 50, mapPage * 50 + 50).map(([path, info]) => <article className="my-3 space-y-2 rounded border border-(--iux-border) p-3" key={path}><button className="underline" data-no-translate onClick={() => { setFile(path); setView("source"); dialog.current?.close(); }}>{path}</button><p data-no-translate>{info.lang} · {info.parser} · {info.role.kind} ({info.role.confidence})</p><ArtifactDetails title="Symbols" value={info.symbols} /><ArtifactDetails title="Imports" value={info.imports} /></article>)}
    </dialog>
  </>;
}
