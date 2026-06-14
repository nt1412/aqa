"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { Project, User } from "@/lib/types";

interface AppState {
  user: User | null;
  loading: boolean;
  projects: Project[];
  currentProject: Project | null;
  setCurrentProject: (p: Project) => void;
  login: (login: string, password: string) => Promise<void>;
  logout: () => void;
  refreshProjects: () => Promise<void>;
}

const Ctx = createContext<AppState | null>(null);

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used within Providers");
  return v;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProjectState] = useState<Project | null>(null);

  async function loadSession() {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
      await refreshProjects();
    } catch {
      setToken(null);
    } finally {
      setLoading(false);
    }
  }

  async function refreshProjects() {
    const ps = await api.projects();
    setProjects(ps);
    setCurrentProjectState((cur) => cur ?? ps[0] ?? null);
  }

  useEffect(() => {
    loadSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(loginName: string, password: string) {
    const { access_token } = await api.login(loginName, password);
    setToken(access_token);
    const me = await api.me();
    setUser(me);
    await refreshProjects();
  }

  function logout() {
    setToken(null);
    setUser(null);
    setProjects([]);
    setCurrentProjectState(null);
  }

  function setCurrentProject(p: Project) {
    setCurrentProjectState(p);
  }

  return (
    <Ctx.Provider
      value={{
        user,
        loading,
        projects,
        currentProject,
        setCurrentProject,
        login,
        logout,
        refreshProjects,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
