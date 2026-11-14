/**
 * Companies from the downloaded content pack (console/content.py), when one is installed.
 *
 * The static dashboard ships a seed (companies.generated.ts). When the console serves a newer,
 * signed set it replaces the seed at run time, so new and edited companies appear without a new
 * app release. Without a console (the GitHub Pages build) or without a downloaded pack, the seed is used.
 */
import { useEffect, useState } from "react";
import { COMPANIES } from "./companies.generated";
import { api } from "../lib/api";
import type { Company } from "./types";

let pending: Promise<Company[] | null> | undefined;

/** The downloaded companies, or null when there are none (or no console). Fetched once per page load. */
export function liveCompanies(): Promise<Company[] | null> {
  if (import.meta.env.PUBLIC_SITE_MODE === "pages") return Promise.resolve(null);
  pending ??= api
    .contentCompanies()
    .then((r) => (r.source === "downloaded" && Array.isArray(r.companies) && r.companies.length ? (r.companies as Company[]) : null))
    .catch(() => null);
  return pending;
}

export function useLiveCompanies(): Company[] {
  const [companies, setCompanies] = useState<Company[]>(COMPANIES);
  useEffect(() => {
    let alive = true;
    void liveCompanies().then((live) => alive && live && setCompanies(live));
    return () => {
      alive = false;
    };
  }, []);
  return companies;
}
