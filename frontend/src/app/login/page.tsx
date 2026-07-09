"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

// ✅ FIX 1: fallback now correctly points to port 9000
const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // ✅ FIX 2: check response content-type before calling .json()
      // prevents crash when server returns HTML error page
      let res: Response;
      try {
        res = await fetch(`${BACKEND_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim(), password }),
        });
      } catch (networkErr) {
        // ✅ FIX 3: explicit network error handling (ERR_CONNECTION_REFUSED etc.)
        throw new Error(
          "Cannot reach the server. Please check your connection or try again later."
        );
      }

      // ✅ FIX 2 continued: safe JSON parse — server might return plain text or HTML on 500
      let data: any = {};
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        data = await res.json();
      }

      if (!res.ok) {
        let message = "Invalid email or password.";
        if (res.status >= 500) {
          message = "Something went wrong on our end. Please try again.";
        } else if (res.status === 401) {
          message = data?.detail ?? "Invalid email or password.";
        } else if (res.status === 403) {
          message = "Account locked. Contact your administrator.";
        } else if (res.status === 429) {
          message = "Too many attempts. Please wait and try again.";
        } else if (data?.error === "account_locked") {
          message = "Account locked. Contact your administrator.";
        } else if (data?.detail) {
          message = data.detail;
        }
        throw new Error(message);
      }

      // Validate response has required fields before trusting it
      if (!data.accessToken || !data.role) {
        throw new Error("Unexpected response from server. Please try again.");
      }

      // ✅ FIX 4: SSR-safe localStorage access
      if (typeof window !== "undefined") {
        localStorage.setItem("token", data.accessToken);
        localStorage.setItem("role", data.role);
        localStorage.setItem("companyId", data.companyId ?? "");
      }

      // Redirect based on role
      router.push(data.role === "hr_admin" ? "/hr" : "/employees");
      router.refresh();

    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="max-w-md mx-auto px-4 py-16">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          <h1 className="text-xl font-semibold mb-1">Login</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-6">
            HR and Employees login to access policy Q&A.
          </p>

          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            <label className="flex flex-col gap-1">
              <span className="text-sm">Email</span>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                autoComplete="email"
                required
                className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-sm">Password</span>
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete="current-password"
                required
                minLength={8}
                className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100"
              />
            </label>

            {error && (
              <div role="alert" className="text-sm text-rose-700 dark:text-rose-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-slate-900 text-white disabled:opacity-50"
            >
              {loading ? "Logging in…" : "Login"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-600 dark:text-slate-300">
            Don't have an account?{" "}
            <Link href="/signup" className="text-blue-600 dark:text-blue-400 hover:underline">
              Sign up
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}