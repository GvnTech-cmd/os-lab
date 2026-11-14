//! Cooperative cancellation for in-flight scans.
//!
//! A scan that cannot be stopped keeps burning CPU and I/O after the user has
//! moved on. The caller keeps a clone of the flag, flips it from any thread, and
//! the scan polls it at its traversal and aggregation checkpoints (see
//! `walk::scan_cancellable`). Cloneable + `Send + Sync` (an `Arc<AtomicBool>`).

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// A shared, thread-safe cancellation flag. Cheap to clone (`Arc` bump) and
/// cheap to poll (a relaxed atomic load).
#[derive(Clone, Debug, Default)]
pub struct CancelFlag(Arc<AtomicBool>);

impl CancelFlag {
    /// A fresh, not-yet-cancelled flag.
    pub fn new() -> Self {
        Self(Arc::new(AtomicBool::new(false)))
    }

    /// Request cancellation. Idempotent; safe to call from any thread.
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }

    /// Whether cancellation has been requested. Polled in the scan hot loop,
    /// so it uses a relaxed load — the exact iteration on which a concurrent
    /// `cancel()` becomes visible doesn't matter, only that it becomes visible
    /// promptly (which `Relaxed` guarantees on the platforms we target).
    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::Relaxed)
    }
}
