interface MetricCardProps {
  label: string;
  value: string;
  accentColor?: string;
  onClick?: () => void;
  valueClassName?: string;
  children?: React.ReactNode;
}

export function MetricCard({
  label,
  value,
  accentColor = "border-primary",
  onClick,
  valueClassName,
  children,
}: MetricCardProps) {
  const isInteractive = onClick !== undefined;

  const baseClasses = `bg-surface-container p-4 border-l-2 ${accentColor}`;
  const interactiveClasses = isInteractive
    ? "cursor-pointer hover:bg-primary transition-colors group"
    : "";

  const defaultValueColor = isInteractive
    ? "text-on-surface group-hover:text-on-primary"
    : "text-on-surface";
  const resolvedValueClass = valueClassName ?? defaultValueColor;

  return (
    <div className={`${baseClasses} ${interactiveClasses}`} onClick={onClick}>
      <p className="font-mono text-[10px] text-outline mb-1">{label}</p>
      {children ?? (
        <p className={`text-2xl font-headline font-black ${resolvedValueClass}`}>
          {value}
        </p>
      )}
    </div>
  );
}
