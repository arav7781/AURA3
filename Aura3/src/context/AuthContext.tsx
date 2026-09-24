'use client';

import React, { createContext, useCallback, useContext, useSyncExternalStore } from 'react';

// Demo session: no sign-in. Visitors pick a role on the landing page and it is
// remembered in localStorage until they exit.

export type UserRole = 'investor' | 'startup';

export interface DemoUser {
  uid: string;
  email: string;
  displayName: string;
}

const STORAGE_KEY = 'aura3.demoSession';

export const getDashboardPath = (role: UserRole | null) => {
  if (role === 'investor') return '/investor';
  if (role === 'startup') return '/founder';
  return '/';
};

interface AuthContextType {
  currentUser: DemoUser | null;
  userRole: UserRole | null;
  loading: boolean;
  enterAs: (role: UserRole) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  currentUser: null,
  userRole: null,
  loading: true,
  enterAs: () => {},
  logout: async () => {},
});

export const useAuth = () => useContext(AuthContext);

const demoUser = (role: UserRole): DemoUser => ({
  uid: `demo-${role}`,
  email: role === 'investor' ? 'investor@aura3.demo' : 'founder@aura3.demo',
  displayName: role === 'investor' ? 'Demo Investor' : 'Demo Founder',
});

const listeners = new Set<() => void>();

const readRole = (): UserRole | null => {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === 'investor' || saved === 'startup' ? saved : null;
  } catch {
    return null;
  }
};

const writeRole = (role: UserRole | null) => {
  try {
    if (role) window.localStorage.setItem(STORAGE_KEY, role);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode): nothing to persist.
  }
  listeners.forEach(listener => listener());
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  window.addEventListener('storage', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', listener);
  };
};

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const userRole = useSyncExternalStore(subscribe, readRole, () => null);
  const enterAs = useCallback((role: UserRole) => writeRole(role), []);
  const logout = useCallback(async () => writeRole(null), []);
  const loading = false;

  return (
    <AuthContext.Provider
      value={{
        currentUser: userRole ? demoUser(userRole) : null,
        userRole,
        loading,
        enterAs,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
