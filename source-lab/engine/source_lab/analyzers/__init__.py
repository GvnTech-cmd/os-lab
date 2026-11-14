"""Platform static analyzers for browser extensions, Windows, macOS, Android, and iOS."""

from .browser import BrowserExtensionAnalyzer
from .windows import WindowsAppAnalyzer
from .macos import MacOSAppAnalyzer
from .android import AndroidAppAnalyzer
from .ios import IOSAppAnalyzer

__all__ = [
    "BrowserExtensionAnalyzer",
    "WindowsAppAnalyzer",
    "MacOSAppAnalyzer",
    "AndroidAppAnalyzer",
    "IOSAppAnalyzer",
]
