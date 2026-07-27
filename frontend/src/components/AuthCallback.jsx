import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCurrentUser } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();

  useEffect(() => {
    getCurrentUser().then((user) => {
      if (user) {
        setUser(user);
        navigate('/', { replace: true });
      } else {
        navigate('/?error=auth_failed', { replace: true });
      }
    });
  }, [navigate, setUser]);

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-logo"><span className="spinner" /></div>
        <p className="login-subtitle">Signing you in...</p>
      </div>
    </div>
  );
}
