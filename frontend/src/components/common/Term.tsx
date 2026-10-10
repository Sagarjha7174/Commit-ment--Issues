import { useId, useState, type ReactNode } from 'react';
import { GLOSSARY } from '../../utils/glossary';
import '../situation/situation.css';

/** A word with a plain-language definition on hover, focus or tap. */
export function Term({ k, children }: { k: keyof typeof GLOSSARY | string; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const text = GLOSSARY[k];
  if (!text) return <>{children ?? k}</>;
  return (
    <span className="term-wrap">
      <button
        type="button"
        className="term"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
      >
        {children ?? k}
      </button>
      {open && <span role="tooltip" id={id} className="term-tip">{text}</span>}
    </span>
  );
}
