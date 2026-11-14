/** /jobs/ — every lab job this console started, with its output, newest first. */
import { useEffect, useRef, useState } from "react";
import { ListChecksIcon, StopIcon } from "@phosphor-icons/react";
import { AppShell, LAB_ICON, labHref } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { Badge, Empty, PageHead, Section, Skeleton } from "../components/ui";
import { ago, api, jobsStore, message, usePoll, type LabJob } from "../lib/api";

const TONE: Record<LabJob["state"], "success" | "warning" | "danger" | undefined> = {
  running: "warning",
  succeeded: "success",
  failed: "danger",
  interrupted: "danger",
  "timed-out": "danger",
  cancelled: undefined
};

function lineClass(line: string) {
  if (/\b(error|failed|traceback|denied)\b/i.test(line)) return "text-red-400";
  if (/\bwarn(ing)?\b/i.test(line)) return "text-amber-400";
  if (/^(==>|\[ok\]|ok\b)/i.test(line.trim())) return "text-[#00d084]";
  return "text-zinc-300";
}

function JobLog({ job }: { job: LabJob }) {
  const { data } = usePoll(() => api.job(job.id), job.state === "running" ? 1500 : 0, [job.id, job.state]);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const logs = data?.logs ?? [];
  useEffect(() => {
    const el = box.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 60) el.scrollTop = el.scrollHeight;
  }, [logs.length]);
  return (
    <div className="apk-crosshair-box rounded-2xl border border-(--iux-border) bg-[#090d14] p-5 shadow-xl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-sm font-semibold text-[#f36c21]">{job.label}</p>
          <p className="truncate font-mono text-xs text-orange-200/70">{job.command}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={TONE[job.state]}>{job.state}</Badge>
          {job.state === "running" ? (
            <button
              type="button"
              disabled={cancelling}
              onClick={async () => {
                setCancelling(true);
                setCancelError(null);
                try {
                  await api.cancel(job.id);
                  await jobsStore.refresh();
                } catch (error) {
                  setCancelError(message(error));
                } finally {
                  setCancelling(false);
                }
              }}
              className="flex items-center gap-1.5 rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-1 text-xs font-semibold text-red-400 hover:bg-red-500/20 disabled:opacity-50"
            >
              <StopIcon size={12} weight="fill" /> {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          ) : null}
        </div>
      </div>
      {cancelError ? <p role="alert" className="mb-3 text-sm text-red-400"><span>Could not cancel job:</span> <span data-no-translate>{cancelError}</span>. <span>Try again.</span></p> : null}
      <div ref={box} className="apk-code-scroll max-h-[28rem] overflow-y-auto rounded-xl border border-white/10 bg-black/90 p-4 font-mono text-xs leading-relaxed">
        {data?.truncated ? <p className="mb-2 text-zinc-500">… earlier output was trimmed</p> : null}
        {logs.length === 0 ? (
          <p className="text-zinc-500">{job.state === "running" ? "Waiting for output…" : "No output."}</p>
        ) : (
          logs.map((line, i) => (
            <div key={i} className="flex whitespace-pre-wrap break-words">
              <span className="mr-3 w-10 shrink-0 text-right text-zinc-600 select-none">{i + 1}</span>
              <span className={lineClass(line)}>{line}</span>
            </div>
          ))
        )}
      </div>
      {job.error ? <p className="mt-2 text-xs text-red-400">{job.error}</p> : null}
    </div>
  );
}

export default function JobsPage() {
  const { data: jobs, error } = jobsStore.use();
  const [selected, setSelected] = useState<string | null>(() => window.location.hash.slice(1) || null);
  const current = (jobs ?? []).find((j) => j.id === selected) ?? jobs?.[0];
  return (
    <AppShell activeId="jobs">
      <div className="iux min-h-screen">
        <TopBar title="Jobs" icon={<ListChecksIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
          <PageHead
            icon={<ListChecksIcon size={22} />}
            title="Lab jobs"
            description="The 50 most recent lab jobs. Source Lab keeps private restart records and marks unfinished work as interrupted."
          />
          {error && !jobs ? (
            <Empty>Could not load jobs: {error}</Empty>
          ) : !jobs ? (
            <Skeleton rows={4} />
          ) : jobs.length === 0 ? (
            <Empty>No jobs yet. Open a lab from This computer and preview an action.</Empty>
          ) : (
            <>
              {current ? <JobLog key={current.id} job={current} /> : null}
              <Section title="History" description={`${jobs.length} jobs`}>
                <ul className="divide-y divide-(--iux-border)">
                  {jobs.map((job) => (
                    <li key={job.id} id={job.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(job.id);
                          history.replaceState(null, "", `#${job.id}`);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                        className={`flex w-full flex-wrap items-center gap-3 rounded-md px-2 py-2.5 text-left text-sm hover:bg-(--iux-accent)/60 ${job.id === current?.id ? "bg-(--iux-accent)" : ""}`}
                      >
                        <span className="text-[#f36c21]">{LAB_ICON[job.lab](16)}</span>
                        <span className="min-w-0 flex-1">
                          <span className="font-medium">{job.label}</span>
                          <span className="block truncate font-mono text-xs text-(--iux-muted-foreground)">{job.command}</span>
                        </span>
                        <span className="text-xs text-(--iux-muted-foreground)">{ago(job.startedAt)}</span>
                        <Badge tone={TONE[job.state]}>{job.state}</Badge>
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-(--iux-muted-foreground)">
                  Start new jobs from a lab page, for example <a className="underline" href={labHref("android")}>Android runtime</a>.
                </p>
              </Section>
            </>
          )}
        </main>
      </div>
    </AppShell>
  );
}
