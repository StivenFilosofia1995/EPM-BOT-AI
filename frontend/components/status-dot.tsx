import { cn } from "@/lib/utils";
import type { RowStatus } from "@/lib/api";

const STYLES: Record<RowStatus, { dot: string; label: string }> = {
  ok: { dot: "bg-emerald-500", label: "Correcta" },
  warning: { dot: "bg-amber-500", label: "Con advertencia" },
  error: { dot: "bg-red-500", label: "Con error" },
};

/**
 * Semáforo de una fila.
 *
 * Lleva texto además del color: el color solo no sirve para quien no
 * distingue verde de rojo, y esta pantalla decide si una parrilla entra o no.
 */
export function StatusDot({
  status,
  className,
}: {
  status: RowStatus;
  className?: string;
}) {
  const style = STYLES[status];
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span
        aria-hidden
        className={cn("size-2 shrink-0 rounded-full", style.dot)}
      />
      <span className="text-sm">{style.label}</span>
    </span>
  );
}
