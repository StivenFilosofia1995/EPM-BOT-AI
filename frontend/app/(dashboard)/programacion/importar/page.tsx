import { ImportForm } from "./import-form";

export const metadata = {
  title: "Cargar programación · epm-wa-platform",
};

export default function ImportarPage() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Cargar programación</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sube el Excel del mes. Antes de guardar nada verás exactamente qué se
          interpretó de tu archivo, fila por fila.
        </p>
      </header>
      <ImportForm />
    </main>
  );
}
