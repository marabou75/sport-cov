
"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getUser, clearAuth, type AuthUser } from "@/lib/auth";

const navItems = [
  { href: "/", label: "Présentation" },
  { href: "/accueil", label: "Accueil" },
  { href: "/equipes", label: "Équipes" },
  { href: "/dashboard", label: "Tableau de bord" },
  { href: "/co2", label: "CO² écon" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setUser(getUser());
  }, []);

  function logout() {
    clearAuth();
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="bg-green-400 text-white shadow">
        <div className="max-w-3xl mx-auto px-4 pt-3 pb-1 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <Image src="/logo.png" alt="Sport Cov" width={36} height={36} className="rounded-full" />
            <span className="font-bold text-lg tracking-tight">Sport Cov</span>
          </Link>

          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="w-9 h-9 bg-white/30 hover:bg-white/40 rounded-full flex items-center justify-center font-bold text-sm transition-colors"
            >
              {user ? user.full_name.charAt(0).toUpperCase() : "?"}
            </button>
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-44 bg-white rounded-xl shadow-lg py-2 z-50 text-gray-700 text-sm">
                {user ? (
                  <>
                    <div className="px-4 py-2 border-b border-gray-100">
                      <div className="font-medium">{user.full_name}</div>
                      <div className={`text-xs mt-0.5 font-semibold ${user.role === "admin" ? "text-purple-500" : "text-green-500"}`}>
                        {user.role === "admin" ? "⭐ Admin" : "🏃 Coach"}
                      </div>
                    </div>
                    <button
                      onClick={logout}
                      className="w-full text-left px-4 py-2 hover:bg-gray-50 text-red-500"
                    >
                      Se déconnecter
                    </button>
                  </>
                ) : (
                  <Link href="/login" className="block px-4 py-2 hover:bg-gray-50">
                    Se connecter
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>

        <nav className="max-w-3xl mx-auto px-4 pb-2 flex gap-0.5 overflow-x-auto text-sm whitespace-nowrap">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-1.5 rounded transition-colors hover:bg-green-300 ${
                pathname === item.href ? "bg-green-300 font-semibold" : ""
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
