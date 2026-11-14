import "../styles/firewall-contribute.css";
import { useEffect, useRef } from "react";
import { WrenchIcon, XIcon } from "@phosphor-icons/react";
import type { Finding } from "../firewall/audit";
import { IMPACT } from "../firewall/impact";
import type { FirewallLocale } from "../firewall/locale";
import { auditCategory, auditUi } from "../firewall/audit-ui";
import { keepModalFocus } from "./modal-focus";

const METERS = [["Hackable", "hack"], ["Weak", "weak"], ["Expensive", "cost"]] as const;

export function GapModal({ f, onClose, locale = "en" }: { f: Finding; onClose: () => void; locale?: FirewallLocale }) {
  const t = auditUi[locale];
  const box = useRef<HTMLDialogElement>(null);
  const im = IMPACT[f.id];
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    box.current?.showModal();
    box.current?.focus();
    return () => {
      if (box.current?.open) box.current.close();
      document.body.style.overflow = previousOverflow;
      prev?.focus();
    };
  }, []);

  return (
    <dialog className="cm gm" aria-labelledby="gm-title" ref={box} tabIndex={-1} data-sev={f.severity} onClose={onClose} onKeyDown={keepModalFocus} onMouseDown={(e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) { e.preventDefault(); onClose(); }
    }}>
        <button className="cm-x" type="button" onClick={onClose} aria-label={t.close}><XIcon size={16} weight="bold" /></button>
        <span className="cm-eyebrow">{auditCategory(f.category, locale)} · {t.severity} {f.severity}/5</span>
        <h2 id="gm-title" className="gm-title" lang="en">{f.title}</h2>

        {im ? (
          <>
            <div className="gm-flow" style={{ ["--n" as string]: im.path.length }} aria-label={`${t.path}: ${im.path.join(" → ")}`}>
              {im.path.map((n, i) => (
                <div key={i} className="gm-node" data-state={i < im.gap ? "ok" : i === im.gap ? "gap" : "hit"} style={{ animationDelay: `${i * 0.35}s` }}>
                  <i />
                  <span lang="en">{n}</span>
                </div>
              ))}
              <b className="gm-dot" aria-hidden="true" />
            </div>
            <p className="gm-scn" lang="en">{im.scenario}</p>
            <div className="gm-meters">
              {METERS.map(([label, k], r) => (
                <div key={k} className="gm-meter">
                  <span>{{ Hackable: t.hackable, Weak: t.weak, Expensive: t.expensive }[label]}</span>
                  <div>{[1, 2, 3, 4, 5].map((n) => <i key={n} data-on={n <= im[k]} style={{ animationDelay: `${0.5 + r * 0.15 + n * 0.06}s` }} />)}</div>
                </div>
              ))}
            </div>
            <p className="gm-price" lang="en">{im.price}</p>
          </>
        ) : (
          <p className="gm-scn" lang="en">{f.why}</p>
        )}

        <p className="gm-fix" lang="en"><WrenchIcon size={14} weight="bold" /> {f.fix}</p>
    </dialog>
  );
}
