import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { homePath, useAuth } from "../../auth/useAuth";
import { ROLE_LABELS } from "../../layouts/navigation";
import { authService, type User } from "../../services/authService";
import Avatar from "../../ui/Avatar";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import PasswordField from "./PasswordField";
import { emailError } from "./validation";

export default function LoginPage() {
  const { login, loginAs } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [emailProblem, setEmailProblem] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  function goHome(user: User) {
    const from = (location.state as { from?: string } | null)?.from;
    const fromMatchesRole = from?.startsWith(homePath(user.role));
    navigate(fromMatchesRole && from ? from : homePath(user.role), { replace: true });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = emailError(email);
    setEmailProblem(problem);
    if (problem) return;
    setPending("form");
    setError(null);
    try {
      goHome(await login(email.trim(), password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setPending(null);
    }
  }

  async function enterAs(user: User) {
    setPending(user.id);
    goHome(await loginAs(user));
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
          loading={pending === "form"}
          disabled={!email || !password}
          className="mt-2 w-full"
        >
          Giriş yap
        </Button>
      </form>

      <div className="mt-10 mb-3">
        <p className="text-sm font-medium text-ink-2">Pilot hesaplar</p>
        <p className="mt-0.5 text-sm text-graphite">Pilot dönemde hazır bir hesapla da girebilirsin.</p>
      </div>

      <ul className="flex flex-col gap-2">
        {authService.demoUsers().map((user) => (
          <li key={user.id}>
            <button
              type="button"
              onClick={() => void enterAs(user)}
              disabled={pending !== null}
              className="flex w-full items-center gap-3 rounded-panel border border-line bg-surface px-3 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-canvas disabled:opacity-60"
            >
              <Avatar name={user.name} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-base font-medium text-ink">{user.name}</span>
                <span className="block truncate text-sm text-graphite">{user.title}</span>
              </span>
              <span className="text-sm text-graphite">{ROLE_LABELS[user.role]}</span>
            </button>
          </li>
        ))}
      </ul>

      <p className="mt-10 text-base text-graphite">
        Hesabın yok mu?{" "}
        <Link to="/register" className="font-medium text-accent hover:text-accent-hover">
          Hesap oluştur
        </Link>
      </p>
    </>
  );
}
