import { TerminalWindowIcon } from "@phosphor-icons/react";
import { AppShell } from "../../shell/app-shell";
import { TopBar } from "../../shell/top-bar";
import { Empty, Section } from "../../components/ui";
import { localeFromPath, localePath } from "../../i18n/paths";
import { SourceBrain } from "./brain";
import { SourcePipeline } from "./pipeline";
import { SourceDeep } from "./deep";
import { SourceRuntime } from "./runtime";
import { SourceEvidence } from "./evidence";
import { SourceCrawler } from "./crawler";
import { SourceOverview, SourceCatalogs } from "./overview";
import { PUBLIC_SOURCE } from "./client";

export const SOURCE_PAGES = ["", "analyzer", "evidence", "deep-analysis", "pipeline", "brain", "sources", "settings/runtime"] as const;
export type SourcePageId = typeof SOURCE_PAGES[number];
export const sourceTitles: Record<SourcePageId, string> = {
  "": "Overview", analyzer: "Crawler", evidence: "Evidence", "deep-analysis": "Deep analysis",
  pipeline: "Pipeline", brain: "Brain", sources: "Sources", "settings/runtime": "Runtime settings"
};
export function sourceHref(page: string, query = "") {
  return localePath(`/source/${page ? page + "/" : ""}`, typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname)) + query;
}
export default function SourcePage({ page = "" }: { page?: SourcePageId }) {
  return <AppShell activeId={`source-${page || "overview"}`}>
    <TopBar title="Source Lab" icon={<TerminalWindowIcon size={20} />} />
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 sm:p-6">
      <nav aria-label="Source Lab pages" className="flex flex-wrap gap-2">
        {SOURCE_PAGES.map(id => <a key={id} className="iux-btn" data-variant={id === page ? "default" : "outline"} aria-current={id === page ? "page" : undefined} href={sourceHref(id)}>{sourceTitles[id]}</a>)}
        <a className="iux-btn" data-variant="outline" href={sourceHref("docs")}>Documentation</a>
        <a className="iux-btn" data-variant="outline" href={localePath("/labs/source/", typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname))}>Readiness & setup</a>
      </nav>
      <h2 className="text-xl font-semibold">{sourceTitles[page]}</h2>
      {PUBLIC_SOURCE ? <Section title="Local Source Lab" description="Run the installed console to inspect private source artifacts and launch analyses.">
        <p>Public pages do not connect to your local engine. No targets, catalogs or sessions are published.</p>
      </Section> : page === "" ? <SourceOverview /> : page === "sources" ? <SourceCatalogs /> : page === "analyzer" ? <SourceCrawler /> : page === "evidence" ? <SourceEvidence /> : page === "settings/runtime" ? <SourceRuntime /> : page === "deep-analysis" ? <SourceDeep /> : page === "pipeline" ? <SourcePipeline /> : page === "brain" ? <SourceBrain /> : <Section title={sourceTitles[page]}><Empty>This view is queued for implementation. Existing engine and console API workflows remain available.</Empty></Section>}
    </main>
  </AppShell>;
}
