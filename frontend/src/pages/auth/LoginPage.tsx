import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useDemoInfo } from "../../auth/useDemoInfo";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import DemoAccounts from "./DemoAccounts";
import PasswordField from "./PasswordField";
import { emailError } from "./validation";

export default function LoginPage() {
  const { login } = useAuth();
  const demo = useDemoInfo();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [emailProblem, setEmailProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = emailError(email);
    setEmailProblem(problem);
    if (problem) return;
    setPending(true);
    setError(null);
    try {
      // Yönlendirmeyi AuthLayout yapar: kullanıcı gelince istenen sayfaya (ya da ana sayfaya) gider.
      await login(email.trim(), password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setPending(false);
    }
  }

  return (
    <>
      <h2 className="text-2xl font-semibold tracking-tight text-ink">Giriş yap</h2>
      <p className="mt-1.5 text-base text-graphite">Üniversite e-posta adresinle devam et.</p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4" noValidate>
        <Field
          label="E-posta"
          type="email"
          autoComplete="email"
          placeholder="ad.soyad@universite.edu.tr"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            if (emailProblem) setEmailProblem(null);
          }}
          onBlur={() => email && setEmailProblem(emailError(email))}
          error={emailProblem}
          required
        />
        <PasswordField
          label="Şifre"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={error}
          required
        />
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={pending}
          disabled={!email || !password}
          className="mt-2 w-full"
        >
          Giriş yap
        </Button>
      </form>

      {demo && demo.accounts.length > 0 && <DemoAccounts info={demo} />}

      <p className="mt-8 rounded-panel border border-line bg-canvas px-4 py-3 text-sm text-graphite">
        Öğrenciler hesap oluşturup eğitmenin verdiği katılım koduyla derse katılır. Eğitmen hesaplarını
        üniversite açar.
      </p>

      <p className="mt-10 text-base text-graphite">
        Hesabın yok mu?{" "}
        <Link to="/register" className="font-medium text-accent hover:text-accent-hover">
          Hesap oluştur
        </Link>
      </p>
    </>
  );
}
