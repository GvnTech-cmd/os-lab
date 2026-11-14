/** The legal documents, rendered from docs/legal/*.md (the single source for the repo and the dashboard). */
import type { FirewallLocale } from "../firewall/locale";
import { localePath } from "../i18n/paths";
export const REPO_BLOB = "https://github.com/keyvanarasteh/os-lab/blob/master";

export const LEGAL_DOCS = [
  { slug: "terms", file: "TERMS.md", title: "Terms of Use", description: "Licence, authorized use, OS licences, data you process, no warranty" },
  { slug: "acceptable-use", file: "ACCEPTABLE_USE.md", title: "Acceptable Use", description: "Supported and unsupported use, responsible disclosure" },
  { slug: "privacy", file: "PRIVACY.md", title: "Privacy Notice", description: "What stays on your machine, browser storage, network connections" },
  { slug: "third-party", file: "THIRD_PARTY_NOTICES.md", title: "Third-Party Notices", description: "Licences of images, tools and bundled components" }
] as const;

export type LegalSlug = (typeof LEGAL_DOCS)[number]["slug"];

export const REPO_TREE = "https://github.com/keyvanarasteh/os-lab/tree/master";

/** Resolve a relative link against the folder of the Markdown file (repo-relative, POSIX). */
function resolve(baseDir: string, href: string): string {
  const parts = baseDir.split("/").filter(Boolean);
  for (const seg of href.split("/")) {
    if (seg === "..") parts.pop();
    else if (seg && seg !== ".") parts.push(seg);
  }
  return parts.join("/") + (href.endsWith("/") ? "/" : "");
}

/**
 * Point a compiled Markdown file's links at dashboard routes or GitHub.
 * `baseDir` is the repo folder the Markdown lives in ("docs/legal" or "" for the root).
 */
export function rewriteLinks(html: string, baseDir = "docs/legal", locale: FirewallLocale = "en"): string {
  return html.replace(/href="([^"]+)"/g, (whole, href: string) => {
    if (/^https?:/.test(href)) return `href="${href}" target="_blank" rel="noreferrer"`;
    if (href.startsWith("#") || href.startsWith("mailto:")) return whole;
    const [path, anchor = ""] = href.split("#");
    const target = resolve(baseDir, path);
    const doc = LEGAL_DOCS.find((d) => target === `docs/legal/${d.file}`);
    if (doc) return `href="${localePath(`/legal/${doc.slug}/`, locale)}${anchor ? `#${anchor}` : ""}"`;
    if (target === "CONTRIBUTING.md") return `href="${localePath("/contribute/", locale)}${anchor ? `#${anchor}` : ""}"`;
    const url = `${target.endsWith("/") ? REPO_TREE : REPO_BLOB}/${target}${anchor ? `#${anchor}` : ""}`;
    return `href="${url}" target="_blank" rel="noreferrer"`;
  });
}
