import { AppShell } from "../../shell/app-shell";
import { TopBar } from "../../shell/top-bar";
import { SOURCE_DOCS } from "../../lib/source-docs";
import { sourceHref } from "./pages";
export function SourceDocs({ html, slug }: { html: string; slug: string }) {
  return <AppShell activeId="source-docs"><TopBar title="Source Lab" />
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-5 p-4 sm:p-6">
      <h2 className="text-xl font-semibold">Documentation</h2>
      <p>Technical documentation is in English. Navigation follows your selected language.</p>
      <nav aria-label="Source documentation" className="flex flex-wrap gap-2"><a className="iux-btn" href={sourceHref("")}>Overview</a>{SOURCE_DOCS.map(doc => <a key={doc.slug} className="iux-btn" aria-current={doc.slug === slug ? "page" : undefined} href={sourceHref(`docs/${doc.slug}`)}>{doc.title}</a>)}</nav>
      <article className="legal-doc" lang="en" translate="no" dangerouslySetInnerHTML={{ __html: html }} />
    </main>
  </AppShell>;
}
