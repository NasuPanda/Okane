// Mr. Kentaro, the tour guide (docs/ASSUMPTIONS.md A39): an original 2D mascot. A traditional
// Japanese office worker (dark suit, white shirt, red tie, round glasses) wearing a samurai
// kabuto with a golden crescent crest, for dramatic effect.
export type Pose = "wave" | "point" | "think";

const SKIN = "#f6d2ad";
const SUIT = "#24314f";
const LACQUER = "#23232b";
const GOLD = "#f2c14e";
const RED = "#c8323a";
const INK = "#1d1d24";

const STEEL = "#dfe6ee";

/** Full samurai armour for the farewell (A39). Every piece unfolds downward from the helmet's rim
 *  (`armour-piece`, index.css), one after another. */
function Armour() {
  const piece = (delay: number) => ({ className: "armour-piece", style: { "--d": `${delay}ms` } as React.CSSProperties });
  const lacing = (y: number, x1: number, x2: number) => (
    <path d={`M${x1} ${y}H${x2}`} stroke={RED} strokeWidth="2" strokeDasharray="3 2" />
  );
  return (
    <g>
      {/* kusazuri: the skirt of plates */}
      <g {...piece(320)}>
        {[34, 48, 62, 76, 90].map((x) => (
          <g key={x}>
            <rect x={x} y="152" width="13" height="18" rx="2" fill={LACQUER} stroke={GOLD} strokeWidth="1" />
            {lacing(158, x + 2, x + 11)}
            {lacing(164, x + 2, x + 11)}
          </g>
        ))}
      </g>
      {/* do: the chest plate, with lacing rows and a crest */}
      <g {...piece(120)}>
        <path d="M42 122 Q70 112 98 122 L100 154 Q70 162 40 154 Z" fill={LACQUER} stroke={GOLD} strokeWidth="1.6" />
        {lacing(134, 46, 94)}
        {lacing(142, 45, 95)}
        {lacing(150, 45, 95)}
        <circle cx="70" cy="127" r="5" fill={GOLD} />
        <circle cx="70" cy="127" r="2" fill={RED} />
      </g>
      {/* kote: the armoured sleeve of the resting arm */}
      <g {...piece(220)}>
        <path d="M42 126 L34 158" stroke={LACQUER} strokeWidth="13" strokeLinecap="round" />
        <path d="M42 126 L34 158" stroke={RED} strokeWidth="2" strokeDasharray="3 4" />
      </g>
      {/* sode: the big shoulder plates */}
      <g {...piece(0)}>
        <path d="M24 118 L46 113 L48 142 L27 147 Z" fill={LACQUER} stroke={GOLD} strokeWidth="1.5" />
        {lacing(124, 27, 46)}
        {lacing(131, 27, 47)}
        {lacing(138, 28, 47)}
        <path d="M94 113 L116 118 L113 147 L92 142 Z" fill={LACQUER} stroke={GOLD} strokeWidth="1.5" />
        {lacing(124, 94, 114)}
        {lacing(131, 93, 114)}
        {lacing(138, 93, 113)}
      </g>
      {/* the raised arm with its sleeve, and the katana */}
      <g {...piece(450)}>
        <path d="M128 14 Q127 52 119 94" stroke={STEEL} strokeWidth="4" strokeLinecap="round" fill="none" />
        <path d="M128 14 Q127 52 119 94" stroke="#ffffff" strokeWidth="1" strokeLinecap="round" fill="none" opacity="0.8" />
        <ellipse cx="119.5" cy="96" rx="7" ry="2.6" fill={GOLD} transform="rotate(-12 119.5 96)" />
        <path d="M119 98 L116 112" stroke={INK} strokeWidth="4.5" strokeLinecap="round" />
        <path d="M98 126 L116 101" stroke={LACQUER} strokeWidth="13" strokeLinecap="round" />
        <path d="M98 126 L116 101" stroke={RED} strokeWidth="2" strokeDasharray="3 4" />
        <circle cx="118" cy="101" r="6" fill={SKIN} />
      </g>
    </g>
  );
}

export function Kentaro({ pose = "point", className, armoured = false }: { pose?: Pose; className?: string; armoured?: boolean }) {
  const happy = pose === "wave" || armoured;
  return (
    <svg viewBox="0 0 140 172" className={className} role="img" aria-label="Mr. Kentaro, your guide">
      {/* shadow */}
      <ellipse cx="70" cy="168" rx="38" ry="4" fill={INK} opacity="0.18" />

      {/* neck guard of the helmet (shikoro): lacquered plates laced in red, behind the head */}
      <path d="M37 64 L27 99 Q70 117 113 99 L103 64 Z" fill={LACQUER} />
      <path d="M31 82 Q70 100 109 82" stroke={RED} strokeWidth="2.4" fill="none" />
      <path d="M28 93 Q70 111 112 93" stroke={RED} strokeWidth="2.4" fill="none" />

      {/* resting arm (viewer's left) */}
      <path d="M42 126 L34 158" stroke={SUIT} strokeWidth="12" strokeLinecap="round" />
      <circle cx="33" cy="161" r="5.5" fill={SKIN} />

      {/* suit */}
      <path d="M30 172 L38 126 Q70 112 102 126 L110 172 Z" fill={SUIT} />
      <path d="M58 118 L70 150 L82 118 Z" fill="#fff" />
      <path d="M66 124 L74 124 L77 150 L70 159 L63 150 Z" fill={RED} />
      <path d="M66 124 L74 124 L72 130 L68 130 Z" fill="#9e2229" />
      <path d="M56 118 L70 150 L60 124 Z" fill="#1a2440" />
      <path d="M84 118 L70 150 L80 124 Z" fill="#1a2440" />
      <circle cx="70" cy="160" r="1.6" fill="#0f1528" />

      {/* active arm */}
      {pose === "wave" && !armoured && (
        <g>
          <path d="M98 126 L116 98" stroke={SUIT} strokeWidth="12" strokeLinecap="round" />
          <circle cx="119" cy="92" r="6" fill={SKIN} />
          <path d="M115 85 l-2 -6 M119 84 l0 -7 M123 85 l2 -6" stroke={SKIN} strokeWidth="3" strokeLinecap="round" />
        </g>
      )}
      {pose === "point" && !armoured && (
        <g>
          <path d="M98 128 L126 122" stroke={SUIT} strokeWidth="12" strokeLinecap="round" />
          <circle cx="129" cy="121" r="5.5" fill={SKIN} />
          <path d="M132 120 L139 118" stroke={SKIN} strokeWidth="3.2" strokeLinecap="round" />
        </g>
      )}
      {pose === "think" && !armoured && (
        <g>
          <path d="M100 132 L90 112" stroke={SUIT} strokeWidth="12" strokeLinecap="round" />
          <circle cx="86" cy="106" r="5.5" fill={SKIN} />
        </g>
      )}

      {armoured && <Armour />}

      {/* neck and head */}
      <rect x="63" y="104" width="14" height="14" rx="4" fill="#eac39c" />
      <circle cx="42" cy="86" r="6" fill={SKIN} />
      <circle cx="98" cy="86" r="6" fill={SKIN} />
      <circle cx="70" cy="84" r="28" fill={SKIN} />

      {/* kabuto bowl, red rim and side flaps (fukigaeshi), sitting above the brows */}
      <path d="M40 66 Q41 36 70 34 Q99 36 100 66 Z" fill={LACQUER} />
      <path d="M47 45 Q70 33 93 45" stroke="#3a3a46" strokeWidth="2" fill="none" />
      <path d="M43 55 Q70 43 97 55" stroke="#3a3a46" strokeWidth="2" fill="none" />
      <path d="M37 63 Q70 57 103 63 L103 68 Q70 62 37 68 Z" fill={RED} />
      <path d="M38 64 L24 55 Q22 68 35 73 Z" fill={LACQUER} stroke={GOLD} strokeWidth="1.5" />
      <path d="M102 64 L116 55 Q118 68 105 73 Z" fill={LACQUER} stroke={GOLD} strokeWidth="1.5" />

      {/* golden crescent crest (maedate), rising from the front emblem */}
      <path d="M34 34 Q70 -8 106 34 Q70 18 34 34 Z" fill={GOLD} stroke="#c99a2e" strokeWidth="1" />
      <circle cx="70" cy="34" r="6.5" fill={GOLD} stroke="#c99a2e" strokeWidth="1" />
      <circle cx="70" cy="34" r="2.6" fill={RED} />

      {/* brows: a little dramatic */}
      <path d={happy ? "M52 72 Q58 69 64 72" : "M51 71 L64 75"} stroke={INK} strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d={happy ? "M76 72 Q82 69 88 72" : "M89 71 L76 75"} stroke={INK} strokeWidth="3" strokeLinecap="round" fill="none" />

      {/* round glasses and eyes */}
      <circle cx="58" cy="84" r="8" fill="#fff" fillOpacity="0.35" stroke={INK} strokeWidth="2.2" />
      <circle cx="82" cy="84" r="8" fill="#fff" fillOpacity="0.35" stroke={INK} strokeWidth="2.2" />
      <path d="M66 83 Q70 80 74 83" stroke={INK} strokeWidth="2" fill="none" />
      {happy ? (
        <>
          <path d="M54 86 Q58 81 62 86" stroke={INK} strokeWidth="2.2" fill="none" strokeLinecap="round" />
          <path d="M78 86 Q82 81 86 86" stroke={INK} strokeWidth="2.2" fill="none" strokeLinecap="round" />
        </>
      ) : (
        <>
          <circle cx={pose === "think" ? 60 : 58} cy={pose === "think" ? 82 : 85} r="2.4" fill={INK} />
          <circle cx={pose === "think" ? 84 : 82} cy={pose === "think" ? 82 : 85} r="2.4" fill={INK} />
        </>
      )}

      {/* cheeks and mouth */}
      <circle cx="50" cy="96" r="3.5" fill="#f29a9a" opacity="0.6" />
      <circle cx="90" cy="96" r="3.5" fill="#f29a9a" opacity="0.6" />
      {pose === "think" ? (
        <path d="M64 100 L76 99" stroke={INK} strokeWidth="2.2" strokeLinecap="round" />
      ) : (
        <path d="M61 98 Q70 106 79 98" stroke={INK} strokeWidth="2.4" fill={happy ? "#8c2b2b" : "none"} strokeLinecap="round" />
      )}
      {armoured && <circle className="armour-flash" cx="70" cy="50" r="44" fill="none" stroke={GOLD} strokeWidth="4" />}
    </svg>
  );
}
