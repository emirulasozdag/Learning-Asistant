import { ListChecks } from "lucide-react";
import { useSearchParams } from "react-router";

import PageHeader from "../../ui/PageHeader";
import UpcomingPage from "../UpcomingPage";

/**
 * Pratik çalışma alanı — EKİP GÖREVİ (docs/UI_GOREVLERI.md).
 * Veri: practiceService.nextQuestion() / submit() (şimdilik mock).
 * AI Tutor'daki "Bu konuyu çalış" buraya ?course=&topic= ile gelir.
 */
export default function PracticePage() {
  const [params] = useSearchParams();
  const topic = params.get("topic");
  return (
    <div className="mx-auto max-w-4xl px-6 pt-8 pb-16 lg:px-10">
      <PageHeader
        title="Pratik"
        description="Ders materyalinden üretilen sorularla çalış; cevabın rubriğe göre değerlendirilir."
      />
      <div className="mt-8">
        <UpcomingPage
          icon={ListChecks}
          title="Pratik çalışma alanı geliştiriliyor"
          description={
            topic
              ? `“${topic}” konusu için ders materyalinden soru üretilecek; cevabın puanlanacak, eksik kavramlar kaynağıyla gösterilecek.`
              : "Ders materyalinden soru üretilecek; cevabın puanlanacak, eksik kavramlar kaynağıyla gösterilecek."
          }
        />
      </div>
    </div>
  );
}
