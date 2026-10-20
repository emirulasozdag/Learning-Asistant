import { createContext } from "react";

import type { RegisterInput, Role, User } from "../services/authService";

export interface AuthContextValue {
  user: User | null;
  /** İlk `GET /me` cevabı gelene kadar true: bu sırada girişe yönlendirilmez. */
  loading: boolean;
  /** `GET /me` sunucuya ulaşamadı (oturum durumu bilinmiyor). */
  failed: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  /** Sunum modu: seçilen roldeki demo hesabına şifresiz giriş. */
  demoLogin: (role: Role) => Promise<User>;
  acceptPolicy: (researchLogging: boolean) => Promise<void>;
  /** Oturumu sunucudan yeniden okur (üyelik ya da onay değişince). */
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
