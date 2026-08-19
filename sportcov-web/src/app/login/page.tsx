
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { saveAuth } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: email, password }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Erreur de connexion");
      }
      const data = await res.json();
      saveAuth(data);
      router.push("/accueil");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-white flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <div className="flex flex-col items-center gap-3">
          <Image src="/logo.png" alt="Sport Cov" width={100} height={100} />
          <h1 className="text-2xl font-bold text-gray-800">Connexion</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm outline-none focus:border-green-400 focus:ring-1 focus:ring-green-400"
              placeholder="votre@email.fr"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mot de passe</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm outline-none focus:border-green-400 focus:ring-1 focus:ring-green-400"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-green-400 hover:bg-green-500 text-white font-semibold py-3 rounded-full transition-colors disabled:opacity-60"
          >
            {loading ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-500">
          Pas encore de compte ?{" "}
          <a href="/register" className="text-green-500 font-medium hover:underline">
            Créer un compte
          </a>
        </p>
      </div>
    </div>
  );
}
