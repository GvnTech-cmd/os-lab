// content.js - creates script tag pointing to web_accessible_resource
const s = document.createElement('script');
s.src = chrome.runtime.getURL('injected.js');
document.documentElement.appendChild(s);

// API hook
const originalFetch = window.fetch;
window.fetch = function(...args) {
  return originalFetch.apply(this, args);
};

// Cross world communication
window.postMessage({ type: 'EXTENSION_INIT' }, '*');
