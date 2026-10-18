/**
 * Kimlik doğrulama — ŞU AN MOCK. Backend'de auth yok (FR-17); oturum tarayıcıda tutulur.
 * Gerçek API gelince yalnızca bu dosyanın içi değişir; `AuthProvider` ve ekranlar aynı kalır.
 */
import { DEMO_USERS } from "../mock/users";

export type Role = "student" | "instructor";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  /** Bölüm / sınıf gibi kısa bilgi. */
  title?: string;
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
  role: Role;
}

const SESSION_KEY = "la.session";
const ACCOUNTS_KEY = "la.accounts";
const MIN_PASSWORD = 6;

export class AuthError extends Error {}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Gizli sekme vb.: oturum yalnızca bu sayfa açıkken sürer.
  }
}

function accounts(): User[] {
  return [...DEMO_USERS, ...read<User[]>(ACCOUNTS_KEY, [])];
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const authService = {
  currentUser(): User | null {
    return read<User | null>(SESSION_KEY, null);
  },

  demoUsers(): User[] {
    return DEMO_USERS;
  },

  async login(email: string, password: string): Promise<User> {
    await delay(350);
    const user = accounts().find((a) => a.email.toLowerCase() === email.trim().toLowerCase());
    if (!user) throw new AuthError("Bu e-posta ile kayıtlı bir hesap bulunamadı.");
    if (password.length < MIN_PASSWORD) throw new AuthError("E-posta veya şifre hatalı.");
    write(SESSION_KEY, user);
    return user;
  },

  async register(input: RegisterInput): Promise<User> {
    await delay(450);
    if (accounts().some((a) => a.email.toLowerCase() === input.email.trim().toLowerCase())) {
      throw new AuthError("Bu e-posta ile zaten bir hesap var. Giriş yapmayı dene.");
    }
    if (input.password.length < MIN_PASSWORD) {
      throw new AuthError(`Şifre en az ${MIN_PASSWORD} karakter olmalı.`);
    }
    const user: User = {
      id: `u-${Date.now()}`,
      name: input.name.trim(),
      email: input.email.trim(),
      role: input.role,
    };
    write(ACCOUNTS_KEY, [...read<User[]>(ACCOUNTS_KEY, []), user]);
    write(SESSION_KEY, user);
    return user;
  },

  /** Demo hesabına doğrudan giriş (sunumda hızlı geçiş için). */
  async loginAs(user: User): Promise<User> {
    await delay(200);
    write(SESSION_KEY, user);
    return user;
  },

  logout(): void {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      // yok say
    }
  },

  minPassword: MIN_PASSWORD,
};
