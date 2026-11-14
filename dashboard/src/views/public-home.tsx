import { useEffect, useState } from "react";
import { AppShell, REPO_URL } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { localeFromPath, localePath } from "../i18n/paths";

type Asset = { name: string; browser_download_url: string };
type Release = { tag_name: string; html_url: string; assets: Asset[] };
const latest = `${REPO_URL}/releases/latest`;
const installers = [
  { label: "macOS · Apple Silicon and Intel", suffix: "macos_universal.dmg" },
  { label: "Windows · x64", suffix: "windows_x64-setup.exe" },
  { label: "Linux · amd64 DEB", suffix: "linux_amd64.deb" },
  { label: "Linux · amd64 RPM", suffix: "linux_amd64.rpm" },
  { label: "Linux · amd64 AppImage", suffix: "linux_amd64.AppImage" }
];
const commands = [
  { label: "Linux", command: "curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.sh | bash" },
  { label: "macOS", command: "curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install-macos.sh | bash" },
  { label: "Windows PowerShell", command: "irm https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.ps1 | iex" }
];

function CommandCard({ label, command }: { label: string; command: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  async function copyCommand() {
    setCopyState("copying");
    try {
      await navigator.clipboard.writeText(command);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }
  return <div className="iux-card p-4">
    <div className="mb-2 flex items-center justify-between gap-2"><strong>{label}</strong><button className="iux-btn" data-variant="outline" type="button" disabled={copyState === "copying"} onClick={() => void copyCommand()}>Copy</button></div>
    <code className="block overflow-x-auto whitespace-nowrap text-xs sm:text-sm">{command}</code>
    {copyState === "copied" || copyState === "failed" ? <p role="status" className="mt-2 text-sm">{copyState === "copied" ? "Copied" : "Clipboard unavailable. Select the text manually."}</p> : null}
  </div>;
}

export default function PublicHome() {
  const firewallHref = localePath("/firewall/", localeFromPath(window.location.pathname));
  const [release, setRelease] = useState<Release | null>(null);
  const [releaseStatus, setReleaseStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  useEffect(() => {
    const controller = new AbortController();
    fetch("https://api.github.com/repos/keyvanarasteh/os-lab/releases/latest", { signal: controller.signal, cache: "no-store", headers: { Accept: "application/vnd.github+json" } })
      .then((response) => { if (!response.ok) throw new Error(`Release: ${response.status}`); return response.json(); })
      .then((value: Release) => { if (!value.tag_name || !Array.isArray(value.assets)) throw new Error("Invalid release response"); setRelease(value); setReleaseStatus("ready"); })
      .catch(() => { if (!controller.signal.aborted) setReleaseStatus("unavailable"); });
    return () => controller.abort();
  }, []);
  return <AppShell activeId="host">
    <TopBar title="os-lab" />
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-10 px-4 py-10 sm:px-8">
      <header className="rounded-2xl border border-(--iux-border) bg-(--iux-card) p-7 sm:p-10">
        <p className="text-sm font-semibold uppercase tracking-widest text-[#f36c21]">Open source security labs</p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">Build, run, and study isolated security labs.</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-(--iux-muted-foreground)">os-lab brings Android, iOS, Windows, Linux, macOS, and firewall exercises into one local console. Install it on your own machine, then choose a lab.</p>
        <div className="mt-7 flex flex-wrap gap-3"><a className="iux-btn" data-variant="primary" href="#download">Download</a><a className="iux-btn" data-variant="outline" href={firewallHref}>Explore Firewall Lab</a><a className="iux-btn" data-variant="outline" href={REPO_URL}>Source code</a></div>
      </header>
      <section id="download" className="space-y-4">
        <div><h2 className="text-2xl font-bold">Desktop downloads</h2><p role="status" className="mt-1 text-sm text-(--iux-muted-foreground)">{releaseStatus === "loading" ? <span>Checking latest release…</span> : releaseStatus === "unavailable" ? <span>Release details unavailable. Open the latest release page.</span> : <><span>Latest published release</span> · <span data-no-translate>{release?.tag_name}</span></>}</p></div>
        <div className="grid gap-3 sm:grid-cols-2">{installers.map(({ label, suffix }) => {
          const asset = release?.assets.find((item) => item.name.endsWith(`_${suffix}`));
          return <a key={suffix} className="iux-card p-4 hover:border-[#f36c21]" href={asset?.browser_download_url ?? latest}><strong className="block">{label}</strong><span className="mt-1 block break-all text-xs text-(--iux-muted-foreground)">{asset?.name ?? "View latest release"}</span></a>;
        })}</div>
        <p className="text-sm text-(--iux-muted-foreground)">Each installer has a checksum and signature on the <a className="underline" href={release?.html_url ?? latest}>release page</a>. For other formats, check the release assets.</p>
      </section>
      <section className="space-y-4"><h2 className="text-2xl font-bold">One-line setup</h2><p className="text-sm text-(--iux-muted-foreground)">These commands install prerequisites, fetch the checkout, and launch the local web console. Review the script before running it.</p>
        {commands.map(({ label, command }) => <CommandCard key={label} label={label} command={command} />)}
      </section>
      <section className="grid gap-3 sm:grid-cols-2"><a className="iux-card p-5 hover:border-[#f36c21]" href={firewallHref}><strong>Firewall Lab</strong><p className="mt-2 text-sm text-(--iux-muted-foreground)">Explore student company networks, firewalls, and rule sets.</p></a><a className="iux-card p-5 hover:border-[#f36c21]" href={`${REPO_URL}/blob/master/README.md`}><strong>Documentation</strong><p className="mt-2 text-sm text-(--iux-muted-foreground)">Requirements, installation, and lab guides.</p></a></section>
    </main>
  </AppShell>;
}
