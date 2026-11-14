import { useState, type KeyboardEvent } from "react";
import { ArrowLeftIcon, ArrowRightIcon, FireIcon, MapPinIcon, ShieldCheckIcon, WarningDiamondIcon, GraphIcon } from "@phosphor-icons/react";
import { AppShell } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { useLiveCompanies } from "../firewall/live";
import type { Branch, Company } from "../firewall/types";
import { branchRole, copy, firewallPath, type FirewallLocale } from "../firewall/locale";
import { numberLocale } from "../firewall/locale";
import { FirewallLanguageSwitch } from "../firewall/language-switch";
import { auditCompany } from "../firewall/audit";
import { GapsTab } from "./firewall-gaps";

const fmt = (value: number, locale: FirewallLocale) => value.toLocaleString(numberLocale(locale));
const people = (branch: Branch) => Object.values(branch.population).reduce<number>((sum, value) => sum + (value ?? 0), 0);
const rules = (branch: Branch) => branch.firewalls.reduce((sum, firewall) => sum + firewall.rules.length, 0);

function BranchNode({ branch, index, selected, onSelect, locale }: { branch: Branch; index: number; selected: boolean; onSelect: () => void; locale: FirewallLocale }) {
  const t = copy[locale];
  return (
    <button
      type="button"
      className="fw-branch"
      data-selected={selected}
      onClick={onSelect}
      aria-pressed={selected}
      style={{ animationDelay: `${index * 85}ms` }}
    >
      <span className="fw-branch-line" aria-hidden="true" />
      <span className="fw-branch-top"><span className="fw-index">{String(index + 1).padStart(2, "0")}</span><span className="fw-role">{branchRole(branch.role, locale)}</span></span>
      <strong>{branch.name}</strong>
      <span className="fw-location"><MapPinIcon size={12} /> {branch.location}</span>
      <span className="fw-branch-meter" aria-hidden="true">
        {branch.network.vlans.map((vlan) => <i key={vlan.id} title={`VLAN ${vlan.id}: ${vlan.name}`} />)}
      </span>
      <span className="fw-branch-foot"><span>{branch.network.vlans.length} VLAN</span><span>{branch.firewalls.length} {branch.firewalls.length === 1 ? t.firewall : t.firewalls.toLocaleLowerCase(locale)}</span></span>
    </button>
  );
}

function BranchDetail({ branch, locale }: { branch: Branch; locale: FirewallLocale }) {
  const t = copy[locale];
  return (
    <section className="fw-detail" key={branch.id} aria-label={`${branch.name} ${t.networkDetails}`}>
      <div className="fw-detail-heading">
        <div><span className="fw-eyebrow">{t.selectedBranch} / {branchRole(branch.role, locale)}</span><h2>{branch.name}</h2><p>{branch.location} · {branch.network.cidr}</p></div>
        <div className="fw-bandwidth"><span>{t.connection}</span><strong>{fmt(branch.bandwidth.downMbps, locale)} <small>↓</small> / {fmt(branch.bandwidth.upMbps, locale)} <small>↑</small></strong><span>Mbps</span></div>
      </div>

      <div className="fw-numbers">
        <div><strong>{fmt(people(branch), locale)}</strong><span>{t.person}</span></div>
        <div><strong>{branch.network.vlans.length}</strong><span>VLAN</span></div>
        <div><strong>{branch.firewalls.length}</strong><span>{t.firewalls.toLocaleLowerCase(locale)}</span></div>
        <div><strong>{rules(branch)}</strong><span>{t.rules.toLocaleLowerCase(locale)}</span></div>
      </div>

      <div className="fw-detail-grid">
        <div className="fw-piece">
          <div className="fw-piece-title"><span>01</span><h3>{t.networkSegments}</h3><span>{branch.network.dmz ? t.dmzPresent : t.internalNetwork}</span></div>
          <div className="fw-vlans">
            {branch.network.vlans.map((vlan, index) => (
              <div className="fw-vlan" key={vlan.id} style={{ animationDelay: `${index * 65}ms` }}>
                <span className="fw-vlan-id">{String(vlan.id).padStart(2, "0")}</span>
                <span className="fw-vlan-main"><strong>{vlan.name}</strong><small>{vlan.note || t.segmentedNetwork}</small></span>
                <code>{vlan.cidr}</code>
              </div>
            ))}
          </div>
        </div>
        <div className="fw-piece">
          <div className="fw-piece-title"><span>02</span><h3>{t.firewallLayers}</h3><span>{rules(branch)} {t.totalRules}</span></div>
          <div className="fw-firewalls">
            {branch.firewalls.map((firewall, index) => (
              <div className="fw-firewall" key={`${firewall.segment}-${index}`} style={{ animationDelay: `${index * 80}ms` }}>
                <div className="fw-firewall-icon"><ShieldCheckIcon size={18} weight="duotone" /></div>
                <div><span className="fw-segment">{firewall.segment}</span><strong>{firewall.chosen.product}</strong><small>{firewall.chosen.vendor}{firewall.chosen.throughputGbps != null ? ` · ${firewall.chosen.throughputGbps} Gbps` : ""}</small></div>
                <span className="fw-rule-count">{firewall.rules.length} {firewall.rules.length === 1 ? t.rule : t.rules.toLocaleLowerCase(locale)}</span>
              </div>
            ))}
          </div>
          <p className="fw-drivers"><strong>{t.linkDrivers}</strong> {branch.bandwidth.drivers.join(" · ")}</p>
        </div>
      </div>
    </section>
  );
}

export function FirewallCompanyPage({ company: seeded, locale = "en" }: { company: Company; locale?: FirewallLocale }) {
  const t = copy[locale];
  const companies = useLiveCompanies();
  const company = companies.find((item) => item.slug === seeded.slug) ?? seeded;
  const [selectedId, setSelectedId] = useState(company.branches[0]?.id ?? "");
  const [tab, setTab] = useState<"network" | "gaps">(() => (typeof location !== "undefined" && location.hash.startsWith("#gap") ? "gaps" : "network"));
  const gaps = auditCompany(company).total;
  const pick = (t: "network" | "gaps") => { setTab(t); history.replaceState(null, "", t === "gaps" ? "#gaps" : location.pathname + location.search); };
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, current: "network" | "gaps") => {
    const direction = document.documentElement.dir === "rtl" ? -1 : 1;
    const delta = event.key === "ArrowRight" ? direction : event.key === "ArrowLeft" ? -direction : 0;
    const next = event.key === "Home" ? "network" : event.key === "End" ? "gaps" : delta ? (current === "network" ? "gaps" : "network") : null;
    if (!next) return;
    event.preventDefault();
    pick(next);
    document.getElementById(`firewall-company-tab-${next}`)?.focus();
  };
  const selected = company.branches.find((branch) => branch.id === selectedId) ?? company.branches[0];
  const next = companies[(companies.findIndex((item) => item.slug === company.slug) + 1) % companies.length];
  return (
    <AppShell activeId="firewall">
      <div className="iux min-h-screen">
        <TopBar title={company.name} icon={<FireIcon size={20} weight="duotone" />} locale={locale} />
        <main className="fw-page">
          <div className="fw-back"><a href={firewallPath(locale)}><ArrowLeftIcon size={15} /> {t.allCompanies}</a><span>{t.lab} / {company.slug}</span><FirewallLanguageSwitch locale={locale} slug={company.slug} /></div>
          <header className="fw-hero">
            <div><span className="fw-eyebrow">BGT207 / {t.companyNetwork}</span><h1>{company.name}</h1><p>{company.summary}</p><span className="fw-sector">{company.sector}</span></div>
            <div className="fw-hero-count"><strong>{String(company.branches.length).padStart(2, "0")}</strong><span>{t.branches.toLocaleLowerCase(locale)}</span></div>
          </header>

          <div className="fw-tabs" data-tab={tab} role="tablist" aria-label={t.companyViews}>
            <span className="fw-tab-pill" aria-hidden="true" />
            <button id="firewall-company-tab-network" type="button" role="tab" className="fw-tab" aria-selected={tab === "network"} aria-controls="firewall-company-panel" tabIndex={tab === "network" ? 0 : -1} onClick={() => pick("network")} onKeyDown={event => onTabKey(event, "network")}><GraphIcon size={15} weight="bold" /> {t.network}</button>
            <button id="firewall-company-tab-gaps" type="button" role="tab" className="fw-tab" aria-selected={tab === "gaps"} aria-controls="firewall-company-panel" tabIndex={tab === "gaps" ? 0 : -1} onClick={() => pick("gaps")} onKeyDown={event => onTabKey(event, "gaps")}><WarningDiamondIcon size={15} weight="bold" /> {t.gaps} <b>{gaps}</b></button>
          </div>

          <div id="firewall-company-panel" role="tabpanel" aria-labelledby={`firewall-company-tab-${tab}`} tabIndex={0}>
          {tab === "gaps" ? <GapsTab company={company} locale={locale} /> : <>
          <section className="fw-map" aria-label={t.branches}>
            <div className="fw-map-heading"><div><span className="fw-eyebrow">01 / {t.overview}</span><h2>{t.branchComposition}</h2></div><span>{t.selectBranch}</span></div>
            <div className="fw-branch-grid">
              {company.branches.map((branch, index) => <BranchNode key={branch.id} branch={branch} index={index} selected={selected?.id === branch.id} onSelect={() => setSelectedId(branch.id)} locale={locale} />)}
            </div>
          </section>

          {selected && <BranchDetail branch={selected} locale={locale} />}
          </>}
          </div>
          <footer className="fw-footer"><a href={firewallPath(locale)}>{t.allDesigns}</a><a href={firewallPath(locale, next.slug)}>{t.next}: {next.name} <ArrowRightIcon size={15} /></a></footer>
        </main>
      </div>
    </AppShell>
  );
}
