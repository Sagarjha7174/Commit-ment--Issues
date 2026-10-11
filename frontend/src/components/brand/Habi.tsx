/**
 * HABI brand mark: an isometric H — two pillars with pointed caps and a Signal Orange crossbar
 * (see "logo reference.png"). Pillar colours follow the theme: Darker alternative on paper, paper on dark.
 */
import './habi.css';

export function HabiMark({ size = 28, tone = 'auto', title }: { size?: number; tone?: 'auto' | 'dark' | 'light'; title?: string }) {
  return (
    <svg
      className={`habi-mark habi-mark-${tone}`}
      viewBox="0 0 240 310"
      height={size}
      width={(size * 240) / 310}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <polygon points="148,28 200,0 200,310 148,282" className="hm-face" />
      <polygon points="200,0 240,22 240,288 200,310" className="hm-side" />
      <polygon points="70,166 196,94 174,81 48,153" className="hm-bar-top" />
      <polygon points="70,226 196,154 196,94 70,166" className="hm-bar" />
      <polygon points="0,28 52,0 52,310 0,282" className="hm-face" />
      <polygon points="52,0 92,22 92,288 52,310" className="hm-side" />
    </svg>
  );
}

export function HabiLogo({ size = 28, tagline = false, tone = 'auto' }: { size?: number; tagline?: boolean; tone?: 'auto' | 'dark' | 'light' }) {
  return (
    <span className={`habi-logo habi-logo-${tone}`}>
      <HabiMark size={size} tone={tone} />
      <span className="habi-logo-text">
        <span className="habi-wordmark" style={{ fontSize: size * 0.82 }}>HABI</span>
        {tagline && <span className="habi-tagline">Property intelligence for better homes.</span>}
      </span>
    </span>
  );
}
