"""Cleanup Lab HTTP contracts (``/api/cleanup/...``).

The console accepts typed, validated calls only: never a command string and never
a free-form path list from the page (``cleanup-lab/README.md``). Ready:
readiness (CLN-01), the detector catalog (CLN-02), the scan job (CLN-03) and the
plan → clean flow (CLN-13), audit history (CLN-15), the volume inventory
(CLN-28), the typed privileged actions (CLN-20) and the cache-relocation plans
(CLN-27); the remaining endpoints add
their own actions here, each validated again by the engine's safety guard.

The engine is imported from ``cleanup-lab/engine`` (``cleanup_lab``), which is a
plain standard-library package: the console does not install it.

Long work runs as an in-process console job: ``POST /api/cleanup/scan`` starts a
scan, ``POST /api/cleanup/plan`` builds a plan (guard, measure, fingerprint),
``POST /api/cleanup/clean {planId}`` runs a confirmed plan — each on a worker
thread polled through ``GET /api/cleanup/jobs/<id>`` and cancelled through
``POST /api/cleanup/jobs/<id>/cancel``. The job store keeps the most recent
:data:`MAX_JOBS` jobs; the plan store keeps the most recent :data:`MAX_PLANS`
plans with the fingerprints that expire them. Both live only in this console
process, like the lab jobs: a restart loses them, and nothing is persisted.
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
import time
import uuid

MAX_JOBS = 20
MAX_PLANS = 20
MAX_ENTRY_IDS = 200
#: The only keys a scan request may carry. Paths are deliberately not among
#: them: the scan walks the catalog, never a list the page sends.
SCAN_KEYS = ("entryIds", "workers")
DEEP_KEYS = ("rootIds", "minIdleDays")
#: The only keys a plan request may carry; ``mode`` defaults to ``trash``.
PLAN_KEYS = ("entryIds", "workers", "mode")
#: The only key a clean request may carry: which confirmed plan to run.
CLEAN_KEYS = ("planId",)
CONTAINER_PREVIEW_KEYS = ("actionId",)
CONTAINER_PRUNE_KEYS = ("previewId",)
#: Engine ``PlanError.code`` → HTTP status on the plan → clean namespace.
PLAN_STATUS = {
    "plan-invalid": 400,
    "unknown-plan": 404,
    "expired": 410,
    "stale": 409,
    "used": 409,
    "cancelled": 409,
}
BODY_KEYS = {"scan": SCAN_KEYS, "deep-scan": DEEP_KEYS, "plan": PLAN_KEYS, "clean": CLEAN_KEYS,
             "macos-leftovers": (), "packages": (), "vm-scan": (),
              "container-preview": CONTAINER_PREVIEW_KEYS, "container-prune": CONTAINER_PRUNE_KEYS,
              "privileged-preview": CONTAINER_PREVIEW_KEYS, "privileged-run": CONTAINER_PRUNE_KEYS,
              "relocation-plan": ("action", "entryId", "destination"), "relocation-run": ("previewId",),
              "leftovers": ()}


class CleanupError(ValueError):
    """A request the Cleanup Lab refused, with the HTTP status to answer."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _module(root, name):
    engine = os.path.join(root, "cleanup-lab", "engine")
    if engine not in sys.path:
        sys.path.insert(0, engine)
    try:
        return importlib.import_module("cleanup_lab." + name)
    except ImportError as exc:  # a lone console copy without the engine
        raise CleanupError(501, "The cleanup engine (cleanup-lab/engine) is not installed") from exc


def _query(query):
    """Reject duplicate or unexpected query parameters instead of guessing."""
    if query:
        raise CleanupError(400, "Unexpected query parameters")


def _object_body(body, kind):
    """Every POST body is a JSON object carrying that action's keys and no others."""
    if not isinstance(body, dict):
        raise CleanupError(400, "Expected a JSON object")
    unknown = set(body) - set(BODY_KEYS[kind])
    if unknown:
        raise CleanupError(400, "Unexpected key(s): {0}".format(", ".join(sorted(unknown))))


def _validate_entry_ids(root, catalog, entry_ids, *, required=False):
    """Catalog ids only, unique, known, bounded — never paths, never commands."""
    if entry_ids is None:
        if required:
            raise CleanupError(400, "entryIds is required")
        return None
    if (
        not isinstance(entry_ids, list)
        or not entry_ids
        or any(not isinstance(item, str) or not item for item in entry_ids)
    ):
        raise CleanupError(400, "entryIds must be a list of detector ids")
    if len(set(entry_ids)) != len(entry_ids):
        raise CleanupError(400, "entryIds contains duplicates")
    if len(entry_ids) > MAX_ENTRY_IDS:
        raise CleanupError(400, "Too many detector ids")
    try:
        known = {entry["id"] for entry in catalog.load(root)}
    except catalog.CatalogError as exc:
        raise CleanupError(500, "The detector catalog is invalid: {0}".format(exc)) from exc
    unknown = sorted(set(entry_ids) - known)
    if unknown:
        raise CleanupError(400, "Unknown detector id(s): {0}".format(", ".join(unknown)))
    return entry_ids


def _validate_workers(scan, workers):
    if workers is None:
        return None
    if not isinstance(workers, int) or isinstance(workers, bool):
        raise CleanupError(400, "workers must be a whole number")
    if not 1 <= workers <= scan.MAX_WORKERS:
        raise CleanupError(400, "workers must be between 1 and {0}".format(scan.MAX_WORKERS))
    return workers


class CleanupJob:
    """One running (or finished) cleanup action: a scan, a plan or a clean."""

    def __init__(self, kind, request):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "running"
        self.request = request
        if kind == "clean":
            self.progress = {
                "phase": "queued",
                "itemsDone": 0,
                "itemsTotal": 0,
                "bytesRemoved": 0,
                "currentPath": "",
            }
        else:
            self.progress = {
                "phase": "queued",
                "pathsDone": 0,
                "pathsTotal": 0,
                "bytesSeen": 0,
                "filesSeen": 0,
                "currentPath": "",
            }
        self.result = None
        self.error = None
        self.startedAt = time.time()
        self.finishedAt = None
        self.cancel = threading.Event()

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "request": self.request,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
        }


class PlanRecord:
    """A built plan plus its single-use flag (the engine's Plan stays pure)."""

    def __init__(self, plan):
        self.plan = plan
        self.used = False

    @property
    def id(self):
        return self.plan.id

    @property
    def created_at(self):
        return self.plan.created_at


class CleanupJobStore:
    """The console's cleanup jobs (scan, plan, clean). One store per process."""

    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()

    def _register(self, job):
        with self.lock:
            self.jobs[job.id] = job
            self._prune_locked()
        return job

    def _spawn(self, job, target, args):
        try:
            threading.Thread(target=target, args=args, daemon=True).start()
        except RuntimeError as exc:
            job.state = "failed"
            job.error = "Could not start the job worker: {0}".format(exc)
            job.finishedAt = time.time()
        return job

    def start_scan(self, root, request):
        """Validate the scan request, then run it on a worker thread.

        ``request`` may name ``entryIds`` (catalog ids only) and ``workers``;
        anything else — a path, a command, an unknown key — is refused before a
        thread exists.
        """
        scan = _module(root, "scan")
        catalog = _module(root, "catalog")
        entry_ids = _validate_entry_ids(root, catalog, request.get("entryIds"))
        workers = _validate_workers(scan, request.get("workers"))
        job = CleanupJob("scan", {"entryIds": entry_ids, "workers": workers})
        self._register(job)
        return self._spawn(job, self._run_scan, (root, job, entry_ids, workers))

    def start_packages(self, root):
        job = CleanupJob("packages", {})
        self._register(job)
        return self._spawn(job, self._run_packages, (root, job))

    def _run_packages(self, root, job):
        try:
            job.result = _module(root, "packages").inventory()
            job.state = "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def start_macos_leftovers(self, root):
        job = CleanupJob("macos-leftovers", {})
        self._register(job)
        return self._spawn(job, self._run_macos_leftovers, (root, job))

    def start_leftovers(self, root):
        job = CleanupJob("leftovers", {})
        self._register(job)
        return self._spawn(job, self._run_leftovers, (root, job))

    def _run_leftovers(self, root, job):
        try:
            platform = _module(root, "paths").platform_id()
            module = "leftovers_macos" if platform == "macos" else "leftovers_cross"
            result = _module(root, module).scan(root, platform=platform, cancel=job.cancel)
            job.result = result
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def _run_macos_leftovers(self, root, job):
        try:
            result = _module(root, "leftovers_macos").scan(root, cancel=job.cancel)
            job.result = result
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def start_vm_scan(self, root):
        job = CleanupJob("vm-scan", {})
        self._register(job)
        return self._spawn(job, self._run_vm_scan, (root, job))

    def _run_vm_scan(self, root, job):
        try:
            result = _module(root, "vms").inventory(root, cancel=job.cancel)
            job.result = result
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def start_container_prune(self, root, preview_id):
        try:
            _module(root, "history").prepare()
        except Exception as exc:
            raise CleanupError(500, "Audit history is unavailable: {0}".format(exc)) from exc
        plan = CONTAINER_PREVIEWS.claim(preview_id)
        job = CleanupJob("container-prune", {"previewId": preview_id, "actionId": plan.action_id})
        self._register(job)
        return self._spawn(job, self._run_container_prune, (root, job, plan))

    def _run_container_prune(self, root, job, plan):
        try:
            result = _module(root, "containers").execute(root, plan)
        except Exception as exc:
            result = {"actionId": plan.action_id, "engine": plan.engine, "status": "failed",
                      "error": "{0}: {1}".format(type(exc).__name__, exc), "bytesRemoved": None}
        job.result = result
        try:
            _module(root, "history").append(result)
            job.state = "done" if result["status"] == "completed" else "failed"
            if job.state == "failed":
                job.error = result.get("error")
        except Exception as exc:
            job.state = "failed"
            job.error = "Audit history could not record the result: {0}".format(exc)
        finally:
            job.finishedAt = time.time()

    def start_privileged_run(self, root, preview_id):
        """Claim a single-use privileged preview and run its audited job."""
        try:
            _module(root, "history").prepare()
        except Exception as exc:
            raise CleanupError(500, "Audit history is unavailable: {0}".format(exc)) from exc
        plan = PRIVILEGED_PREVIEWS.claim(preview_id)
        job = CleanupJob("privileged-run", {"previewId": preview_id, "actionId": plan.action_id})
        self._register(job)
        return self._spawn(job, self._run_privileged, (root, job, plan))

    def _run_privileged(self, root, job, plan):
        try:
            result = _module(root, "privilege").execute(root, plan)
        except Exception as exc:
            result = {"actionId": plan.action_id, "platform": plan.platform, "status": "failed",
                      "error": "{0}: {1}".format(type(exc).__name__, exc), "bytesRemoved": None}
        job.result = result
        try:
            _module(root, "history").append(result)
            job.state = "done" if result["status"] == "completed" else "failed"
            if job.state == "failed":
                job.error = result.get("error")
        except Exception as exc:
            job.state = "failed"
            job.error = "Audit history could not record the result: {0}".format(exc)
        finally:
            job.finishedAt = time.time()

    def start_relocation_plan(self, root, request):
        """Validate the typed relocation request, then build its plan on a worker."""
        action = request.get("action")
        entry_id = request.get("entryId")
        destination = request.get("destination")
        if action not in ("move", "restore", "relink", "resume"):
            raise CleanupError(400, "action must be move, restore, relink or resume")
        if not isinstance(entry_id, str) or not entry_id:
            raise CleanupError(400, "entryId must name a catalog entry")
        if not isinstance(destination, str) or not destination:
            raise CleanupError(400, "destination must be a volume mount point from GET /api/cleanup/relocation")
        job = CleanupJob("relocation-plan", {"action": action, "entryId": entry_id, "destination": destination})
        self._register(job)
        return self._spawn(job, self._run_relocation_plan, (root, job, action, entry_id, destination))

    def _run_relocation_plan(self, root, job, action, entry_id, destination):
        try:
            record = _module(root, "relocation").build_plan(root, entry_id, destination, action)
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
            job.finishedAt = time.time()
            return
        preview_id = RELOCATION_PREVIEWS.register(RelocationPreview(record))
        job.result = dict(record, previewId=preview_id)
        job.state = "done"
        job.finishedAt = time.time()

    def start_relocation_run(self, root, preview_id):
        """Claim a single-use relocation preview and run its audited job."""
        try:
            _module(root, "history").prepare()
        except Exception as exc:
            raise CleanupError(500, "Audit history is unavailable: {0}".format(exc)) from exc
        record = RELOCATION_PREVIEWS.claim(preview_id).record
        job = CleanupJob("relocation-run", {"previewId": preview_id, "entryId": record.get("entryId"),
                                            "action": record.get("action")})
        self._register(job)
        return self._spawn(job, self._run_relocation_run, (root, job, record))

    def _run_relocation_run(self, root, job, record):
        def update(payload):
            job.progress = dict(payload)

        try:
            result = _module(root, "relocation").execute(record, cancel=job.cancel,
                                                          progress_callback=update)
            job.result = result
            _module(root, "history").append(result)
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
            try:
                _module(root, "history").append({
                    "entryId": record.get("entryId"), "action": record.get("action"),
                    "status": "failed", "error": str(exc), "bytesRemoved": None,
                })
            except Exception:
                pass
        finally:
            job.finishedAt = time.time()

    def start_deep_scan(self, root, request):
        deep = _module(root, "deep")
        root_ids = request.get("rootIds")
        idle = request.get("minIdleDays", 0)
        if not isinstance(root_ids, list) or not root_ids or any(not isinstance(x, str) for x in root_ids) or len(root_ids) != len(set(root_ids)):
            raise CleanupError(400, "rootIds must be unique configured root ids")
        if not isinstance(idle, int) or isinstance(idle, bool) or not 0 <= idle <= 3650:
            raise CleanupError(400, "minIdleDays must be an integer from 0 to 3650")
        available = {x["id"] for x in deep.roots(root) if x["available"]}
        if any(x not in available for x in root_ids):
            raise CleanupError(400, "Unknown or unavailable rootId")
        job = CleanupJob("deep-scan", {"rootIds": root_ids, "minIdleDays": idle})
        self._register(job)
        return self._spawn(job, self._run_deep_scan, (root, job, root_ids, idle))

    def _run_deep_scan(self, root, job, root_ids, idle):
        try:
            result = _module(root, "deep").sweep(root, root_ids, min_idle_days=idle, cancel=job.cancel)
            job.result = result
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def start_plan(self, root, request):
        """Validate the plan request, then build the plan on a worker thread.

        The typed keys of a scan plus ``mode`` (``trash`` by default; ``delete``
        must be explicit). ``entryIds`` is required — a plan always names what it
        would clean. The request carries no path list and no command.
        """
        clean = _module(root, "clean")
        scan = _module(root, "scan")
        catalog = _module(root, "catalog")
        entry_ids = _validate_entry_ids(root, catalog, request.get("entryIds"), required=True)
        workers = _validate_workers(scan, request.get("workers"))
        mode = request.get("mode", clean.DEFAULT_MODE)
        if mode not in clean.MODES:
            raise CleanupError(400, "mode must be one of {0}".format(", ".join(clean.MODES)))
        job = CleanupJob("plan", {"entryIds": entry_ids, "workers": workers, "mode": mode})
        self._register(job)
        return self._spawn(job, self._run_plan, (root, job, entry_ids, workers, mode))

    def start_clean(self, root, plan_id):
        """Claim the plan (single-use, unexpired) and run it on a worker thread.

        The cheap checks — unknown, already run, past its TTL — answer here; the
        expensive one (an item changed since the plan was made) is re-checked
        inside the job, which then fails honestly with nothing removed.
        """
        clean = _module(root, "clean")
        try:
            _module(root, "history").prepare()
        except Exception as exc:
            raise CleanupError(500, "Audit history is unavailable: {0}".format(exc)) from exc
        try:
            record = PLANS.claim(plan_id)
        except PlanStoreError as exc:
            raise CleanupError(PLAN_STATUS.get(exc.code, 409), str(exc)) from exc
        job = CleanupJob("clean", {"planId": plan_id})
        self._register(job)
        return self._spawn(job, self._run_clean, (root, job, record.plan, clean))

    def _run_scan(self, root, job, entry_ids, workers):
        def update(payload):
            job.progress = dict(payload)

        try:
            result = _module(root, "scan").scan_catalog(
                root, entry_ids, cancel=job.cancel, progress_callback=update, workers=workers
            )
            job.result = result
            job.progress = result["progress"]
            job.state = "cancelled" if result["cancelled"] else "done"
        except Exception as exc:  # the job must answer, never hang in "running"
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def _run_plan(self, root, job, entry_ids, workers, mode):
        def update(payload):
            job.progress = dict(payload)

        try:
            plan = _module(root, "clean").build_plan(
                root,
                entry_ids,
                mode=mode,
                workers=workers,
                cancel=job.cancel,
                progress_callback=update,
            )
            if plan.payload is None:  # cancelled before it finished: no plan exists
                job.progress = plan.progress
                job.state = "cancelled"
            else:
                PLANS.register(plan)
                job.result = plan.to_dict()
                job.progress = plan.progress
                job.state = "done"
        except Exception as exc:  # the job must answer, never hang in "running"
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def _run_clean(self, root, job, plan, clean):
        def update(payload):
            job.progress = dict(payload)

        try:
            measures = clean.verify_plan(plan, cancel=job.cancel)
            result = clean.execute_plan(
                plan, measures, cancel=job.cancel, progress_callback=update
            )
            job.result = result
            job.progress = result["progress"]
            _module(root, "history").append(result)
            job.state = "cancelled" if result["cancelled"] else "done"
        except clean.PlanError as exc:
            # A stale or expired plan fails the job honestly: nothing was removed.
            job.state = "failed"
            job.error = str(exc)
        except Exception as exc:  # the job must answer, never hang in "running"
            job.state = "failed"
            job.error = "{0}: {1}".format(type(exc).__name__, exc)
        finally:
            job.finishedAt = time.time()

    def get(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def list(self):
        with self.lock:
            return [
                job.to_dict()
                for job in sorted(self.jobs.values(), key=lambda j: j.startedAt, reverse=True)
            ]

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            job.cancel.set()
            return job

    def _prune_locked(self):
        finished = sorted(
            (j for j in self.jobs.values() if j.state != "running"),
            key=lambda j: j.startedAt,
        )
        for old in finished[:-MAX_JOBS]:
            self.jobs.pop(old.id, None)


class PlanStoreError(ValueError):
    """A plan was refused by the store. ``code`` maps to an HTTP status."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class PlanStore:
    """The console's built plans, each single-use, with the fingerprints that expire them."""

    def __init__(self):
        self.plans = {}
        self.lock = threading.Lock()

    def register(self, plan):
        with self.lock:
            self.plans[plan.id] = PlanRecord(plan)
            self._prune_locked()
        return plan

    def get(self, plan_id):
        with self.lock:
            return self.plans.get(plan_id)

    def claim(self, plan_id, *, clock=time.time):
        """Mark the plan as run — atomically, so one plan can never run twice."""
        with self.lock:
            record = self.plans.get(plan_id)
            if record is None:
                raise PlanStoreError("Unknown plan id.", "unknown-plan")
            if record.used:
                raise PlanStoreError("This plan was already run. Build a new plan.", "used")
            if record.plan.expires_at < clock():
                raise PlanStoreError("This plan expired; build a new one.", "expired")
            record.used = True
            return record

    def _prune_locked(self):
        ordered = sorted(self.plans.values(), key=lambda record: record.created_at, reverse=True)
        for old in ordered[MAX_PLANS:]:
            self.plans.pop(old.id, None)


class PreviewStore:
    """Single-use, short-lived preview records, kept in this console process."""

    def __init__(self, label="Container preview"):
        self.label = label
        self.records = {}
        self.lock = threading.Lock()

    def register(self, plan):
        preview_id = uuid.uuid4().hex[:12]
        with self.lock:
            self.records[preview_id] = {"plan": plan, "used": False}
            if len(self.records) > MAX_PLANS:
                oldest = min(self.records, key=lambda key: self.records[key]["plan"].created_at)
                self.records.pop(oldest)
        return preview_id

    def claim(self, preview_id):
        with self.lock:
            record = self.records.get(preview_id)
            if record is None:
                raise CleanupError(404, "{0} not found".format(self.label))
            if record["used"]:
                raise CleanupError(409, "{0} was already used".format(self.label))
            if time.time() - record["plan"].created_at > 600:
                raise CleanupError(410, "{0} expired".format(self.label))
            record["used"] = True
            return record["plan"]


#: One store per console process; the handler instances are per-request.
JOBS = CleanupJobStore()
PLANS = PlanStore()
CONTAINER_PREVIEWS = PreviewStore()
PRIVILEGED_PREVIEWS = PreviewStore("Privileged preview")
RELOCATION_PREVIEWS = PreviewStore("Relocation preview")


class RelocationPreview:
    """A relocation record wrapped for the preview store's expiry contract."""

    def __init__(self, record):
        self.record = record
        self.created_at = time.time()


class CleanupAPI:
    # @lat: [[cleanup-lab#Console API]]
    def __init__(self, root):
        self.root = os.path.realpath(root)

    def get(self, path, query):
        if path == "/api/cleanup/status":
            _query(query)
            return _module(self.root, "readiness").probe(self.root)
        if path == "/api/cleanup/catalog":
            _query(query)
            catalog = _module(self.root, "catalog")
            try:
                return catalog.report(self.root)
            except catalog.CatalogError as exc:
                raise CleanupError(500, "The detector catalog is invalid: {0}".format(exc)) from exc
        if path == "/api/cleanup/containers":
            _query(query)
            return _module(self.root, "containers").capabilities(self.root)
        if path == "/api/cleanup/deep-roots":
            _query(query)
            return {"roots": _module(self.root, "deep").roots(self.root)}
        if path == "/api/cleanup/volumes":
            _query(query)
            return _module(self.root, "volumes").inventory()
        if path == "/api/cleanup/relocation":
            _query(query)
            return _module(self.root, "relocation").status(self.root)
        if path == "/api/cleanup/privileged":
            _query(query)
            return _module(self.root, "privilege").capabilities(self.root)
        if path == "/api/cleanup/simulators":
            _query(query)
            return _module(self.root, "deep").simulators(self.root)
        if path == "/api/cleanup/history":
            _query(query)
            try:
                return _module(self.root, "history").read()
            except Exception as exc:
                raise CleanupError(500, "Audit history is unavailable: {0}".format(exc)) from exc
        if path == "/api/cleanup/jobs":
            _query(query)
            return {"jobs": JOBS.list()}
        if path.startswith("/api/cleanup/jobs/"):
            _query(query)
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:3] == ["api", "cleanup", "jobs"]:
                job = JOBS.get(parts[3])
                if job is None:
                    raise CleanupError(404, "Job not found")
                return job.to_dict()
            raise CleanupError(404, "Cleanup Lab endpoint not found")
        raise CleanupError(404, "Cleanup Lab endpoint not found")

    def post(self, path, body):
        """The typed POST surface: start a scan, plan or clean; cancel a job."""
        if path == "/api/cleanup/scan":
            _object_body(body, "scan")
            return JOBS.start_scan(self.root, body)
        if path == "/api/cleanup/vms/scan":
            _object_body(body, "vm-scan")
            return JOBS.start_vm_scan(self.root)
        if path == "/api/cleanup/containers/preview":
            _object_body(body, "container-preview")
            action_id = body.get("actionId")
            if not isinstance(action_id, str) or not action_id:
                raise CleanupError(400, "actionId must name an available container action")
            try:
                plan, candidates = _module(self.root, "containers").preview(self.root, action_id)
            except Exception as exc:
                raise CleanupError(400, str(exc)) from exc
            preview_id = CONTAINER_PREVIEWS.register(plan)
            return {"previewId": preview_id, "actionId": plan.action_id, "engine": plan.engine,
                    "risk": plan.risk, "candidateCount": plan.count, "candidates": candidates,
                    "command": [plan.engine, *plan.prune_argv], "expiresAt": plan.created_at + 600}
        if path == "/api/cleanup/containers/prune":
            _object_body(body, "container-prune")
            preview_id = body.get("previewId")
            if not isinstance(preview_id, str) or not preview_id:
                raise CleanupError(400, "previewId must name a confirmed preview")
            return JOBS.start_container_prune(self.root, preview_id)
        if path == "/api/cleanup/privileged/preview":
            _object_body(body, "privileged-preview")
            action_id = body.get("actionId")
            if not isinstance(action_id, str) or not action_id:
                raise CleanupError(400, "actionId must name an available privileged action")
            try:
                plan, candidates = _module(self.root, "privilege").preview(self.root, action_id)
            except Exception as exc:
                raise CleanupError(400, str(exc)) from exc
            preview_id = PRIVILEGED_PREVIEWS.register(plan)
            return {"previewId": preview_id, "actionId": plan.action_id, "elevation": plan.elevation,
                    "risk": plan.risk, "candidateCount": plan.count, "candidates": candidates,
                    "totalBytes": plan.total_bytes, "command": list(plan.elevation_argv),
                    "expiresAt": plan.created_at + 600}
        if path == "/api/cleanup/privileged/run":
            _object_body(body, "privileged-run")
            preview_id = body.get("previewId")
            if not isinstance(preview_id, str) or not preview_id:
                raise CleanupError(400, "previewId must name a confirmed privileged preview")
            return JOBS.start_privileged_run(self.root, preview_id)
        if path == "/api/cleanup/relocation/plan":
            _object_body(body, "relocation-plan")
            return JOBS.start_relocation_plan(self.root, body)
        if path == "/api/cleanup/relocation/run":
            _object_body(body, "relocation-run")
            preview_id = body.get("previewId")
            if not isinstance(preview_id, str) or not preview_id:
                raise CleanupError(400, "previewId must name a confirmed relocation preview")
            return JOBS.start_relocation_run(self.root, preview_id)
        if path == "/api/cleanup/packages/scan":
            _object_body(body, "packages")
            return JOBS.start_packages(self.root)
        if path == "/api/cleanup/leftovers/macos/scan":
            _object_body(body, "macos-leftovers")
            return JOBS.start_macos_leftovers(self.root)
        if path == "/api/cleanup/leftovers/scan":
            _object_body(body, "leftovers")
            return JOBS.start_leftovers(self.root)
        if path == "/api/cleanup/deep-scan":
            _object_body(body, "deep-scan")
            return JOBS.start_deep_scan(self.root, body)
        if path == "/api/cleanup/plan":
            _object_body(body, "plan")
            return JOBS.start_plan(self.root, body)
        if path == "/api/cleanup/clean":
            _object_body(body, "clean")
            plan_id = body.get("planId")
            if not isinstance(plan_id, str) or not plan_id:
                raise CleanupError(400, "planId must be the id of a built plan")
            return JOBS.start_clean(self.root, plan_id)
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[:3] == ["api", "cleanup", "jobs"] and parts[4] == "cancel":
            if body:
                raise CleanupError(400, "A cancel request carries no body")
            job = JOBS.cancel(parts[3])
            if job is None:
                raise CleanupError(404, "Job not found")
            return job.to_dict()
        raise CleanupError(404, "Cleanup Lab endpoint not found")
