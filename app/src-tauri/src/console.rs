//! The os-lab console as a child process.
//!
//! `android-lab/lab/web_ui.py <port>` is the only backend (host detection, lab plans, jobs, the
//! committed dashboard build). The app starts it on a free loopback port, waits until
//! `/healthz` answers and then points the window at it. Nothing here executes lab commands:
//! every lab action still goes through the console's preview → token → run flow in the page.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::runtime::Source;

/// argv: script, port, parent pid. Runs the console in-process (runpy) and watches the parent.
const SUPERVISOR: &str = r#"
import os, sys, threading, time, runpy, signal
script, port, parent = sys.argv[1], sys.argv[2], int(sys.argv[3])
def alive(pid):
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not h:
            return False
        r = ctypes.windll.kernel32.WaitForSingleObject(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)
        return r == 0x102  # WAIT_TIMEOUT: still running
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
def watch():
    while alive(parent):
        time.sleep(1.5)
    try:
        if os.name != "nt":
            os.killpg(os.getpgrp(), signal.SIGTERM)
    finally:
        os._exit(0)
threading.Thread(target=watch, daemon=True).start()
sys.argv = [script, port]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
"#;

/// Cheap to clone: every clone is the same child process.
#[derive(Clone)]
pub struct Console {
    inner: Arc<Mutex<Inner>>,
}

#[derive(Default)]
struct Inner {
    child: Option<Child>,
    port: Option<u16>,
}

#[derive(Clone, serde::Serialize)]
pub struct Started {
    pub url: String,
    pub root: String,
    pub source: Source,
    pub python: String,
    pub log: String,
}

impl Console {
    pub fn new() -> Self {
        Console { inner: Arc::new(Mutex::new(Inner::default())) }
    }

    /// The URL if a console child is alive and answering.
    pub fn running_url(&self) -> Option<String> {
        let mut inner = self.inner.lock().ok()?;
        let port = inner.port?;
        let child = inner.child.as_mut()?;
        if child.try_wait().ok()?.is_some() {
            inner.child = None;
            inner.port = None;
            return None;
        }
        healthy(port).then(|| url_for(port))
    }

    pub fn start(&self, root: &Path, source: Source, log: &Path, data_dir: &Path, content_dir: &Path, app_version: &str) -> Result<Started, String> {
        if let Some(url) = self.running_url() {
            return Ok(Started {
                url,
                root: root.display().to_string(),
                source,
                python: String::new(),
                log: log.display().to_string(),
            });
        }
        self.stop();
        let python = find_python(data_dir)?;
        let port = free_port()?;
        let script = root.join("android-lab").join("lab").join("web_ui.py");
        if let Some(parent) = log.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let mut out = OpenOptions::new().create(true).append(true).open(log).map_err(|e| format!("Cannot open {}: {e}", log.display()))?;
        let _ = writeln!(out, "--- starting console on 127.0.0.1:{port} from {} ({python}) ---", root.display());
        let err = out.try_clone().map_err(|e| e.to_string())?;

        let mut cmd = Command::new(&python);
        if python == "py" {
            cmd.arg("-3");
        }
        // The console runs under a small supervisor so it cannot outlive the app, even when the
        // app is killed rather than quit: the supervisor watches the app's pid and ends the
        // console's process group when it goes.
        cmd.arg("-u").arg("-c").arg(SUPERVISOR).arg(&script).arg(port.to_string()).arg(std::process::id().to_string());
        cmd.current_dir(root)
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env("OSLAB_CONTENT_DIR", content_dir)
            // Lets the dashboard compare this build with the published release (console/app_update.py).
            .env("OSLAB_APP_VERSION", app_version)
            .stdin(Stdio::null())
            .stdout(Stdio::from(out))
            .stderr(Stdio::from(err));
        isolate(&mut cmd);
        let child = cmd.spawn().map_err(|e| format!("Could not start {python}: {e}"))?;
        {
            let mut inner = self.inner.lock().map_err(|_| "console state poisoned".to_string())?;
            inner.child = Some(child);
            inner.port = Some(port);
        }

        let deadline = Instant::now() + Duration::from_secs(20);
        loop {
            if healthy(port) {
                break;
            }
            {
                let mut inner = self.inner.lock().map_err(|_| "console state poisoned".to_string())?;
                if let Some(child) = inner.child.as_mut() {
                    if let Ok(Some(status)) = child.try_wait() {
                        inner.child = None;
                        inner.port = None;
                        return Err(format!("The console exited ({status}) before it answered.\n\n{}", tail(log, 20)));
                    }
                }
            }
            if Instant::now() > deadline {
                self.stop();
                return Err(format!("The console did not answer within 20 seconds.\n\n{}", tail(log, 20)));
            }
            std::thread::sleep(Duration::from_millis(150));
        }
        Ok(Started {
            url: url_for(port),
            root: root.display().to_string(),
            source,
            python,
            log: log.display().to_string(),
        })
    }

    pub fn stop(&self) {
        let Ok(mut inner) = self.inner.lock() else { return };
        if let Some(mut child) = inner.child.take() {
            kill_tree(&mut child);
        }
        inner.port = None;
    }
}

fn url_for(port: u16) -> String {
    format!("http://127.0.0.1:{port}/")
}

/// Ask the OS for a free loopback port. The console binds it a moment later; a collision there
/// shows up as the child exiting, which `start` reports with the log tail.
fn free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| format!("No free local port: {e}"))?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    Ok(port)
}

/// `GET /healthz` over a plain socket: no HTTP client, no CORS, and only loopback.
pub fn healthy(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(400)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(800)));
    let req = format!("GET /healthz HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut head = [0u8; 16];
    let n = stream.read(&mut head).unwrap_or(0);
    head[..n].starts_with(b"HTTP/1.") && head[..n].windows(3).any(|w| w == b"200")
}

/// The first Python supported by every bundled lab. On Windows the `py` launcher comes first.
pub fn find_python(data_dir: &Path) -> Result<String, String> {
    let managed = crate::python_runtime::saved_python(data_dir);
    let host: &[&str] = if cfg!(windows) { &["py", "python", "python3"] } else { &["python3", "python"] };
    for name in managed.iter().map(String::as_str).chain(host.iter().copied()) {
        let mut cmd = Command::new(name);
        if name == "py" {
            cmd.arg("-3");
        }
        cmd.args(["-c", "import sys; print(sys.version_info >= (3, 11))"]);
        hide_window(&mut cmd);
        if let Ok(out) = cmd.output() {
            if out.status.success() && String::from_utf8_lossy(&out.stdout).trim() == "True" {
                return Ok(name.to_string());
            }
        }
    }
    Err("Python 3.11 or newer was not found. Choose Get Python to install a managed copy for os-lab, then retry.".to_string())
}

pub fn tail(path: &Path, lines: usize) -> String {
    let mut text = String::new();
    if let Ok(mut f) = File::open(path) {
        let _ = f.read_to_string(&mut text);
    }
    let all: Vec<&str> = text.lines().collect();
    all[all.len().saturating_sub(lines)..].join("\n")
}

pub fn log_path(dir: &Path) -> PathBuf {
    dir.join("console.log")
}

#[cfg(unix)]
fn isolate(cmd: &mut Command) {
    use std::os::unix::process::CommandExt;
    // Its own process group, so quitting the app can stop the console and the jobs it started.
    cmd.process_group(0);
}

#[cfg(windows)]
fn isolate(cmd: &mut Command) {
    hide_window(cmd);
}

#[cfg(windows)]
fn hide_window(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
}

#[cfg(not(windows))]
fn hide_window(_cmd: &mut Command) {}

#[cfg(unix)]
fn kill_tree(child: &mut Child) {
    let pid = child.id() as i32;
    // SAFETY-free path: use `kill` so this crate needs no libc. Negative pid = the whole group.
    let _ = Command::new("kill").args(["-TERM", &format!("-{pid}")]).status();
    for _ in 0..20 {
        if matches!(child.try_wait(), Ok(Some(_))) {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = Command::new("kill").args(["-KILL", &format!("-{pid}")]).status();
    let _ = child.wait();
}

#[cfg(windows)]
fn kill_tree(child: &mut Child) {
    let mut cmd = Command::new("taskkill");
    cmd.args(["/T", "/F", "/PID", &child.id().to_string()]);
    hide_window(&mut cmd);
    let _ = cmd.status();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn free_port_is_usable() {
        let port = free_port().unwrap();
        assert!(port > 0);
        assert!(TcpListener::bind(("127.0.0.1", port)).is_ok());
    }

    #[test]
    fn nothing_listening_is_not_healthy() {
        let port = free_port().unwrap();
        assert!(!healthy(port));
    }

    #[test]
    fn healthy_requires_200() {
        for (reply, want) in [("HTTP/1.0 200 OK\r\n\r\nok", true), ("HTTP/1.0 404 Not Found\r\n\r\n", false)] {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let port = listener.local_addr().unwrap().port();
            let handle = std::thread::spawn(move || {
                if let Ok((mut s, _)) = listener.accept() {
                    let mut buf = [0u8; 256];
                    let _ = s.read(&mut buf);
                    let _ = s.write_all(reply.as_bytes());
                }
            });
            assert_eq!(healthy(port), want, "{reply}");
            handle.join().unwrap();
        }
    }

    #[test]
    fn tail_returns_last_lines() {
        let p = std::env::temp_dir().join(format!("oslab-tail-{}.log", std::process::id()));
        fs::write(&p, "a\nb\nc\nd\n").unwrap();
        assert_eq!(tail(&p, 2), "c\nd");
        let _ = fs::remove_file(&p);
    }
}
