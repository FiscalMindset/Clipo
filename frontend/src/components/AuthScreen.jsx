import { useState } from 'react';
import ClipoMark from './ClipoMark';
import { loginWithPassword, requestPasswordReset, resetPassword, signUp } from '../lib/auth';
import { useAuth } from '../contexts/AuthContext';

const BENEFITS = [
    'Secure local workflow',
    'No setup after first sign in',
    'Your recent jobs stay on this device',
];

export default function AuthScreen() {
    const resetToken = new URLSearchParams(window.location.search).get('reset_token');
    const [mode, setMode] = useState(resetToken ? 'reset' : 'login');
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [loading, setLoading] = useState(false);
    const { setUser } = useAuth();

    const changeMode = (nextMode) => {
        setMode(nextMode);
        setError('');
        setNotice('');
        setPassword('');
        setConfirmPassword('');
    };

    const submit = async (event) => {
        event.preventDefault();
        setError('');
        setNotice('');

        if ((mode === 'signup' || mode === 'reset') && password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        setLoading(true);
        try {
            if (mode === 'signup') {
                setUser(await signUp({ name, email, password }));
            } else if (mode === 'login') {
                setUser(await loginWithPassword({ email, password }));
            } else if (mode === 'forgot') {
                await requestPasswordReset(email);
                setNotice('If an account exists for that email, a reset link has been sent.');
            } else {
                await resetPassword(resetToken, password);
                window.history.replaceState({}, '', window.location.pathname);
                setNotice('Password updated. You can now log in.');
                setMode('login');
            }
        } catch (submitError) {
            setError(submitError.message || 'Could not continue.');
        } finally {
            setLoading(false);
        }
    };

    return <div className="auth-shell">
        <div className="auth-aura" />
        <div className="auth-frame">
            <header className="auth-brand">
                <span><ClipoMark /></span>
                <div>
                    <strong>Clipo</strong>
                    <small>Sign in to access your studio</small>
                </div>
            </header>

            <main className="auth-layout">
                <section className="auth-marketing">
                    <div className="eyebrow">Welcome back</div>
                    <h1>Login or sign up to use your clip dashboard.</h1>
                    <p>After you sign in, you can upload videos, generate clips, track processing and export results from the same workspace.</p>
                    <ul>
                        {BENEFITS.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                </section>

                <section className="auth-card">
                    {mode !== 'forgot' && mode !== 'reset' && <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
                        <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => changeMode('login')}>Login</button>
                        <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => changeMode('signup')}>Sign up</button>
                    </div>}
                    {mode === 'forgot' && <h2 className="auth-form-heading">Reset your password</h2>}
                    {mode === 'reset' && <h2 className="auth-form-heading">Choose a new password</h2>}

                    <form onSubmit={submit} className="auth-form">
                        {mode === 'signup' && <label>
                            <span>Full name</span>
                            <input required value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" autoComplete="name" />
                        </label>}
                        {mode !== 'reset' && <label>
                            <span>Email</span>
                            <input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" />
                        </label>}
                        {mode !== 'forgot' && <label>
                            <span>Password</span>
                            <input type="password" required minLength="8" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" autoComplete={mode === 'signup' || mode === 'reset' ? 'new-password' : 'current-password'} />
                        </label>
                        }
                        {(mode === 'signup' || mode === 'reset') && <label>
                            <span>Confirm password</span>
                            <input type="password" required minLength="8" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Repeat password" autoComplete="new-password" />
                        </label>}

                        {error && <p className="auth-error">{error}</p>}
                        {notice && <p className="auth-notice">{notice}</p>}

                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Please wait...' : (mode === 'signup' ? 'Create Account' : mode === 'forgot' ? 'Send Reset Link' : mode === 'reset' ? 'Update Password' : 'Login')}
                        </button>
                        {mode === 'login' && <button className="auth-text-button" type="button" onClick={() => changeMode('forgot')}>Forgot Password?</button>}
                        {mode === 'forgot' && <button className="auth-text-button" type="button" onClick={() => changeMode('login')}>Back to Login</button>}
                        {mode === 'login' && <p className="auth-switch">New to Clipo? <button type="button" onClick={() => changeMode('signup')}>Sign Up</button></p>}
                    </form>
                </section>
            </main>
        </div>
    </div>;
}
