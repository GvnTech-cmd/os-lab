/** Content updates: what is installed, check for a newer signed pack, install it (data, and hooks only on request). */
import { useEffect, useRef, useState } from "react";
import { ArrowsClockwiseIcon } from "@phosphor-icons/react";
import { Badge, Section, Status } from "../components/ui";
import { api, contentStore, message, type ContentState } from "../lib/api";

const when = (seconds: number | null) => (seconds ? new Date(seconds * 1000).toLocaleString() : null);

export function ContentPanel() {
  const { data, error, refresh } = contentStore.use();
  const [busy, setBusy] = useState(false);
  const [hooks, setHooks] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [fresh, setFresh] = useState<ContentState | null>(null);
  const [phase, setPhase] = useState<"checking" | "installing" | null>(null);
  const autoCheckStarted = useRef(false);
  const advanced = useRef<HTMLDetailsElement>(null);
  const state = fresh ?? data;

  useEffect(() => {
    if (!state || state.offline || autoCheckStarted.current || (state.checkedAt && Date.now() / 1000 - state.checkedAt < 900)) return;
    autoCheckStarted.current = true;
    setBusy(true);
    setPhase("checking");
    api.contentCheck().then((next) => {
      setFresh(next);
      void refresh();
    }).catch((e) => setResult({ ok: false, text: message(e) })).finally(() => {
      setBusy(false);
      setPhase(null);
    });
  }, [state, refresh]);

  async function run(action: () => Promise<ContentState>, done: (s: ContentState) => string) {
    setBusy(true);
    setPhase(null);
    setResult(null);
    try {
      const next = await action();
      setFresh(next);
      setResult({ ok: true, text: done(next) });
      void refresh();
    } catch (e) {
      setResult({ ok: false, text: message(e) });
    } finally {
      setBusy(false);
      setConfirmReset(false);
    }
  }

  async function quickUpdate() {
    if (state?.hooks && available) {
      if (advanced.current) advanced.current.open = true;
      setResult({ ok: true, text: "Frida hooks are installed. Choose whether to include them in Advanced options before updating." });
      return;
    }
    setBusy(true);
    setResult(null);
    setPhase("checking");
    try {
      const checked = await api.contentCheck();
      setFresh(checked);
      if (!checked.updateAvailable) {
        setResult({ ok: true, text: "Content is up to date." });
        return;
      }
      if (checked.hooks) {
        if (advanced.current) advanced.current.open = true;
        setResult({ ok: true, text: "Frida hooks are installed. Choose whether to include them in Advanced options before updating." });
        return;
      }
      setPhase("installing");
      const installed = await api.contentUpdate(false);
      setFresh(installed);
      setResult({ ok: true, text: "Content updated." });
      void refresh();
    } catch (e) {
      setResult({ ok: false, text: message(e) });
    } finally {
      setBusy(false);
      setPhase(null);
    }
  }

  const available = Boolean(state?.latest && state.latest.sequence > state.sequence);
  // The card appears when something is installable and stays for the result of an action.
  if (!available && !result) return null;
  return (
    <Section
      id="content"
      icon={<ArrowsClockwiseIcon size={16} />}
      title="Content updates"
      description="Firewall Lab companies, guides and legal documents update from a signed pack, without a new app release."
      action={<a className="text-xs underline" href="/content/">Learn more</a>}
    >
      {error && !state ? (
        <p className="text-sm text-(--iux-muted-foreground)">Content updates are not available in this view.</p>
      ) : !state ? null : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1 text-sm">
              <p className="font-medium">{state.installed ? <><span>Installed</span>: <span data-no-translate>{state.version}</span></> : <><span>Bundled with this app</span>: <span data-no-translate>{state.version}</span></>}</p>
              <p className="text-xs text-(--iux-muted-foreground)">
                {state.offline ? "Content updates are switched off on this computer (OSLAB_CONTENT_OFFLINE)." :
                  available ? <><span>A newer content pack is available.</span> <span data-no-translate>{state.latest?.version}</span></> :
                    state.checkedAt ? "Content is up to date." : phase === "checking" ? "Checking for updates…" : "Check for updates"}
              </p>
            </div>
            <button type="button" className="iux-btn bg-[#f36c21] text-white hover:bg-[#fa7b32]"
              disabled={busy || state.offline} onClick={() => void quickUpdate()}>
              {busy ? "Working…" : state.hooks && available ? "Review update" : available ? "Install update" : "Check and update"}
            </button>
          </div>
          {phase ? (
            <div role="status" className="space-y-1 text-xs text-(--iux-muted-foreground)">
              <p>{phase === "checking" ? "Checking for updates…" : "Downloading, verifying and installing…"}</p>
              <progress className="h-2 w-full accent-[#f36c21]" />
            </div>
          ) : null}
          <Status value={result} />
          <details ref={advanced} className="border-t border-(--iux-border) pt-3">
            <summary className="cursor-pointer text-sm font-medium">Advanced options</summary>
            <div className="mt-4 flex flex-col gap-4">
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <div className="flex items-center gap-2">
              <dt className="text-(--iux-muted-foreground)">{state.installed ? "Installed" : "Using"}</dt>
              <dd className="font-mono text-xs">{state.installed ? state.version : <Badge>Bundled with this app</Badge>}</dd>
            </div>
            {state.installed ? (
              <div className="flex items-center gap-2">
                <dt className="text-(--iux-muted-foreground)">Updated</dt>
                <dd className="text-xs">{when(state.updatedAt)}</dd>
              </div>
            ) : null}
            <div className="flex items-center gap-2">
              <dt className="text-(--iux-muted-foreground)">Latest available</dt>
              <dd className="font-mono text-xs">{state.latest?.version ?? "–"}</dd>
            </div>
            <div className="flex items-center gap-2">
              <dt className="text-(--iux-muted-foreground)">Last checked</dt>
              <dd className="text-xs">{when(state.checkedAt) ?? "–"}</dd>
            </div>
            {state.installed ? (
              <div className="flex items-center gap-2">
                <dt className="text-(--iux-muted-foreground)">Frida hooks</dt>
                <dd>{state.hooks ? <Badge tone="warning">Hooks installed</Badge> : <Badge>Hooks not installed</Badge>}</dd>
              </div>
            ) : null}
            {available ? (
              <div className="flex items-center gap-2">
                <dt className="sr-only">Status</dt>
                <dd><Badge tone="success">A newer content pack is available.</Badge></dd>
              </div>
            ) : null}
          </dl>

          {state.offline ? (
            <p className="text-sm text-(--iux-warning)">Content updates are switched off on this computer (OSLAB_CONTENT_OFFLINE).</p>
          ) : (
            <>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={hooks} onChange={(e) => setHooks(e.target.checked)} disabled={busy} />
                <span>
                  <span className="font-medium">Include Frida hooks</span>
                  <span className="block text-xs text-(--iux-muted-foreground)">
                    Hook scripts run inside other processes. They are installed only when you tick this box, and every update asks again.
                  </span>
                </span>
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="iux-btn"
                  data-variant="outline"
                  disabled={busy}
                  onClick={() => void run(api.contentCheck, (s) => (s.updateAvailable ? "A newer content pack is available." : "Content is up to date."))}
                >
                  Check for updates
                </button>
                <button
                  type="button"
                  className="iux-btn bg-[#f36c21] text-white hover:bg-[#fa7b32]"
                  disabled={busy}
                  onClick={() => void run(() => api.contentUpdate(hooks), () => "Content updated.")}
                >
                  Update content
                </button>
                {state.installed ? (
                  confirmReset ? (
                    <>
                      <button type="button" className="iux-btn" data-variant="outline" disabled={busy} onClick={() => void run(api.contentReset, () => "Reset to the bundled content.")}>
                        Confirm reset
                      </button>
                      <button type="button" className="iux-btn" data-variant="outline" disabled={busy} onClick={() => setConfirmReset(false)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button type="button" className="iux-btn" data-variant="outline" disabled={busy} onClick={() => setConfirmReset(true)}>
                      Reset to bundled
                    </button>
                  )
                ) : null}
              </div>
            </>
          )}
          <p className="text-xs text-(--iux-muted-foreground)" data-no-translate>{state.source}</p>
            </div>
          </details>
        </div>
      )}
    </Section>
  );
}
