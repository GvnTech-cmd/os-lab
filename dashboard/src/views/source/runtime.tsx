import { useEffect, useState } from "react";
import { Field, Section, Skeleton, Status } from "../../components/ui";
import { hostStore } from "../../lib/api";
import { SourceAction } from "./action";
import { useSource } from "./client";
interface Runtime { key: { configured: boolean; source: string; problem: string | null }; canary: { testUrl: string }; playwright: boolean; rotationWarning: string }
export function SourceRuntime() {
  const runtime = useSource<Runtime>("settings/runtime");
  const { data: host, error } = hostStore.use();
  const [action, setAction] = useState("generate-key"); const [rotate, setRotate] = useState(false);
  const [url, setUrl] = useState(""); const [slug, setSlug] = useState(""); const [session, setSession] = useState("");
  const targets = useSource<{ targets: { slug: string }[] }>("evidence");
  const detail = useSource<{ sessions: { session_id: string }[] }>(slug ? `evidence?slug=${encodeURIComponent(slug)}` : "");
  useEffect(() => { if (runtime.data) setUrl(runtime.data.canary.testUrl); }, [runtime.data?.canary.testUrl]);
  const owned = ["env", "env-file"].includes(runtime.data?.key.source ?? "");
  const labReady = host?.labs.find(l => l.id === "source")?.state === "ready" && !error;
  const keyReady = !owned && (runtime.data?.key.source === "none" || rotate);
  const options = action === "set-canary" ? { action, testUrl: url } : action === "verify-session" ? { action, slug, session } : { action, rotate };
  let urlValid = false;
  try { const parsed = new URL(url); urlValid = ["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password && !parsed.search && !parsed.hash; } catch { /* Invalid URLs cannot be submitted. */ }
  return <Section title="Runtime settings" action={<button className="iux-btn" onClick={runtime.refresh}>Refresh</button>}>
    {runtime.loading && !runtime.data ? <Skeleton /> : runtime.error ? <Status value={{ ok: false, text: runtime.error }} /> : runtime.data && <div className="space-y-4">
      <dl><dt>Key status</dt><dd data-no-translate>{runtime.data.key.source} · {String(runtime.data.key.configured)}</dd></dl>
      {runtime.data.key.problem && <Status value={{ ok: false, text: runtime.data.key.problem }} />}
      {owned && <p>The environment owns this key. Change it outside the dashboard.</p>}
      {!runtime.data.playwright && <p>Playwright is optional. Without live browser tooling, canary events are synthetic and cannot establish live behavior.</p>}
      <p>Keys are never displayed. Rotation requires the original key to verify older sessions.</p>
      <Field label="Action"><select className="iux-input" value={action} onChange={e => { setAction(e.target.value); setRotate(false); }}><option value="generate-key">Signing key</option><option value="set-canary">Canary URL</option><option value="verify-session">Verification</option></select></Field>
      {action === "generate-key" && runtime.data.key.source !== "none" && <label className="block"><input type="checkbox" checked={rotate} disabled={owned} onChange={e => setRotate(e.target.checked)} /> I understand that rotation prevents verification of old sessions with the new key.</label>}
      {action === "set-canary" && <Field label="Configured canary URL"><input className="iux-input" type="url" value={url} onChange={e => setUrl(e.target.value)} /></Field>}
      {action === "verify-session" && <div className="grid gap-3 sm:grid-cols-2"><Field label="Target"><select className="iux-input" value={slug} onChange={e => { setSlug(e.target.value); setSession(""); }}><option value="">Select</option>{targets.data?.targets.map(t => <option key={t.slug}>{t.slug}</option>)}</select></Field><Field label="Session"><select className="iux-input" value={session} onChange={e => setSession(e.target.value)}><option value="">Select</option>{detail.data?.sessions.map(s => <option key={s.session_id}>{s.session_id}</option>)}</select></Field>{detail.error && <Status value={{ ok: false, text: detail.error }} />}</div>}
      <SourceAction endpoint="settings/runtime" options={options} ready={Boolean(labReady && (action === "generate-key" ? keyReady : action === "set-canary" ? urlValid : runtime.data.key.configured && slug && session))} onFinished={runtime.refresh} />
    </div>}
  </Section>;
}
