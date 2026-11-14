import { useState, type FormEvent } from "react";
import { BookOpenIcon } from "@phosphor-icons/react";
import { AppShell } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { PageHead } from "../components/ui";
import { buildHowToUsePrompt } from "../lib/how-to-use";
import { localeFromPath } from "../i18n/paths";

export default function HowToUsePage() {
  const [request, setRequest] = useState("");
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<"idle" | "copying" | "copied" | "failed">("idle");

  async function copyPrompt(value: string) {
    setStatus("copying");
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!request.trim() || status === "copying") return;
    const value = buildHowToUsePrompt(request, import.meta.env.PUBLIC_SITE_MODE === "pages", localeFromPath(window.location.pathname));
    setPrompt(value);
    void copyPrompt(value);
  }

  return <AppShell activeId="how-to-use">
    <TopBar title="How to use" icon={<BookOpenIcon size={20} weight="duotone" />} />
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 sm:p-6">
      <PageHead icon={<BookOpenIcon size={22} />} title="How to use" description="Describe your task and copy a prompt for any LLM to guide you through os-lab." />
      <p className="text-sm text-(--iux-muted-foreground)">Built in your browser. No request is sent to an LLM or saved by this page. Review the prompt before sharing it; leave out secrets and private data.</p>
      <form onSubmit={submit} className="iux-card gap-4 p-5">
        <label htmlFor="task-request" className="font-medium">What do you want to do?</label>
        <textarea id="task-request" required maxLength={12000} rows={6} value={request} disabled={status === "copying"}
          onChange={event => { setRequest(event.target.value); setPrompt(""); setStatus("idle"); }}
          className="w-full rounded-md border border-(--iux-input) bg-(--iux-background) p-3 focus-visible:outline-2 focus-visible:outline-(--iux-ring)" />
        <p className="text-sm text-(--iux-muted-foreground)">The prompt includes the shipped capability catalog, platform limits, lab workflows, documentation links and your task. It does not include live host data. Generated guidance context is in English; the LLM is asked to answer in your task language.</p>
        <button type="submit" disabled={!request.trim() || status === "copying"} data-variant="primary" className="iux-btn self-start">Generate and copy prompt</button>
      </form>
      <div role="status" aria-live="polite" className="text-sm">
        {status === "copying" && <p>Copying prompt…</p>}
        {status === "copied" && <p>Prompt copied. Paste it into your preferred LLM.</p>}
        {status === "failed" && <p>Clipboard unavailable. Select the generated prompt and copy it manually, or try again.</p>}
      </div>
      {prompt && <section className="iux-card gap-4 p-5">
        <label htmlFor="generated-prompt" className="font-medium">Generated prompt</label>
        <textarea id="generated-prompt" readOnly translate="no" lang="en" rows={16} value={prompt} className="w-full rounded-md border border-(--iux-input) bg-(--iux-background) p-3 text-sm" />
        <div className="flex flex-wrap gap-3">
          <button type="button" disabled={status === "copying"} onClick={() => void copyPrompt(prompt)} data-variant="primary" className="iux-btn">Copy prompt again</button>
          <button type="button" className="iux-btn" onClick={() => { const area = document.getElementById("generated-prompt") as HTMLTextAreaElement; area.focus(); area.select(); }}>Select prompt</button>
        </div>
      </section>}
    </main>
  </AppShell>;
}
