import { rewriteLinks } from "./legal";
import { localePath } from "../i18n/paths";
import type { FirewallLocale } from "../firewall/locale";
export const SOURCE_DOCS = [
  { slug: "guide", file: "README.md", title: "Guide" },
  { slug: "collectors", file: "COLLECTORS.md", title: "Collectors" },
  { slug: "brain", file: "BRAIN.md", title: "Brain" },
  { slug: "import", file: "IMPORT.md", title: "Legacy import" },
  { slug: "runbook", file: "RUNBOOK.md", title: "Runbook" }
];
export function sourceDocHtml(html: string, locale: FirewallLocale) {
  return html.replace(/href="([^"]+)"/g, (whole, href: string) => {
    if (href.startsWith("/source/")) return `href="${localePath(href, locale)}"`;
    const [path, hash = ""] = href.split("#");
    const match = SOURCE_DOCS.find(doc => path === doc.file || path === `./${doc.file}`);
    if (match) return `href="${localePath(`/source/docs/${match.slug}/`, locale)}${hash ? `#${hash}` : ""}"`;
    return rewriteLinks(whole, "source-lab", locale);
  });
}
