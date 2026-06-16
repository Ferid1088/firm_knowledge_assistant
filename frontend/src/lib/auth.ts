// Auth API helpers. Cookie is managed by the server (HttpOnly; not JS-accessible).
import type { AuthStatus, User } from "./types";

export async function getAuthStatus(): Promise<AuthStatus> {
  const res = await fetch("/api/auth/status");
  return res.json();
}

export async function login(username: string, password: string): Promise<User> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(detail.detail ?? "Login failed");
  }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
}

export async function getMe(): Promise<User | null> {
  const res = await fetch("/api/auth/me", { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}
