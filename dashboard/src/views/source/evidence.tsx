import { useCallback, useEffect, useState } from "react";
import type { Coverage, Finding } from "../../lib/source-contracts";
import { Empty, Field, Section, Skeleton, Status } from "../../components/ui";
import { hostStore, type LabJob } from "../../lib/api";
import { useSource } from "./client";
import { SourceAction } from "./action";
import { sourceHref } from "./pages";
export function ArtifactDetails({ title, value }: { title: string; value: unknown }) {
  return <details className="rounded border border-(--iux-border) p-3"><summary>{title}</summary><pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-all text-xs" data-no-translate>{JSON.stringify(value ?? null, null, 2)}</pre></details>;
}
interface Session { session_id: string; platform: string; collector?: { profile_mode?: string }; limitations?: string[]; integrity: string }
interface Detail { slug: string; platform: string; findings: Finding[]; coverage: Coverage | null; scorecard: unknown; reports: string[]; sessions: Session[]; sessionsTruncated: boolean }
interface Targets { targets: { slug: string; platform?: string; findingCount?: number; error?: string }[]; truncated: boolean }
interface Detection { targets: { key: string; name: string; slug: string }[]; runner: { ready: boolean }; run: LabJob | null }
export function SourceEvidence() {
  const query = new URLSearchParams(window.location.search);
  const [slug, setSlug] = useState(query.get("slug") ?? ""); const [session, setSession] = useState(query.get("session") ?? "");
  const runtime = useSource<{ key: { configured: boolean }; canary: { testUrl: string }; playwright: boolean }>("settings/runtime");
  const [mode, setMode] = useState("static"); const [testUrl, setTestUrl] = useState("");
  useEffect(() => { if (runtime.data) setTestUrl(runtime.data.canary.testUrl); }, [runtime.data?.canary.testUrl]);
  const [target, setTarget] = useState(""); const [platform, setPlatform] = useState("auto");
  const [state, setState] = useState(""); const [severity, setSeverity] = useState(""); const [filter, setFilter] = useState("");
  const list = useSource<Targets>("evidence"); const detection = useSource<Detection>("detection");
  const detail = useSource<Detail>(slug ? `evidence?slug=${encodeURIComponent(slug)}` : "");
  const events = useSource<{ events: Record<string, unknown>[]; truncated: boolean; integrity: string }>(slug && session ? `evidence?slug=${encodeURIComponent(slug)}&session=${encodeURIComponent(session)}` : "");
  const { data: host, error: hostError } = hostStore.use();
  useEffect(() => {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries({ slug, session })) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key); }
    history.replaceState(null, "", url);
  }, [slug, session]);
  const finished = useCallback(() => { list.refresh(); detail.refresh(); detection.refresh(); }, [list.refresh, detail.refresh, detection.refresh]);
  const labReady = host?.labs.find(l => l.id === "source")?.state === "ready" && !hostError;
  const data = slug ? detail.data : undefined;
  const selectedTarget = detection.data?.targets.find(t => t.key === target);
  const sessionMatches = Boolean(session && selectedTarget?.slug === slug);
  const modeReady = mode === "static" || (runtime.data?.key.configured && (mode === "session" ? sessionMatches : ["auto", "browser-extension"].includes(platform) && /^https?:\/\//.test(testUrl)));
  const findings = (data?.findings ?? []).filter(f => (!state || f.state === state) && (!severity || f.severity === severity) && JSON.stringify(f).toLowerCase().includes(filter.toLowerCase()));
  return <>
    <Section title="Detection"><div className="grid gap-3 sm:grid-cols-2"><Field label="Target"><select className="iux-input" value={target} onChange={e => setTarget(e.target.value)}><option value="">Select</option>{detection.data?.targets?.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}</select></Field>
      <Field label="Platform"><select className="iux-input" value={platform} onChange={e => setPlatform(e.target.value)}>{["auto", "browser-extension", "windows-app", "macos-app", "android-app", "ios-app"].map(p => <option key={p}>{p}</option>)}</select></Field></div>
      {detection.error && <Status value={{ ok: false, text: detection.error }} />}
      <details className="mt-3 rounded border border-(--iux-border) p-3"><summary>Runtime settings</summary><div className="mt-3 space-y-3">
        <Field label="Runtime mode"><select className="iux-input" value={mode} onChange={e => setMode(e.target.value)}><option value="static">Static analysis</option><option value="canary">Browser canary</option><option value="session">Selected session</option></select></Field>
        {mode !== "static" && <p>Signatures are not verified by browsing. Synthetic events cannot establish live behavior.</p>}
        {mode === "canary" && <><Field label="Configured canary URL"><input type="url" className="iux-input" value={testUrl} onChange={e => setTestUrl(e.target.value)} /></Field>{!runtime.data?.playwright && <p>Playwright is optional. Without live browser tooling, canary events are synthetic and cannot establish live behavior.</p>}</>}
        {mode === "session" && !sessionMatches && <p>Select a session belonging to the detection target.</p>}
        {runtime.error && <Status value={{ ok: false, text: runtime.error }} />}
      </div></details>
      <SourceAction endpoint="detection" options={{ target, platform, ...(mode === "session" ? { session } : mode === "canary" ? { runCanary: true, testUrl } : {}) }} ready={Boolean(labReady && target && modeReady && detection.data?.runner.ready)} initialJob={detection.data?.run} onFinished={finished} />
      <a className="mt-3 inline-block underline" href={sourceHref("settings/runtime")}>Runtime settings</a>
    </Section>
    <Section title="Evidence" action={<button className="iux-btn" onClick={() => { list.refresh(); detail.refresh(); }}>Refresh</button>}>
      <Field label="Target"><select className="iux-input" value={slug} onChange={e => { setSlug(e.target.value); setSession(""); }}><option value="">Select</option>{list.data?.targets?.map(t => <option key={t.slug} value={t.slug}>{t.slug} · {t.platform ?? t.error ?? ""}</option>)}</select></Field>
      {list.loading && <Skeleton />}{list.error && <Status value={{ ok: false, text: list.error }} />}
      {list.data?.truncated && <p>Results are capped. Refine the private workspace before comparing totals.</p>}
      {!slug && <Empty>Select a target to inspect evidence.</Empty>}
      {slug && detail.loading && <Skeleton />}{slug && detail.error && <Status value={{ ok: false, text: detail.error }} />}
      {data && <div className="mt-4 space-y-4">
        <ArtifactDetails title="Coverage" value={data.coverage} /><ArtifactDetails title="Scorecard" value={data.scorecard} />
        <div className="grid gap-3 sm:grid-cols-3"><Field label="State"><select className="iux-input" value={state} onChange={e => setState(e.target.value)}><option value="">All</option>{["capability", "static_lead", "runtime_observation", "correlated_behavior", "not_observed_under_test"].map(s => <option key={s}>{s}</option>)}</select></Field><Field label="Severity"><select className="iux-input" value={severity} onChange={e => setSeverity(e.target.value)}><option value="">All</option>{["info", "low", "medium", "high", "critical", "review"].map(s => <option key={s}>{s}</option>)}</select></Field><Field label="Filter results"><input className="iux-input" value={filter} onChange={e => setFilter(e.target.value)} /></Field></div>
        {findings.map((f, index) => <article className="space-y-2 rounded border border-(--iux-border) p-3" key={`${f.finding_id}-${index}`}>
          <h3 className="font-semibold" data-no-translate>{f.finding_id}</h3><p data-no-translate>{f.state} · {f.severity} · {f.confidence} · {f.heuristic}</p><p data-no-translate>{f.hypothesis}</p>
          <ArtifactDetails title="Evidence" value={f.evidence} /><ArtifactDetails title="Verification" value={f.verification} /><ArtifactDetails title="Alternatives" value={f.alternative_explanations} /><ArtifactDetails title="Remediation" value={f.remediation} /><ArtifactDetails title="Limitations" value={{ scope: f.scope, limitations: f.limitations }} />
        </article>)}
        {!findings.length && <Empty>No findings.</Empty>}
        <Section title="Sessions"><Field label="Session"><select className="iux-input" value={session} onChange={e => setSession(e.target.value)}><option value="">Select</option>{data.sessions.map(s => <option key={s.session_id} value={s.session_id}>{s.session_id} · {s.collector?.profile_mode} · {s.integrity}</option>)}</select></Field><p>Signatures are not verified by browsing. Synthetic events cannot establish live behavior.</p>{session && <><ArtifactDetails title="Sessions" value={data.sessions.find(s => s.session_id === session)} />{events.error && <Status value={{ ok: false, text: events.error }} />}<ArtifactDetails title="Timeline" value={events.data} /></>}</Section>
        <div className="flex flex-wrap gap-3">{data.reports.map(file => <a key={file} className="underline" href={`/api/source/evidence/report?slug=${encodeURIComponent(slug)}&file=${encodeURIComponent(file)}`} data-no-translate>{file}</a>)}</div>
      </div>}
    </Section>
  </>;
}
