/**
 * macOS Lab roadmap (MIR-xx): rich-feature follow-ups for the app mirror introduced in the
 * macos-app-mirror PR. Everything builds on the shipped guardrails — read-only endpoints,
 * preview → confirm by default, armed control mode that disarms itself, localhost-only POSTs —
 * and follows docs/UX_READINESS.md. Permissions (Screen Recording, Accessibility) stay honest
 * in the UI; no task may post input or read windows without saying so.
 */
import type { TodoTask } from "./contribute-page";

type MacLabTask = Omit<TodoTask, "category" | "categoryLabel" | "reference" | "suggestedBranch"> & {
  reference?: string;
};

const tasks: MacLabTask[] = [
  {
    id: "MIR-01",
    title: "Element action menu: double-click, right-click, type, press keys",
    priority: "High",
    effort: "Medium",
    summary:
      "Extend macos-click into a small typed action family (double, right, type, key) driven from the hotspot: a long-press or right-click on a hotspot opens a menu; type goes through a small dialog and never sends Return without an explicit confirm, so composers and forms cannot fire accidentally. All variants run the same preview → confirm → job pipeline and CGEvent posting as the single click.",
    deliverables: [
      "macos-app.sh input family with fixed argv (pid, x, y, kind) and plan() validation per kind",
      "Hotspot menu in the panel; typed text is echoed in the preview before it runs",
      "Control mode keeps the same actions immediate; the audit row records kind and text length",
    ],
    targetPaths: ["ios-lab/mac/", "console/oslab.py", "dashboard/src/views/macos-app-mirror.tsx", "android-lab/lab/web_ui.py"],
  },
  {
    id: "MIR-02",
    title: "Accessibility diff overlay: highlight what changed since the last read",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Cache the previous element tree per window in the console and return added / removed / changed entries alongside the snapshot, so the mirror can ring new hotspots and fade stale ones — the cheap loop that makes long automation sessions readable. No extra permission work: the diff reuses the existing Accessibility read.",
    deliverables: [
      "GET …/elements accepts the previous revision token and returns {added, removed, changed}",
      "Panel renders new hotspots with a ring and removed ones as fading outlines",
      "Diff is bounded (same 150-element cap) and tested on recorded tree snapshots",
    ],
    targetPaths: ["console/oslab.py", "ios-lab/mac/", "dashboard/src/views/macos-app-mirror.tsx"],
  },
  {
    id: "MIR-03",
    title: "Retina and multi-display correctness for the mirror",
    priority: "High",
    effort: "Small–Medium",
    summary:
      "Make captures and hotspots exact on scaled displays: report the backing scale factor per window (CGWindowBounds are points; pixels are 2× on Retina), keep hotspot math in points end to end, and verify windows on secondary displays with negative or offset coordinates. Add a display report to doctor so coordinates can be reasoned about remotely.",
    deliverables: [
      "Scale factor from CGWindowCopyScreenInfo or the capture's pixel size, surfaced with the window record",
      "Hotspots land within a few points of their elements in a scripted two-display check",
      "doctor prints displays with origins, sizes and scale factors",
    ],
    targetPaths: ["console/oslab.py", "ios-lab/mac/", "dashboard/src/views/macos-app-mirror.tsx"],
  },
  {
    id: "MIR-04",
    title: "Streaming mirror: multipart MJPEG instead of the 1.5 s poll",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Replace the screenshot poll with a chunked multipart MJPEG response from the console (stdlib http.server can stream): the panel's <img> points at the stream, frames flow while the tab is visible, and the loop pauses on hidden tabs and when no client is connected. Capture errors degrade to an inline frame message instead of breaking the stream.",
    deliverables: [
      "GET /api/labs/macos/apps/<id>/stream with correct multipart boundaries and no-store headers",
      "Frame rate adapts (fast while pointer is over the mirror, slow otherwise) without extra permission work",
      "Fallback to the existing poll when the stream errors, verified in e2e with a stubbed stream",
    ],
    targetPaths: ["console/oslab.py", "android-lab/lab/web_ui.py", "dashboard/src/views/macos-app-mirror.tsx"],
  },
  {
    id: "MIR-05",
    title: "mac2 deep-inspect mode: robust element ids behind the mirror",
    priority: "Medium",
    effort: "Medium",
    summary:
      "Coordinate clicks break when windows move; Appium mac2 element ids do not. Add a panel mode that opens one mac2 session for the selected app (through the existing Appium install), lists its elements with stable ids, and routes hotspot actions through the session when it is open — falling back to CGEvent coordinates otherwise. The session is shown, closable, and never left dangling.",
    deliverables: [
      "Console session helper: create/find/close by app bundle id, with the pid guard reuse",
      "Hotspot actions carry element ids when a session is open; plans display that in effects",
      "The session closes when the panel hides, the tab unloads or the app quits; tested on mocks",
    ],
    targetPaths: ["console/oslab.py", "ios-lab/mac/", "dashboard/src/views/macos-app-mirror.tsx", "android-lab/lab/web_ui.py"],
  },
  {
    id: "MIR-06",
    title: "Session audit log: downloadable record of frames and actions",
    priority: "Medium",
    effort: "Small–Medium",
    summary:
      "Security reports need reproducibility: while the mirror is open, record one JSON row per action (time, app, window, kind, coordinates or element, previewed vs armed) plus periodic frame thumbnails, and expose a download from the panel. Recording stays local under the lab's artifacts/ folder, never uploaded, and includes the control-mode arm/disarm events.",
    deliverables: [
      "Console-side recorder with a bounded ring buffer and artifacts/ writer",
      "Panel download button producing a single JSON file with embedded base64 thumbnails",
      "The log records preview tokens (not secrets) so each action ties back to its confirmation",
    ],
    targetPaths: ["console/oslab.py", "ios-lab/mac/", "dashboard/src/views/macos-app-mirror.tsx", "android-lab/lab/web_ui.py"],
  },
];

export const MACOS_LAB_TASKS: TodoTask[] = tasks.map((t) => ({
  ...t,
  category: "os",
  categoryLabel: "macOS Lab",
  reference: t.reference ?? "lat.md/ios-lab.md",
  deliverables: [
    ...t.deliverables,
    "VERIFY.md entry with commands and output; mirror screenshots taken by script for UI changes",
  ],
  suggestedBranch: `feat/${t.id.toLowerCase()}`,
}));
