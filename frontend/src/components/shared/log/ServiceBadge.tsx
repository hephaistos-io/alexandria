import { serviceColour } from "./logStyles";

interface ServiceBadgeProps {
  service: string;
  /** Override layout/spacing classes. Colour classes are always applied from
   *  the shared palette — only pass classes that control padding, margin,
   *  rounding, etc. */
  className?: string;
}

export function ServiceBadge({
  service,
  className = "px-1.5 py-0 mr-2 shrink-0",
}: ServiceBadgeProps) {
  return (
    <span
      className={`inline-block font-mono text-[9px] leading-tight ${className} ${serviceColour(service)}`}
    >
      {service}
    </span>
  );
}
