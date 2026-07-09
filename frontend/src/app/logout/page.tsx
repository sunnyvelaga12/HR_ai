"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    async function run() {
      try {
        const token = localStorage.getItem("token");
        await fetch(`${BACKEND_URL}/api/auth/logout`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
      } catch {
        // ignore
      } finally {
        localStorage.removeItem("token");
        localStorage.removeItem("role");
        localStorage.removeItem("companyId");
        router.push("/login");
      }
    }
    run();
  }, [router]);

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="max-w-md mx-auto px-4 py-16">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          Logging out…
        </div>
      </div>
    </div>
  );
}

