/** Open bonus contributions; native/live acceptance is not claimed as complete. */
import type { TodoTask } from "./contribute-page";

export const SOURCE_BONUS_TASKS: TodoTask[] = [
  {
    "id": "SRC-B01",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: native Source installation",
    "priority": "High",
    "effort": "Medium",
    "summary": "Verify fresh installs, updates and private state on macOS and Windows.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "scripts/setup/",
      "app/src-tauri/src/runtime.rs"
    ],
    "suggestedBranch": "feat/source-bonus-01"
  },
  {
    "id": "SRC-B02",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: live browser acceptance",
    "priority": "High",
    "effort": "Medium",
    "summary": "Verify the browser canary on owned targets with real Playwright and Chromium.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "source-lab/engine/source_lab/collectors/browser/",
      "source-lab/COLLECTORS.md"
    ],
    "suggestedBranch": "feat/source-bonus-02"
  },
  {
    "id": "SRC-B03",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: native telemetry workflows",
    "priority": "Medium",
    "effort": "Large",
    "summary": "Add authorized host collection recipes for the four native telemetry importers.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "source-lab/engine/source_lab/collectors/",
      "source-lab/COLLECTORS.md"
    ],
    "suggestedBranch": "feat/source-bonus-03"
  },
  {
    "id": "SRC-B04",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: reproducible Source snapshots",
    "priority": "Medium",
    "effort": "Medium",
    "summary": "Generate Brain and Pipeline snapshots with provenance from owned source trees.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "console/source_pipeline.json",
      "dashboard/src/views/source/",
      "source-lab/BRAIN.md"
    ],
    "suggestedBranch": "feat/source-bonus-04"
  },
  {
    "id": "SRC-B05",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: native process and path checks",
    "priority": "High",
    "effort": "Medium",
    "summary": "Verify cancellation, restart, locks and filesystem protections on native hosts.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "console/source_jobs.py",
      "console/source_worker.py",
      "console/source_control.py"
    ],
    "suggestedBranch": "feat/source-bonus-05"
  },
  {
    "id": "SRC-B06",
    "category": "os",
    "categoryLabel": "Source Lab",
    "title": "Bonus: large workspace browsing",
    "priority": "Medium",
    "effort": "Medium",
    "summary": "Add bounded pagination and summaries for workspaces beyond current read limits.",
    "deliverables": [
      "Document results and required patches in source-lab/VALIDATION.md."
    ],
    "reference": "source-lab/RUNBOOK.md",
    "targetPaths": [
      "console/source_artifacts.py",
      "console/source_overview.py",
      "dashboard/src/views/source/"
    ],
    "suggestedBranch": "feat/source-bonus-06"
  }
];
