import { ArrowRight, Play, Shuffle } from "lucide-react";
import { useId, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { MAX_TOPIC_CHARS, type ConceptProgress, type Difficulty, type PracticeType } from "../../api/types";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import { inputClasses } from "../../ui/Field";
import SegmentedControl, { type SegmentOption } from "../../ui/SegmentedControl";
import { DIFFICULTY_LABEL, TYPE_DETAILS, TYPE_LABEL, conceptLabel } from "./labels";
import type { PracticeSettings } from "./usePracticeSession";

const TYPES: PracticeType[] = ["mcq", "short_answer", "code_tracing"];
const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];

const TYPE_OPTIONS: SegmentOption<PracticeType>[] = TYPES.map((type) => ({
  value: type,
  label: TYPE_LABEL[type],
  description: TYPE_DETAILS[type].description,
  icon: TYPE_DETAILS[type].icon,
}));

const DIFFICULTY_OPTIONS: SegmentOption<Difficulty>[] = DIFFICULTIES.map((value) => ({
  value,
  label: DIFFICULTY_LABEL[value],
}));

/**
 * Oturum kurulumu: önce ne çalışılacağı (konu), sonra soru türü ve zorluk. Konu önerileri
 * uydurma değildir: öğrencinin öğrenme kaydındaki eksik kavramlar ve dersin materyal başlıkları.
 */
export default function PracticeSetup({
  initial,
  gaps,
  topics,
  researchLogging,
  activeQuestions,
  onStart,
  onResume,
}: {
  initial: PracticeSettings | null;
  gaps: ConceptProgress[];
  topics: string[];
  researchLogging: boolean;
  /** Süren oturumdaki soru sayısı (0: oturum yok). */
  activeQuestions: number;
  onStart: (settings: PracticeSettings) => void;
  onResume: () => void;
}) {
  const [topic, setTopic] = useState(initial?.topic ?? "");
  const [type, setType] = useState<PracticeType>(initial?.type ?? "mcq");
  const [difficulty, setDifficulty] = useState<Difficulty>(initial?.difficulty ?? "medium");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const pool = [...new Set([...gaps.map((gap) => conceptLabel(gap.concept)), ...topics])];

  function pick(value: string) {
    setTopic(value.slice(0, MAX_TOPIC_CHARS));
    setError(null);
  }

  function surprise() {
    const others = pool.filter((candidate) => candidate !== topic);
    if (others.length > 0) pick(others[Math.floor(Math.random() * others.length)]);
    inputRef.current?.focus();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = topic.trim();
    if (!value) {
      setError("Hangi konuda soru istediğini yaz ya da aşağıdan bir konu seç.");
      inputRef.current?.focus();
      return;
    }
    onStart({ topic: value, type, difficulty });
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-8">
      {activeQuestions > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-accent-line bg-accent-soft/50 px-4 py-3">
          <p className="text-base text-ink">
            Süren bir oturumun var: <span className="font-semibold">{activeQuestions} soru</span>. Ayarları
            değiştirip yeni soruyla sürdürebilir ya da kaldığın yere dönebilirsin.
          </p>
          <Button size="sm" trailingIcon={ArrowRight} onClick={onResume}>
            Oturuma dön
          </Button>
        </div>
      )}

      <section aria-labelledby={`${inputId}-title`}>
        <h2 id={`${inputId}-title`} className="text-xl font-semibold text-ink">
          Ne çalışmak istiyorsun?
        </h2>
        <p className="mt-1 text-base text-graphite">
          Konu ders materyalinde aranır; soru bulunan bölüme dayanır ve bağımsız bir çözümle kontrol edilir.
        </p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <div className="min-w-0 flex-1">
            <label htmlFor={inputId} className="sr-only">
              Konu
            </label>
            <input
              ref={inputRef}
              id={inputId}
              value={topic}
              onChange={(event) => pick(event.target.value)}
              maxLength={MAX_TOPIC_CHARS}
              // Örnek dersin kendi konularından; sabit örnek başka dersin konusu olurdu (#32).
              placeholder={topics.length > 0 ? `ör. ${topics[0]}` : "Bir konu yaz"}
              autoComplete="off"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${inputId}-error` : undefined}
              className={cx(inputClasses, "h-12 text-md")}
            />
          </div>
          {pool.length > 1 && (
            <Button variant="secondary" size="lg" icon={Shuffle} onClick={surprise}>
              Bana bir konu seç
            </Button>
          )}
        </div>
        {error && (
          <p id={`${inputId}-error`} className="mt-1.5 text-sm text-danger">
            {error}
          </p>
        )}

        {gaps.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-ink-2">Tekrar etmen gerekenler</h3>
            <p className="text-sm text-graphite">Öğrenme kaydında hâlâ eksiği görünen kavramlar.</p>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {gaps.map((gap) => {
                const label = conceptLabel(gap.concept);
                const percent = Math.round(gap.last_score_ratio * 100);
                const active = topic.trim() === label;
                return (
                  <li key={gap.concept}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => pick(label)}
                      className={cx(
                        "flex w-full flex-col gap-2 rounded-panel border px-3 py-2.5 text-left transition-colors",
                        active ? "border-accent bg-accent-soft/60" : "border-line bg-surface hover:border-line-strong",
                      )}
                    >
                      <span className="text-base font-medium text-ink">{label}</span>
                      <span className="flex items-center gap-2 text-sm text-graphite">
                        <span aria-hidden className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle">
                          <span
                            className={cx("block h-full rounded-full", percent >= 50 ? "bg-warning" : "bg-danger")}
                            style={{ width: `${Math.max(percent, 4)}%` }}
                          />
                        </span>
                        <span className="tabular-nums">
                          son deneme %{percent} · {gap.attempts} deneme
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {topics.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-semibold text-ink-2">Dersin konuları</h3>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {topics.map((candidate) => {
                const active = topic.trim() === candidate;
                return (
                  <li key={candidate}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => pick(candidate)}
                      className={cx(
                        "rounded-full border px-3 py-1 text-sm transition-colors",
                        active
                          ? "border-accent bg-accent text-on-accent"
                          : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink",
                      )}
                    >
                      {candidate}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <SegmentedControl
        name="practice-type"
        label="Soru türü"
        variant="cards"
        columns={3}
        options={TYPE_OPTIONS}
        value={type}
        onChange={setType}
      />

      <SegmentedControl
        name="practice-difficulty"
        label="Zorluk"
        options={DIFFICULTY_OPTIONS}
        value={difficulty}
        onChange={setDifficulty}
      />

      <div className="flex flex-col gap-3 border-t border-line pt-6 sm:flex-row sm:items-center">
        <Button type="submit" variant="primary" size="lg" icon={Play}>
          {activeQuestions > 0 ? "Yeni soruyla sürdür" : "Pratiğe başla"}
        </Button>
        <p className="text-sm text-graphite">
          Her soru birkaç saniyede hazırlanır. Puanlar çalışman içindir, resmî not değildir.
        </p>
      </div>

      {!researchLogging && (
        <p className="text-sm text-graphite">
          Öğrenme kaydın kapalı: sorular geri bildirim alır ama kaydına yazılmaz.{" "}
          <Link to="/student/account" className="link">
            Hesabım
          </Link>{" "}
          sayfasından açabilirsin.
        </p>
      )}
    </form>
  );
}
