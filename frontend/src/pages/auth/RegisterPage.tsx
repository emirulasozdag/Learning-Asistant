import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { authService } from "../../services/authService";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import PasswordField from "./PasswordField";
import { emailError } from "./validation";

export default function RegisterPage() {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [emailProblem, setEmailProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = emailError(email);
    setEmailProblem(problem);
    if (problem) return;
    setSaving(true);
    setError(null);
    try {
      // Yönlendirmeyi AuthLayout yapar.
      await register({ name: name.trim(), email: email.trim(), password });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setSaving(false);
    }
  }

  return (
    <>
      <h2 className="text-2xl font-semibold tracking-tight text-ink">Hesap oluştur</h2>
      <p className="mt-1.5 text-base text-graphite">
        Öğrenci hesabını oluştur; derslerine eğitmenin verdiği katılım koduyla katılırsın. Eğitmen hesaplarını
        üniversite açar.
      </p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4" noValidate>
        <Field
          label="Ad soyad"
          autoComplete="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Elif Kaya"
          required
          minLength={2}
        />
        <Field
          label="Üniversite e-postası"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            if (emailProblem) setEmailProblem(null);
          }}
          onBlur={() => email && setEmailProblem(emailError(email))}
          error={emailProblem}
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
        {error && (
          <p role="alert" className="text-base text-danger">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" size="lg" loading={saving} className="mt-2 w-full">
          Öğrenci hesabı oluştur
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
