export function RadarWidget() {
  return (
    <div className="bg-surface-container border border-outline-variant/15 aspect-square relative overflow-hidden shrink-0">
      {/* Dot-grid background */}
      <div
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: "radial-gradient(circle, #424751 1px, transparent 1px)",
          backgroundSize: "16px 16px",
        }}
      />

      {/* Radar rings */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {/* Outermost ring */}
        <div className="absolute w-[80%] aspect-square border border-primary/10 rounded-full" />
        {/* Middle ring */}
        <div className="absolute w-[55%] aspect-square border border-primary/20 rounded-full" />
        {/* Inner ring — pulsing */}
        <div className="absolute w-[30%] aspect-square border border-primary/40 rounded-full animate-ping" />
        {/* Centre dot */}
        <div className="absolute w-1.5 h-1.5 bg-primary" />
      </div>

      {/* Cross-hair lines */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="absolute w-full h-px bg-primary/8" />
        <div className="absolute h-full w-px bg-primary/8" />
      </div>

      {/* Corner labels */}
      <div className="absolute top-2 left-2 font-mono text-[9px] text-outline/60 bg-surface/70 px-1">
        LAT: 51.4902
      </div>
      <div className="absolute bottom-2 right-2 font-mono text-[9px] text-outline/60 bg-surface/70 px-1">
        LON: -0.0146
      </div>
      <div className="absolute top-2 right-2 font-mono text-[9px] text-tertiary">
        LIVE
      </div>
    </div>
  );
}
