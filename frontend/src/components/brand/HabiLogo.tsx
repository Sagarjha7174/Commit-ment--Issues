import type { CSSProperties, SVGProps } from 'react';

export type LogoVariant = 'full' | 'symbol' | 'mono-dark' | 'mono-light' | 'on-orange';

export interface HabiLogoProps extends SVGProps<SVGSVGElement> {
  variant?: LogoVariant;
  size?: number | string;
  showTagline?: boolean;
  className?: string;
  style?: CSSProperties;
}

/**
 * HABI brand logo component.
 * Features an "H" made of two isometric pillars with pointed caps, joined by an orange isometric bar at 45°.
 * Variants:
 *  - full: symbol + "HABI" wordmark + tagline
 *  - symbol: symbol only
 *  - mono-dark: monochrome ink for light surfaces
 *  - mono-light: monochrome paper/white for dark surfaces
 *  - on-orange: white pillars with ink/contrast bar on orange ground
 */
export function HabiLogo({
  variant = 'full',
  size,
  showTagline = true,
  className = '',
  style,
  ...props
}: HabiLogoProps) {
  // Determine color palette based on variant
  const isMonoDark = variant === 'mono-dark';
  const isMonoLight = variant === 'mono-light';
  const isOnOrange = variant === 'on-orange';

  // Pillar colors
  let pShadow = '#121512';
  let pMid = '#191E19';
  let pCapLeft = '#222822';
  let pCapRight = '#2E352E';

  // Bar colors
  let bTop = '#FF7A5C';
  let bFront = '#FF512F';
  let bSide = '#D63D1B';

  // Text colors
  let textTitle = 'var(--ink, #191E19)';
  let textTagline = 'var(--ink-muted, #5F665D)';

  if (isMonoDark) {
    pShadow = '#101310';
    pMid = '#191E19';
    pCapLeft = '#222822';
    pCapRight = '#2E352E';
    bTop = '#2E352E';
    bFront = '#191E19';
    bSide = '#101310';
    textTitle = '#191E19';
    textTagline = '#5F665D';
  } else if (isMonoLight) {
    pShadow = '#D7D4CA';
    pMid = '#F3F0E8';
    pCapLeft = '#E2DFD6';
    pCapRight = '#FFFFFF';
    bTop = '#FFFFFF';
    bFront = '#F3F0E8';
    bSide = '#D7D4CA';
    textTitle = '#F3F0E8';
    textTagline = '#D7D4CA';
  } else if (isOnOrange) {
    pShadow = '#E2DFD6';
    pMid = '#FFFFFF';
    pCapLeft = '#F3F0E8';
    pCapRight = '#FFFFFF';
    bTop = '#2E352E';
    bFront = '#191E19';
    bSide = '#121512';
    textTitle = '#191E19';
    textTagline = '#191E19';
  }

  // Symbol element reusable in symbol and full views
  const renderSymbol = () => (
    <g className="habi-symbol">
      {/* Background if on-orange variant */}
      {isOnOrange && (
        <rect width="64" height="64" rx="4" fill="#FF512F" />
      )}

      {/* Left Pillar */}
      {/* Left shadow face */}
      <polygon points="10,14 18,18 18,58 10,54" fill={pShadow} />
      {/* Right midtone face */}
      <polygon points="18,18 26,14 26,54 18,58" fill={pMid} />
      {/* Pointed cap: left facet */}
      <polygon points="18,6 10,14 18,18" fill={pCapLeft} />
      {/* Pointed cap: right facet */}
      <polygon points="18,6 18,18 26,14" fill={pCapRight} />

      {/* Isometric 45-degree Connecting Bar */}
      {/* Top face (highlight) */}
      <polygon points="24,34 27,32 43,24 40,26" fill={bTop} />
      {/* Front face (signal orange) */}
      <polygon points="24,34 40,26 40,36 24,44" fill={bFront} />
      {/* Right/under edge (shadow) */}
      <polygon points="40,26 43,24 43,34 40,36" fill={bSide} />

      {/* Right Pillar */}
      {/* Left shadow face */}
      <polygon points="38,14 46,18 46,58 38,54" fill={pShadow} />
      {/* Right midtone face */}
      <polygon points="46,18 54,14 54,54 46,58" fill={pMid} />
      {/* Pointed cap: left facet */}
      <polygon points="46,6 38,14 46,18" fill={pCapLeft} />
      {/* Pointed cap: right facet */}
      <polygon points="46,6 46,18 54,14" fill={pCapRight} />
    </g>
  );

  if (variant === 'symbol' || isMonoDark || isMonoLight || isOnOrange) {
    const s = size ?? 32;
    return (
      <svg
        width={s}
        height={s}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`habi-logo habi-logo-symbol ${className}`}
        style={style}
        role="img"
        aria-label="HABI logo"
        {...props}
      >
        <title>HABI</title>
        {renderSymbol()}
      </svg>
    );
  }

  // Full variant: Symbol + Wordmark
  const defaultHeight = size ?? 36;
  return (
    <svg
      height={defaultHeight}
      viewBox="0 0 220 54"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`habi-logo habi-logo-full ${className}`}
      style={style}
      role="img"
      aria-label="HABI - Property intelligence for better homes."
      {...props}
    >
      <title>HABI - Property intelligence for better homes.</title>
      {/* Symbol scaled into left slot */}
      <g transform="translate(-2, -5)">
        {renderSymbol()}
      </g>
      {/* Wordmark "HABI" */}
      <g transform="translate(62, 0)">
        <text
          x="0"
          y="30"
          fontFamily="'Inter', 'Helvetica Neue', Arial, sans-serif"
          fontWeight="900"
          fontSize="28"
          letterSpacing="0.08em"
          fill={textTitle}
        >
          HABI
        </text>
        {showTagline && (
          <text
            x="0"
            y="43"
            fontFamily="'Inter', 'Helvetica Neue', Arial, sans-serif"
            fontWeight="500"
            fontSize="8.5"
            letterSpacing="0.02em"
            fill={textTagline}
          >
            Property intelligence for better homes.
          </text>
        )}
      </g>
    </svg>
  );
}

export default HabiLogo;
