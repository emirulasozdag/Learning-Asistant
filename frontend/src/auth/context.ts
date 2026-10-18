import { createContext } from "react";

import type { RegisterInput, User } from "../services/authService";

export interface AuthContextValue {
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  loginAs: (user: User) => Promise<User>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
