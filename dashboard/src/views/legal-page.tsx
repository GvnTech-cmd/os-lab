/** /legal/<doc>/ — one legal document, rendered from docs/legal/*.md at build time. */
import { ScalesIcon } from "@phosphor-icons/react";
import { AppShell } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { LEGAL_DOCS, REPO_BLOB, type LegalSlug } from "../lib/legal";
import { localeFromPath, localePath } from "../i18n/paths";

const legalHref = (slug: string) => localePath(`/legal/${slug}/`, typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname));

function Tabs({ active }: { active?: LegalSlug }) {
  return (
    <nav aria-label="Legal documents" className="flex flex-wrap gap-2 border-b border-(--iux-border) pb-3">
      {LEGAL_DOCS.map((doc) => (
        <a
          key={doc.slug}
          href={legalHref(doc.slug)}
          aria-current={doc.slug === active ? "page" : undefined}
          className={`iux-touch-target inline-flex items-center rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
            doc.slug === active
              ? "bg-[#f36c21] text-white"
              : "border border-(--iux-border) bg-(--iux-card) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
          }`}
        >
          {doc.title}
        </a>
      ))}
    </nav>
  );
}

export function LegalDocPage({ slug, html }: { slug: LegalSlug; html: string }) {
  const doc = LEGAL_DOCS.find((d) => d.slug === slug)!;
  return (
    <AppShell activeId={`legal-${slug}`}>
      <div className="iux min-h-screen">
        <TopBar title={doc.title} back={{ href: "/legal/", label: "Legal" }} icon={<ScalesIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
          <Tabs active={slug} />
          {/* Our own Markdown from docs/legal, compiled at build time */}
          <article className="legal-doc" lang="en" translate="no" dangerouslySetInnerHTML={{ __html: html }} />
          <p className="border-t border-(--iux-border) pt-4 text-xs text-(--iux-muted-foreground)">
            Source:{" "}
            <a className="underline" href={`${REPO_BLOB}/docs/legal/${doc.file}`} target="_blank" rel="noreferrer">
              docs/legal/{doc.file}
            </a>
            . The same text ships with the repository; its history is the change log.
          </p>
        </main>
      </div>
    </AppShell>
  );
}

export function LegalIndexPage() {
  return (
    <AppShell activeId="legal">
      <div className="iux min-h-screen">
        <TopBar title="Legal" icon={<ScalesIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              <ScalesIcon size={22} className="text-[#f36c21]" /> Legal
            </h1>
            <p className="mt-1 text-sm text-(--iux-muted-foreground)">
              os-lab is open-source software under the Apache License 2.0 that you run on your own machine. These documents explain
              your responsibilities when you operate the labs, what the software does with data, and the licences of the
              components it uses.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {LEGAL_DOCS.map((doc) => (
              <a key={doc.slug} href={legalHref(doc.slug)} className="apk-crosshair-box iux-card gap-1.5 p-5 transition-colors hover:border-[#f36c21]/40">
                <span className="text-sm font-semibold">{doc.title}</span>
                <span className="text-xs text-(--iux-muted-foreground)">{doc.description}</span>
              </a>
            ))}
            <a href={`${REPO_BLOB}/LICENSE`} target="_blank" rel="noreferrer" className="apk-crosshair-box iux-card gap-1.5 p-5 transition-colors hover:border-[#f36c21]/40">
              <span className="text-sm font-semibold">Apache License 2.0</span>
              <span className="text-xs text-(--iux-muted-foreground)">The licence that governs the os-lab source code</span>
            </a>
            <a href={`${REPO_BLOB}/SECURITY.md`} target="_blank" rel="noreferrer" className="apk-crosshair-box iux-card gap-1.5 p-5 transition-colors hover:border-[#f36c21]/40">
              <span className="text-sm font-semibold">Security policy</span>
              <span className="text-xs text-(--iux-muted-foreground)">How to report a vulnerability in os-lab privately</span>
            </a>
          </div>
        </main>
      </div>
    </AppShell>
  );
}
