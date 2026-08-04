"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { SearchIcon, TriangleAlertIcon } from "lucide-react";

import {
  ApiError,
  listActivities,
  listVenues,
  type Activity,
  type Venue,
} from "@/lib/api";
import {
  audienceLabel,
  formatDate,
  formatTime,
  monthOptions,
  warningLabel,
} from "@/lib/format";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const PAGE_SIZE = 50;

const SELECT_CLASS =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30";

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  published: "Publicada",
  archived: "Archivada",
};

function Missing() {
  return <span className="text-muted-foreground/60">sin dato</span>;
}

export function ActivityBrowser() {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venue, setVenue] = useState("");
  const [month, setMonth] = useState("");
  const [status, setStatus] = useState("");
  const [onlyWarnings, setOnlyWarnings] = useState(false);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [offset, setOffset] = useState(0);

  const [items, setItems] = useState<Activity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const months = monthOptions();

  useEffect(() => {
    listVenues()
      .then(setVenues)
      .catch(() => setVenues([]));
  }, []);

  // La búsqueda espera a que el usuario deje de escribir: cada tecla sería una
  // consulta a la base.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search);
      setOffset(0);
      setLoading(true);
    }, 350);
    return () => clearTimeout(timer);
  }, [search]);

  // El efecto solo lanza la petición; el estado se actualiza en el callback,
  // nunca de forma síncrona dentro del efecto. `cancelled` descarta la
  // respuesta de una consulta que ya quedó obsoleta porque el usuario cambió
  // un filtro: sin esto, una petición lenta puede pisar a una más reciente.
  useEffect(() => {
    let cancelled = false;
    listActivities({
      venue: venue || undefined,
      month: month || undefined,
      status: status || undefined,
      onlyWarnings,
      search: debounced || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setItems([]);
        setTotal(0);
        setError(
          err instanceof ApiError
            ? err.message
            : "No se pudo consultar la programación.",
        );
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [venue, month, status, onlyWarnings, debounced, offset]);

  /** Cambiar un filtro vuelve a la primera página y muestra el esqueleto. */
  function change<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setOffset(0);
      setLoading(true);
    };
  }

  function goTo(next: number) {
    setOffset(next);
    setLoading(true);
  }

  const showing = items.length;
  const from = total === 0 ? 0 : offset + 1;
  const to = offset + showing;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="f-venue">Espacio</Label>
          <select
            id="f-venue"
            className={SELECT_CLASS}
            value={venue}
            onChange={(e) => change(setVenue)(e.target.value)}
          >
            <option value="">Todos</option>
            {venues.map((v) => (
              <option key={v.slug} value={v.slug}>
                {v.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="f-month">Mes</Label>
          <select
            id="f-month"
            className={SELECT_CLASS}
            value={month}
            onChange={(e) => change(setMonth)(e.target.value)}
          >
            <option value="">Todos</option>
            {months.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="f-status">Estado</Label>
          <select
            id="f-status"
            className={SELECT_CLASS}
            value={status}
            onChange={(e) => change(setStatus)(e.target.value)}
          >
            <option value="">Todos</option>
            <option value="draft">Borrador</option>
            <option value="published">Publicada</option>
            <option value="archived">Archivada</option>
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="f-search">Buscar</Label>
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="f-search"
              value={search}
              placeholder="Título o descripción"
              className="pl-8"
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="flex items-end">
          <label className="flex h-8 cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={onlyWarnings}
              onChange={(e) => change(setOnlyWarnings)(e.target.checked)}
            />
            Solo con advertencias
          </label>
        </div>
      </div>

      {error ? (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>No se pudo cargar</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState hasFilters={Boolean(venue || month || status || onlyWarnings || debounced)} />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Actividad</TableHead>
                  <TableHead className="w-56">Cuándo</TableHead>
                  <TableHead className="w-40">Lugar</TableHead>
                  <TableHead className="w-32">Público</TableHead>
                  <TableHead className="w-28">Estado</TableHead>
                  <TableHead className="w-56">Advertencias</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="align-top">
                      <div className="font-medium">{a.title}</div>
                      {a.description ? (
                        <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                          {a.description}
                        </div>
                      ) : null}
                      {a.registration_url ? (
                        <a
                          href={a.registration_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 inline-block text-xs underline underline-offset-4"
                        >
                          Enlace de inscripción
                        </a>
                      ) : null}
                    </TableCell>
                    <TableCell className="align-top">
                      <div className="text-sm">{formatDate(a.starts_at)}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatTime(a.starts_at)}
                        {a.ends_at ? ` a ${formatTime(a.ends_at)}` : ""}
                      </div>
                    </TableCell>
                    <TableCell className="align-top text-sm">
                      {a.room_name ?? a.room_raw ?? <Missing />}
                    </TableCell>
                    <TableCell className="align-top text-sm">
                      {audienceLabel(a.audience) ?? a.audience_raw ?? (
                        <Missing />
                      )}
                    </TableCell>
                    <TableCell className="align-top">
                      <Badge variant={a.status === "draft" ? "secondary" : "outline"}>
                        {STATUS_LABELS[a.status] ?? a.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="align-top">
                      {a.warnings.length === 0 ? (
                        <span className="text-xs text-muted-foreground/60">
                          ninguna
                        </span>
                      ) : (
                        <ul className="flex flex-col gap-1">
                          {a.warnings.map((w) => (
                            <li key={w} className="text-xs text-amber-600 dark:text-amber-400">
                              {warningLabel(w)}
                            </li>
                          ))}
                        </ul>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Mostrando {from}–{to} de {total}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => goTo(Math.max(0, offset - PAGE_SIZE))}
              >
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={to >= total}
                onClick={() => goTo(offset + PAGE_SIZE)}
              >
                Siguiente
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Estado vacío.
 *
 * Distingue «no hay nada cargado» de «los filtros no devuelven nada»: son
 * problemas distintos y la acción que corresponde también.
 */
function EmptyState({ hasFilters }: { hasFilters: boolean }) {
  return (
    <div className="rounded-lg border border-dashed px-6 py-12 text-center">
      {hasFilters ? (
        <>
          <p className="text-sm font-medium">
            Ninguna actividad coincide con los filtros
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Prueba con otro mes o quita algún filtro.
          </p>
        </>
      ) : (
        <>
          <p className="text-sm font-medium">Todavía no hay programación</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Sube el Excel del mes para empezar.
          </p>
          <Button
            className="mt-4"
            render={<Link href="/programacion/importar" />}
          >
            Cargar programación
          </Button>
        </>
      )}
    </div>
  );
}
