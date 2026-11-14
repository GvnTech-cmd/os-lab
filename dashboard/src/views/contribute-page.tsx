/** /contribute/ — CONTRIBUTING.md and interactive curated roadmap & TODOs. */
import { useState, useMemo, useEffect } from "react";
import {
  GitPullRequestIcon,
  BookOpenIcon,
  ListChecksIcon,
  CrosshairIcon,
  TerminalWindowIcon,
  ShieldCheckIcon,
  MagnifyingGlassIcon,
  CheckCircleIcon,
  CopyIcon,
  CheckIcon,
  TagIcon,
  CaretRightIcon,
  LockKeyIcon,
  LockKeyOpenIcon,
  SealCheckIcon,
  UserCircleIcon,
  ArrowSquareOutIcon
} from "@phosphor-icons/react";
import { AppShell } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { REPO_BLOB } from "../lib/legal";
import { SOURCE_BONUS_TASKS } from "./source-bonus-tasks";
import { CLEANUP_LAB_TASKS } from "./cleanup-lab-tasks";

export type TaskCategory = "all" | "pentest" | "os" | "firewall";
export type TaskPriority = "all" | "high" | "medium";

export interface TodoTask {
  id: string;
  category: "pentest" | "os" | "firewall";
  categoryLabel: string;
  title: string;
  priority: "High" | "Medium";
  effort: "Small" | "Medium" | "Large" | "Tiny–Small" | "Small–Medium";
  summary: string;
  deliverables: string[];
  reference: string;
  targetPaths: string[];
  suggestedBranch: string;
  /** Set when the task is "held": names the prerequisite (lecture / verified lab) it waits on. */
  prerequisite?: string;
}

export const CURATED_TASKS: TodoTask[] = [
  ...SOURCE_BONUS_TASKS,
  ...CLEANUP_LAB_TASKS,
  // --- 1. Penetration Testing (Pentesting) ---
  {
    id: "PENT-01",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Native Frida Instrumentation Module & Runtime Hook Suite",
    priority: "High",
    effort: "Medium",
    summary:
      "Implement universal native function interception templates using Frida's Interceptor API (onEnter, onLeave, and retval.replace). Includes a deterministic native test harness simulating auth loops, along with pre-built observation and parameter-modification scripts.",
    deliverables: [
      "android-lab/lab/hooks/native_interceptor.js: universal Interceptor skeleton with argument inspection and return value rewriting",
      "android-lab/lab/tests/targets/native_auth_harness.c: lightweight C test binary for reproducible injection testing",
      "CLI action in labctl and console to deploy hooks directly into target processes"
    ],
    reference: "Teached Dynamic Instrumentation (hedef.c, gozlem.js, degistir.js)",
    targetPaths: ["android-lab/lab/hooks/", "android-lab/lab/tests/", "console/oslab.py"],
    suggestedBranch: "feat/frida-native-interceptor"
  },
  {
    id: "PENT-02",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Automated Browser Extension Injection & Malicious Script Audit Engine",
    priority: "High",
    effort: "Medium",
    summary:
      "Build an automated static and runtime scanner for unpacked browser extensions (Manifest V3 and V2). Audits high-risk permissions (all_urls, cookies, scripting, activeTab, nativeMessaging) and scans code for dynamic code execution (eval, new Function, chrome.scripting.executeScript), external script loading, and two-stage dynamic payload delivery.",
    deliverables: [
      "Manifest parser extracting CSP rules, declarative network requests, and dangerous host permissions",
      "AST / regex engine detecting eval, dynamic iframe injection, and exfiltration endpoints",
      "Dual-profile differential runner comparing baseline browser storage/network artifacts against extension execution"
    ],
    reference: "Teached Extension Injection Analysis (iExtensionCrawler methodology)",
    targetPaths: ["scripts/analysis/", "console/oslab.py", "dashboard/src/apk-lab/"],
    suggestedBranch: "feat/extension-injection-scanner"
  },
  {
    id: "PENT-03",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Headless Android Analysis Pipeline & Objection SSL Pinning Bypass",
    priority: "High",
    effort: "Large",
    summary:
      "Provide a headless, containerized Android emulation and instrumentation runner. Integrates automated frida-server bootstrapping, mitmproxy CA installation into system trust (/system/etc/security/cacerts/), and automated objection scripts for universal root detection and SSL pinning bypass.",
    deliverables: [
      "android-lab/lab/scripts/auto_bypass_pinning.py: automated injection pipeline using Frida and Objection",
      "System certificate authority push script for Android 10+ images",
      "End-to-end smoke test validating encrypted network payload capture in mitmproxy output"
    ],
    reference: "Teached Mobile Runtime Analysis & Objection/Mitmproxy",
    targetPaths: ["android-lab/lab/scripts/", "android-lab/lab/hooks/", "android-lab/Makefile"],
    suggestedBranch: "feat/android-ssl-bypass-pipeline"
  },
  {
    id: "PENT-04",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Local MCP Security Tool Provider Host (Pattern D8/D9)",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Embed a Model Context Protocol (MCP) stdio JSON-RPC host within os-lab to expose local security tools (Frida attachment, APK manifest inspector, open socket scanner) as structured tools for autonomous AI agents, without exposing raw shells.",
    deliverables: [
      "console/mcp_server.py: Stdio JSON-RPC server conforming to the MCP 2024-11 specification",
      "Typed tool declarations for inspect_apk, run_frida_hook, and audit_network_ports",
      "Strict parameter validation and sandbox boundaries preventing execution outside lab targets"
    ],
    reference: "iQ-iSun Gap D8 / D9 (Embedded Local MCP Host)",
    targetPaths: ["console/mcp_server.py", "console/oslab.py"],
    suggestedBranch: "feat/mcp-security-tools"
  },
  {
    id: "PENT-05",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Binary Exploitation & Hardening Verification Harness",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Automated binary hardening assessment tool using readelf and checksec checks (NX, ASLR/PIE, Stack Canaries, and RELRO) on compiled lab binaries, coupled with a lightweight AFL++ fuzzing crash triage smoke runner.",
    deliverables: [
      "scripts/analysis/binary_checksec.py: python CLI tool verifying compiler mitigation flags",
      "Integration into dashboard jobs view to display binary security posture alongside test runs"
    ],
    reference: "Teached Binary Hardening & Exploit Mitigations",
    targetPaths: ["scripts/analysis/", "linux-lab/", "dashboard/src/views/jobs-page.tsx"],
    suggestedBranch: "feat/binary-hardening-checksec"
  },

  // --- 2. Open Source Operating Systems ---
  {
    id: "OS-01",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Automated Linux Server Provisioning with Systemd Lifecycle Engine",
    priority: "High",
    effort: "Medium",
    summary:
      "Reproducible, unattended Ubuntu Server and Alpine Linux provisioning scripts via cloud-init / preseed. Includes hardened systemd service templates (.service and .timer) with sandboxing (ProtectSystem=strict, PrivateTmp=true), watchdog timers (Type=notify), and structured journald logging.",
    deliverables: [
      "linux-lab/templates/systemd/lab-daemon.service: hardened systemd unit template",
      "linux-lab/setup-ubuntu-server.sh: cloud-init unattended deployment automation",
      "Automated Python verification checking systemd service health and journal status"
    ],
    reference: "Teached Linux Server Management & Systemd Unit Architecture",
    targetPaths: ["linux-lab/", "scripts/setup/"],
    suggestedBranch: "feat/systemd-server-engine"
  },
  {
    id: "OS-02",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Remote-SSH Fleet Orchestration & Zero-Config Key Distribution",
    priority: "High",
    effort: "Medium",
    summary:
      "Automated remote administration manager that generates ed25519 keypairs, auto-discovers dynamic lab IP addresses across NAT/bridged virtualization interfaces, and automatically updates client ~/.ssh/config blocks with ProxyCommand and Cloudflare Access support.",
    deliverables: [
      "scripts/ssh-fleet-manager.sh: key provisioning and ~/.ssh/config block generator",
      "Passwordless authentication validator with automated host key verification",
      "Security enforcement: strict 0600 unix permissions and non-root privilege separation"
    ],
    reference: "Teached Remote-SSH Setup & Automation",
    targetPaths: ["scripts/setup/", "console/oslab.py"],
    suggestedBranch: "feat/ssh-fleet-manager"
  },
  {
    id: "OS-03",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Host Hardware & Installed Software Capability Detection Engine (Pattern D6)",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Cross-platform local capability detection engine querying package managers (apt, dpkg, rpm), developer toolchains (git, node, uv, python3), hypervisors (/dev/kvm, VT-x/AMD-V, WSL2), and system architecture. Feeds the dashboard host page and client registry without external telemetry.",
    deliverables: [
      "console/capabilities.py: cross-platform capability scanner for Linux, macOS, and Windows",
      "Integration into /api/host endpoint and dashboard host page",
      "Graceful degradation when virtualization extensions are disabled in BIOS/UEFI"
    ],
    reference: "iQ-iSun Gap D6 (Installed-Software Detection) & Teached System Info Gathering",
    targetPaths: ["console/capabilities.py", "console/oslab.py", "dashboard/src/views/host-page.tsx"],
    suggestedBranch: "feat/host-capability-scanner"
  },
  {
    id: "OS-04",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Automated Auth Log Audit & Brute-Force Extraction Daemon",
    priority: "Medium",
    effort: "Small",
    summary:
      "Lightweight systemd service parsing /var/log/auth.log or system journal logs for SSH brute-force attempts, credential stuffing, and unauthorized sudo executions. Aggregates attacker IP addresses, attempt counts, and target usernames into a local SQLite store.",
    deliverables: [
      "linux-lab/scripts/auth_audit_daemon.py: event-driven authentication log parser",
      "Systemd unit file and journal watcher configuration",
      "Structured SQLite/JSON analytics schema consumed by the dashboard jobs view"
    ],
    reference: "Teached SSH Log Analysis & Brute-Force Detection",
    targetPaths: ["linux-lab/scripts/", "console/oslab.py"],
    suggestedBranch: "feat/auth-log-audit-daemon"
  },
  {
    id: "OS-05",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Release Profile Tuning & Single-Instance Process Enforcement (Pattern D1/D5)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Apply compiler release tuning (lto = true, codegen-units = 1, opt-level = 's', panic = 'abort', and binary stripping) across native lab utilities. Implement single-instance socket/lockfile enforcement so secondary executions focus existing instances rather than duplicating memory footprint.",
    deliverables: [
      "Compiler configuration tuning with optimized flags across lab binaries",
      "Single-instance IPC / socket lock in CLI runners",
      "Automated binary size and memory footprint validation in test suite"
    ],
    reference: "iQ-iSun Gap D1 (Single-Instance) & D5 (Release Profile Tuning)",
    targetPaths: ["labctl", "scripts/run-tests.sh", "console/"],
    suggestedBranch: "chore/release-tuning-single-instance"
  },

  // --- 3. Firewall Solutions ---
  {
    id: "FW-01",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW Automation Engine & Priority-Aware Rule Optimizer",
    priority: "High",
    effort: "Medium",
    summary:
      "Programmatic UFW orchestration library managing default policies (default deny incoming, default allow outgoing), port definitions, and subnet rules. Features a rule priority optimizer that places high-frequency matchers ahead of broad rules to minimize connection latency, and properly distinguishes deny (silent drop) from reject (ICMP unreachable) postures.",
    deliverables: [
      "console/ufw_manager.py: Python interface for programmatic UFW rule management and numbered status",
      "Rule priority optimization algorithm ordering specific high-hit rules before broad fallthroughs",
      "Unit test suite validating rule generation, deletion, and order preservation"
    ],
    reference: "Teached UFW Fundamentals & Rule Ordering Optimization",
    targetPaths: ["console/ufw_manager.py", "linux-lab/scripts/", "console/oslab.py"],
    suggestedBranch: "feat/ufw-rule-optimizer"
  },
  {
    id: "FW-02",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Real-Time Firewall Log Streaming & Telegram Alert Daemon with Loop Suppression",
    priority: "High",
    effort: "Medium",
    summary:
      "Event-driven daemon tailing /var/log/ufw.log and dispatching real-time attack notifications via Telegram bot or webhook. Incorporates intelligent noise reduction: deduplicates repeated attack IPs, and explicitly suppresses outbound ALLOW traffic and port 53 UDP DNS loop triggers to prevent notification storms and Telegram rate limits.",
    deliverables: [
      "scripts/ufw-telegram/ufw_alert_daemon.py: real-time log follower with credentials in /etc/ufw-telegram/",
      "Noise filter suppressing outbound ALLOW traffic and internal DNS queries",
      "Systemd unit file and logrotate configuration for long-running stability"
    ],
    reference: "Teached UFW Telegram Bot & Notification Loop Prevention",
    targetPaths: ["scripts/ufw-telegram/", "linux-lab/"],
    suggestedBranch: "feat/ufw-alert-daemon-loop-suppression"
  },
  {
    id: "FW-03",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Automated Firewall Security Audit Engine & Systemd Timer",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Continuous firewall rule auditor running as a periodic systemd service and timer (ufw-audit.timer). Evaluates active rules against RFC 1918 private subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), flags insecure exposed management ports, detects duplicate/redundant rules, and verifies DMZ boundary enforcement.",
    deliverables: [
      "scripts/security/ufw_audit.py: rule compliance evaluation and risk scoring engine",
      "ufw-audit.service and ufw-audit.timer systemd unit definitions",
      "Structured JSON and markdown audit report generator"
    ],
    reference: "Teached UFW AI Audit Service & Timer Architecture",
    targetPaths: ["scripts/security/", "linux-lab/"],
    suggestedBranch: "feat/ufw-security-audit-timer"
  },
  {
    id: "FW-04",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Layer 7 WAF Integration & Application Threat Defense",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Ready-to-deploy Layer 7 Web Application Firewall (WAF) recipes (ModSecurity / OWASP Core Rule Set / Nginx reverse proxy) demonstrating defense-in-depth where traditional network firewalls (L3/L4) cannot inspect application payloads. Includes custom rules mitigating application-layer memory exhaustion, deserialization exploits, and injection attacks.",
    deliverables: [
      "Pre-configured Nginx + ModSecurity container with OWASP Core Rule Set (CRS)",
      "Automated demonstration test suite contrasting L3/L4 packet filtering against L7 WAF protection"
    ],
    reference: "Teached PHP Memory-Exhaustion RCE & Application Security vs Network Firewalls",
    targetPaths: ["linux-lab/waf/", "linux-lab/docker-compose.yml"],
    suggestedBranch: "feat/l7-waf-defense-in-depth"
  },
  {
    id: "FW-05",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Multi-Branch Enterprise Network Segmentation & Open Source Appliance Benchmarks",
    priority: "Medium",
    effort: "Large",
    summary:
      "Realistic network segmentation templates for multi-branch organizations (Headquarters, Regional Branch, DMZ, Internal Dev LAN) with CIDR allocations (/24, /17) and VLAN tagging rules. Includes an automated benchmark harness comparing throughput and latency across pfSense, OPNsense, IPFire, and native UFW/nftables.",
    deliverables: [
      "Multi-zone network configuration files and routing rules for isolated lab testing",
      "Automated benchmark runner collecting packet drop latency, memory usage, and throughput metrics"
    ],
    reference: "Teached Multi-Branch Network Architecture & Top 5 Firewall Selection",
    targetPaths: ["linux-lab/topology/", "docs/network/"],
    suggestedBranch: "feat/network-segmentation-benchmarks"
  },
  {
    id: "FW-06",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Zero-Trust Role-Based VPN Gateway vs Direct SSH Ingress",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Automated WireGuard VPN mesh gateway removing the need to expose raw public SSH ports. Features automated client key generation and role-based packet forwarding rules granting least-privilege subnet access per authenticated client profile.",
    deliverables: [
      "WireGuard configuration generator with automated client key distribution",
      "Integrated UFW forwarding rules restricting client access to authorized lab subnets only"
    ],
    reference: "Teached Role-Based VPN vs Exposed Port Architecture",
    targetPaths: ["scripts/setup/vpn.sh", "linux-lab/"],
    suggestedBranch: "feat/wireguard-role-based-vpn"
  },

  // ===== EXPANSION — scaled to 1.5× enrollment (BGT207 25 · MYO062 23 · MYO203 24 = 72 → ~108 options) =====
  // Grounded in teached/ transcripts + planned syllabus. "held" items carry a `prerequisite`.

  // --- Penetration Testing (MYO062) continued ---
  {
    id: "PENT-06",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "frida-trace Auto-Tracer & Call-Map Builder",
    priority: "High",
    effort: "Small",
    summary:
      "Wrapper around frida-trace that discovers and traces exported/native functions of a lab process, then renders a call map of which functions fire for a given action, with per-call argument snapshots.",
    deliverables: [
      "android-lab/lab/hooks/trace_runner.py: frida-trace wrapper taking a process and a symbol glob, emitting a JSON call map",
      "labctl action to trace a lab target and save an annotated session log"
    ],
    reference: "Teached 05.10 Frida pratik (frida-trace, süreç→fonksiyon→hook)",
    targetPaths: ["android-lab/lab/hooks/", "console/oslab.py"],
    suggestedBranch: "feat/frida-trace-runner"
  },
  {
    id: "PENT-07",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Interceptor retval.replace & Argument-Tampering Script Library",
    priority: "Medium",
    effort: "Small",
    summary:
      "Parametrized gozlem.js/degistir.js templates that observe onEnter arguments and rewrite onLeave return values against the deterministic lab auth harness, driven by a small JSON policy (which function, which argument, what value).",
    deliverables: [
      "android-lab/lab/hooks/tamper_policy.js: policy-driven onEnter/onLeave/retval.replace runner",
      "Golden-file test asserting the 2-second password check in hedef.c is observed and overridden deterministically"
    ],
    reference: "Teached 05.10 degistir.js / retval.replace, hedef.c parola kontrolü",
    targetPaths: ["android-lab/lab/hooks/", "android-lab/lab/tests/"],
    suggestedBranch: "feat/frida-retval-tamper"
  },
  {
    id: "PENT-08",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Java / Objective-C Bridge Class Enumerator & Method Overrider",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Verified Android lab (26.10 setup not yet student-verified)",
    summary:
      "Uses Frida's Java/ObjC bridge to list loaded classes and methods in a lab app and override a chosen method, logging before/after behavior — the class-listing and method-overriding shown for Android/iOS.",
    deliverables: [
      "android-lab/lab/hooks/java_bridge.js: class/method enumerator with selective override and logging",
      "Smoke test against a lab APK confirming an overridden method changes observed behavior"
    ],
    reference: "Teached 05.10 Java köprüsü (Android/iOS sınıf listeleme, metot ezme)",
    targetPaths: ["android-lab/lab/hooks/", "android-lab/lab/tests/"],
    suggestedBranch: "feat/frida-java-bridge"
  },
  {
    id: "PENT-09",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Frida Device & Process Inventory Tool",
    priority: "High",
    effort: "Tiny–Small",
    summary:
      "Wraps frida-ls-devices and frida-ps (USB/TCP) into a single read-only inventory returning attached devices and attachable processes as structured JSON for the console and agents.",
    deliverables: [
      "console/frida_inventory.py: JSON inventory of devices and processes with transport (USB/TCP)",
      "Dashboard jobs-view card listing attachable lab targets"
    ],
    reference: "Teached 28.09/05.10 frida-ls-devices, frida-ps, USB/TCP",
    targetPaths: ["console/frida_inventory.py", "dashboard/src/views/jobs-page.tsx"],
    suggestedBranch: "feat/frida-inventory"
  },
  {
    id: "PENT-10",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Electron App Unpacker & Injection-Point Mapper",
    priority: "Medium",
    effort: "Small–Medium",
    summary:
      "Static analyzer that unpacks an open-source Electron app's asar archive, inventories main/renderer entry points and Node-integration/preload surfaces, and flags where an agent could be injected — reproducing the lab's successful Electron injection case.",
    deliverables: [
      "scripts/analysis/electron_asar_inspect.py: asar unpack + entry/preload/nodeIntegration mapper → JSON",
      "Report highlighting injectable surfaces for a provided open-source Electron lab target"
    ],
    reference: "Teached 28.09 açık kaynak Electron uygulamalarında enjeksiyon çalıştı",
    targetPaths: ["scripts/analysis/", "console/oslab.py"],
    suggestedBranch: "feat/electron-injection-mapper"
  },
  {
    id: "PENT-11",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "SSL / Certificate Pinning Detector & Classifier (Static)",
    priority: "High",
    effort: "Small",
    summary:
      "Static scanner that inspects an APK/binary for pinning implementations (OkHttp CertificatePinner, TrustManager, Network Security Config, native BoringSSL) and classifies the pinning method before any dynamic analysis is attempted, in lab scope only.",
    deliverables: [
      "scripts/analysis/pinning_detect.py: signature scan classifying pinning type with evidence lines",
      "Markdown report mapping each detected pin to the recommended lab analysis approach"
    ],
    reference: "Teached 28.09 sertifika iğnelemesi; 26.10 proxy/objection",
    targetPaths: ["scripts/analysis/", "android-lab/lab/"],
    suggestedBranch: "feat/pinning-detector"
  },
  {
    id: "PENT-12",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "APK Static Triage: aapt Manifest, Permissions & Strings Report",
    priority: "Medium",
    effort: "Small–Medium",
    prerequisite: "Verified Android lab",
    summary:
      "Runs aapt over a lab APK to extract AndroidManifest.xml, declared permissions, components and strings.xml, producing a static triage report that precedes any dynamic run.",
    deliverables: [
      "android-lab/lab/scripts/apk_triage.py: aapt-based manifest/permissions/strings extractor → JSON + markdown",
      "Permission risk scoring (exported components, dangerous permissions)"
    ],
    reference: "Teached 26.10 aapt, AndroidManifest.xml, strings.xml",
    targetPaths: ["android-lab/lab/scripts/", "console/oslab.py"],
    suggestedBranch: "feat/apk-static-triage"
  },
  {
    id: "PENT-13",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "mitmproxy Lab-Traffic Summarizer with Scope Guard",
    priority: "Medium",
    effort: "Small–Medium",
    prerequisite: "Verified Android lab",
    summary:
      "Parses a mitmproxy flow dump for a lab app and summarizes hosts, endpoints, tokens seen and data sent/written, refusing to process flows whose hosts fall outside the declared lab scope.",
    deliverables: [
      "android-lab/lab/scripts/mitm_summary.py: flow → summary with host-allowlist scope guard",
      "Report of endpoints, methods and payload categories for the lab target only"
    ],
    reference: "Teached 26.10 mitmproxy, ortadaki adam proxy; kapsam kuralı",
    targetPaths: ["android-lab/lab/scripts/"],
    suggestedBranch: "feat/mitm-summarizer"
  },
  {
    id: "PENT-14",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Objection Runtime Toolkit Wrapper (Lab-Only)",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Verified Android lab",
    summary:
      "Thin wrapper exposing objection's common runtime actions (root/emulator detection checks, keystore/heap inspection) as approved, logged steps against a lab app, behind a hard scope guard.",
    deliverables: [
      "android-lab/lab/scripts/objection_toolkit.py: curated objection actions with per-step session log",
      "needsApproval gate on every state-touching action"
    ],
    reference: "Teached 26.10 objection, runtime enjeksiyon",
    targetPaths: ["android-lab/lab/scripts/"],
    suggestedBranch: "feat/objection-toolkit"
  },
  {
    id: "PENT-15",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Two-Stage \"Clean Dropper\" Detection Harness",
    priority: "High",
    effort: "Medium",
    summary:
      "Builds a benign-looking lab artifact that fetches a second stage from a local server, plus a detector that flags the clean→cloud-payload pattern (deferred fetch + eval of remote code) — teaching detection of the new-generation trojan model, entirely in lab.",
    deliverables: [
      "scripts/analysis/dropper_lab/: benign first-stage + local second-stage server for reproducible study",
      "dropper_detect.py flagging deferred remote-code fetch/eval patterns with evidence"
    ],
    reference: "Teached 19.10 yeni nesil Truva atı (tertemiz gelir, zararlı sonradan buluttan iner)",
    targetPaths: ["scripts/analysis/", "console/oslab.py"],
    suggestedBranch: "feat/dropper-detection"
  },
  {
    id: "PENT-16",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Browser-Extension Corpus Scanner & Injection Aggregator",
    priority: "High",
    effort: "Medium",
    summary:
      "Batch scanner that runs the extension audit over a directory of unpacked extensions and aggregates dangerous-call sites across the corpus into a single ranked report — the method used to sweep ~988 extensions.",
    deliverables: [
      "scripts/analysis/ext_corpus_scan.py: batch runner producing a corpus-wide injection-point table",
      "Aggregation and ranking by permission surface and sink density"
    ],
    reference: "Teached 19.10 988 eklenti taranıp enjeksiyon noktaları birleştirildi",
    targetPaths: ["scripts/analysis/", "dashboard/src/views/jobs-page.tsx"],
    suggestedBranch: "feat/extension-corpus-scanner"
  },
  {
    id: "PENT-17",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Extension Exfiltration Endpoint & CSP Analyzer",
    priority: "Medium",
    effort: "Small",
    summary:
      "Extracts remote endpoints, fetch/XHR targets and CSP / declarativeNetRequest rules from an extension and flags likely exfiltration destinations and CSP weakenings.",
    deliverables: [
      "scripts/analysis/ext_exfil.py: endpoint + CSP extractor with exfiltration heuristics",
      "Report listing external hosts contacted and any CSP relaxations"
    ],
    reference: "Teached 19.10 çerez çalma riski, uzaktan kod/dış script, CSP",
    targetPaths: ["scripts/analysis/"],
    suggestedBranch: "feat/extension-exfil-analyzer"
  },
  {
    id: "PENT-18",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Extension Native-Messaging Host Risk Analyzer",
    priority: "Medium",
    effort: "Small",
    summary:
      "Audits an extension's nativeMessaging usage and the referenced native host manifests/binaries, flagging privilege-escalation bridges from the browser sandbox to a local process.",
    deliverables: [
      "scripts/analysis/ext_native_host.py: nativeMessaging manifest + allowed_origins + host-binary inspector",
      "Risk notes on browser → native privilege bridges"
    ],
    reference: "Teached 19.10 native messaging izni",
    targetPaths: ["scripts/analysis/"],
    suggestedBranch: "feat/extension-native-host"
  },
  {
    id: "PENT-19",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Analysis Session Brain-Map (lat.md) Generator",
    priority: "Medium",
    effort: "Small",
    summary:
      "Generates a lat.md-style knowledge graph for an analysis project — nodes for targets, findings and scripts, with links between them — so a long investigation stays navigable, as introduced in class.",
    deliverables: [
      "scripts/analysis/latmap.py: emits a lat.md graph from a session's findings/scripts",
      "lat check-compatible node/link output"
    ],
    reference: "Teached 19.10 lat.md ile proje beyin haritası",
    targetPaths: ["scripts/analysis/", "lat.md/"],
    suggestedBranch: "feat/analysis-brainmap"
  },
  {
    id: "PENT-20",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Pentest Session Scribe: Scoped, Logged, AI-Disclosed (Subagent)",
    priority: "High",
    effort: "Medium",
    summary:
      "A subagent that holds the engagement scope file, records every step, discloses AI use per step, and refuses actions against out-of-scope targets — the method/ethics discipline taught in week 1. Exports a signed markdown report.",
    deliverables: [
      "labctl pentest-scribe subagent: scope file, per-step log, AI-use disclosure, out-of-scope refusal",
      "Session export as a signed markdown report"
    ],
    reference: "Teached 28.09 yöntem/etik: kapsam, oturum notu, AI kullanımının belgelenmesi",
    targetPaths: ["labctl", "console/oslab.py"],
    suggestedBranch: "feat/pentest-scribe"
  },
  {
    id: "PENT-21",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Authorization & Scope-Guard Library (Refuses Non-Lab Targets)",
    priority: "High",
    effort: "Small",
    summary:
      "Shared guard that every lab tool imports to assert a target (host, package, path, device) is inside the declared lab scope, refusing with a clear reason otherwise — enforcing the \"lab only\" rule in code.",
    deliverables: [
      "console/scope_guard.py: scope-manifest loader + assert_in_scope() used by lab tools",
      "Unit tests for allow/deny of hosts, packages and device serials"
    ],
    reference: "Teached 19.10 kapsam kuralı; 28.09 yetki olmadan deneme yok",
    targetPaths: ["console/scope_guard.py", "console/oslab.py"],
    suggestedBranch: "feat/scope-guard"
  },
  {
    id: "PENT-22",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "AI-Use Disclosure & Analysis Report Generator",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Collects a session's AI prompts/outputs and tool calls into a disclosure appendix and a readable analysis report, so each finding is reproducible and each AI contribution is documented.",
    deliverables: [
      "console/report_gen.py: session log → markdown report with an AI-use appendix",
      "Template with findings, evidence and reproducibility steps"
    ],
    reference: "Teached 28.09 yapay zeka kullanımının belgelenmesi, her adımda kayıt",
    targetPaths: ["console/report_gen.py"],
    suggestedBranch: "feat/ai-disclosure-report"
  },
  {
    id: "PENT-23",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Windows No-Admin Lab Preflight (VT-x / Podman / VirtualBox / WSL)",
    priority: "High",
    effort: "Small",
    summary:
      "Checks a Windows 10/11 machine without admin rights for virtualization readiness — VT-x/AMD-V state, Hyper-V/WSL2, VirtualBox/Podman presence — and reports blockers with fixes, reproducing the 26.10 live setup issues.",
    deliverables: [
      "win-lab/scripts/preflight.ps1: no-admin capability + virtualization preflight → JSON",
      "Actionable report (e.g. VT-x disabled in BIOS) with remediation notes"
    ],
    reference: "Teached 26.10 yönetici yetkisi olmadan VirtualBox/Podman, VT-x BIOS kapalı",
    targetPaths: ["win-lab/scripts/", "dashboard/src/views/host-page.tsx"],
    suggestedBranch: "feat/win-noadmin-preflight"
  },
  {
    id: "PENT-24",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Docker-Based Android Emulator Provisioner",
    priority: "Medium",
    effort: "Large",
    prerequisite: "Verified Android lab",
    summary:
      "One-command provisioner bringing up a containerized Android emulator with adb reachable and frida-server staged — the setup script promised to students for the mobile lab.",
    deliverables: [
      "android-lab/lab/scripts/provision_emulator.sh: container emulator + adb + frida-server bootstrap",
      "Smoke test: adb devices shows the emulator and frida-ps attaches"
    ],
    reference: "Teached 26.10 Docker tabanlı Android emulator, kurulum repoda hazır script",
    targetPaths: ["android-lab/lab/scripts/", "android-lab/Makefile"],
    suggestedBranch: "feat/android-emulator-provision"
  },
  {
    id: "PENT-25",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "C2 Beacon Traffic Simulator & Blue-Team Detector (Lab)",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "C2 lecture (ders03, planned — not yet taught)",
    summary:
      "In an isolated lab network, generates benign beacon-like traffic with tunable jitter/interval/profile plus a detector that spots periodic beaconing — teaching detection rather than operation.",
    deliverables: [
      "linux-lab/c2-lab/beacon_sim.py: configurable interval/jitter beacon generator (lab network only)",
      "beacon_detect.py scoring periodicity and flagging suspected C2 channels"
    ],
    reference: "Planned ders03 C2 çatıları (beacon, C2 profilleri, OPSEC)",
    targetPaths: ["linux-lab/c2-lab/"],
    suggestedBranch: "feat/c2-beacon-detection"
  },
  {
    id: "PENT-26",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Loader Behavior Telemetry Harness (Defensive, Lab)",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "AV/EDR lecture (ders04, planned — not yet taught)",
    summary:
      "Instruments a lab binary loader to emit telemetry (memory allocation, in-memory execution, syscall sequence) so students study what endpoint sensors observe — an observability exercise, not an evasion toolkit.",
    deliverables: [
      "linux-lab/edr-lab/loader_telemetry.py: records allocation/exec/syscall events of a lab loader",
      "Report mapping observed events to detection opportunities"
    ],
    reference: "Planned ders04 AV/EDR (in-memory yürütme, syscall'lar) — savunma odaklı",
    targetPaths: ["linux-lab/edr-lab/"],
    suggestedBranch: "feat/loader-telemetry"
  },
  {
    id: "PENT-27",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Advanced Web Exploitation Lab Targets + Detection",
    priority: "Medium",
    effort: "Large",
    prerequisite: "Advanced-web lecture (ders05, planned — not yet taught)",
    summary:
      "Intentionally vulnerable, self-contained lab apps demonstrating SSRF→cloud metadata, SSTI, insecure deserialization and request smuggling, each paired with a detector and a remediation note.",
    deliverables: [
      "linux-lab/web-lab/: dockerized vulnerable targets (SSRF, SSTI, deserialization, smuggling)",
      "Per-target detection rule and remediation writeup"
    ],
    reference: "Planned ders05 ileri web (SSRF→cloud metadata, deserialization, SSTI, request smuggling)",
    targetPaths: ["linux-lab/web-lab/", "linux-lab/docker-compose.yml"],
    suggestedBranch: "feat/web-exploitation-lab"
  },
  {
    id: "PENT-28",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Binary Exploitation Teaching Harness with Mitigation Toggles",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Binary-exploitation lecture (ders06, planned — not yet taught)",
    summary:
      "Compiles a vulnerable lab binary with toggleable NX/ASLR/PIE/canary/RELRO so students observe how each mitigation changes exploitability (stack overflow → ROP), complementing the PENT-05 checksec auditor.",
    deliverables: [
      "linux-lab/binexp-lab/Makefile: builds the target with per-mitigation flags",
      "Guided exercises showing behavior with each mitigation on/off (lab only)"
    ],
    reference: "Planned ders06 binary exploitation (stack overflow, ROP, ASLR/NX/canary)",
    targetPaths: ["linux-lab/binexp-lab/"],
    suggestedBranch: "feat/binexp-teaching-harness"
  },
  {
    id: "PENT-29",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Linux Privilege-Escalation Audit Tool (GTFOBins / SUID / Caps)",
    priority: "Medium",
    effort: "Small–Medium",
    prerequisite: "Privesc lecture (ders08, planned — not yet taught)",
    summary:
      "Read-only auditor enumerating SUID/SGID binaries, capabilities, writable PATH entries and known GTFOBins on a lab host, reporting escalation paths for defenders to close (no exploitation payloads).",
    deliverables: [
      "linux-lab/scripts/privesc_audit.py: SUID/caps/GTFOBins enumerator → ranked findings",
      "Remediation notes per finding"
    ],
    reference: "Planned ders08 Linux privesc (GTFOBins/SUID/caps/kernel)",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/linux-privesc-audit"
  },
  {
    id: "PENT-30",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Windows Privilege-Escalation Audit (Token / UAC / Service)",
    priority: "Medium",
    effort: "Small–Medium",
    prerequisite: "Privesc lecture (ders08, planned — not yet taught)",
    summary:
      "Audits a lab Windows host for common escalation surfaces — unquoted service paths, weak service ACLs, token/UAC posture — and reports hardening actions (audit-only).",
    deliverables: [
      "win-lab/scripts/privesc_audit.ps1: service ACL / unquoted-path / UAC posture audit → report",
      "Hardening recommendations per finding"
    ],
    reference: "Planned ders08 Windows privesc (token/UAC/potato)",
    targetPaths: ["win-lab/scripts/"],
    suggestedBranch: "feat/win-privesc-audit"
  },
  {
    id: "PENT-31",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Isolated Wireless Lab: WPA2/WPA3 Handshake & PMKID Study",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Wireless lecture (ders09, planned — not yet taught)",
    summary:
      "In a fully isolated RF lab the student owns, captures and analyzes WPA2/WPA3 handshakes and PMKID material to study the protocol, with a strict refusal to operate against any network outside the owned lab.",
    deliverables: [
      "linux-lab/wifi-lab/handshake_study.py: capture parsing + PMKID/handshake analysis (owned lab AP only)",
      "Hard scope guard refusing non-lab BSSIDs"
    ],
    reference: "Planned ders09 kablosuz (WPA2/WPA3, PMKID, deauth)",
    targetPaths: ["linux-lab/wifi-lab/"],
    suggestedBranch: "feat/wireless-handshake-study"
  },
  {
    id: "PENT-32",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Pivoting & Tunneling Lab Topology + Detection",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Pivoting lecture (ders10, planned — not yet taught)",
    summary:
      "Spins up a multi-subnet lab where students practice SOCKS / chisel / ligolo tunneling between isolated segments, paired with a detector that flags tunneling and lateral-movement signatures.",
    deliverables: [
      "linux-lab/pivot-lab/: multi-subnet compose topology + guided SOCKS/chisel exercises",
      "pivot_detect.py flagging tunnel / lateral-movement indicators"
    ],
    reference: "Planned ders10 pivoting & tünelleme (SOCKS, chisel/ligolo, port yönlendirme)",
    targetPaths: ["linux-lab/pivot-lab/"],
    suggestedBranch: "feat/pivoting-lab"
  },
  {
    id: "PENT-33",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Container & Kubernetes Security Auditor",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Container/k8s lecture (ders11, planned — not yet taught)",
    summary:
      "Audits a lab Docker / Kubernetes setup for escape surfaces — privileged containers, dangerous mounts, over-broad RBAC — and reports least-privilege fixes.",
    deliverables: [
      "linux-lab/k8s-lab/container_audit.py: privileged / mount / capability audit for containers",
      "rbac_audit.py flagging over-broad Kubernetes roles and bindings"
    ],
    reference: "Planned ders11 container & k8s (docker escape, yetkili konteyner, RBAC)",
    targetPaths: ["linux-lab/k8s-lab/"],
    suggestedBranch: "feat/container-k8s-audit"
  },
  {
    id: "PENT-34",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Fuzzing Harness: AFL++/libFuzzer Coverage & Crash Triage",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Fuzzing lecture (ders12, planned — not yet taught)",
    summary:
      "Sets up AFL++/libFuzzer against a lab binary with coverage collection and automated crash triage/dedup, extending the PENT-05 smoke runner into a full campaign harness.",
    deliverables: [
      "linux-lab/fuzz-lab/run_campaign.py: corpus / coverage / crash-triage orchestration",
      "Dedup + minimized repro output per unique crash"
    ],
    reference: "Planned ders12 fuzzing (AFL++/libFuzzer, coverage, crash triage, N-day)",
    targetPaths: ["linux-lab/fuzz-lab/"],
    suggestedBranch: "feat/fuzzing-campaign"
  },
  {
    id: "PENT-35",
    category: "pentest",
    categoryLabel: "Penetration Testing",
    title: "Red-Team Report & MITRE ATT&CK Mapping Generator",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "Red-team reporting lecture (ders13, planned — not yet taught)",
    summary:
      "Turns a session log into a professional red-team report with findings, evidence and an automatic MITRE ATT&CK technique mapping, formalizing the scribe's output.",
    deliverables: [
      "labctl report tool: session log → ATT&CK-mapped professional report (markdown + PDF)",
      "Technique inference from logged tool actions"
    ],
    reference: "Planned ders13 red team & MITRE ATT&CK eşlemesi & raporlama",
    targetPaths: ["labctl", "console/oslab.py"],
    suggestedBranch: "feat/redteam-attack-report"
  },

  // --- Open Source OS (MYO203) continued ---
  {
    id: "OS-06",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Reproducible Ubuntu Server VM Installer & Snapshot Automation",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Scripts a repeatable VirtualBox Ubuntu Server build (2 GB RAM, OpenSSH preselected, bridged adapter) and takes a labeled post-install snapshot so a broken VM can be restored in seconds.",
    deliverables: [
      "win-lab/scripts/new_ubuntu_vm.(ps1|sh): unattended VM create + install options + snapshot",
      "Verification step confirming SSH is reachable after boot"
    ],
    reference: "Teached 28.09 VirtualBox Ubuntu Server, OpenSSH; 26.10 VM onarımı",
    targetPaths: ["win-lab/scripts/", "linux-lab/"],
    suggestedBranch: "feat/ubuntu-vm-provisioner"
  },
  {
    id: "OS-07",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Lab Environment Selector: WSL vs VirtualBox for Constrained PCs",
    priority: "Medium",
    effort: "Small",
    summary:
      "Detects a student's Windows machine constraints and recommends WSL2 or VirtualBox, then runs the matching bootstrap — addressing the restricted lab PCs discussed in week 1.",
    deliverables: [
      "win-lab/scripts/env_select.ps1: constraint check → WSL2 | VirtualBox recommendation + bootstrap",
      "Fallback guidance when virtualization is unavailable"
    ],
    reference: "Teached 21.09 kısıtlı lab PC'leri, WSL ve VirtualBox seçenekleri",
    targetPaths: ["win-lab/scripts/"],
    suggestedBranch: "feat/lab-env-selector"
  },
  {
    id: "OS-08",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Distro Comparison & Selector (Ubuntu / Debian / Kali / Alpine)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "A reference tool comparing the distros covered in class by base, package manager, footprint and use-case, returning a recommendation for a given lab goal.",
    deliverables: [
      "linux-lab/distro_select.py: structured distro dataset + recommender",
      "Markdown comparison-table generator"
    ],
    reference: "Teached 28.09 dağıtımlar: Ubuntu, Debian, Kali, Alpine",
    targetPaths: ["linux-lab/"],
    suggestedBranch: "feat/distro-selector"
  },
  {
    id: "OS-09",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Open-Source License Classifier (GPL / MIT / Apache)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Scans a repository for license files and SPDX headers and classifies the effective license (copyleft vs permissive), explaining the GPL/MIT distinction taught in week 2.",
    deliverables: [
      "linux-lab/scripts/license_scan.py: license/SPDX detector → report with copyleft/permissive note",
      "Flag for mixed or missing licenses"
    ],
    reference: "Teached 28.09 dört özgürlük, GPL ve MIT farkı",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/license-classifier"
  },
  {
    id: "OS-10",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Linux Filesystem Hierarchy Explorer & Teaching Map",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Walks and annotates the standard hierarchy (/, /home, /etc, /opt, /root) with what lives where and why, including a hidden-file (dotfile) explanation — a teaching aid for week 2.",
    deliverables: [
      "linux-lab/scripts/fs_explore.py: annotated hierarchy walker with per-directory purpose",
      "Hidden-file listing and explanation"
    ],
    reference: "Teached 28.09 dosya sistemi /, /home, /etc, /opt, /root; gizli dosyalar",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/fs-hierarchy-explorer"
  },
  {
    id: "OS-11",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Guided Shell-Basics Practice & Auto-Grader",
    priority: "High",
    effort: "Small",
    summary:
      "An interactive checker for the week-3 exercise (ali/eda/aleyna with odevler/sinavlar/sunumlar/puan.txt) that verifies the student's directory/file structure and gives feedback.",
    deliverables: [
      "linux-lab/exercises/shell_basics_check.py: validates the taught directory/file exercise",
      "Pass/fail feedback per expected path with hints"
    ],
    reference: "Teached 05.10 alıştırma: ali/eda/aleyna + odevler/sinavlar/sunumlar/puan.txt",
    targetPaths: ["linux-lab/exercises/"],
    suggestedBranch: "feat/shell-basics-grader"
  },
  {
    id: "OS-12",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Directory-Structure Scaffolder (mkdir -p Templates)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Generates nested directory trees from a simple template spec (the mkdir -p pattern taught in class), for setting up course/exercise folders reproducibly.",
    deliverables: [
      "linux-lab/scripts/scaffold.py: YAML/JSON template → mkdir -p tree with touch'd files",
      "Dry-run preview before creating"
    ],
    reference: "Teached 05.10 mkdir -p, birden fazla klasör, touch",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/dir-scaffolder"
  },
  {
    id: "OS-13",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "apt update/upgrade Safe Wrapper (Correct Order + Dry-Run)",
    priority: "High",
    effort: "Small",
    summary:
      "Enforces the taught update-before-upgrade order, shows a dry-run of what will change, and chains steps safely with clear output — codifying the \"order matters\" lesson.",
    deliverables: [
      "linux-lab/scripts/apt_safe.py: ordered update → upgrade with dry-run and summary",
      "Guard refusing upgrade when update failed"
    ],
    reference: "Teached 05.10 apt update≠upgrade, sıra önemli; 19.10 && zincirleme",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/apt-safe-wrapper"
  },
  {
    id: "OS-14",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Node.js & Python Toolchain Installer with Version Check",
    priority: "Medium",
    effort: "Small",
    summary:
      "Installs Python and Node (detecting apt's stale Node and offering NodeSource), verifies node -v / python versions, and sets python-is-python3 — reproducing weeks 5–6.",
    deliverables: [
      "linux-lab/scripts/install_toolchains.sh: apt vs NodeSource choice + version verification",
      "python-is-python3 setup and post-install checks"
    ],
    reference: "Teached 19.10/26.10 Node apt eski sürüm, python-is-python3",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/toolchain-installer"
  },
  {
    id: "OS-15",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Disk Reclamation Helper (node_modules / Rust target / apt clean)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Finds and safely removes space hogs — node_modules, Rust target/, apt caches — with a dry-run and size report, reproducing the in-class disk-full recovery.",
    deliverables: [
      "linux-lab/scripts/disk_reclaim.py: scan + dry-run + approved cleanup with reclaimed-size report",
      "Safety: never deletes outside a chosen root; approval required"
    ],
    reference: "Teached 26.10 disk dolunca node_modules ve Rust target temizlendi; apt clean",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/disk-reclaim"
  },
  {
    id: "OS-16",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Server First-Look Health Report (uname / lsb_release / free / disk / services)",
    priority: "High",
    effort: "Small",
    summary:
      "Collects the \"first look at a server\" facts taught in week 5 — OS version, CPU architecture, RAM, disk and key service status — as JSON plus a readable report.",
    deliverables: [
      "linux-lab/scripts/server_firstlook.py: uname/lsb_release/inxi/free/df/systemctl → JSON + report",
      "Architecture note affecting package choices"
    ],
    reference: "Teached 19.10 sistem bilgisi: uname, lsb_release, inxi, free, /proc",
    targetPaths: ["linux-lab/scripts/", "console/oslab.py"],
    suggestedBranch: "feat/server-firstlook"
  },
  {
    id: "OS-17",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "SSH Connection Troubleshooter",
    priority: "High",
    effort: "Small",
    summary:
      "Diagnoses the exact failures students hit — connection timeout, wrong password, 127.0.1.1 binding, school-firewall block, wrong adapter — and prints the fix for each.",
    deliverables: [
      "linux-lab/scripts/ssh_doctor.py: targeted checks that classify the failure cause",
      "Remediation per cause (bridged adapter, hosts file, firewall)"
    ],
    reference: "Teached 12.10 SSH hataları: zaman aşımı, yanlış parola, 127.0.1.1, okul güvenlik duvarı",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/ssh-troubleshooter"
  },
  {
    id: "OS-18",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Dynamic Lab IP Finder via ARP + Auto-SSH",
    priority: "Medium",
    effort: "Small",
    summary:
      "Cross-platform rewrite of the week-5 PowerShell idea: start/await a VM, find its IP from the ARP table, SSH in and collect system info in one hardened step.",
    deliverables: [
      "win-lab/scripts/find_and_ssh.(ps1|py): VM boot wait → ARP IP discovery → SSH → info collection",
      "Robust error reporting (detailed messages, retry logic)"
    ],
    reference: "Teached 19.10 PowerShell: VM başlat, ARP'tan IP bul, SSH ile bağlan, bilgi çıkar",
    targetPaths: ["win-lab/scripts/"],
    suggestedBranch: "feat/arp-autossh"
  },
  {
    id: "OS-19",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "SSH Port-Relocation Hardening Helper",
    priority: "Medium",
    effort: "Small",
    summary:
      "Safely moves sshd off 22 to a chosen port, updates sshd_config and the firewall together, and verifies the new port before closing the old — the \"move the door\" lesson.",
    deliverables: [
      "linux-lab/scripts/ssh_port_move.sh: sshd_config + ufw update with pre-close verification",
      "Rollback if the new port is unreachable"
    ],
    reference: "Teached 12.10 port taşıma (22 yerine başka port)",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/ssh-port-relocation"
  },
  {
    id: "OS-20",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "VS Code Remote-SSH Host Registration & Bootstrap",
    priority: "Medium",
    effort: "Small",
    summary:
      "Registers a lab host for VS Code Remote-SSH (Add New SSH Host), validates the connection and the remote server bootstrap, and checks the green-indicator state programmatically.",
    deliverables: [
      "scripts/setup/remote_ssh_register.py: writes/validates the SSH host entry and tests connect",
      "Checklist verifying the remote extension host is ready"
    ],
    reference: "Teached 19.10/26.10 VS Code Remote-SSH, Add New SSH Host, yeşil gösterge",
    targetPaths: ["scripts/setup/"],
    suggestedBranch: "feat/vscode-remote-ssh-bootstrap"
  },
  {
    id: "OS-21",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Boot-Time Python Service Starter (systemd)",
    priority: "High",
    effort: "Small",
    summary:
      "Scaffolds the week-6 homework: an enabled-at-boot systemd service running a simple looping Python program, with enable/status/journal verification — the student-facing entry point to OS-01.",
    deliverables: [
      "linux-lab/templates/loop-service/: minimal .service + loop.py + install/enable script",
      "Verification: systemctl is-enabled/is-active and journalctl shows loop output"
    ],
    reference: "Teached 26.10 ileri ödev: açılışta aktif service + döngülü Python",
    targetPaths: ["linux-lab/templates/"],
    suggestedBranch: "feat/boot-service-starter"
  },
  {
    id: "OS-22",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "apt Repair Assistant: Clock/Timezone & Broken Sources",
    priority: "High",
    effort: "Small",
    summary:
      "Detects the week-6 failure cause — a wrong server clock/timezone breaking apt — plus held packages and broken sources, and proposes/applies fixes (timezone → Istanbul).",
    deliverables: [
      "linux-lab/scripts/apt_repair.py: clock/timezone/held/source diagnostics → proposed fixes",
      "Approval-gated apply with before/after check"
    ],
    reference: "Teached 26.10 apt hataları sunucu saat/tarih yanlışı; zaman dilimi İstanbul",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/apt-repair-assistant"
  },
  {
    id: "OS-23",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "dpkg Package Inventory & File Reverse-Lookup",
    priority: "Medium",
    effort: "Small",
    summary:
      "Wraps dpkg -l/-L/-S into a tool that answers \"what's installed\", \"what files does this package own\" and \"which package owns this file\", with clean JSON output.",
    deliverables: [
      "linux-lab/scripts/dpkg_inventory.py: -l/-L/-S wrappers → structured results",
      "Reverse-lookup mode mapping a path to its owning package"
    ],
    reference: "Teached ders05 dpkg (-l/-L/-S/-i/-r)",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/dpkg-inventory"
  },
  {
    id: "OS-24",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Local .deb Installer with Dependency Resolution",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Installs a local .deb via apt install ./x.deb, resolving dependencies and reporting what will be pulled in, with a dry-run first.",
    deliverables: [
      "linux-lab/scripts/deb_install.sh: apt install ./x.deb with a dependency preview",
      "Post-install verification of the package"
    ],
    reference: "Teached ders05 apt install ./x.deb",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/local-deb-installer"
  },
  {
    id: "OS-25",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "apt Sources Manager & Validator (/etc/apt/sources.list.d)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Lists, adds and validates apt sources (modern .sources format), checking GPG keys and reachability before enabling a new repo.",
    deliverables: [
      "linux-lab/scripts/apt_sources.py: list/add/validate sources with key + reachability checks",
      "Guard against duplicate or unsigned repos"
    ],
    reference: "Teached ders05 /etc/apt/sources.list.d/ubuntu.sources",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/apt-sources-manager"
  },
  {
    id: "OS-26",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "File Permission & Ownership Auditor",
    priority: "Medium",
    effort: "Small",
    summary:
      "Scans a directory for world-writable files, over-permissive modes and ownership drift, reporting fixes — the week-3 \"read the door\" permissions lesson as an audit.",
    deliverables: [
      "linux-lab/scripts/perm_audit.py: world-writable / bad-mode / ownership-drift scan → findings",
      "Suggested chmod/chown per finding"
    ],
    reference: "Teached ders03 ls -l, rwx, chmod, chown",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/permission-auditor"
  },
  {
    id: "OS-27",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Permission-Fix Advisor with 644/755/600 Presets",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Applies the taught ready-made modes (644 files, 755 dirs/executables, 600 secrets) to a tree with a preview, teaching safe defaults.",
    deliverables: [
      "linux-lab/scripts/perm_fix.py: preset-based chmod with preview and approval",
      "Explains why each preset fits files / dirs / secrets"
    ],
    reference: "Teached ders03 hazır 644/755/600, chmod aç/kapat",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/permission-fixer"
  },
  {
    id: "OS-28",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "File Search & Text-Grep Teaching Wrapper (find / grep / wildcards)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "A friendly wrapper over find and grep (with wildcard examples) that builds correct commands from a simple query and explains what it ran — reinforcing week-2 search skills.",
    deliverables: [
      "linux-lab/scripts/search_helper.py: query → correct find/grep command + results",
      "Explain mode printing the generated command"
    ],
    reference: "Teached ders02 find/grep, joker karakterler",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/search-helper"
  },
  {
    id: "OS-29",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Server Log Viewer Helper (less / head / tail / wc)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Convenience viewer for server logs using head/tail/less/wc patterns, with a follow mode and quick counts — the week-2 log-reading toolkit.",
    deliverables: [
      "linux-lab/scripts/logview.py: head/tail/follow/count modes over a log path",
      "Safe handling of large and rotating files"
    ],
    reference: "Teached ders02 less/head/tail/wc",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/log-viewer-helper"
  },
  {
    id: "OS-30",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Ubuntu Server Hardening Checker / Applier",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Checks SSH config, user accounts, pending updates and ufw status against a hardening baseline and applies fixes on approval — the week-6 \"hardened Ubuntu from scratch\" candidate.",
    deliverables: [
      "linux-lab/scripts/harden_check.py: SSH / users / updates / ufw baseline audit → report",
      "Approval-gated apply with documented changes"
    ],
    reference: "Teached vize adayı: sıfırdan sertleştirilmiş Ubuntu Server",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/ubuntu-hardening-checker"
  },
  {
    id: "OS-31",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "journald Structured Logging & Log-Rotation Setup",
    priority: "Medium",
    effort: "Small",
    summary:
      "Configures journald persistence and size limits plus a logrotate profile for lab services, so long-running daemons don't fill the disk — complements the service work.",
    deliverables: [
      "linux-lab/scripts/setup_journald.sh: persistent journald + size limits + logrotate profile",
      "Verification of rotation and retention"
    ],
    reference: "Teached 26.10 servisler, loglar; 05.10 disk yönetimi",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/journald-logging-setup"
  },
  {
    id: "OS-32",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Service Inventory & Health Report (systemctl)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Read-only inventory of systemd units with active/enabled state and recent failures, rendered as a report — the week-6 \"always-on / start-at-boot service\" concept.",
    deliverables: [
      "linux-lab/scripts/service_inventory.py: systemctl list-units + failed + enabled → JSON/report",
      "Highlight of failed or flapping services"
    ],
    reference: "Teached 12.10/26.10 systemctl status, servis kavramı",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/service-inventory"
  },
  {
    id: "OS-33",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "VirtualBox Snapshot / Restore Automation for Lab VMs",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Wraps VBoxManage snapshot take/list/restore so students can checkpoint a working VM before risky steps and roll back instantly — the snapshot practice from week 2.",
    deliverables: [
      "win-lab/scripts/vm_snapshot.(ps1|py): take / list / restore named snapshots",
      "Optional pre-change auto-snapshot hook"
    ],
    reference: "Teached ders02 güncelleme + snapshot",
    targetPaths: ["win-lab/scripts/"],
    suggestedBranch: "feat/vm-snapshot-automation"
  },
  {
    id: "OS-34",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Bridged vs NAT Network Adapter Configurator & Checker",
    priority: "Medium",
    effort: "Small",
    summary:
      "Checks and sets a VM's adapter mode and verifies the guest gets a reachable LAN IP (bridged) — the recurring requirement behind students' SSH failures.",
    deliverables: [
      "win-lab/scripts/net_adapter.(ps1|py): read/set adapter mode + verify reachable IP",
      "Explains when bridged vs NAT is needed for lab SSH"
    ],
    reference: "Teached 12.10 bridged adaptör gerekliliği, aynı ağ/IP",
    targetPaths: ["win-lab/scripts/"],
    suggestedBranch: "feat/vm-net-adapter"
  },
  {
    id: "OS-35",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Browser-Extension Injection Detector (Static: sha256sum / unzip / jq / rg)",
    priority: "Medium",
    effort: "Small",
    summary:
      "The simpler, OS-course version (week 6): unzip an extension, hash it, parse the manifest with jq and grep sinks with ripgrep, producing a clue-level H1–H5 report — detector, evidence collector and risk rule kept distinct.",
    deliverables: [
      "linux-lab/scripts/ext_detect.sh: sha256sum / unzip / jq / rg pipeline → H1–H5 clue report",
      "Clear separation of detector, evidence collector and risk rule"
    ],
    reference: "Teached MYO203 ders06 eklenti tespiti; kaynak iExtensionCrawler injection-steps",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/os-extension-detector"
  },
  {
    id: "OS-36",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Classroom Server Reachability Checker (ping + SSH sweep)",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Sweeps the class subnet (e.g. 10.25.130.x), confirms each student's server is up and SSH-reachable, and lists who's offline — the check the instructor ran before Remote-SSH.",
    deliverables: [
      "linux-lab/scripts/class_reachability.py: subnet ping + SSH-port sweep → up/down table",
      "Optional IP → student mapping from a roster file (kept local, never committed)"
    ],
    reference: "Teached 26.10 ping ile 10.25.130.x doğrulama, üç öğrencinin sunucusu",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/class-reachability"
  },
  {
    id: "OS-37",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "DNS Resolver Inventory & Health Check",
    priority: "High",
    effort: "Small",
    summary:
      "Reads how the server resolves names — resolvectl status, /etc/resolv.conf, the systemd stub (127.0.0.53), and per-interface DNS — and flags the broken state where an interface has no usable resolver, the exact fault found live on 02.11.",
    deliverables: [
      "linux-lab/scripts/dns_health.py: resolvectl/resolv.conf parse → per-interface resolver table as JSON + readable report",
      "Flags: no nameserver set, stub-only, and DHCP-provided vs manual DNS",
      "Clear 'why no internet on Wi-Fi but fine on cable' explanation when the pattern matches"
    ],
    reference: "Teached 02.11 DNS çözümleme, resolvectl, 127.0.0.53 stub",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/dns-health"
  },
  {
    id: "OS-38",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Multi-Resolver nslookup/dig Comparator",
    priority: "High",
    effort: "Small",
    summary:
      "Queries one or more names against several DNS servers (campus, 8.8.8.8 Google, 1.1.1.1 Cloudflare), compares the answers and measures latency over N tries — the exact 02.11 homework, as a repeatable tool instead of by hand.",
    deliverables: [
      "linux-lab/scripts/dns_compare.py: query google.com / istinye.edu.tr / ois.istinye.edu.tr against a resolver list",
      "Per-resolver answer set + min/median/max latency over N tries, written to a report (md/HTML)",
      "Notes when a resolver returns internal vs external records (split-horizon)"
    ],
    reference: "Teached 02.11 nslookup, istinye/8.8.8.8/1.1.1.1 karşılaştırma + hız",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/dns-compare"
  },
  {
    id: "OS-39",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "netplan DNS Configurator (approval-gated)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Sets a persistent DNS server on an Ubuntu Server by editing /etc/netplan/*.yaml (e.g. 50-cloud-init.yaml), then netplan try/apply and verifies resolution — with the change shown and approved before it is written.",
    deliverables: [
      "linux-lab/scripts/netplan_dns.py: show current nameservers, propose a diff, apply on approval, verify with a test query",
      "Supports a fallback list (e.g. 1.1.1.1 then 8.8.8.8) and static vs DHCP interfaces",
      "Refuses to apply if it would break the active SSH session's resolution"
    ],
    reference: "Teached 02.11 /etc/netplan/*.yaml, sudo nano, kalıcı DNS",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/netplan-dns"
  },
  {
    id: "OS-40",
    category: "os",
    categoryLabel: "Open Source OS",
    title: "Wi-Fi / Interface DNS Troubleshooter",
    priority: "High",
    effort: "Small",
    summary:
      "Reproduces and fixes the 02.11 live fault: a Wi-Fi profile that rejects DHCP-provided DNS with none set manually, so names resolve on cable but not on Wi-Fi. Diagnoses the interface, explains the cause, and offers the nmcli fix.",
    deliverables: [
      "linux-lab/scripts/dns_troubleshoot.py: detect interface (eth/wlan), check ignore-auto-dns, compare cable vs Wi-Fi resolution",
      "Suggested fix: nmcli connection modify <con> ipv4.ignore-auto-dns no (shown, applied only on approval)",
      "DNS cache note (flush / Ctrl+Shift+R) and a short AP/router/switch primer in the report"
    ],
    reference: "Teached 02.11 ignore-auto-dns, DHCP vs manuel, AP/router/switch",
    targetPaths: ["linux-lab/scripts/"],
    suggestedBranch: "feat/dns-troubleshoot"
  },

  // --- Firewall Solutions (BGT207) continued ---
  {
    id: "FW-07",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW Application Profiles Manager",
    priority: "Medium",
    effort: "Small",
    summary:
      "Lists, creates and applies UFW application profiles (/etc/ufw/applications.d) so services are allowed by name, with validation — the application-profiles topic from week 3.",
    deliverables: [
      "scripts/firewall/ufw_app_profiles.py: list / create / apply profiles with port + protocol validation",
      "Report mapping each enabled profile to its underlying rules"
    ],
    reference: "Teached 09.10 uygulama profilleri",
    targetPaths: ["scripts/firewall/", "linux-lab/"],
    suggestedBranch: "feat/ufw-app-profiles"
  },
  {
    id: "FW-08",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "before.rules ICMP Policy & hashlimit Rate-Limit Generator",
    priority: "Medium",
    effort: "Small–Medium",
    summary:
      "Generates correct before.rules fragments for ICMP handling and connection rate-limiting (hashlimit), avoiding the archived guide's non-working commands flagged in the deck notes.",
    deliverables: [
      "scripts/firewall/before_rules_gen.py: ICMP + hashlimit fragments validated on a lab VM",
      "Guard rejecting the known-invalid `ufw route ... limit in rate` / `ufw append` forms"
    ],
    reference: "Teached ders02 before.rules (ICMP, hız sınırı); slides-index düzeltmesi",
    targetPaths: ["scripts/firewall/", "linux-lab/"],
    suggestedBranch: "feat/before-rules-generator"
  },
  {
    id: "FW-09",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "nmap-Based Firewall Rule Verification Harness",
    priority: "High",
    effort: "Small",
    summary:
      "Runs nmap from the client VM against the server VM to prove each rule's effect (open/filtered/closed) and diffs observed state against the intended policy — the external-test step.",
    deliverables: [
      "scripts/firewall/nmap_verify.py: scan srv from cli and compare to intended policy → pass/fail",
      "Report of unexpected open / filtered ports"
    ],
    reference: "Teached ders02/09.10 nmap ile test, dışarıdan test",
    targetPaths: ["scripts/firewall/", "linux-lab/"],
    suggestedBranch: "feat/nmap-rule-verify"
  },
  {
    id: "FW-10",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Stateful vs Stateless Rule Explainer & Validator",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Classifies a rule set's stateful/stateless behavior, explains established/related handling, and flags rules that assume state where none exists — the week-1 concept as a checker.",
    deliverables: [
      "scripts/firewall/state_check.py: classify rules + flag stateful assumptions",
      "Teaching output explaining each classification"
    ],
    reference: "Teached 25.09 stateful vs stateless, kuralın anatomisi",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/stateful-explainer"
  },
  {
    id: "FW-11",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW Enable Safety Guard (SSH-Before-Enable)",
    priority: "High",
    effort: "Tiny–Small",
    summary:
      "Refuses to enable UFW unless an allow rule for the current SSH session's port/source exists, preventing the classic remote lockout taught as a hard rule.",
    deliverables: [
      "scripts/firewall/safe_enable.py: preflight asserting an SSH allow rule before `ufw enable`",
      "Detects the active SSH port/source automatically"
    ],
    reference: "Teached ders03 UFW'yi açmadan önce SSH'ye izin ver",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/ufw-safe-enable"
  },
  {
    id: "FW-12",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW Log-Level Configurator & [UFW BLOCK] Parser",
    priority: "Medium",
    effort: "Small",
    summary:
      "Sets the taught log levels (off/low/medium/high/full) and parses [UFW BLOCK] lines into structured events for downstream alerting.",
    deliverables: [
      "scripts/firewall/ufw_logging.py: set level + tail/parse ufw.log into JSON events",
      "Field extraction (src, dst, proto, port, action)"
    ],
    reference: "Teached ders02 log seviyeleri, [UFW BLOCK] okuma, tail -f /var/log/ufw.log",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/ufw-log-levels"
  },
  {
    id: "FW-13",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Service Port Exposure Limiter (MySQL 3306 → App Subnet Only)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Generates allow-from rules binding a service port to a specific source subnet (e.g. MySQL 3306 only from the app tier) and verifies it's unreachable elsewhere — the week-3 scenario.",
    deliverables: [
      "scripts/firewall/port_limit.py: `allow from <subnet> to <port>` generator + reachability check",
      "Refuses to expose management / DB ports to 0.0.0.0/0"
    ],
    reference: "Teached 09.10 MySQL + 3306 yalnız uygulamaya, allow from",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/service-port-limiter"
  },
  {
    id: "FW-14",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Serverless UFW Alert via Cloudflare Workers",
    priority: "Medium",
    effort: "Small",
    summary:
      "A serverless webhook (Cloudflare Workers) that receives block events and notifies without running a bot on the server — the serverless-bot approach shown in week 3.",
    deliverables: [
      "scripts/firewall/worker/: Cloudflare Worker receiving block events + forwarding alerts",
      "Server-side poster sending only block events to the worker"
    ],
    reference: "Teached 09.10 sunucusuz Telegram botu (Cloudflare Workers)",
    targetPaths: ["scripts/firewall/worker/"],
    suggestedBranch: "feat/serverless-ufw-alert"
  },
  {
    id: "FW-15",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Rule-Order Simulator & Latency Estimator Under Load",
    priority: "Medium",
    effort: "Small–Medium",
    summary:
      "Simulates first-match evaluation over a rule set and estimates match cost under heavy / DDoS-like traffic, recommending a reordering that puts high-hit rules first.",
    deliverables: [
      "scripts/firewall/order_sim.py: first-match simulator + per-rule hit cost + reorder suggestion",
      "Before/after estimated-latency report"
    ],
    reference: "Teached 09.10 ilk eşleşen kazanır, sıra performansı etkiler, DDoS altında",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/rule-order-simulator"
  },
  {
    id: "FW-16",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Duplicate & Shadowed Rule Detector (status numbered)",
    priority: "High",
    effort: "Small",
    summary:
      "Parses `ufw status numbered` and flags shadowed, duplicate, over-broad and wrongly-ordered rules, plus a missing SSH-before-enable — the rule-set auditor.",
    deliverables: [
      "scripts/firewall/rule_audit.py: shadow / duplicate / over-broad / order findings with line refs",
      "Markdown report with a suggested corrected order"
    ],
    reference: "Teached 09.10 kural sırası, status numbered",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/ufw-shadow-detector"
  },
  {
    id: "FW-17",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW Log Analyzer: Top Blocked Sources, Ports & Scan Detection",
    priority: "High",
    effort: "Small",
    summary:
      "Summarizes /var/log/ufw.log into top blocked sources/ports, detects port-scan patterns and gives a rate summary.",
    deliverables: [
      "scripts/firewall/log_summary.py: aggregate blocked src/port + scan detection + rate summary",
      "Time-bucketed JSON for the dashboard"
    ],
    reference: "Teached ders02/09.10 ufw.log",
    targetPaths: ["scripts/firewall/", "dashboard/src/views/jobs-page.tsx"],
    suggestedBranch: "feat/ufw-log-analyzer"
  },
  {
    id: "FW-18",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Reject-vs-Deny Scanner-Exposure Tester",
    priority: "Medium",
    effort: "Small",
    summary:
      "Sets up both deny and reject rules in the lab and compares how each appears to an nmap scan (silent drop vs ICMP unreachable), teaching why reject reveals the firewall.",
    deliverables: [
      "scripts/firewall/reject_vs_deny.py: apply both, scan, and tabulate scanner-visible differences",
      "Teaching report on exposure trade-offs"
    ],
    reference: "Teached 09.10 deny sessiz, reject yanıt verir",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/reject-vs-deny-tester"
  },
  {
    id: "FW-19",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Notification-Storm Regression Harness (Loop Suppression)",
    priority: "High",
    effort: "Small",
    summary:
      "Reproduces the 09.10 incident in a lab and asserts the notifier suppresses outbound ALLOW and 53/udp DNS traffic and dedupes/rate-limits, so the storm can't recur — a test harness for FW-02.",
    deliverables: [
      "scripts/firewall/tests/test_storm_suppression.py: feeds synthetic ufw.log, asserts no storm",
      "Fixtures covering outbound ALLOW and DNS-loop lines"
    ],
    reference: "Teached 09.10 bildirim fırtınası (giden ALLOW + 53/udp), block-only çözüm",
    targetPaths: ["scripts/firewall/tests/"],
    suggestedBranch: "feat/storm-regression-harness"
  },
  {
    id: "FW-20",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Subnet & Bandwidth Planner (Users × Services → CIDR + Estimate)",
    priority: "High",
    effort: "Medium",
    summary:
      "Takes per-branch user/device counts and a service mix (Zoom, VoIP, ERP, email, git, CI/CD, web, cloud) and outputs a CIDR plan and bandwidth estimate — the week-5 homework core.",
    deliverables: [
      "scripts/firewall/net_planner.py: counts + services → CIDR allocation + per-branch bandwidth estimate",
      "Explains /24 vs /17 sizing for device density"
    ],
    reference: "Teached 23.10 /24 /17, kişi×cihaz, bant genişliği",
    targetPaths: ["scripts/firewall/", "docs/network/"],
    suggestedBranch: "feat/subnet-bandwidth-planner"
  },
  {
    id: "FW-21",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Multi-Branch Company Repo Scaffolder (HQ / Branch / Academic / DMZ)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Generates the week-5 homework skeleton: per-branch folders (Ankara / İstanbul / Londra + 10 000-student academic branch) with placeholders for counts, bandwidth, product shortlist and rule sets.",
    deliverables: [
      "scripts/firewall/company_scaffold.py: branch folders + README templates per the assignment",
      "Per-branch stubs for staff / student / R&D / software counts"
    ],
    reference: "Teached 23.10 çok şubeli firma senaryosu, her şube için klasör",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/company-repo-scaffold"
  },
  {
    id: "FW-22",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "VLAN Segmentation Rule-Set Generator (Staff / Student / R&D / Software)",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Produces per-VLAN rule sets giving each team its own policy and inter-VLAN restrictions, from a simple segment spec — the segmentation taught in week 5.",
    deliverables: [
      "scripts/firewall/vlan_rules.py: segment spec → per-VLAN UFW/nftables rules + inter-VLAN matrix",
      "Default-deny between segments with explicit allows"
    ],
    reference: "Teached 23.10 VLAN ve bölütleme, ayrı kural seti",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/vlan-ruleset-generator"
  },
  {
    id: "FW-23",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "DMZ Boundary Policy Generator & Validator",
    priority: "Medium",
    effort: "Small",
    summary:
      "Generates DMZ-to-internal and internet-to-DMZ rules and validates that internal services aren't reachable from the DMZ except through defined paths.",
    deliverables: [
      "scripts/firewall/dmz_policy.py: DMZ boundary rule generator + reachability validation",
      "Flags any internal exposure leaking through the DMZ"
    ],
    reference: "Teached 25.09/23.10 DMZ ayrımı",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/dmz-policy-generator"
  },
  {
    id: "FW-24",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Base-Service Rule Templates (NTP 123, DHCP 67/68) with Lockout Prevention",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Emits the essential infrastructure rules so a locked-down host still gets DHCP/NTP, codifying the \"deny everything and you also kill DHCP\" warning.",
    deliverables: [
      "scripts/firewall/base_services.py: NTP / DHCP / DNS templates with lockout-prevention checks",
      "Warning when a default-deny policy would break address assignment"
    ],
    reference: "Teached 23.10 NTP 123, DHCP 67/68, DNS 53; DHCP kilitlenmesi",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/base-service-rules"
  },
  {
    id: "FW-25",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Private-IP (RFC 1918) Range Validator & Misconfig Flag",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Validates that internal rules reference only private ranges (10/8, 172.16/12, 192.168/16) and flags accidental public-range allows — the 10./172./192. reminder.",
    deliverables: [
      "scripts/firewall/rfc1918_check.py: classify rule sources/dests + flag public ranges in internal rules",
      "Report of any internal rule exposed to public space"
    ],
    reference: "Teached 09.10 özel IP blokları 10./172./192.",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/rfc1918-validator"
  },
  {
    id: "FW-26",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Firewall Product Comparison & Segment Selector",
    priority: "Medium",
    effort: "Medium",
    summary:
      "A curated dataset and selector for the week-5 deliverable: top-5 products per segment (FortiGate, pfSense, OPNsense, Sophos, local vendors) with bandwidth fit and real-license vs trial notes.",
    deliverables: [
      "scripts/firewall/product_select.py: segment + bandwidth → top-5 recommendation with rationale",
      "Dataset with license model and price tier (real license, not trial)"
    ],
    reference: "Teached 23.10 her parça için en iyi 5 ürün, FortiGate/pfSense/OPNsense/Sophos",
    targetPaths: ["scripts/firewall/", "docs/network/"],
    suggestedBranch: "feat/firewall-product-selector"
  },
  {
    id: "FW-27",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "pfSense / OPNsense Rule Export & Cross-Translation from UFW",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "pfSense/OPNsense appliance lab",
    summary:
      "Translates a UFW rule set into pfSense/OPNsense equivalents (and back), so the same policy can be validated across the appliances compared in class.",
    deliverables: [
      "scripts/firewall/appliance_translate.py: UFW ↔ pfSense/OPNsense rule mapping with caveats",
      "Diff report of rules that don't translate cleanly"
    ],
    reference: "Teached 09.10/23.10 aynı mantık pfSense/FortiGate; ürün karşılaştırması",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/appliance-rule-translate"
  },
  {
    id: "FW-28",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Attack-Surface Analyzer: VPN vs Exposed-Port Posture",
    priority: "Medium",
    effort: "Small",
    summary:
      "Enumerates publicly-exposed ports/services on a lab host and scores the reduction achieved by moving remote access behind a role-based VPN — quantifying the week-5 VPN argument.",
    deliverables: [
      "scripts/firewall/attack_surface.py: exposed-service enumeration + VPN-behind scoring",
      "Before/after exposure report"
    ],
    reference: "Teached 23.10 SSH yerine rol bazlı VPN, uzaktan erişim",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/attack-surface-analyzer"
  },
  {
    id: "FW-29",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Firewall Monitoring Plan Generator (Human + Systematic)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Produces the week-5 monitoring deliverable: where alerts land, who watches them, the human on-call vs systematic/automated split, and application- vs security-monitoring separation.",
    deliverables: [
      "scripts/firewall/monitoring_plan.py: template → monitoring plan (routing, ownership, human/auto split)",
      "Separates application monitoring from security monitoring"
    ],
    reference: "Teached 23.10 izleme: kim bakar, insani vs sistematik, uygulama vs güvenlik",
    targetPaths: ["scripts/firewall/", "docs/network/"],
    suggestedBranch: "feat/monitoring-plan-generator"
  },
  {
    id: "FW-30",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Branch Firewall Generator from Company Spec (Why-Per-Rule)",
    priority: "Medium",
    effort: "Large",
    prerequisite: "Rule-set lecture (BGT207, planned — kural setleri sonra)",
    summary:
      "Turns a company spec (branches, VLANs, subnets, services) into a full UFW/nftables rule set with a justification for every rule, requiring approval before any apply.",
    deliverables: [
      "scripts/firewall/branch_fw_gen.py: spec → rule set with a per-rule rationale",
      "needsApproval gate before applying any generated rule"
    ],
    reference: "Teached 23.10 kural setleri sonra oluşturulacak",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/branch-firewall-generator"
  },
  {
    id: "FW-31",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "UFW → nftables Equivalent Generator",
    priority: "Medium",
    effort: "Small–Medium",
    summary:
      "Emits the nftables ruleset equivalent to a given UFW policy, so students see the lower-level representation and can run either backend in the lab.",
    deliverables: [
      "scripts/firewall/ufw_to_nft.py: UFW policy → nft ruleset with comments",
      "Lab verification that both backends produce the same scan result"
    ],
    reference: "Teached 23.10/09.10 UFW/nftables, aynı mantık farklı ürün",
    targetPaths: ["scripts/firewall/", "linux-lab/"],
    suggestedBranch: "feat/ufw-to-nftables"
  },
  {
    id: "FW-32",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Vulnerable-PHP Lab + Virtual-Patch Verification (ModSecurity)",
    priority: "Medium",
    effort: "Medium",
    prerequisite: "ModSecurity/WAF lecture (BGT207, planned)",
    summary:
      "A lab PHP target reproducing the week-5 application-layer RCE class, plus a check that a ModSecurity/CRS virtual patch blocks the exploit path while the real fix (upgrade) is pending.",
    deliverables: [
      "linux-lab/waf/php-target/: intentionally vulnerable PHP app (lab only)",
      "virtual_patch_check.py asserting the CRS rule blocks the exploit path"
    ],
    reference: "Teached 23.10 PHP RCE, WAF/ModSecurity",
    targetPaths: ["linux-lab/waf/", "linux-lab/docker-compose.yml"],
    suggestedBranch: "feat/vuln-php-virtual-patch"
  },
  {
    id: "FW-33",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "L3/L4 vs L7 Demonstration: Why Network Firewalls Miss App Attacks",
    priority: "Medium",
    effort: "Small–Medium",
    prerequisite: "WAF lecture (BGT207, planned)",
    summary:
      "A side-by-side lab showing an application-layer attack passing an L3/L4 firewall but caught by an L7 WAF — making concrete the week-5 point that regex/CDN alone can't see a memory-limit attack.",
    deliverables: [
      "linux-lab/waf/l3l4_vs_l7/: compose demo routing the same attack through UFW-only vs WAF",
      "Report contrasting what each layer sees and blocks"
    ],
    reference: "Teached 23.10 açık uygulama katmanında; normal güvenlik duvarı yetmez; CDN/regex sınırı",
    targetPaths: ["linux-lab/waf/"],
    suggestedBranch: "feat/l3l4-vs-l7-demo"
  },
  {
    id: "FW-34",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "CVE / Advisory Watcher with Version-Affected Check",
    priority: "Medium",
    effort: "Small",
    summary:
      "Watches for new advisories affecting the stack a branch runs and checks the server's installed versions against affected ranges — the weekly-advisory tracking worth extra credit.",
    deliverables: [
      "scripts/firewall/cve_watch.py: advisory feed + installed-version affected check → alerts",
      "Per-service exposure report (am I affected?)"
    ],
    reference: "Teached 23.10 haftanın kritik açıkları, güncel açık takibi ek puan",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/cve-watcher"
  },
  {
    id: "FW-35",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Patch vs Mitigation Decision Assistant",
    priority: "Medium",
    effort: "Tiny–Small",
    summary:
      "Given an advisory and the server's state, separates a temporary mitigation from the real fix (apt upgrade) and recommends an ordered action plan — the week-5 incident lesson.",
    deliverables: [
      "scripts/firewall/patch_decide.py: advisory + state → temporary vs permanent action plan",
      "Checklist: assess impact, check version, mitigate, patch"
    ],
    reference: "Teached 23.10 geçici önlem vs kalıcı çözüm, asıl çözüm yama",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/patch-mitigation-assistant"
  },
  {
    id: "FW-36",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "Trusted apt Source Adder & Verifier (When the Distro Lags)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Safely adds a vetted third-party repo (e.g. for a newer PHP) with GPG key verification and apt pinning, for when the distro's packages lag behind — the discussion from the PHP incident.",
    deliverables: [
      "scripts/firewall/trusted_source.py: add repo + verify GPG key + apt pin with reachability check",
      "Refuses unsigned sources; records why the source was added"
    ],
    reference: "Teached 23.10 güvenilir ek kaynak, en güncel sürüm PHP 8.5",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/trusted-apt-source"
  },
  {
    id: "FW-37",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "KVKK / Cookie / Privacy-Text Compliance Checker",
    priority: "Medium",
    effort: "Small",
    summary:
      "Checks a branch's web presence (lab / allowlisted hosts) for required KVKK, cookie and privacy notices and flags missing or broken policy pages — the compliance gap raised in week 5.",
    deliverables: [
      "scripts/firewall/kvkk_check.py: fetch allowlisted pages + detect missing KVKK/cookie/privacy texts",
      "Report of missing or stale policy pages"
    ],
    reference: "Teached 23.10 KVKK, çerez, gizlilik metni eksikleri",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/kvkk-compliance-checker"
  },
  {
    id: "FW-38",
    category: "firewall",
    categoryLabel: "Firewall Solutions",
    title: "\"Explain-Your-Rule\" Audit (Unexplained Rule = Vulnerability)",
    priority: "Medium",
    effort: "Small",
    summary:
      "Requires a one-line justification for every rule and flags any rule the author can't explain, encoding the instructor's principle that an unexplainable rule is itself a weakness.",
    deliverables: [
      "scripts/firewall/explain_audit.py: rule set + justifications file → flags unexplained/undocumented rules",
      "Blocks sign-off until every rule has a rationale"
    ],
    reference: "Teached 23.10 açıklamasını yapamadığın kural zafiyettir",
    targetPaths: ["scripts/firewall/"],
    suggestedBranch: "feat/explain-your-rule-audit"
  }
];

/**
 * Task reservations. Each claimed task is one file at repo-root
 * `reservations/<TASK-ID>.json` (see reservations/README.md). A contributor
 * reserves a task by opening a PR that adds their file; this reads them all at
 * build time and the cards show Available / Reserved / PR open / Done.
 */
export type ReservationStatus = "reserved" | "in-progress" | "pr-open" | "done" | "released";

export interface Reservation {
  id: string;
  name?: string;
  github?: string;
  course?: string;
  note?: string;
  status: ReservationStatus;
  pr?: string;
  date?: string;
}

const RESERVATION_FILES = import.meta.glob<{ default: Reservation }>(
  "../../../reservations/*.json",
  { eager: true }
);

const TASK_IDS = new Set(CURATED_TASKS.map((t) => t.id));

/** id -> active reservation (released/unknown ids dropped; latest date wins on duplicates). */
export const RESERVATIONS: Record<string, Reservation> = (() => {
  const map: Record<string, Reservation> = {};
  for (const path in RESERVATION_FILES) {
    const base = path.split("/").pop() ?? "";
    if (base.startsWith("_")) continue; // _schema.json and other underscore files
    const r = RESERVATION_FILES[path]?.default;
    if (!r || typeof r.id !== "string" || !TASK_IDS.has(r.id)) continue;
    if (r.status === "released") continue;
    const prev = map[r.id];
    if (!prev || (r.date ?? "") >= (prev.date ?? "")) map[r.id] = r;
  }
  return map;
})();

/** GitHub "new file" editor, pre-filled, so a reserve click becomes a PR (auto-forks for non-collaborators). */
function reserveViaPrUrl(id: string): string {
  const today = new Date().toISOString().slice(0, 10);
  const template = `${JSON.stringify(
    { id, name: "", github: "", status: "reserved", pr: "", date: today },
    null,
    2
  )}\n`;
  return (
    "https://github.com/keyvanarasteh/os-lab/new/master" +
    `?filename=reservations/${id}.json` +
    `&value=${encodeURIComponent(template)}` +
    `&message=${encodeURIComponent(`reserve: ${id}`)}`
  );
}

export default function ContributePage({ html }: { html: string }) {
  const [activeTab, setActiveTab] = useState<"guide" | "todos">("guide");
  const [selectedCategory, setSelectedCategory] = useState<TaskCategory>("all");
  const [selectedPriority, setSelectedPriority] = useState<TaskPriority>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<"all" | "available" | "reserved" | "done">("all");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copyError, setCopyError] = useState(false);
  const [copyFallbackText, setCopyFallbackText] = useState("");
  const [copyPendingId, setCopyPendingId] = useState<string | null>(null);

  // Sync hash on initial mount and when hash changes
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash.toLowerCase();
      if (hash === "#todos" || hash === "#roadmap" || hash === "#tasks") {
        setActiveTab("todos");
      } else if (hash === "#guide") {
        setActiveTab("guide");
      }
    };
    handleHash();
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);

  const handleTabSwitch = (tab: "guide" | "todos") => {
    setActiveTab(tab);
    const newHash = tab === "todos" ? "#todos" : "#guide";
    if (window.location.hash !== newHash) {
      window.history.replaceState(null, "", newHash);
    }
  };

  const filteredTasks = useMemo(() => {
    return CURATED_TASKS.filter((task) => {
      if (selectedCategory !== "all" && task.category !== selectedCategory) {
        return false;
      }
      if (selectedPriority !== "all" && task.priority.toLowerCase() !== selectedPriority) {
        return false;
      }
      if (selectedStatus !== "all") {
        const res = RESERVATIONS[task.id];
        if (selectedStatus === "available" && res) return false;
        if (selectedStatus === "reserved" && !(res && res.status !== "done")) return false;
        if (selectedStatus === "done" && res?.status !== "done") return false;
      }
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const res = RESERVATIONS[task.id];
      return (
        task.id.toLowerCase().includes(q) ||
        task.title.toLowerCase().includes(q) ||
        task.summary.toLowerCase().includes(q) ||
        task.reference.toLowerCase().includes(q) ||
        task.targetPaths.some((p) => p.toLowerCase().includes(q)) ||
        task.deliverables.some((d) => d.toLowerCase().includes(q)) ||
        (task.prerequisite?.toLowerCase().includes(q) ?? false) ||
        ("held".includes(q) && !!task.prerequisite) ||
        (res?.github?.toLowerCase().includes(q) ?? false) ||
        (res?.name?.toLowerCase().includes(q) ?? false) ||
        (("reserved".includes(q) || "taken".includes(q)) && !!res)
      );
    });
  }, [selectedCategory, selectedPriority, selectedStatus, searchQuery]);

  const categoryCounts = useMemo(() => {
    return {
      all: CURATED_TASKS.length,
      pentest: CURATED_TASKS.filter((t) => t.category === "pentest").length,
      os: CURATED_TASKS.filter((t) => t.category === "os").length,
      firewall: CURATED_TASKS.filter((t) => t.category === "firewall").length
    };
  }, []);

  const heldCount = useMemo(() => CURATED_TASKS.filter((t) => t.prerequisite).length, []);

  const reservationCounts = useMemo(() => {
    const values = Object.values(RESERVATIONS);
    const done = values.filter((r) => r.status === "done").length;
    const reserved = values.length - done;
    return { reserved, done, available: CURATED_TASKS.length - values.length };
  }, []);

  const copyToClipboard = async (text: string, id: string) => {
    if (copyPendingId) return;
    setCopiedId(null);
    setCopyError(false);
    setCopyPendingId(id);
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId((curr) => (curr === id ? null : curr)), 2000);
    } catch {
      setCopyFallbackText(text);
      setCopyError(true);
    } finally {
      setCopyPendingId(null);
    }
  };

  return (
    <AppShell activeId="contribute">
      <div className="iux min-h-screen">
        <TopBar title="Contribute" icon={<GitPullRequestIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
          {/* Header navigation tabs */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-(--iux-border) pb-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleTabSwitch("guide")}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
                  activeTab === "guide"
                    ? "bg-[#f36c21] text-white shadow-sm"
                    : "border border-(--iux-border) bg-(--iux-card) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                }`}
              >
                <BookOpenIcon size={16} weight={activeTab === "guide" ? "bold" : "regular"} />
                Contribution Guide
              </button>
              <button
                type="button"
                onClick={() => handleTabSwitch("todos")}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
                  activeTab === "todos"
                    ? "bg-[#f36c21] text-white shadow-sm"
                    : "border border-(--iux-border) bg-(--iux-card) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                }`}
              >
                <ListChecksIcon size={16} weight={activeTab === "todos" ? "bold" : "regular"} />
                Roadmap &amp; TODOs
                <span
                  className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                    activeTab === "todos" ? "bg-white/20 text-white" : "bg-(--iux-muted) text-(--iux-foreground)"
                  }`}
                >
                  {CURATED_TASKS.length}
                </span>
              </button>
            </div>

            <p className="hidden text-xs text-(--iux-muted-foreground) sm:block">
              {activeTab === "guide" ? "Workflow, setup, tests and PR guidelines" : "Classified tasks for pentesting, open-source OS & firewalls"}
            </p>
          </div>

          {activeTab === "guide" ? (
            /* Tab 1: Contribution Guide from CONTRIBUTING.md */
            <div className="space-y-6">
              <article className="legal-doc" lang="en" translate="no" dangerouslySetInnerHTML={{ __html: html }} />
              <p className="border-t border-(--iux-border) pt-4 text-xs text-(--iux-muted-foreground)">
                Source:{" "}
                <a className="underline" href={`${REPO_BLOB}/CONTRIBUTING.md`} target="_blank" rel="noreferrer">
                  CONTRIBUTING.md
                </a>
              </p>
            </div>
          ) : (
            /* Tab 2: Roadmap & Curated TODO List */
            <div className="space-y-6">
              {/* Overview hero banner */}
              <div className="rounded-xl border border-(--iux-border) bg-(--iux-card) p-5 sm:p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-1">
                    <h2 className="text-lg font-bold tracking-tight text-(--iux-foreground)">
                      Curated Contribution Roadmap &amp; Priority TODOs
                    </h2>
                    <p className="text-xs leading-relaxed text-(--iux-muted-foreground) max-w-2xl">
                      Production-ready engineering tasks classified across our core domains:{" "}
                      <strong className="text-(--iux-foreground)">Penetration Testing</strong>,{" "}
                      <strong className="text-(--iux-foreground)">Open Source Operating Systems</strong>, and{" "}
                      <strong className="text-(--iux-foreground)">Firewall Solutions</strong>. These items reflect
                      architectural gaps (local MCP hosting, capability discovery, single-instance execution, release optimization)
                      and live security instrumentation priorities. <strong className="text-(--iux-foreground)">Reserve</strong> a
                      task before you start so two people don&apos;t build the same thing — a reservation is just a PR adding
                      one file under{" "}
                      <a className="underline" href={`${REPO_BLOB}/reservations/README.md`} target="_blank" rel="noreferrer">
                        reservations/
                      </a>.
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <span className="rounded-md border border-(--iux-border) bg-(--iux-muted)/50 px-2.5 py-1 text-xs font-medium text-(--iux-foreground)">
                      {CURATED_TASKS.length} tasks
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                      <LockKeyOpenIcon size={12} weight="bold" />
                      {reservationCounts.available} open
                    </span>
                    {reservationCounts.reserved > 0 ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-[#f36c21]/30 bg-[#f36c21]/10 px-2.5 py-1 text-xs font-medium text-[#f36c21]">
                        <LockKeyIcon size={12} weight="bold" />
                        {reservationCounts.reserved} reserved
                      </span>
                    ) : null}
                    {reservationCounts.done > 0 ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-600 dark:text-blue-400">
                        <SealCheckIcon size={12} weight="bold" />
                        {reservationCounts.done} done
                      </span>
                    ) : null}
                    {heldCount > 0 ? (
                      <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
                        {heldCount} held
                      </span>
                    ) : null}
                  </div>
                </div>

                {/* Metrics badges */}
                <div className="mt-4 grid grid-cols-2 gap-2 border-t border-(--iux-border) pt-4 sm:grid-cols-4">
                  <div className="flex flex-col">
                    <span className="text-[11px] text-(--iux-muted-foreground)">Total Tasks</span>
                    <span className="text-base font-bold text-(--iux-foreground)">{CURATED_TASKS.length}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-(--iux-muted-foreground)">Penetration Testing</span>
                    <span className="text-base font-bold text-amber-500">{categoryCounts.pentest}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-(--iux-muted-foreground)">Open Source OS</span>
                    <span className="text-base font-bold text-blue-500">{categoryCounts.os}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[11px] text-(--iux-muted-foreground)">Firewall Solutions</span>
                    <span className="text-base font-bold text-emerald-500">{categoryCounts.firewall}</span>
                  </div>
                </div>
              </div>

              {/* Filter controls & Search */}
              <div className="flex flex-col gap-3 rounded-lg border border-(--iux-border) bg-(--iux-card) p-3 sm:flex-row sm:items-center sm:justify-between">
                {/* Domain Category Filter Tabs */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setSelectedCategory("all")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      selectedCategory === "all"
                        ? "bg-[#f36c21] text-white"
                        : "bg-(--iux-muted)/60 text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                    }`}
                  >
                    All ({categoryCounts.all})
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedCategory("pentest")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      selectedCategory === "pentest"
                        ? "bg-amber-600 text-white"
                        : "bg-(--iux-muted)/60 text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                    }`}
                  >
                    <CrosshairIcon size={14} />
                    Pentesting ({categoryCounts.pentest})
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedCategory("os")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      selectedCategory === "os"
                        ? "bg-blue-600 text-white"
                        : "bg-(--iux-muted)/60 text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                    }`}
                  >
                    <TerminalWindowIcon size={14} />
                    Open Source OS ({categoryCounts.os})
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedCategory("firewall")}
                    className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      selectedCategory === "firewall"
                        ? "bg-emerald-600 text-white"
                        : "bg-(--iux-muted)/60 text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
                    }`}
                  >
                    <ShieldCheckIcon size={14} />
                    Firewall Solutions ({categoryCounts.firewall})
                  </button>
                </div>

                {/* Priority & Search filter */}
                <div className="flex items-center gap-2">
                  <select
                    value={selectedPriority}
                    onChange={(e) => setSelectedPriority(e.target.value as TaskPriority)}
                    className="rounded-md border border-(--iux-border) bg-(--iux-background) px-2.5 py-1.5 text-xs text-(--iux-foreground) focus:outline-none"
                    aria-label="Filter by priority"
                  >
                    <option value="all">All Priorities</option>
                    <option value="high">High Priority</option>
                    <option value="medium">Medium Priority</option>
                  </select>

                  <select
                    value={selectedStatus}
                    onChange={(e) => setSelectedStatus(e.target.value as typeof selectedStatus)}
                    className="rounded-md border border-(--iux-border) bg-(--iux-background) px-2.5 py-1.5 text-xs text-(--iux-foreground) focus:outline-none"
                    aria-label="Filter by reservation status"
                  >
                    <option value="all">Any status</option>
                    <option value="available">Available</option>
                    <option value="reserved">Reserved</option>
                    <option value="done">Done</option>
                  </select>

                  <div className="relative min-w-[180px] flex-1 sm:w-56">
                    <MagnifyingGlassIcon
                      size={14}
                      className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-(--iux-muted-foreground)"
                    />
                    <input
                      type="text"
                      placeholder="Filter tasks..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full rounded-md border border-(--iux-border) bg-(--iux-background) py-1.5 pl-8 pr-2.5 text-xs text-(--iux-foreground) placeholder:text-(--iux-muted-foreground) focus:outline-none focus:ring-1 focus:ring-[#f36c21]"
                    />
                  </div>
                </div>
              </div>

              {/* Tasks List */}
              {filteredTasks.length === 0 ? (
                <div className="rounded-lg border border-dashed border-(--iux-border) p-8 text-center text-xs text-(--iux-muted-foreground)">
                  No tasks found matching your filter criteria. Try resetting the search or category filters.
                </div>
              ) : (
                <div className="space-y-4">
                  {filteredTasks.map((task) => {
                    const isCopied = copiedId === task.id;
                    const res = RESERVATIONS[task.id];
                    const isDone = res?.status === "done";
                    const who = res?.github ? `@${res.github}` : res?.name || "a contributor";
                    return (
                      <div
                        key={task.id}
                        id={task.id.toLowerCase()}
                        className={`rounded-xl border bg-(--iux-card) p-5 transition-shadow hover:shadow-sm space-y-4 ${
                          res ? "border-(--iux-border)/70" : "border-(--iux-border)"
                        }`}
                      >
                        {/* Task Top Meta */}
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-(--iux-border) pb-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-(--iux-muted) text-(--iux-foreground)">
                              {task.id}
                            </span>
                            <span
                              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                                task.category === "pentest"
                                  ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                                  : task.category === "os"
                                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                                  : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                              }`}
                            >
                              {task.categoryLabel}
                            </span>
                            <span
                              className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                                task.priority === "High"
                                  ? "bg-orange-500/10 text-[#f36c21] border border-orange-500/20 font-semibold"
                                  : "bg-zinc-500/10 text-(--iux-muted-foreground)"
                              }`}
                            >
                              Priority: {task.priority}
                            </span>
                            <span className="text-[11px] text-(--iux-muted-foreground)">
                              Effort: <strong>{task.effort}</strong>
                            </span>
                            {task.prerequisite ? (
                              <span
                                className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                                title={`Held — needs: ${task.prerequisite}`}
                              >
                                Held · needs {task.prerequisite}
                              </span>
                            ) : null}
                            {res ? (
                              <span
                                className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                                  isDone
                                    ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20"
                                    : "bg-[#f36c21]/10 text-[#f36c21] border-[#f36c21]/20"
                                }`}
                                title={
                                  isDone
                                    ? `Done by ${who}`
                                    : `Reserved by ${who}${res.date ? ` on ${res.date}` : ""} (${res.status})`
                                }
                              >
                                {isDone ? <SealCheckIcon size={12} weight="bold" /> : <LockKeyIcon size={12} weight="bold" />}
                                {isDone ? "Done" : res.status === "pr-open" ? "PR open" : "Reserved"}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                                <LockKeyOpenIcon size={12} weight="bold" />
                                Available
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1.5">
                            {res ? (
                              <span className="flex items-center gap-1 rounded border border-(--iux-border) bg-(--iux-muted)/40 px-2 py-1 text-[11px] text-(--iux-muted-foreground)">
                                <UserCircleIcon size={13} weight="duotone" />
                                {res.github ? (
                                  <a
                                    className="font-medium text-(--iux-foreground) hover:underline"
                                    href={`https://github.com/${res.github}`}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    @{res.github}
                                  </a>
                                ) : (
                                  <span className="font-medium text-(--iux-foreground)">{res.name || "reserved"}</span>
                                )}
                                {res.pr ? (
                                  <a
                                    className="ml-1 inline-flex items-center gap-0.5 text-[#f36c21] hover:underline"
                                    href={res.pr}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    PR <ArrowSquareOutIcon size={11} />
                                  </a>
                                ) : null}
                              </span>
                            ) : (
                              <a
                                href={reserveViaPrUrl(task.id)}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 rounded border border-[#f36c21]/40 bg-[#f36c21]/10 px-2 py-1 text-[11px] font-semibold text-[#f36c21] transition-colors hover:bg-[#f36c21] hover:text-white"
                                title="Reserve this task — opens a pre-filled os-lab PR"
                              >
                                <LockKeyIcon size={12} weight="bold" />
                                <span>Reserve via PR</span>
                              </a>
                            )}
                            <button
                              type="button"
                              disabled={copyPendingId !== null}
                              onClick={() => copyToClipboard(`${task.id}: ${task.title}`, task.id)}
                              className="iux-touch-target flex items-center gap-1 rounded border border-(--iux-border) px-2 py-1 text-[11px] text-(--iux-muted-foreground) transition-colors hover:bg-(--iux-muted) hover:text-(--iux-foreground)"
                              title="Copy task reference"
                            >
                              {isCopied ? (
                                <>
                                  <CheckIcon size={12} className="text-emerald-500" weight="bold" />
                                  <span className="text-emerald-500 font-medium">Copied</span>
                                </>
                              ) : (
                                <>
                                  <CopyIcon size={12} />
                                  <span>Copy Reference</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Title & Summary */}
                        <div className="space-y-1.5">
                          <h3 className="text-sm font-semibold text-(--iux-foreground)">
                            {task.title}
                          </h3>
                          <p className="text-xs leading-relaxed text-(--iux-muted-foreground)">
                            {task.summary}
                          </p>
                        </div>

                        {/* Deliverables */}
                        <div className="space-y-1.5 rounded-lg bg-(--iux-muted)/30 p-3">
                          <div className="text-[11px] font-semibold text-(--iux-foreground)">Key Deliverables:</div>
                          <ul className="space-y-1">
                            {task.deliverables.map((deliv, idx) => (
                              <li key={idx} className="flex items-start gap-2 text-xs text-(--iux-muted-foreground)">
                                <CheckCircleIcon size={14} className="shrink-0 text-emerald-500 mt-0.5" weight="fill" />
                                <span>{deliv}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        {/* Footer info: reference, paths, branch suggestion */}
                        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-[11px] text-(--iux-muted-foreground)">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex items-center gap-1 font-medium text-(--iux-foreground)">
                              <TagIcon size={12} className="text-[#f36c21]" />
                              Ref: {task.reference}
                            </span>
                            <span>•</span>
                            <span>
                              Paths: <code className="font-mono text-[10px]">{task.targetPaths.join(", ")}</code>
                            </span>
                          </div>

                          <div className="flex items-center gap-1">
                            <span className="text-[10px] text-(--iux-muted-foreground)">Branch:</span>
                            <button
                              type="button"
                              disabled={copyPendingId !== null}
                              onClick={() => copyToClipboard(`git checkout -b ${task.suggestedBranch}`, `b-${task.id}`)}
                              className="iux-touch-target font-mono text-[10px] text-[#f36c21] hover:underline"
                              title="Copy git checkout branch command"
                            >
                              {copiedId === `b-${task.id}` ? "Copied command!" : `git checkout -b ${task.suggestedBranch}`}
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {copyError ? <div role="alert" className="fixed bottom-4 left-4 right-4 z-50 rounded-lg border border-(--iux-danger) bg-(--iux-card) p-3 text-sm shadow-lg sm:left-auto sm:max-w-md"><p>Clipboard unavailable. Select the text manually.</p><code data-no-translate className="mt-2 block select-text break-all text-xs">{copyFallbackText}</code></div> : null}
        </main>
      </div>
    </AppShell>
  );
}
