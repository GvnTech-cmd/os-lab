/**
 * 404, plus one exception: a Firewall Lab company that arrived in a downloaded content pack has no
 * prerendered page, so /firewall/<slug>/ (and /<locale>/firewall/<slug>/) is drawn here from the pack.
 */
import { useEffect, useState } from "react";
import { FirewallCompanyPage } from "./firewall-company-page";
import { liveCompanies } from "../firewall/live";
import { FIREWALL_LOCALES, type FirewallLocale } from "../firewall/locale";
import type { Company } from "../firewall/types";

const MATCH = /^\/(?:([a-z]{2})\/)?firewall\/([a-z0-9-]+)\/?$/;

export function NotFoundPage() {
  const [company, setCompany] = useState<{ company: Company; locale: FirewallLocale } | "none" | "pending">("pending");
  useEffect(() => {
    const m = MATCH.exec(location.pathname);
    const locale = (m?.[1] ?? "en") as FirewallLocale;
    if (!m || !FIREWALL_LOCALES.includes(locale)) {
      setCompany("none");
      return;
    }
    void liveCompanies().then((list) => {
      const found = list?.find((c) => c.slug === m[2]);
      setCompany(found ? { company: found, locale } : "none");
    });
  }, []);

  if (company === "pending") return null;
  if (company !== "none") return <FirewallCompanyPage company={company.company} locale={company.locale} />;
  return (
    <main style={{ display: "grid", placeItems: "center", height: "100dvh", textAlign: "center", padding: "1rem" }}>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Page not found</h1>
        <p style={{ marginTop: 8, opacity: 0.7 }}>
          <a href={import.meta.env.PUBLIC_SITE_MODE === "pages" ? import.meta.env.BASE_URL : "/"} style={{ textDecoration: "underline" }}>Back to {import.meta.env.PUBLIC_SITE_MODE === "pages" ? "os-lab" : "this computer"}</a>
        </p>
      </div>
    </main>
  );
}
