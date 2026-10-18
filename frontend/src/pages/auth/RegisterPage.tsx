import { GraduationCap, Presentation } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { homePath, useAuth } from "../../auth/useAuth";
import { authService, type Role } from "../../services/authService";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import SegmentedControl from "../../ui/SegmentedControl";
import PasswordField from "./PasswordField";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>("student");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const user = await register({ name, email, password, role });
      navigate(homePath(user.role), { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setSaving(false);
    }
  }

  return (
    <>
      <h2 className="text-xl font-semibold tracking-tight text-ink">Hesap oluştur</h2>
      <p className="mt-1.5 text-base text-graphite">Birkaç saniye sürer.</p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
        <SegmentedControl
          name="role"
          label="Bu platformu nasıl kullanacaksın?"
          variant="cards"
          value={role}
          onChange={setRole}
          options={[
            {
              value: "student",
              label: "Öğrenci",
              description: "Derslerine soru sor, pratik yap.",
              icon: GraduationCap,
            },
            {
              value: "instructor",
              label: "Eğitmen",
              description: "Ders materyallerini yönet.",
              icon: Presentation,
            },
          ]}
        />
        <Field
          label="Ad soyad"
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={role === "instructor" ? "Dr. Ayşe Demir" : "Elif Kaya"}
          required
          minLength={2}
        />
        <Field
          label="Üniversite e-postası"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="ad.soyad@universite.edu.tr"
          required
        />
        <PasswordField
          label="Şifre"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint={`En az ${authService.minPassword} karakter.`}
          required
          minLength={authService.minPassword}
        />
        {error && <p className="text-base text-danger">{error}</p>}
        <Button type="submit" variant="primary" size="lg" loading={saving} className="mt-2 w-full">
          {role === "instructor" ? "Eğitmen hesabı oluştur" : "Öğrenci hesabı oluştur"}
        </Button>
      </form>

      <p className="mt-10 text-base text-graphite">
        Zaten hesabın var mı?{" "}
        <Link to="/login" className="font-medium text-accent hover:text-accent-hover">
          Giriş yap
        </Link>
      </p>
    </>
  );
}
