const USERS_KEY = 'clipo-auth-users';
const SESSION_KEY = 'clipo-auth-session';

function canUseStorage() {
    return typeof window !== 'undefined' && Boolean(window.localStorage);
}

function readJson(key, fallback) {
    if (!canUseStorage()) return fallback;
    try {
        const raw = window.localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    } catch {
        return fallback;
    }
}

function writeJson(key, value) {
    if (!canUseStorage()) return;
    window.localStorage.setItem(key, JSON.stringify(value));
}

function getUsers() {
    return readJson(USERS_KEY, {});
}

function setUsers(users) {
    writeJson(USERS_KEY, users);
}

export function getCurrentUser() {
    const session = readJson(SESSION_KEY, null);
    if (!session?.email) return null;

    const users = getUsers();
    const user = users[session.email.toLowerCase()];
    return user ? { name: user.name, email: user.email } : null;
}

export function signUp({ name, email, password }) {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = name.trim();
    const normalizedPassword = password;

    if (!normalizedName) {
        throw new Error('Enter your name to create an account.');
    }
    if (!normalizedEmail) {
        throw new Error('Enter an email address to create an account.');
    }
    if (!normalizedPassword || normalizedPassword.length < 6) {
        throw new Error('Choose a password with at least 6 characters.');
    }

    const users = getUsers();
    if (users[normalizedEmail]) {
        throw new Error('An account with that email already exists. Please log in.');
    }

    const user = { name: normalizedName, email: normalizedEmail, password: normalizedPassword };
    users[normalizedEmail] = user;
    setUsers(users);
    writeJson(SESSION_KEY, { email: normalizedEmail });

    return { name: normalizedName, email: normalizedEmail };
}

export function signIn({ email, password }) {
    const normalizedEmail = email.trim().toLowerCase();
    const users = getUsers();
    const user = users[normalizedEmail];

    if (!normalizedEmail || !password) {
        throw new Error('Enter your email and password to log in.');
    }
    if (!user || user.password !== password) {
        throw new Error('Invalid email or password.');
    }

    writeJson(SESSION_KEY, { email: normalizedEmail });
    return { name: user.name, email: user.email };
}

export function signOut() {
    if (!canUseStorage()) return;
    window.localStorage.removeItem(SESSION_KEY);
}
