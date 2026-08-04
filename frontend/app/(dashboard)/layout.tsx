import Link from "next/link";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b">
        <nav className="mx-auto flex w-full max-w-7xl items-center gap-6 px-6 py-3">
          <Link href="/" className="text-sm font-semibold">
            epm-wa-platform
          </Link>
          <Link
            href="/programacion"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Programación
          </Link>
          <Link
            href="/programacion/importar"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Cargar
          </Link>
        </nav>
      </header>
      {children}
    </div>
  );
}
