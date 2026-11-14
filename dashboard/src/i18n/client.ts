import { localeFromPath, localePath } from "./paths";
import type { FirewallLocale } from "../firewall/locale";

type Dictionary = Record<string, string>;
const dictionaries = import.meta.glob<{ default: Dictionary }>("./generated/*.json");
const ROUTE = /^\/(?:$|(?:jobs|contribute|how-to-use|feedback|content|health|legal|labs|android|source|cleanup|firewall)(?:\/|$))/;
const SKIP = "script, style, pre, code, kbd, samp, textarea, [translate='no'], [data-no-translate]";

function localizeLink(anchor: HTMLAnchorElement, locale: FirewallLocale) {
  const raw = anchor.getAttribute("href");
  if (!raw || !ROUTE.test(raw)) return;
  const hash = raw.indexOf("#");
  const query = raw.indexOf("?");
  const cut = Math.min(...[hash, query].filter((n) => n >= 0), raw.length);
  const translated = `${localePath(raw.slice(0, cut), locale)}${raw.slice(cut)}`;
  if (translated !== raw) anchor.setAttribute("href", translated);
}

function start(dictionary: Dictionary, locale: FirewallLocale) {
  const previous = new WeakMap<Text, string>();
  const safe = (source: string, target: string) => {
    if (/^(?:adb|docker|curl|git|npm|pnpm|python3?|npx)\s/.test(source)) return false;
    if (/^(?:bg-|text-|border-|px-|py-|flex|grid|items-|justify-|rounded-|gap-|w-|h-)\S*(?:\s|$)/.test(source)) return false;
    const technical = source.match(/(?:[\w.-]+\/)+[\w.-]+|\b[\w-]+\.(?:py|js|ts|tsx|json|md|apk|xml|html|sh)\b|\b\d{1,3}(?:\.\d{1,3}){3}\b/g) ?? [];
    return technical.every((token) => target.includes(token));
  };
  const translate = (value: string) => {
    const trimmed = value.trim().replace(/\s+/g, " ");
    const target = dictionary[trimmed] ?? (trimmed.includes(" · ")
      ? trimmed.split(" · ").map((part) => dictionary[part] ?? part).join(" · ")
      : undefined);
    return target && target !== trimmed && safe(trimmed, target)
      ? `${value.match(/^\s*/)?.[0] ?? ""}${target}${value.match(/\s*$/)?.[0] ?? ""}` : null;
  };
  const textNode = (node: Text) => {
    if (node.parentElement?.closest(SKIP)) return;
    if (node.nodeValue === previous.get(node)) return;
    const target = translate(node.nodeValue ?? "");
    if (target) {
      previous.set(node, target);
      node.nodeValue = target;
      if (node.parentElement?.lang === "en") node.parentElement.lang = locale;
    }
  };
  const element = (node: Element) => {
    if (node instanceof HTMLAnchorElement) localizeLink(node, locale);
    if (node.matches(SKIP)) return;
    for (const key of ["title", "aria-label", "placeholder", "alt"]) {
      const current = node.getAttribute(key);
      if (current) {
        const target = translate(current);
        if (target) node.setAttribute(key, target);
      }
    }
    for (const child of node.childNodes) visit(child);
  };
  const visit = (node: Node) => {
    if (node instanceof Text) textNode(node);
    else if (node instanceof Element) element(node);
  };
  visit(document.body);
  const title = document.title.replace(/ · os-lab$/, "");
  const translatedTitle = translate(title);
  if (translatedTitle) document.title = `${translatedTitle} · os-lab`;
  new MutationObserver((changes) => {
    for (const change of changes) {
      if (change.type === "characterData") visit(change.target);
      else if (change.type === "attributes" && change.target instanceof Element) visit(change.target);
      else for (const node of change.addedNodes) visit(node);
    }
  }).observe(document.body, { childList: true, characterData: true, attributes: true, attributeFilter: ["title", "aria-label", "placeholder", "alt"], subtree: true });
}

const locale = localeFromPath(window.location.pathname);
if (locale !== "en") {
  const key = `./generated/${locale}.json`;
  const load = dictionaries[key];
  if (load) void load().then((module) => start(module.default, locale));
} else if (import.meta.env.PUBLIC_SITE_MODE === "pages") {
  // Public pages are served below the repository base path even in English.
  start({}, "en");
}
