"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/app/providers";
import { Button, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const { login } = useApp();
  const router = useRouter();
  const [loginName, setLoginName] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(loginName, password);
      router.push("/");
    } catch {
      setError("Invalid credentials");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div
            className="mono text-4xl font-bold"
            style={{ color: "var(--color-accent)", textShadow: "0 0 24px var(--color-accent-dim)" }}
          >
            ▰
          </div>
          <h1 className="mono mt-3 text-xl font-bold tracking-[0.3em]">AQA</h1>
          <p className="label mt-1">mission control · qa supervision</p>
        </div>
        <form onSubmit={submit} className="space-y-4 border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-6">
          <Field label="operator">
            <Input value={loginName} onChange={(e) => setLoginName(e.target.value)} autoFocus />
          </Field>
          <Field label="passphrase">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {error && <div className="mono text-[0.75rem] text-[var(--color-fail)]">{error}</div>}
          <Button type="submit" disabled={busy} className="w-full justify-center">
            {busy ? "authenticating…" : "authenticate"}
          </Button>
        </form>
      </div>
    </main>
  );
}
