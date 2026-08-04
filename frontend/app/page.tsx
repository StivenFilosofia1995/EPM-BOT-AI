import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex min-h-full flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-semibold">epm-wa-platform</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        Panel de administración de la Fundación Grupo EPM. Por ahora solo está
        disponible la carga de programación desde Excel.
      </p>
      <div className="flex gap-3">
        <Button render={<Link href="/programacion/importar" />}>
          Cargar programación
        </Button>
        <Button variant="outline" render={<Link href="/programacion" />}>
          Ver programación
        </Button>
      </div>
    </main>
  );
}
