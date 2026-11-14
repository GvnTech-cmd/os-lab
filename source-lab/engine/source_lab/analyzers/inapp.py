"""Scripts that native apps inject into embedded web views and what they listen for.

The Playbook's in-app browser methodology looks for apps that inject JavaScript trackers, DOM scrapers or keyloggers into
the pages they open. A listener for key, input or clipboard events is only suspicious inside script text that the app itself
injects, so these rules require an injection API in the same file.
"""

from __future__ import annotations

from source_lab.evidence.schema import SeverityLevel

from ._common import Rule

INJECTION_CONTEXT = (
    r"WKUserScript|evaluateJavaScript|evaluateJavascript|addDocumentStartJavaScript|WebViewCompat|"
    r"loadUrl\s*\(\s*[\"']javascript:|stringByEvaluatingJavaScript|WebView2|ExecuteScriptAsync"
)

RULES = (
    Rule(
        "inapp.script-listener.keyboard",
        r"addEventListener\s*\(\s*\\?[\"'](keydown|keyup|keypress|input|beforeinput|paste|copy|cut)\\?[\"']",
        SeverityLevel.HIGH,
        0.7,
        "key / input / clipboard listener in injected script",
        "A script the app injects into a web view listens for key, input or clipboard events, the signature of a keylogger or form scraper on pages the app does not own.",
        ("A form helper or accessibility feature operating on the app's own pages.",),
        requires=INJECTION_CONTEXT,
        world="MAIN",
    ),
    Rule(
        "inapp.script-listener.pointer",
        r"addEventListener\s*\(\s*\\?[\"'](click|touchstart|touchend|submit|focusin|change)\\?[\"']",
        SeverityLevel.MEDIUM,
        0.5,
        "click / submit listener in injected script",
        "A script the app injects into a web view listens for taps, clicks or form submission, which lets it observe what the user does on third-party pages.",
        ("Link-tracking or UI helper on the app's own pages.",),
        requires=INJECTION_CONTEXT,
        world="MAIN",
    ),
)
