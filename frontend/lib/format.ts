/**
 * Presentación de datos del backend.
 *
 * Regla del proyecto: la base de datos guarda UTC y el usuario ve
 * `America/Bogota`. La conversión se hace SOLO aquí, con `Intl`, pasando la
 * zona explícita. Nunca con aritmética de horas a mano ni dependiendo de la
 * zona del navegador: quien revise la parrilla desde otro huso debe ver la
 * hora de Medellín, no la suya.
 */

export const BOGOTA = "America/Bogota";

const dateTimeFormatter = new Intl.DateTimeFormat("es-CO", {
  timeZone: BOGOTA,
  weekday: "short",
  day: "2-digit",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const dateFormatter = new Intl.DateTimeFormat("es-CO", {
  timeZone: BOGOTA,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

const timeFormatter = new Intl.DateTimeFormat("es-CO", {
  timeZone: BOGOTA,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

export function formatDateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso));
}

export function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

/** Mes en formato `AAAA-MM` a partir de una fecha UTC, en hora de Bogotá. */
export function monthOf(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: BOGOTA,
    year: "numeric",
    month: "2-digit",
  }).format(new Date(iso));
  return parts;
}

/**
 * Advertencias en español.
 *
 * Los códigos vienen del importador (`IngestionWarning`). Si aparece uno que
 * no está en esta tabla se muestra el código crudo: es preferible un código
 * feo pero cierto a esconder una advertencia que no supimos traducir.
 */
const WARNING_LABELS: Record<string, string> = {
  out_of_month: "Fecha fuera del mes indicado",
  room_fuzzy_match: "El salón se emparejó por aproximación",
  room_unknown: "Salón no reconocido",
  registration_unresolved: "No se pudo determinar si requiere inscripción",
  registration_inconsistent: "La inscripción se contradice con el enlace",
  registro_no_es_url: "El campo de inscripción no es un enlace",
  audience_from_sheet_name: "Público deducido del nombre de la hoja",
  month_from_parameter: "Mes tomado del formulario, no del archivo",
  no_end_time: "Sin hora de finalización",
  unknown_columns: "Hay columnas que el contrato no reconoce",
  weekday_mismatch: "El día de la semana no coincide con la fecha",
};

export function warningLabel(code: string): string {
  return WARNING_LABELS[code] ?? code;
}

const AUDIENCE_LABELS: Record<string, string> = {
  infantil: "Infantil",
  juvenil: "Juvenil",
  adulto: "Adulto",
  familiar: "Familiar",
  todo_publico: "Todo público",
};

export function audienceLabel(value: string | null): string | null {
  if (!value) return null;
  return AUDIENCE_LABELS[value] ?? value;
}

const MONTHS = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];

export function monthLabel(value: string): string {
  const [year, month] = value.split("-");
  const name = MONTHS[Number(month) - 1];
  return name ? `${name} de ${year}` : value;
}

/** Opciones de mes: doce meses centrados en el actual, en hora de Bogotá. */
export function monthOptions(): { value: string; label: string }[] {
  const now = new Date();
  const [year, month] = new Intl.DateTimeFormat("en-CA", {
    timeZone: BOGOTA,
    year: "numeric",
    month: "2-digit",
  })
    .format(now)
    .split("-")
    .map(Number);

  const options: { value: string; label: string }[] = [];
  for (let offset = -3; offset <= 8; offset += 1) {
    const total = year * 12 + (month - 1) + offset;
    const y = Math.floor(total / 12);
    const m = (total % 12) + 1;
    const value = `${y}-${String(m).padStart(2, "0")}`;
    options.push({ value, label: monthLabel(value) });
  }
  return options;
}

/** Mes actual en Bogotá, en formato `AAAA-MM`. */
export function currentMonth(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: BOGOTA,
    year: "numeric",
    month: "2-digit",
  }).format(new Date());
}
