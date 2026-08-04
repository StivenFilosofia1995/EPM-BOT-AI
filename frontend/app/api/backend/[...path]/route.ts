/**
 * Proxy hacia el backend.
 *
 * Existe por una razón concreta: el `ADMIN_API_TOKEN` NO puede llegar al
 * navegador. Si el cliente llamara al backend directamente, el token tendría
 * que ir en el bundle de JavaScript, y cualquiera que abra las herramientas de
 * desarrollo lo tendría. Aquí se inyecta en el servidor de Next, donde el
 * usuario no lo ve.
 *
 * Por eso la variable se llama `ADMIN_API_TOKEN` y no `NEXT_PUBLIC_*`: Next
 * solo expone al cliente las que llevan ese prefijo.
 *
 * Esto es temporal, igual que la guarda del backend: en P5 lo sustituye la
 * autenticación de Supabase con roles.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const ADMIN_TOKEN = process.env.ADMIN_API_TOKEN ?? "";

/** Ruta del backend a partir del segmento capturado, conservando la query. */
function targetUrl(request: NextRequest, path: string[]): string {
  const search = request.nextUrl.search;
  return `${BACKEND_URL}/api/v1/${path.join("/")}${search}`;
}

function missingToken(): NextResponse {
  return NextResponse.json(
    {
      error: {
        code: "admin_token_not_configured",
        message:
          "Falta ADMIN_API_TOKEN en el entorno del frontend. Sin él, el panel no puede autenticarse contra el backend.",
      },
    },
    { status: 503 },
  );
}

/**
 * Reenvía la petición y devuelve la respuesta del backend tal cual.
 *
 * El cuerpo se pasa como stream, sin leerlo ni reconstruirlo: un Excel de
 * varios MB no tiene por qué pasar por memoria dos veces, y así el
 * `multipart/form-data` (con su boundary) llega intacto.
 */
async function forward(
  request: NextRequest,
  path: string[],
  body?: BodyInit | null,
): Promise<NextResponse> {
  if (!ADMIN_TOKEN) return missingToken();

  const headers = new Headers();
  headers.set("X-Admin-Token", ADMIN_TOKEN);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  let response: Response;
  try {
    response = await fetch(targetUrl(request, path), {
      method: request.method,
      headers,
      body,
      // El backend es un servicio interno; no hay caché intermedia que valga.
      cache: "no-store",
      // Necesario en Node cuando el cuerpo es un stream.
      ...(body ? { duplex: "half" } : {}),
    } as RequestInit);
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "backend_unreachable",
          message: `No se pudo conectar con el backend en ${BACKEND_URL}. ¿Está levantado?`,
        },
      },
      { status: 502 },
    );
  }

  const payload = await response.text();
  return new NextResponse(payload, {
    status: response.status,
    headers: {
      "content-type":
        response.headers.get("content-type") ?? "application/json",
    },
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  const { path } = await context.params;
  return forward(request, path);
}

export async function POST(request: NextRequest, context: Context) {
  const { path } = await context.params;
  return forward(request, path, request.body);
}
