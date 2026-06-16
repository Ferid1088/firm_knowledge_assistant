// user.ts — stub: cookie auth replaces localStorage-based user switching.
export function getCurrentUserId(): string | null {
  return null;
}
export function setCurrentUserId(_id: string): void {
  // no-op — session cookie from server is authoritative
}
