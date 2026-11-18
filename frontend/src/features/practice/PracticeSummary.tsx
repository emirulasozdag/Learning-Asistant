import { ArrowLeft, BarChart3, Play, Target } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Link } from "react-router";

import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import StatRow from "../../ui/StatRow";
import { conceptLabel } from "./labels";
import { EntryRow } from "./PracticeSession";
import type { PracticeEntry, PracticeSettings } from "./usePracticeSession";

/** Kavramları büyük/küçük harf ve boşluk farkı olmadan birleştirir, en sık görülen önce. */
function tally(lists: string[][]): string[] {
  const counts = new Map<string, { label: string; count: number }>();
  for (const concept of lists.flat()) {
    const label = conceptLabel(concept).trim();
    const key = label.toLocaleLowerCase("tr");
    const current = counts.get(key);
    counts.set(key, { label: current?.label ?? label, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.values()].sort((a, b) => b.count - a.count).map((item) => item.label);
}

/**
 * Oturum özeti: kaç soru, kaçı doğru, ortalama puan; kavranan ve eksik kalan kavramlar ve
 * sorular. Eksik kavramdan tek tıkla yeni soru başlar. Hesap yalnızca bu oturumun cevaplarından.
 */
export default function PracticeSummary({
  entries,
  settings,
  courseId,
  researchLogging,
  onPractice,
  onResume,
  onNewSession,
}: {
  entries: PracticeEntry[];
  settings: PracticeSettings | null;
  courseId: number;
  researchLogging: boolean;
  onPractice: (settings: PracticeSettings) => void;
  onResume: () => void;
  onNewSession: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const answered = entries.filter((entry) => entry.feedback);
  const correct = answered.filter((entry) => entry.feedback!.score >= entry.feedback!.max_score).length;
  const ratio =
    answered.length > 0
      ? answered.reduce((sum, entry) => sum + entry.feedback!.score / entry.feedback!.max_score, 0) /
        answered.length
      : null;
  const missing = tally(answered.map((entry) => entry.feedback!.missing_concepts));
  const understood = tally(answered.map((entry) => entry.feedback!.understood)).filter(
    (concept) => !missing.some((gap) => gap.toLocaleLowerCase("tr") === concept.toLocaleLowerCase("tr")),
  );

  useEffect(() => headingRef.current?.focus(), []);

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-8">
      <div>
        <h2 ref={headingRef} id={headingId} tabIndex={-1} className="text-xl font-semibold text-ink outline-none">
          Oturum özeti
        </h2>
        {settings && <p className="mt-1 text-base text-graphite">Konu: {settings.topic}</p>}
      </div>

      <StatRow
        stats={[
          { label: "Cevaplanan soru", value: answered.length },
          { label: "Tam puan", value: correct },
          { label: "Ortalama puan", value: ratio === null ? "–" : `%${Math.round(ratio * 100)}` },
        ]}
      />

      {missing.length > 0 && (
        <div>
          <h3 className="text-base font-semibold text-ink">Üzerinde çalışman gerekenler</h3>
          <p className="text-sm text-graphite">Cevaplarında eksik ya da yanlış görünen kavramlar.</p>
          <ul className="mt-3 flex flex-col gap-2">
            {missing.map((concept) => (
              <li
                key={concept}
                className="flex flex-wrap items-center justify-between gap-2 rounded-panel border border-warning/30 bg-warning-soft px-3 py-2"
              >
                <span className="text-base text-ink">{concept}</span>
                <Button
                  size="sm"
                  icon={Target}
                  onClick={() =>
                    onPractice({
                      topic: concept,
                      type: settings?.type ?? "mcq",
                      difficulty: settings?.difficulty ?? "medium",
                    })
                  }
                >
                  Bu kavramla çalış
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {understood.length > 0 && (
        <div>
          <h3 className="text-base font-semibold text-ink">Kavradıkların</h3>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {understood.map((concept) => (
              <li key={concept} className="rounded-full bg-success-soft px-3 py-1 text-sm text-success">
                {concept}
              </li>
            ))}
          </ul>
        </div>
      )}

      {entries.length > 0 && (
        <div>
          <h3 className="text-base font-semibold text-ink">Sorular</h3>
          <ol className="mt-2 flex flex-col divide-y divide-line rounded-panel border border-line bg-surface px-4">
            {entries.map((entry, index) => (
              <li key={entry.item.id} className="py-2.5">
                <EntryRow entry={entry} number={index + 1} />
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-6">
        <Button variant="primary" icon={Play} onClick={onNewSession}>
          Yeni oturum
        </Button>
        <Button icon={ArrowLeft} onClick={onResume}>
          Oturuma dön
        </Button>
        <Link to={`/student/courses/${courseId}/learning`} className={buttonClasses("ghost")}>
          <BarChart3 size={14} aria-hidden />
          Öğrenme kaydım
        </Link>
      </div>
      {!researchLogging && answered.length > 0 && (
        <p className="text-sm text-graphite">
          Öğrenme kaydın kapalı olduğu için bu cevaplar kaydına yazılmadı.
        </p>
      )}
    </section>
  );
}
