"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [role, setRole] = useState<"hr_admin" | "employee">("hr_admin");
  const [companyName, setCompanyName] = useState("");
  const [passkey, setPasskey] = useState("");
  const [resolvedCompanyName, setResolvedCompanyName] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);

    try {
      const payload: any = {
        email: email.trim(),
        password,
        role,
      };

      if (role === "hr_admin" && companyName.trim()) {
        payload.companyName = companyName.trim();
      } else if (role === "employee" && passkey.trim()) {
        payload.passkey = passkey.trim();
      }

      const res = await fetch(`${BACKEND_URL}/api/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let message = "Signup failed.";
        try {
          const data = await res.json();
          if (data?.detail) message = data.detail;
          else if (res.status >= 500) message = "Something went wrong. Please try again.";
        } catch {
          // ignore parse errors
        }
        throw new Error(message);
      }

      // Automatically redirect to login page after successful signup
      router.push("/login?signup=success");
    } catch (err) {
      if (err instanceof TypeError && err.message === "Failed to fetch") {
        setError("Cannot reach the server. Please try again later.");
      } else {
        setError(err instanceof Error ? err.message : "Signup failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="max-w-md mx-auto px-4 py-16">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          <h1 className="text-xl font-semibold mb-1">Sign Up</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-6">
            Create an account to access policy Q&A.
          </p>

          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            <label className="flex flex-col gap-1">
              <span className="text-sm">I am a...</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as "hr_admin" | "employee")}
                className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100"
              >
                <option value="hr_admin">HR Admin</option>
                <option value="employee">Employee</option>
              </select>
            </label>

            {role === "hr_admin" && (
              <label className="flex flex-col gap-1">
                <span className="text-sm">Company Name (Optional)</span>
                <input
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  type="text"
                  placeholder="My Company"
                  className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100"
                />
              </label>
            )}

            {role === "employee" && (
              <label className="flex flex-col gap-1">
                <span className="text-sm">Workspace Passkey (Required)</span>
                <div className="flex gap-2">
                  <input
                    value={passkey}
                    onChange={(e) => {
                      setPasskey(e.target.value);
                      setResolvedCompanyName(null);
                    }}
                    type="text"
                    placeholder="e.g. SMART-X4Z"
                    required
                    className="flex-1 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 uppercase"
                  />
                  <button
                    type="button"
                    disabled={resolving || !passkey.trim()}
                    onClick={async () => {
                      if (!passkey.trim()) return;
                      setResolving(true);
                      setError(null);
                      try {
                        const r = await fetch(`${BACKEND_URL}/api/auth/workspace/${passkey.trim()}`);
                        if (!r.ok) throw new Error("Invalid passkey");
                        const data = await r.json();
                        setResolvedCompanyName(data.companyName);
                      } catch (err) {
                        setError("Invalid or expired workspace passkey.");
                        setResolvedCompanyName(null);
                      } finally {
                        setResolving(false);
                      }
                    }}
                    className="px-4 py-2 rounded-lg bg-slate-200 dark:bg-slate-800 text-sm whitespace-nowrap disabled:opacity-50"
                  >
                    {resolving ? "Checking..." : "Verify"}
                  </button>
                </div>
                {resolvedCompanyName && (
                  <span className="text-sm text-green-600 dark:text-green-400 mt-1">
                    ✓ Joining <strong>{resolvedCompanyName}</strong>
                  </span>
                )}
              </label>
            )}

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
                autoComplete="new-password"
                required
                minLength={6}
                className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-sm">Confirm Password</span>
              <input
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                type="password"
                autoComplete="new-password"
                required
                minLength={6}
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
              className="px-4 py-2 mt-2 rounded-lg bg-slate-900 text-white disabled:opacity-50"
            >
              {loading ? "Signing up…" : "Sign Up"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-600 dark:text-slate-300">
            Already have an account?{" "}
            <Link href="/login" className="text-blue-600 dark:text-blue-400 hover:underline">
              Log in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
