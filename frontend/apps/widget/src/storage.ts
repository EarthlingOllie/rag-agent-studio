/**
 * Where the widget keeps the Visitor's Conversation token between page loads: the iframe's local
 * storage, which browsers partition per top-level site, so a reload on the same site resumes the
 * Conversation (the API refuses the token 24 hours after the last activity). A browser that
 * blocks the iframe's storage throws on any access; the widget then keeps the token in memory
 * only, and a reload starts a new Conversation.
 */
export type TokenStore = {
  load: () => string | null;
  save: (token: string) => void;
  clear: () => void;
};

export function tokenStore(agent: string): TokenStore {
  const key = `rag-widget:conversation:${agent}`;
  return {
    load() {
      try {
        return window.localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    save(token) {
      try {
        window.localStorage.setItem(key, token);
      } catch {
        // No storage: no resume.
      }
    },
    clear() {
      try {
        window.localStorage.removeItem(key);
      } catch {
        // No storage: nothing was kept.
      }
    },
  };
}
