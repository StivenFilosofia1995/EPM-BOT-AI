import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ActivityBrowser } from "./activity-browser";

export const metadata = {
  title: "Programación · epm-wa-platform",
};

export default function ProgramacionPage() {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 p-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Programación</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Lo que hay cargado en la base de datos. Las horas se muestran en
            hora de Colombia.
          </p>
        </div>
        <Button render={<Link href="/programacion/importar" />}>
          Cargar programación
        </Button>
      </header>
      <ActivityBrowser />
    </main>
  );
}
