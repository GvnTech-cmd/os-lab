import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRightIcon,
  BookOpenIcon,
  BugIcon,
  FilesIcon,
  GitPullRequestIcon,
  HeartIcon,
  ListChecksIcon,
  ScrollIcon,
  SealCheckIcon,
  ShareNetworkIcon,
  XIcon
} from "@phosphor-icons/react";
import { COMPANIES } from "../firewall/companies.generated";
import type { FirewallLocale } from "../firewall/locale";
import { contributeUi } from "../firewall/contribute-ui";
import { keepModalFocus } from "./modal-focus";

const REPO = "https://github.com/keyvanarasteh/os-lab";
const blob = (p: string) => `${REPO}/blob/master/${p}`;

const STEPS = [
  ["Copy", "cp -r firewall-lab/templates/company firewall-lab/companies/<slug>"],
  ["Fill", "company.json + README.md. Every rule gets a reason."],
  ["Validate", "python3 firewall-lab/scripts/validate.py <slug>"],
  ["Open a PR", "CI revalidates and rebuilds the catalog."]
] as const;

const LINKS = [
  { icon: ScrollIcon, label: "CONTRIBUTING", href: blob("CONTRIBUTING.md") },
  { icon: HeartIcon, label: "CONTRIBUTORS", href: blob("firewall-lab/CONTRIBUTORS.md") },
  { icon: ListChecksIcon, label: "Standards", href: blob("firewall-lab/README.md#the-rules-of-a-good-submission") },
  { icon: FilesIcon, label: "Schema", href: blob("firewall-lab/schema/README.md") },
  { icon: BookOpenIcon, label: "Knowledge notes", href: `${REPO}/tree/master/firewall-lab/knowledge` },
  { icon: GitPullRequestIcon, label: "PR template", href: blob(".github/PULL_REQUEST_TEMPLATE.md") },
  { icon: BugIcon, label: "Issue templates", href: `${REPO}/issues/new/choose` },
  { icon: SealCheckIcon, label: "Code of conduct", href: blob("CODE_OF_CONDUCT.md") }
];

export function ContributeModal({ onClose, locale = "en" }: { onClose: () => void; locale?: FirewallLocale }) {
  const ui = contributeUi[locale];
  const box = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    box.current?.showModal();
    box.current?.focus();
    return () => {
      if (box.current?.open) box.current.close();
      document.body.style.overflow = previousOverflow;
      prev?.focus();
    };
  }, []);

  const [people, setPeople] = useState(() => COMPANIES.filter((c) => c.author.github && c.author.name !== "Seed Example")
    .map((c) => ({ slug: c.slug, company: c.name, github: c.author.github! })));
  useEffect(() => {
    const controller = new AbortController();
    fetch(`https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/firewall-lab/catalog.json?t=${Date.now()}`, { signal: controller.signal, cache: "no-store" })
      .then((response) => { if (!response.ok) throw new Error(`Catalog: ${response.status}`); return response.json(); })
      .then((catalog: { contributors?: typeof people }) => {
        if (Array.isArray(catalog.contributors)) setPeople(Array.from(new Map(catalog.contributors
          .filter((c) => c.slug && c.company && /^[\w-]+$/.test(c.github))
          .map((c) => [c.github.toLowerCase(), c])).values()));
      })
      .catch(() => { /* The bundled list remains available offline. */ });
    return () => controller.abort();
  }, []);

  return (
    <dialog className="cm" aria-labelledby="cm-title" ref={box} tabIndex={-1} onClose={onClose} onKeyDown={keepModalFocus} onMouseDown={(e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) { e.preventDefault(); onClose(); }
    }}>
        <button className="cm-x" type="button" onClick={onClose} aria-label={ui.close}><XIcon size={16} weight="bold" /></button>
        <header className="cm-head">
          <span className="cm-eyebrow">{ui.contribute}</span>
          <h2 id="cm-title">{ui.title}</h2>
          <p>{ui.intro}</p>
        </header>

        <ol className="cm-steps">
          {STEPS.map(([t, d], i) => (
            <li key={t} style={{ animationDelay: `${120 + i * 90}ms` }}>
              <span>{i + 1}</span>
              <div><strong>{ui.steps[i]}</strong><code>{i === 1 ? ui.fill : i === 3 ? ui.ci : d}</code></div>
            </li>
          ))}
        </ol>

        <section>
          <h3 className="cm-h"><ShareNetworkIcon size={14} weight="bold" /> {ui.contributors} <b>{people.length}</b></h3>
          <ul className="cm-people">
            {people.map((c, i) => (
              <li key={c.slug} style={{ animationDelay: `${300 + i * 45}ms` }}>
                <a href={`https://github.com/${c.github}`} target="_blank" rel="noreferrer">
                  <img src={`https://github.com/${c.github}.png?size=64`} alt="" width="32" height="32" loading="lazy" />
                  <span><strong>@{c.github}</strong><small>{c.company}</small></span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="cm-h"><ListChecksIcon size={14} weight="bold" /> {ui.guides}</h3>
          <ul className="cm-links">
            {LINKS.map(({ icon: Icon, label, href }, i) => (
              <li key={label} style={{ animationDelay: `${400 + i * 40}ms` }}>
                <a href={href} target="_blank" rel="noreferrer">
                  <Icon size={18} weight="duotone" />
                  <span><strong>{ui.links[i]}</strong><small>{ui.notes[i]}</small></span>
                  <ArrowUpRightIcon size={14} />
                </a>
              </li>
            ))}
          </ul>
        </section>
    </dialog>
  );
}
