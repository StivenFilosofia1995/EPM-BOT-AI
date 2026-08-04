/**
 * Cliente del panel.
 *
 * Todo pasa por `/api/backend/*`, el proxy que añade el token en el servidor.
 * Desde el navegador nunca se llama al backend directamente.
 */

export type Venue = {
  slug: string;
  name: string;
  kind: string;
};

export type RowStatus = "ok" | "warning" | "error";

export type ImportSummary = {
  file_name: string;
  venue_slug: string;
  rows_read: number;
  rows_ok: number;
  rows_warning: number;
  rows_error: number;
  activities: number;
  unknown_columns: string[];
  sheets_skipped: string[];
};

export type PreviewRow = {
  sheet: string;
  row_number: number;
  status: RowStatus;
  title: string | null;
  dates_raw: string | null;
  time_raw: string | null;
  room_raw: string | null;
  audience_raw: string | null;
  activities: number;
  warnings: string[];
  errors: string[];
  starts_at: string[];
};

export type PreviewResult = {
  summary: ImportSummary;
  rows: PreviewRow[];
};

export type ImportResult = {
  summary: ImportSummary;
  ingestion_run_id: string | null;
  activities_inserted: number;
  activities_updated: number;
  skipped_unchanged: boolean;
  message: string;
};

export type Activity = {
  id: string;
  title: string;
  description: string | null;
  venue_slug: string;
  room_name: string | null;
  room_raw: string | null;
  starts_at: string;
  ends_at: string | null;
  audience: string | null;
  audience_raw: string | null;
  age_min: number | null;
  age_max: number | null;
  requires_registration: boolean | null;
  registration_url: string | null;
  status: string;
  confidence: number;
  warnings: string[];
  source_row: string | null;
  evidence_snippet: string | null;
};

export type ActivityPage = {
  items: Activity[];
  total: number;
  limit: number;
  offset: number;
};

/** Error con el mensaje que devolvió la API, no uno genérico. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Saca el mensaje del cuerpo de error.
 *
 * El backend envuelve los errores en `{error: {code, message, details}}`; en
 * las validaciones de FastAPI el detalle útil está en `details`. Se muestra
 * ese texto en vez de un «algo salió mal», porque casi siempre dice
 * exactamente qué columna o qué formato falló.
 */
async function readError(response: Response): Promise<string> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return `El servidor respondió ${response.status}.`;
  }

  const error = (body as { error?: { message?: string; details?: unknown } })
    ?.error;
  if (!error) return `El servidor respondió ${response.status}.`;

  const details = error.details;
  if (Array.isArray(details) && details.length > 0) {
    const first = details[0] as { msg?: string; loc?: unknown[] };
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? first.loc.at(-1) : undefined;
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  if (typeof details === "string") return details;
  return error.message ?? `El servidor respondió ${response.status}.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, init);
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  return (await response.json()) as T;
}

export function listVenues(): Promise<Venue[]> {
  return request<Venue[]>("venues");
}

export type ActivityFilters = {
  venue?: string;
  month?: string;
  status?: string;
  onlyWarnings?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
};

export function listActivities(filters: ActivityFilters): Promise<ActivityPage> {
  const query = new URLSearchParams();
  if (filters.venue) query.set("venue", filters.venue);
  if (filters.month) query.set("month", filters.month);
  if (filters.status) query.set("status", filters.status);
  if (filters.onlyWarnings) query.set("only_warnings", "true");
  if (filters.search) query.set("search", filters.search);
  query.set("limit", String(filters.limit ?? 50));
  query.set("offset", String(filters.offset ?? 0));
  return request<ActivityPage>(`activities?${query.toString()}`);
}

function importForm(file: File, venue: string, month: string): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("venue", venue);
  form.append("month", month);
  return form;
}

export function previewImport(
  file: File,
  venue: string,
  month: string,
): Promise<PreviewResult> {
  return request<PreviewResult>("programacion/import/preview", {
    method: "POST",
    body: importForm(file, venue, month),
  });
}

export function confirmImport(
  file: File,
  venue: string,
  month: string,
  force = false,
): Promise<ImportResult> {
  const form = importForm(file, venue, month);
  if (force) form.append("force", "true");
  return request<ImportResult>("programacion/import", {
    method: "POST",
    body: form,
  });
}
