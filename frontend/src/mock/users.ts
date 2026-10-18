import type { User } from "../services/authService";

/** Demo hesapları (sunum için). Şifre kontrolü yok: kimlik doğrulama backend'i henüz yok. */
export const DEMO_USERS: User[] = [
  {
    id: "u-instructor",
    name: "Dr. Ayşe Demir",
    email: "ayse.demir@universite.edu.tr",
    role: "instructor",
    title: "Bilgisayar Mühendisliği",
  },
  {
    id: "u-student",
    name: "Elif Kaya",
    email: "elif.kaya@ogr.universite.edu.tr",
    role: "student",
    title: "Bilgisayar Mühendisliği, 2. sınıf",
  },
];
