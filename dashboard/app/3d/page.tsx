import Link from "next/link";
import Ciudad3DCliente from "@/components/Ciudad3DCliente";

export const metadata = {
  title: "SIGE-BA — CABA en 3D",
  description: "El tejido construido de la Ciudad, extruido, con las capas operativas encima.",
};

export default function Page3D() {
  return (
    <main className="relative flex-1">
      <Link href="/"
        className="absolute bottom-16 right-3 z-20 rounded border border-white/10
                   bg-black/70 px-3 py-1.5 text-xs text-slate-200 backdrop-blur
                   hover:bg-white/10">
        ← Tablero
      </Link>
      <Ciudad3DCliente />
    </main>
  );
}
