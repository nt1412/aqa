"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useApp } from "@/app/providers";
import { Shell } from "@/components/Shell";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading) return <Spinner label="initializing" />;
  if (!user) return null;

  return <Shell>{children}</Shell>;
}
