/**
 * Kimlik doğrulama: backend oturumu (ADR-1). Oturum httpOnly `la_session` çerezindedir; tarayıcıda
 * kimlik saklanmaz. Kullanıcı her açılışta `GET /me` ile çözülür.
 */
import { ApiError, api } from "../api/client";
import type { DemoInfo, Me } from "../api/types";

/** Arayüzün iki alanı: eğitmen (`/instructor`) ve öğrenci (`/student`). Asıl rol ders başınadır. */
export type Role = "student" | "instructor";

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  /** Bölüm / unvan gibi kısa bilgi. */
  title?: string;
  /** Aydınlatma metninin güncel sürümü kabul edildi mi (soru sormak için gerekli, ADR-4). */
  consented: boolean;
  researchLogging: boolean;
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
}

/** Aydınlatma metninin sürümü; metin değişince backend'deki PRIVACY_POLICY_VERSION ile birlikte artar. */
export const PRIVACY_POLICY_VERSION = "2026-10-20";

const MIN_PASSWORD = 8;

export class AuthError extends Error {}

/**
 * `Me` → arayüz kullanıcısı. Eğitmen alanı: ders açabilen hesap ya da bir derste eğitmen/TA olan
 * kullanıcı. Diğer herkes öğrenci alanını görür.
 */
export function toUser(me: Me): User {
  const teaches = me.memberships.some((m) => m.role === "instructor" || m.role === "ta");
  return {
    id: me.user.id,
    name: me.user.name,
    email: me.user.email,
    title: me.user.title ?? undefined,
    role: me.user.can_create_courses || teaches ? "instructor" : "student",
    consented: me.consent.consented_at !== null && me.consent.policy_version === PRIVACY_POLICY_VERSION,
    researchLogging: me.consent.research_logging,
  };
}

function authError(reason: unknown, fallback: string): AuthError {
  if (reason instanceof ApiError) {
    if (reason.kind === "network") return new AuthError("Sunucuya ulaşılamıyor. Bağlantını kontrol edip tekrar dene.");
    if (reason.code === "not_authenticated") return new AuthError("E-posta veya şifre hatalı.");
    if (reason.code === "email_exists") return new AuthError("Bu e-posta ile zaten bir hesap var. Giriş yapmayı dene.");
    return new AuthError(reason.message);
  }
  return new AuthError(fallback);
}

export const authService = {
  /** Oturumdaki kullanıcı; oturum yoksa `null`. Ağ hatası olduğu gibi fırlatılır. */
  async currentUser(signal?: AbortSignal): Promise<User | null> {
    try {
      return toUser(await api.me(signal));
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) return null;
      throw reason;
    }
  },

  async login(email: string, password: string): Promise<User> {
    try {
      return toUser(await api.login({ email: email.trim(), password }));
    } catch (reason) {
      throw authError(reason, "Giriş yapılamadı.");
    }
  },

  async register(input: RegisterInput): Promise<User> {
    try {
      return toUser(await api.register({ ...input, name: input.name.trim(), email: input.email.trim() }));
    } catch (reason) {
      throw authError(reason, "Hesap oluşturulamadı.");
    }
  },

  /** Sunum modu açıksa demo hesapları ve katılım kodları; kapalıysa `null`. */
  async demoInfo(signal?: AbortSignal): Promise<DemoInfo | null> {
    try {
      return await api.demoInfo(signal);
    } catch {
      return null;
    }
  },

  async demoLogin(role: Role): Promise<User> {
    try {
      return toUser(await api.demoLogin(role));
    } catch (reason) {
      throw authError(reason, "Demo hesabıyla girilemedi.");
    }
  },

  async acceptPolicy(researchLogging: boolean): Promise<void> {
    await api.updateConsent({ research_logging: researchLogging, policy_version: PRIVACY_POLICY_VERSION });
  },

  async logout(): Promise<void> {
    try {
      await api.logout();
    } catch {
      // Oturum zaten düşmüş olabilir; arayüz yine de çıkış yapmış sayılır.
    }
  },

  minPassword: MIN_PASSWORD,
};
