"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2Icon,
  FileSpreadsheetIcon,
  Loader2Icon,
  TriangleAlertIcon,
  UploadIcon,
  XIcon,
} from "lucide-react";

import {
  ApiError,
  confirmImport,
  listVenues,
  previewImport,
  type ImportResult,
  type PreviewResult,
  type Venue,
} from "@/lib/api";
import {
  currentMonth,
  formatDateTime,
  monthLabel,
  monthOptions,
  warningLabel,
} from "@/lib/format";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { StatusDot } from "@/components/status-dot";
import { cn } from "@/lib/utils";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".xlsx,.xlsm";

/** Estilo del `<select>` nativo, alineado con el resto de controles. */
const SELECT_CLASS =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30";

/** Texto para un dato que el Excel no trae. Nunca se inventa un valor. */
function Missing() {
  return <span className="text-muted-foreground/60">sin dato</span>;
}

export function ImportForm() {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [venuesError, setVenuesError] = useState<string | null>(null);
  const [loadingVenues, setLoadingVenues] = useState(true);

  const [venue, setVenue] = useState("");
  const [month, setMonth] = useState(currentMonth());
  const [file, setFile] = useState<File | null>(null);

  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const months = monthOptions();

  useEffect(() => {
    listVenues()
      .then((data) => {
        setVenues(data);
        // No se preselecciona ninguno: elegir el espacio equivocado significa
        // meter la parrilla de un museo en una biblioteca.
      })
      .catch((err: unknown) =>
        setVenuesError(
          err instanceof ApiError
            ? err.message
            : "No se pudo cargar la lista de espacios.",
        ),
      )
      .finally(() => setLoadingVenues(false));
  }, []);

  /** Cualquier cambio invalida lo que ya se había interpretado. */
  function reset() {
    setPreview(null);
    setResult(null);
    setError(null);
  }

  function acceptFile(candidate: File | undefined) {
    reset();
    if (!candidate) return;
    const name = candidate.name.toLowerCase();
    if (!name.endsWith(".xlsx") && !name.endsWith(".xlsm")) {
      setError(`«${candidate.name}» no es un Excel. Se admiten .xlsx y .xlsm.`);
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError(
        `«${candidate.name}» pesa más de 10 MB. Revisa si el archivo trae imágenes pegadas.`,
      );
      return;
    }
    setFile(candidate);
  }

  async function onPreview() {
    if (!file || !venue) return;
    setBusy("preview");
    setError(null);
    setResult(null);
    try {
      setPreview(await previewImport(file, venue, month));
    } catch (err: unknown) {
      setPreview(null);
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo leer el archivo. Revisa que sea la parrilla del mes.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function onConfirm(force = false) {
    if (!file || !venue) return;
    setBusy("import");
    setError(null);
    try {
      setResult(await confirmImport(file, venue, month, force));
    } catch (err: unknown) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo guardar la programación.",
      );
    } finally {
      setBusy(null);
    }
  }

  function startOver() {
    setFile(null);
    reset();
    if (inputRef.current) inputRef.current.value = "";
  }

  const canPreview = Boolean(file && venue && !busy);
  const venueName = venues.find((v) => v.slug === venue)?.name ?? venue;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. Elige el archivo</CardTitle>
          <CardDescription>
            El espacio y el mes deben corresponder al contenido del Excel.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="venue">Espacio</Label>
              <select
                id="venue"
                className={SELECT_CLASS}
                value={venue}
                disabled={loadingVenues || venues.length === 0}
                onChange={(e) => {
                  setVenue(e.target.value);
                  reset();
                }}
              >
                <option value="">
                  {loadingVenues ? "Cargando…" : "Selecciona un espacio"}
                </option>
                {venues.map((v) => (
                  <option key={v.slug} value={v.slug}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="month">Mes de la parrilla</Label>
              <select
                id="month"
                className={SELECT_CLASS}
                value={month}
                onChange={(e) => {
                  setMonth(e.target.value);
                  reset();
                }}
              >
                {months.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {venuesError ? (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>No hay espacios disponibles</AlertTitle>
              <AlertDescription>{venuesError}</AlertDescription>
            </Alert>
          ) : null}

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              acceptFile(e.dataTransfer.files?.[0]);
            }}
            className={cn(
              "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
              dragging ? "border-ring bg-muted/50" : "border-input",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => acceptFile(e.target.files?.[0])}
            />
            {file ? (
              <>
                <FileSpreadsheetIcon className="size-6 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(0)} KB
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={startOver}>
                  <XIcon /> Quitar
                </Button>
              </>
            ) : (
              <>
                <UploadIcon className="size-6 text-muted-foreground" />
                <div>
                  <p className="text-sm">
                    Arrastra aquí el Excel de la programación
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Formatos .xlsx o .xlsm · hasta 10 MB
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => inputRef.current?.click()}
                >
                  Buscar en el equipo
                </Button>
              </>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={onPreview} disabled={!canPreview}>
              {busy === "preview" ? (
                <Loader2Icon className="animate-spin" />
              ) : null}
              Ver qué se interpretó
            </Button>
            {!venue && file ? (
              <p className="text-xs text-muted-foreground">
                Falta elegir el espacio.
              </p>
            ) : null}
          </div>

          {error ? (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>No se pudo continuar</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {preview ? (
        <PreviewPanel
          preview={preview}
          venueName={venueName}
          month={month}
          result={result}
          busy={busy === "import"}
          onConfirm={() => onConfirm(false)}
          onForce={() => onConfirm(true)}
          onCancel={startOver}
        />
      ) : null}
    </div>
  );
}

function PreviewPanel({
  preview,
  venueName,
  month,
  result,
  busy,
  onConfirm,
  onForce,
  onCancel,
}: {
  preview: PreviewResult;
  venueName: string;
  month: string;
  result: ImportResult | null;
  busy: boolean;
  onConfirm: () => void;
  onForce: () => void;
  onCancel: () => void;
}) {
  const s = preview.summary;
  const hasErrors = s.rows_error > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>2. Revisa antes de guardar</CardTitle>
        <CardDescription>
          Esto es lo que se leyó de <strong>{s.file_name}</strong> para{" "}
          {venueName}, {monthLabel(month)}. Todavía no se ha guardado nada.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Filas leídas" value={s.rows_read} />
          <Stat label="Correctas" value={s.rows_ok} tone="ok" />
          <Stat label="Con advertencia" value={s.rows_warning} tone="warning" />
          <Stat label="Con error" value={s.rows_error} tone="error" />
          <Stat label="Actividades" value={s.activities} />
        </div>

        <p className="text-xs text-muted-foreground">
          Una fila puede generar varias actividades: «todos los martes» se
          expande a una por fecha. Las horas se muestran en hora de Colombia
          (America/Bogotá).
        </p>

        {s.unknown_columns.length > 0 ? (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Columnas que no se reconocieron</AlertTitle>
            <AlertDescription>
              Se ignoraron: {s.unknown_columns.join(", ")}. Si contienen datos
              necesarios, revisa el contrato del Excel antes de guardar.
            </AlertDescription>
          </Alert>
        ) : null}

        {s.sheets_skipped.length > 0 ? (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Hojas omitidas</AlertTitle>
            <AlertDescription>
              No se leyeron: {s.sheets_skipped.join(", ")}. Suele pasar cuando
              la hoja no tiene la fila de encabezados esperada.
            </AlertDescription>
          </Alert>
        ) : null}

        {preview.rows.length === 0 ? (
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>El archivo no tiene filas de programación</AlertTitle>
            <AlertDescription>
              No se encontró ninguna fila con datos. Revisa que sea el archivo
              correcto y que conserve la fila de encabezados.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-40">Estado</TableHead>
                  <TableHead className="w-16">Fila</TableHead>
                  <TableHead>Título</TableHead>
                  <TableHead>Fechas en el archivo</TableHead>
                  <TableHead>Horario</TableHead>
                  <TableHead>Lugar</TableHead>
                  <TableHead>Público</TableHead>
                  <TableHead className="w-20 text-right">Activid.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.rows.map((row) => (
                  <TableRow key={`${row.sheet}-${row.row_number}`}>
                    <TableCell className="align-top">
                      <StatusDot status={row.status} />
                      {row.warnings.length > 0 || row.errors.length > 0 ? (
                        <ul className="mt-1.5 flex flex-col gap-1">
                          {row.errors.map((e) => (
                            <li key={e} className="text-xs text-destructive">
                              {e}
                            </li>
                          ))}
                          {row.warnings.map((w) => (
                            <li
                              key={w}
                              className="text-xs text-muted-foreground"
                            >
                              {warningLabel(w)}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </TableCell>
                    <TableCell className="align-top text-xs text-muted-foreground">
                      <div>{row.row_number}</div>
                      <div className="mt-0.5">{row.sheet}</div>
                    </TableCell>
                    <TableCell className="align-top font-medium">
                      {row.title ?? <Missing />}
                    </TableCell>
                    <TableCell className="align-top">
                      <div>{row.dates_raw ?? <Missing />}</div>
                      {row.starts_at.length > 0 ? (
                        <div className="mt-1 text-xs text-muted-foreground">
                          {row.starts_at.slice(0, 3).map((iso) => (
                            <div key={iso}>{formatDateTime(iso)}</div>
                          ))}
                          {row.starts_at.length > 3 ? (
                            <div>y {row.starts_at.length - 3} más</div>
                          ) : null}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="align-top">
                      {row.time_raw ?? <Missing />}
                    </TableCell>
                    <TableCell className="align-top">
                      {row.room_raw ?? <Missing />}
                    </TableCell>
                    <TableCell className="align-top">
                      {row.audience_raw ?? <Missing />}
                    </TableCell>
                    <TableCell className="align-top text-right tabular-nums">
                      {row.activities}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {result ? (
          <Alert>
            {result.skipped_unchanged ? (
              <TriangleAlertIcon />
            ) : (
              <CheckCircle2Icon className="text-emerald-600" />
            )}
            <AlertTitle>
              {result.skipped_unchanged
                ? "No había nada que guardar"
                : "Programación guardada como borrador"}
            </AlertTitle>
            <AlertDescription>
              <p>{result.message}</p>
              {result.skipped_unchanged ? null : (
                <p className="mt-1">
                  {result.activities_inserted} actividades nuevas ·{" "}
                  {result.activities_updated} actualizadas. Nada está publicado
                  todavía.
                </p>
              )}
              <p className="mt-2 flex flex-wrap gap-3">
                {result.skipped_unchanged ? (
                  <button
                    type="button"
                    onClick={onForce}
                    disabled={busy}
                    className="underline underline-offset-4 disabled:opacity-50"
                  >
                    Reimportar de todos modos
                  </button>
                ) : null}
                <Link
                  href="/programacion"
                  className="underline underline-offset-4"
                >
                  Ver la programación cargada
                </Link>
                <button
                  type="button"
                  onClick={onCancel}
                  className="underline underline-offset-4"
                >
                  Cargar otro archivo
                </button>
              </p>
            </AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={onConfirm} disabled={busy || hasErrors}>
              {busy ? <Loader2Icon className="animate-spin" /> : null}
              Guardar como borrador
            </Button>
            <Button variant="ghost" onClick={onCancel} disabled={busy}>
              Cancelar
            </Button>
            {hasErrors ? (
              <p className="text-xs text-destructive">
                Hay filas con error. Corrígelas en el Excel y vuelve a subirlo.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Se guarda como borrador. La publicación es un paso aparte.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "ok" | "warning" | "error";
}) {
  const emphasise = tone && value > 0;
  return (
    <div className="rounded-lg border px-3 py-2">
      <div
        className={cn(
          "text-xl font-semibold tabular-nums",
          emphasise && tone === "ok" && "text-emerald-600 dark:text-emerald-400",
          emphasise && tone === "warning" && "text-amber-600 dark:text-amber-400",
          emphasise && tone === "error" && "text-destructive",
        )}
      >
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
