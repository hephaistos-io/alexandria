interface ProgressBarProps {
  percent: number;
  color?: string;
}

export function ProgressBar({ percent, color = "bg-primary-container" }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div className="h-1.5 bg-surface-container-lowest w-full">
      <div
        className={`h-full transition-all ${color}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
