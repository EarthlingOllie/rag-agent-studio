/**
 * Where the widget keeps the Visitor's Conversation token between page loads: the iframe's local
 * storage, which browsers partition per top-level site, so a reload on the same site resumes the
 * Conversation (the API refuses the token 24 hours after the last activity). A browser that
 * blocks the iframe's storage throws on any access; the widget then keeps the token in memory
 * only, and a reload starts a new Conversation.
 *
 * It also keeps whether a Call was being held when the page went away, so the resumed
 * Conversation can offer to continue it.
 */
export type TokenStore = {
  load: () => string | null;
  save: (token: string) => void;
  /** Forgets the token, and any Call that was being held. */
  clear: () => void;
  /** Whether a Call was being held in the Conversation when the page last went away. */
  inCall: () => boolean;
  /** Keeps (or forgets) that a Call is being held. */
  saveCall: (holding: boolean) => void;
};

export function tokenStore(agent: string): TokenStore {
  const key = `rag-widget:conversation:${agent}`;
  const callKey = `rag-widget:call:${agent}`;
  function read(item: string): string | null {
    try {
      return window.localStorage.getItem(item);
    } catch {
      return null;
    }
  }
  function saveCall(holding: boolean) {
    try {
      if (holding) window.localStorage.setItem(callKey, "1");
      else window.localStorage.removeItem(callKey);
    } catch {
      // No storage: no Continue call after a reload.
    }
  }
  return {
    load() {
      return read(key);
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
      saveCall(false);
    },
    inCall() {
      return read(callKey) !== null;
    },
    saveCall,
  };
}
