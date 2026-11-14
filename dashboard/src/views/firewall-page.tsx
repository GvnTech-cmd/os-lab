/**
 * /firewall/ — firewall-lab: every student's "dream company" firewall design (BGT207).
 *
 * Read-only. The data is seeded from firewall-lab/companies/<slug>/company.json, compiled
 * into ../firewall/companies.generated.ts by firewall-lab/scripts/build-seed.py. Students add
 * a company by opening a PR against firewall-lab/companies/ — see CONTRIBUTING / the lab README.
 */
import { useMemo, useState } from "react";
import {
  ArrowSquareOutIcon,
  BuildingsIcon,
  FireIcon,
  GitPullRequestIcon,
  ListNumbersIcon,
  MapPinIcon,
  PlusIcon,
  ShieldCheckIcon,
  UsersThreeIcon
} from "@phosphor-icons/react";
import { ContributeModal } from "./contribute-modal";
import "../styles/firewall-contribute.css";
import { AppShell } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { Badge, Section, type Tone } from "../components/ui";
import { useLiveCompanies } from "../firewall/live";
import type { Branch, Company, Firewall, Rule } from "../firewall/types";
import { branchRole, copy, cveStatus, firewallPath, ruleAction, ruleDirection, type FirewallLocale } from "../firewall/locale";
import { FirewallLanguageSwitch } from "../firewall/language-switch";
import { numberLocale } from "../firewall/locale";

const ACCENT = "#f36c21";
const REPO = "https://github.com/keyvanarasteh/os-lab";

const ACTION_TONE: Record<Rule["action"], Tone> = {
  allow: "success",
  deny: "danger",
  reject: "warning",
  limit: "warning"
};

function peopleTotal(b: Branch): number {
  const p = b.population;
  return (p.staff ?? 0) + (p.students ?? 0) + (p.rnd ?? 0) + (p.software ?? 0);
}

function companyStats(c: Company) {
  let people = 0;
  let segments = 0;
  let rules = 0;
  for (const b of c.branches) {
    people += peopleTotal(b);
    segments += b.firewalls.length;
    for (const f of b.firewalls) rules += f.rules.length;
  }
  return { branches: c.branches.length, people, segments, rules };
}

const fmt = (n: number, locale: FirewallLocale) => n.toLocaleString(numberLocale(locale));

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-(--iux-border) bg-(--iux-card) px-3 py-2">
      <div className="text-lg font-bold tabular-nums leading-tight">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-(--iux-muted-foreground)">{label}</div>
    </div>
  );
}

function RuleRow({ rule, locale }: { rule: Rule; locale: FirewallLocale }) {
  const t = copy[locale];
  const target = [rule.from && `${t.from} ${rule.from}`, rule.to && `→ ${rule.to}`].filter(Boolean).join(" ");
  const portText =
    rule.port != null || (rule.proto && rule.proto !== "any")
      ? `${rule.proto && rule.proto !== "any" ? rule.proto : ""}${rule.port != null ? `/${rule.port}` : ""}`.trim()
      : t.any;
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 text-sm">
      <Badge tone={ACTION_TONE[rule.action]}>{ruleAction(rule.action, locale)}</Badge>
      <span className="font-mono text-xs text-(--iux-muted-foreground)">{ruleDirection(rule.direction ?? "in", locale)}</span>
      <span className="font-mono text-xs">{portText}</span>
      {target ? <span className="font-mono text-xs text-(--iux-muted-foreground)">{target}</span> : null}
      <span className="min-w-0 flex-1 basis-full text-(--iux-muted-foreground) sm:basis-auto">— {rule.note}</span>
    </li>
  );
}

function FirewallCard({ fw, locale }: { fw: Firewall; locale: FirewallLocale }) {
  const t = copy[locale];
  const [showAlts, setShowAlts] = useState(false);
  return (
    <div className="rounded-xl border border-(--iux-border) bg-(--iux-card)/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{fw.segment}</Badge>
        <span className="font-semibold">{fw.chosen.product}</span>
        <span className="text-sm text-(--iux-muted-foreground)">· {fw.chosen.vendor}</span>
        {fw.chosen.throughputGbps != null ? (
          <span className="text-xs text-(--iux-muted-foreground)">{fw.chosen.throughputGbps} Gbps</span>
        ) : null}
        {fw.chosen.priceUsd != null ? (
          <span className="text-xs text-(--iux-muted-foreground)">${fmt(fw.chosen.priceUsd, locale)}</span>
        ) : null}
      </div>
      {fw.chosen.reason ? <p className="mt-1.5 text-sm text-(--iux-muted-foreground)">{fw.chosen.reason}</p> : null}

      <button
        type="button"
        onClick={() => setShowAlts((v) => !v)}
        className="iux-touch-target mt-2 inline-flex items-center text-xs font-semibold text-[#f36c21] hover:underline"
      >
        {showAlts ? t.hide : t.show} {fw.alternatives.length} {t.alternatives}
      </button>
      {showAlts ? (
        <ul className="mt-2 space-y-1.5 border-l-2 border-(--iux-border) pl-3">
          {fw.alternatives.map((a, i) => (
            <li key={i} className="text-sm">
              <span className="font-medium">{a.product}</span>
              <span className="text-(--iux-muted-foreground)">
                {" "}
                · {a.vendor}
                {a.throughputGbps != null ? ` · ${a.throughputGbps} Gbps` : ""}
                {a.priceUsd != null ? ` · $${fmt(a.priceUsd, locale)}` : ""}
              </span>
              {a.reason ? <span className="block text-xs text-(--iux-muted-foreground)">{a.reason}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3">
        <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-(--iux-muted-foreground)">
          <ListNumbersIcon size={13} /> {t.ruleSet}
        </div>
        <ul className="divide-y divide-(--iux-border)">
          {fw.rules.map((r, i) => (
            <RuleRow key={i} rule={r} locale={locale} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function BranchCard({ branch, locale }: { branch: Branch; locale: FirewallLocale }) {
  const t = copy[locale];
  const people = peopleTotal(branch);
  return (
    <div className="rounded-xl border border-(--iux-border) p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold">{branch.name}</h3>
        <Badge>{branchRole(branch.role, locale)}</Badge>
        {branch.network.dmz ? <Badge tone="warning">DMZ</Badge> : null}
        <span className="flex items-center gap-1 text-xs text-(--iux-muted-foreground)">
          <MapPinIcon size={13} /> {branch.location}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-(--iux-muted-foreground)">
        <span className="flex items-center gap-1">
          <UsersThreeIcon size={14} /> {fmt(people, locale)} {t.person}
        </span>
        <span className="font-mono text-xs">{branch.network.cidr}</span>
        <span>
          {branch.bandwidth.downMbps}/{branch.bandwidth.upMbps} Mbps
        </span>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {branch.network.vlans.map((v) => (
          <span
            key={v.id}
            title={v.note}
            className="rounded-md border border-(--iux-border) bg-(--iux-card) px-2 py-0.5 font-mono text-[11px]"
          >
            {v.id} {v.name} · {v.cidr}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-(--iux-muted-foreground)">
        {t.linkDrivers}: {branch.bandwidth.drivers.join(", ")}
      </p>

      <div className="mt-3 space-y-3">
        {branch.firewalls.map((fw, i) => (
          <FirewallCard key={i} fw={fw} locale={locale} />
        ))}
      </div>
    </div>
  );
}

function CompanyPanel({ company, locale }: { company: Company; locale: FirewallLocale }) {
  const t = copy[locale];
  const stats = companyStats(company);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-bold tracking-tight">{company.name}</h2>
          <Badge>{company.sector}</Badge>
          {company.author.github ? (
            <a
              className="flex items-center gap-1 text-xs text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
              href={`${REPO}/tree/master/firewall-lab/companies/${company.slug}`}
              target="_blank"
              rel="noreferrer"
            >
              companies/{company.slug} <ArrowSquareOutIcon size={12} />
            </a>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-(--iux-muted-foreground)">
          {company.author.name}
          {company.author.studentId ? ` · ${company.author.studentId}` : ""} · {company.author.course}
        </p>
        <p className="mt-2 max-w-3xl text-sm text-(--iux-muted-foreground)">{company.summary}</p>
        <a className="fw-cta mt-4" href={firewallPath(locale, company.slug)}>
          {t.explore} <ArrowSquareOutIcon size={16} weight="bold" />
        </a>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat value={fmt(stats.branches, locale)} label={t.branches} />
        <Stat value={fmt(stats.people, locale)} label={t.people} />
        <Stat value={fmt(stats.segments, locale)} label={t.firewalls} />
        <Stat value={fmt(stats.rules, locale)} label={t.rules} />
      </div>

      <Section title={t.branches} icon={<BuildingsIcon size={16} />}>
        <div className="space-y-4">
          {company.branches.map((b) => (
            <BranchCard key={b.id} branch={b} locale={locale} />
          ))}
        </div>
      </Section>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title={t.remote} icon={<ShieldCheckIcon size={16} />}>
          <dl className="space-y-2 text-sm">
            {company.remoteAccess ? (
              <div>
                <dt className="font-semibold">{t.remote} · {company.remoteAccess.type}</dt>
                {company.remoteAccess.note ? (
                  <dd className="text-(--iux-muted-foreground)">{company.remoteAccess.note}</dd>
                ) : null}
              </div>
            ) : null}
            <div>
              <dt className="font-semibold">{t.owner}</dt>
              <dd className="text-(--iux-muted-foreground)">{company.monitoring.owner}</dd>
            </div>
            <div>
              <dt className="font-semibold">{t.alerts}</dt>
              <dd className="text-(--iux-muted-foreground)">{company.monitoring.alertSink}</dd>
            </div>
            {company.monitoring.siem ? (
              <div>
                <dt className="font-semibold">SIEM</dt>
                <dd className="text-(--iux-muted-foreground)">{company.monitoring.siem}</dd>
              </div>
            ) : null}
            {company.monitoring.appVsSecurity ? (
              <div>
                <dt className="font-semibold">{t.appSecurity}</dt>
                <dd className="text-(--iux-muted-foreground)">{company.monitoring.appVsSecurity}</dd>
              </div>
            ) : null}
          </dl>
        </Section>

        <Section title={t.cve} icon={<FireIcon size={16} />}>
          {company.cveWatch && company.cveWatch.length ? (
            <ul className="space-y-2 text-sm">
              {company.cveWatch.map((c) => (
                <li key={c.id}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs">{c.id}</span>
                    <Badge tone={c.status === "patched" || c.status === "not-affected" ? "success" : "warning"}>
                      {cveStatus(c.status, locale)}
                    </Badge>
                    <span className="text-(--iux-muted-foreground)">{c.product}</span>
                  </div>
                  {c.note ? <p className="text-xs text-(--iux-muted-foreground)">{c.note}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-(--iux-muted-foreground)">
              {t.noCve}
            </p>
          )}
        </Section>
      </div>
    </div>
  );
}

export function FirewallPage({ locale = "en" }: { locale?: FirewallLocale }) {
  const t = copy[locale];
  const companies = useLiveCompanies();
  const [showContribute, setShowContribute] = useState(false);
  const [activeSlug, setActiveSlug] = useState(companies[0]?.slug ?? "");
  const active = useMemo(() => companies.find((c) => c.slug === activeSlug) ?? companies[0], [companies, activeSlug]);

  return (
    <AppShell activeId="firewall">
      <div className="iux min-h-screen">
        <TopBar title={t.lab} icon={<FireIcon size={20} weight="duotone" />} locale={locale} />
        <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
          <header>
            <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
              <FireIcon size={22} className="text-[#f36c21]" weight="duotone" /> {t.lab}
            </h1>
            <p className="mt-1.5 max-w-3xl text-sm text-(--iux-muted-foreground)">
              {t.intro}
            </p>
            <div className="mt-3"><FirewallLanguageSwitch locale={locale} /></div>
          </header>

          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed border-[#f36c21]/50 bg-[#f36c21]/5 p-4">
            <GitPullRequestIcon size={20} className="text-[#f36c21]" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">{t.add}</p>
              <p className="text-xs text-(--iux-muted-foreground)">
                {t.contributeHint}
              </p>
            </div>
            <button type="button" onClick={() => setShowContribute(true)} className="fw-cta fw-cta-lg">
              <PlusIcon size={17} weight="bold" /> {t.contribute}
            </button>
          </div>

          {companies.length ? (
            <>
              <nav aria-label={t.companies} className="flex flex-wrap gap-2 border-b border-(--iux-border) pb-3">
                {companies.map((c) => (
                  <button
                    key={c.slug}
                    type="button"
                    onClick={() => setActiveSlug(c.slug)}
                    aria-current={c.slug === active?.slug ? "page" : undefined}
                    className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                      c.slug === active?.slug
                        ? "bg-[#f36c21] text-white"
                        : "border border-(--iux-border) bg-(--iux-card) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                    }`}
                  >
                    {c.name}
                  </button>
                ))}
              </nav>
              {active ? <CompanyPanel company={active} locale={locale} /> : null}
            </>
          ) : (
            <p className="text-sm text-(--iux-muted-foreground)">{t.empty}</p>
          )}
        </main>
      </div>
    {showContribute ? <ContributeModal onClose={() => setShowContribute(false)} locale={locale} /> : null}
    </AppShell>
  );
}
