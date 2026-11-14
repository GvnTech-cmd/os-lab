// collectors/browser/canary.js — Six-phase runtime detection canary
// Runs inline in the host page before any extension content script.

(function() {
  'use strict';

  if (window.__iqCanaryInitialized) return;
  window.__iqCanaryInitialized = true;

  const observations = [];
  const captureTime = () => performance.now();

  // Phase 1: Prototype descriptor freezing & native code string baseline
  const originalFetch = window.fetch;
  const originalToString = Function.prototype.toString;
  const fetchDesc = Object.getOwnPropertyDescriptor(window, 'fetch');

  // Phase 2: Frozen global property traps on window
  const trapProperty = (propName) => {
    try {
      let internalValue = window[propName];
      Object.defineProperty(window, propName, {
        configurable: true,
        enumerable: true,
        get() { return internalValue; },
        set(val) {
          observations.push({
            phase: 'global_trap',
            type: 'property_tamper',
            property: propName,
            valueType: typeof val,
            stack: new Error().stack,
            time: captureTime()
          });
          internalValue = val;
        }
      });
    } catch (e) {}
  };

  ['ethereum', 'solana', 'web3', 'chrome', 'browser'].forEach(trapProperty);

  // Phase 3: Cross-realm clean iframe verification probe (defeats toString spoofing)
  const verifyNativeIdentity = (fn, fnName) => {
    try {
      const iframe = document.createElement('iframe');
      iframe.src = 'about:blank';
      iframe.style.display = 'none';
      (document.head || document.documentElement).appendChild(iframe);

      const cleanRealm = iframe.contentWindow;
      const isCleanToString = cleanRealm.Function.prototype.toString.call(fn) === `function ${fnName}() { [native code] }`;
      const isIdenticalPrototype = fn.toString === cleanRealm.Function.prototype.toString;

      iframe.parentNode.removeChild(iframe);
      return { isCleanToString, isIdenticalPrototype };
    } catch (err) {
      return { error: err.message };
    }
  };

  // Phase 4: EventTarget.prototype.addEventListener listener proxy probe
  try {
    const originalAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
      const sensitiveEvents = ['keydown', 'keyup', 'input', 'paste', 'submit', 'click'];
      if (sensitiveEvents.includes(type)) {
        observations.push({
          phase: 'listener_registered',
          type: 'listener_proxy',
          eventType: type,
          target: this.nodeName || (this === window ? 'Window' : 'UnknownTarget'),
          listenerSource: typeof listener === 'function' ? listener.toString().slice(0, 160) : 'handleEvent',
          stack: new Error().stack,
          time: captureTime()
        });
      }
      return originalAddEventListener.call(this, type, listener, options);
    };
  } catch (e) {}

  // Phase 5: Inline <head> MutationObserver for transient script/style elements
  try {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === 1 && ['SCRIPT', 'STYLE', 'LINK', 'IFRAME'].includes(node.nodeName)) {
            const src = node.src || node.href || null;
            const isExt = Boolean(src && (src.startsWith('chrome-extension://') || src.startsWith('moz-extension://')));
            observations.push({
              phase: 'dom_addition',
              type: 'dom_mutation',
              nodeName: node.nodeName,
              src: src,
              isExtensionUrl: isExt,
              time: captureTime()
            });
          }
        }
        for (const node of mutation.removedNodes) {
          if (node.nodeType === 1 && node.nodeName === 'SCRIPT') {
            observations.push({
              phase: 'dom_removal_ephemeral',
              type: 'dom_mutation',
              nodeName: node.nodeName,
              src: node.src || null,
              time: captureTime()
            });
          }
        }
      }
    });

    const rootTarget = document.documentElement || document;
    observer.observe(rootTarget, { childList: true, subtree: true });
  } catch (e) {}

  // Phase 6: Call stack origin extraction via synthetic error
  window.__iqCanaryExtractOrigin = function() {
    try {
      throw new Error('Canary Stack Probe');
    } catch (err) {
      const extensionFrames = (err.stack || '').split('\n').filter(line =>
        line.includes('chrome-extension://') || line.includes('moz-extension://')
      );
      return extensionFrames;
    }
  };

  // Export hook for test runner
  window.__iqExportObservations = () => ({
    observations,
    prototypeAudit: {
      fetch: verifyNativeIdentity(window.fetch, 'fetch'),
      toString: verifyNativeIdentity(Function.prototype.toString, 'toString')
    }
  });
})();
