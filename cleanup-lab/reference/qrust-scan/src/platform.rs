//! The only platform-specific part of the scan: how much space a file actually
//! takes on disk, which hard links point at the same bytes, and how many walk
//! threads to run.
//!
//! Both numbers exist on every desktop OS os-lab supports; they are just asked
//! for differently:
//!
//! - allocated size — unix `st_blocks * 512`; Windows `GetCompressedFileSizeW`,
//!   the size the file occupies after compression and sparse handling, which is
//!   the closest Windows equivalent of "blocks allocated".
//! - file identity — unix `(st_dev, st_ino)`; Windows `(volume serial, file
//!   index)` out of `GetFileInformationByHandle`. `std::os::windows::fs::
//!   MetadataExt` exposes the same fields, but `volume_serial_number` and
//!   `file_index` are behind the unstable `windows_by_handle` feature, so the
//!   Win32 call is used instead.
//!
//! Everything here is pure measurement: it never writes, and a failure to read
//! one field degrades to the apparent size rather than failing the scan.

use std::fs::Metadata;
use std::path::Path;

/// `std::fs::Metadata` plus the numbers a scan needs but `Metadata` alone does
/// not offer on every platform.
#[derive(Debug, Clone, Copy, Default)]
pub struct EntryFacts {
    /// Space actually occupied: allocated blocks where the platform reports
    /// them, the apparent length otherwise.
    pub allocated: u64,
    /// The apparent length (`metadata.len()`), used by `--apparent-size`.
    pub logical: u64,
    /// Device or volume; part of a file's identity and what `-x` compares.
    pub dev: u64,
    /// Inode or Windows file index; part of a file's identity.
    pub ino: u64,
    /// Hard links pointing at these bytes.
    pub nlink: u64,
    /// Modification time in unix seconds (negative before 1970 is allowed).
    pub mtime: i64,
    pub is_dir: bool,
}

impl EntryFacts {
    /// Read an entry's facts. `path` names the same entry `meta` came from, so
    /// the walk hands over the metadata it already has and no extra `stat`
    /// happens for the common case.
    pub fn new(path: &Path, meta: &Metadata) -> Self {
        let (allocated, dev, ino, nlink) = identity(path, meta);
        Self {
            allocated,
            logical: meta.len(),
            dev,
            ino,
            nlink,
            mtime: mtime_secs(meta),
            is_dir: meta.is_dir(),
        }
    }

    /// The size this entry contributes to the tree: allocated, or apparent when
    /// the caller asked for it.
    pub fn size(&self, apparent_size: bool) -> u64 {
        if apparent_size {
            self.logical
        } else {
            self.allocated
        }
    }
}

/// The default thread count when the caller passes 0.
///
/// dua pins Apple Silicon to 3 threads because APFS/VFS contention makes more
/// counter-productive there. That argument does not hold on NTFS or ext4, so
/// elsewhere the count follows the machine, capped, since the walk turns I/O
/// bound long before it turns CPU bound.
pub fn default_threads() -> usize {
    default_threads_for(std::env::consts::OS, available_parallelism())
}

/// The same decision with its inputs passed in, so it is testable and the Apple
/// rule is visible as a rule rather than a comment.
pub fn default_threads_for(os: &str, parallelism: usize) -> usize {
    match os {
        "macos" | "ios" => 3,
        _ => parallelism.clamp(1, 16),
    }
}

fn available_parallelism() -> usize {
    std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
}

#[cfg(unix)]
fn identity(_path: &Path, meta: &Metadata) -> (u64, u64, u64, u64) {
    use std::os::unix::fs::MetadataExt as _;
    let allocated = meta.blocks().saturating_mul(512);
    (allocated, meta.dev(), meta.ino(), meta.nlink())
}

#[cfg(unix)]
fn mtime_secs(meta: &Metadata) -> i64 {
    use std::os::unix::fs::MetadataExt as _;
    meta.mtime()
}

#[cfg(windows)]
fn identity(path: &Path, meta: &Metadata) -> (u64, u64, u64, u64) {
    // Directories have no meaningful compressed size. Their identity is still
    // read: the walk compares a directory's volume with the root's for
    // `stay_on_filesystem`.
    let allocated = if meta.is_file() {
        allocated_size(path).unwrap_or(meta.len())
    } else {
        0
    };
    let (dev, ino, nlink) = file_identity(path).unwrap_or((0, 0, 1));
    (allocated, dev, ino, nlink)
}

#[cfg(windows)]
fn allocated_size(path: &Path) -> Option<u64> {
    use windows::core::HSTRING;
    use windows::Win32::Storage::FileSystem::GetCompressedFileSizeW;

    // `GetCompressedFileSizeW` returns the low 32 bits and writes the high 32
    // bits through the out-parameter; both being `INVALID_FILE_SIZE` means the
    // call failed rather than "a 4 GiB file".
    let mut high: u32 = 0;
    let low = unsafe { GetCompressedFileSizeW(&HSTRING::from(path.as_os_str()), Some(&mut high)) };
    if low == u32::MAX && high == u32::MAX {
        None
    } else {
        Some(((high as u64) << 32) | low as u64)
    }
}

#[cfg(windows)]
fn file_identity(path: &Path) -> Option<(u64, u64, u64)> {
    use std::os::windows::io::AsRawHandle;
    use windows::Win32::Foundation::HANDLE;
    use windows::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    use std::os::windows::fs::OpenOptionsExt as _;

    // Opening the entry is the only way to ask this question, so it is the one
    // place the engine touches a handle. A denied open degrades to "unknown
    // identity", which the scan treats as a single-link file.
    //
    // os-lab fix: a plain `File::open` fails on a directory, so the scan root's
    // volume serial used to come back as 0 while every file reported its real
    // serial — and `stay_on_filesystem` then zeroed the size of every file.
    // `FILE_FLAG_BACKUP_SEMANTICS` lets the same call open directories, and an
    // access mask of 0 asks only for attributes (no read access needed).
    const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
    let file = std::fs::OpenOptions::new()
        .access_mode(0)
        .custom_flags(FILE_FLAG_BACKUP_SEMANTICS)
        .open(path)
        .ok()?;
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe { GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info).ok() }?;
    let ino = ((info.nFileIndexHigh as u64) << 32) | info.nFileIndexLow as u64;
    Some((
        info.dwVolumeSerialNumber as u64,
        ino,
        info.nNumberOfLinks as u64,
    ))
}

#[cfg(windows)]
fn mtime_secs(meta: &Metadata) -> i64 {
    use std::time::UNIX_EPOCH;
    match meta.modified() {
        Ok(time) => match time.duration_since(UNIX_EPOCH) {
            Ok(d) => d.as_secs() as i64,
            // Before 1970: report the negative offset instead of clamping to 0,
            // so an old file still sorts as old.
            Err(e) => -(e.duration().as_secs() as i64),
        },
        Err(_) => 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apple_keeps_the_three_thread_rule() {
        assert_eq!(default_threads_for("macos", 12), 3);
        assert_eq!(default_threads_for("ios", 8), 3);
    }

    #[test]
    fn other_platforms_follow_the_machine_within_a_cap() {
        assert_eq!(default_threads_for("windows", 12), 12);
        assert_eq!(default_threads_for("linux", 64), 16, "capped");
        assert_eq!(default_threads_for("linux", 1), 1);
        assert_eq!(default_threads_for("linux", 0), 1, "never zero threads");
    }

    #[test]
    fn a_real_file_is_measured_without_asking_the_caller_for_anything() {
        let dir = std::env::temp_dir().join(format!("qrust-scan-facts-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("payload.bin");
        std::fs::write(&path, vec![b'x'; 8192]).unwrap();

        let meta = std::fs::metadata(&path).unwrap();
        let facts = EntryFacts::new(&path, &meta);

        assert!(!facts.is_dir);
        assert_eq!(facts.logical, 8192, "apparent size is the real length");
        assert!(
            facts.size(false) > 0,
            "allocated size must be measurable on this platform"
        );
        assert_eq!(
            facts.size(true),
            8192,
            "apparent size is what --apparent-size asks for"
        );
        assert!(facts.nlink >= 1, "a file has at least one link");

        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn two_hard_links_share_one_identity() {
        let dir = std::env::temp_dir().join(format!("qrust-scan-link-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let a = dir.join("a.bin");
        let b = dir.join("b.bin");
        std::fs::write(&a, vec![b'x'; 4096]).unwrap();
        std::fs::hard_link(&a, &b).unwrap();

        let fa = EntryFacts::new(&a, &std::fs::metadata(&a).unwrap());
        let fb = EntryFacts::new(&b, &std::fs::metadata(&b).unwrap());
        assert_eq!(
            (fa.dev, fa.ino),
            (fb.dev, fb.ino),
            "same bytes, same identity"
        );
        assert_eq!(fa.nlink, 2, "both names count as links");

        std::fs::remove_dir_all(&dir).unwrap();
    }
}
