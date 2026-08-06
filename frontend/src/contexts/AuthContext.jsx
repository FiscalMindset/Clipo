import { createContext, useContext, useState, useEffect } from 'react';
import { getCurrentUser } from '../lib/auth';
import { checkSupabaseConnection } from '../lib/supabase';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    checkSupabaseConnection()
      .then(() => {
        if (!cancelled) {
          console.info('Supabase connection check succeeded');
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.warn('Supabase connection check failed', error);
        }
      });

    getCurrentUser()
      .then(setUser)
      .finally(() => setLoading(false));

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
