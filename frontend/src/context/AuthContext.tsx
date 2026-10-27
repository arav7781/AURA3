'use client';

import React, { createContext, useCallback, useContext } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '@/lib/api/client';

// Accounts live in the AURA-3 backend. Signing in sets an HttpOnly cookie holding a signed JWT whose
// session id the API checks on every request, so signing out revokes it server-side. The browser
// never sees the token; this context only reads who is signed in from /api/me.

export type UserRole = 'investor' | 'startup';
export type PlanId = 'scout' | 'angel' | 'syndicate';

export interface Me {
  user: { id: string; email: string; name: string; role: UserRole; is_admin: boolean };
  plan: {
    id: PlanId;
    name: string;
    price_inr_month: number;
    monthly_ac: number;
    pending_plan: PlanId | null;
    period_index: number;
    next_grant_at: string | null;
  } | null;
  entitlements: {
    features: string[];
    feature_labels: Record<string, string>;
    quotas: Record<string, { used: number; limit: number | null; resets_at?: string }>;
  };
  balances: { available: number; locked: number; escrowed: number };
  startup: { id: string; slug: string; name: string; status: string } | null;
}

export interface RegisterInput {
  email: string;
  password: string;
  name: string;
  role: UserRole;
  plan?: PlanId;
  startup_name?: string;
}

export const getDashboardPath = (role: UserRole | null | undefined) => {
  if (role === 'investor') return '/investor';
  if (role === 'startup') return '/founder';
  return '/';
};

interface AuthContextType {
  me: Me | null;
  currentUser: Me['user'] | null;
  userRole: UserRole | null;
  loading: boolean;
  has: (feature: string) => boolean;
  login: (email: string, password: string) => Promise<Me>;
  register: (input: RegisterInput) => Promise<Me>;
  logout: (redirectTo?: string) => Promise<void>;
  refresh: () => Promise<Me | null>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
};

const ME_KEY = ['me'] as const;

async function fetchMe(): Promise<Me | null> {
  try {
    return await api<Me>('/api/me');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // A cookie the API rejects (expired, revoked, or from a reset database) is cleared, so the
      // route guard stops treating this browser as signed in.
      await api('/api/auth/logout', { method: 'POST' }).catch(() => undefined);
      return null;
    }
    throw error;
  }
}

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery({ queryKey: ME_KEY, queryFn: fetchMe, retry: false, staleTime: 30_000 });
  const me = data ?? null;

  const refresh = useCallback(async () => {
    const fresh = await fetchMe();
    queryClient.setQueryData(ME_KEY, fresh);
    return fresh;
  }, [queryClient]);

  const signedIn = useCallback(async () => {
    queryClient.removeQueries({ predicate: query => query.queryKey[0] !== 'me' });
    const fresh = await refresh();
    if (!fresh) throw new ApiError(401, 'UNAUTHORIZED', 'The session could not be started. Check that cookies are allowed.');
    return fresh;
  }, [queryClient, refresh]);

  const login = useCallback(async (email: string, password: string) => {
    await api('/api/auth/login', { method: 'POST', body: { email, password } });
    return signedIn();
  }, [signedIn]);

  const register = useCallback(async (input: RegisterInput) => {
    await api('/api/auth/register', { method: 'POST', body: input });
    return signedIn();
  }, [signedIn]);

  const logout = useCallback(async (redirectTo?: string) => {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => undefined);
    if (redirectTo) {
      // A full page load: no protected page gets to react to the signed-out state on the way out.
      window.location.assign(redirectTo);
      return;
    }
    // Update the query the provider is subscribed to first; clearing the whole cache would detach it
    // and leave the signed-out user on screen.
    queryClient.setQueryData(ME_KEY, null);
    queryClient.removeQueries({ predicate: query => query.queryKey[0] !== 'me' });
  }, [queryClient]);

  const has = useCallback((feature: string) => !!me?.entitlements.features.includes(feature), [me]);

  return (
    <AuthContext.Provider
      value={{
        me,
        currentUser: me?.user ?? null,
        userRole: me?.user.role ?? null,
        loading: isPending,
        has,
        login,
        register,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
