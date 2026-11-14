import { FIREWALL_LOCALES, type FirewallLocale } from "../firewall/locale";

const base = import.meta.env.PUBLIC_SITE_MODE === "pages" ? import.meta.env.BASE_URL.replace(/\/$/, "") : "";
const withoutBase = (pathname: string) => base && (pathname === base || pathname.startsWith(`${base}/`))
  ? pathname.slice(base.length) || "/"
  : pathname;

export function localeFromPath(pathname: string): FirewallLocale {
  const first = withoutBase(pathname).split("/")[1];
  return FIREWALL_LOCALES.includes(first as FirewallLocale) ? first as FirewallLocale : "en";
}

export function localePath(pathname: string, locale: FirewallLocale): string {
  if (!pathname.startsWith("/") || pathname.startsWith("//")) return pathname;
  const route = withoutBase(pathname);
  const current = localeFromPath(pathname);
  const plain = current === "en" ? route : route.slice(current.length + 1) || "/";
  const result = locale === "en" ? plain : `/${locale}${plain}`;
  return base ? `${base}${result}` : result;
}
