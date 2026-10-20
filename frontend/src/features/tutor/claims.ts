/**
 * Doğrulanmış cevabı iddialara ayırır: her cümle, dayandığı alıntı numaralarıyla bir satır olur.
 * Backend her iddianın kaynağını doğruladığı için ([1], [2] işaretleri `citations` sırasıdır)
 * arayüz cümleyi kaynağına bağlayabilir.
 */

export interface Claim {
  /** Ekranda gösterilen sıra (1'den başlar). */
  number: number;
  text: string;
  /** `response.citations` içindeki 1 tabanlı alıntı numaraları. */
  citations: number[];
}

export interface StructuredAnswer {
  /** Cevabın ilk cümlesi: başlık olarak öne çıkar. Kısa cevaplarda yoktur. */
  lead: Claim | null;
  claims: Claim[];
}

const CITATION = /\[(\d+)\]/g;
/** Cümle sonu: noktalama (ardından alıntı işaretleri olabilir) ve boşluk ya da metin sonu. */
const SENTENCE_END = /[.!?…]+((?:\s*\[\d+\])*)(?=\s|$)/g;
/** Başlık ayrılabilmesi için gereken en az cümle sayısı. */
const LEAD_MIN_SENTENCES = 3;
const MIN_CLAIM_LENGTH = 3;
/** Noktayla biten ama cümleyi bitirmeyen kısaltmalar (küçük harfle). */
const ABBREVIATIONS = new Set([
  "dr", "prof", "doç", "doc", "öğr", "ogr", "gör", "uzm", "bkz", "örn", "orn", "vb", "vs", "vd", "s", "sf", "sy",
  "no", "nr", "yy", "yzy", "bl", "böl", "şek", "tab", "ör", "mr", "mrs", "ms", "fig", "eq", "vol", "pp", "etc",
  "e.g", "i.e",
]);
const MAX_HEADING_LENGTH = 60;

const LIST_ITEM = /^\s*(?:[-*•]|\d+[.)])\s+/;

/**
 * Kod bloğu, tablo, başlık ya da biçimi boşluklara dayanan metin (LLM'siz modda alıntılanan
 * girintili kod, hizalı sütunlar) cümlelere bölünmez; bölünürse yapıları bozulur. Bunlar düz metin
 * olarak gösterilir. Madde işaretli listeler bölünür: her madde kendi iddiasıdır.
 */
export function isStructurable(answer: string): boolean {
  if (answer.includes("```")) return false;
  if (/^\s*\|.*\|\s*$/m.test(answer)) return false;
  if (/^(?: {2,}|\t)\S/m.test(answer) || /\S {3,}\S/.test(answer)) return false;
  if (/^#{1,6}\s/m.test(answer)) return false;
  return splitSentences(answer).length > 0;
}

/** Boş satırla ayrılan paragraflar; liste maddeleri (işareti atılarak) ayrı paragraf sayılır. */
function paragraphsOf(answer: string): string[] {
  const paragraphs: string[] = [];
  for (const block of answer.split(/\n{2,}/)) {
    let current: string[] = [];
    for (const line of block.split("\n")) {
      if (LIST_ITEM.test(line)) {
        if (current.length > 0) paragraphs.push(current.join("\n"));
        current = [line.replace(LIST_ITEM, "")];
      } else {
        current.push(line);
      }
    }
    if (current.length > 0) paragraphs.push(current.join("\n"));
  }
  return paragraphs.map((paragraph) => paragraph.trim()).filter(Boolean);
}

/** Noktanın önündeki kelime bir kısaltma ya da tek harfli baş harf mi ("Dr.", "A. Yılmaz")? */
function endsWithAbbreviation(text: string): boolean {
  const word = /([\p{L}.]+)\.$/u.exec(text.trimEnd())?.[1];
  if (!word) return false;
  const key = word.toLocaleLowerCase("tr");
  return ABBREVIATIONS.has(key) || /^\p{Lu}$/u.test(word);
}

/** `end` noktadan hemen sonrası: önünde rakam, ardında küçük harfle süren kelime varsa sıra sayısıdır. */
function isOrdinal(paragraph: string, end: number): boolean {
  return /\d\.$/.test(paragraph.slice(0, end)) && /^\s+\p{Ll}/u.test(paragraph.slice(end));
}

export function splitSentences(paragraph: string): string[] {
  const sentences: string[] = [];
  let start = 0;
  for (const match of paragraph.matchAll(SENTENCE_END)) {
    const end = (match.index ?? 0) + match[0].length;
    // Alıntı işareti yoksa ve nokta bir kısaltmaya ya da sıra sayısına ("2. durum") aitse
    // cümle sürüyordur.
    if (!match[1] && match[0] === "." && endsWithAbbreviation(paragraph.slice(start, end))) continue;
    if (!match[1] && match[0] === "." && isOrdinal(paragraph, end)) continue;
    const sentence = paragraph.slice(start, end).trim();
    if (sentence) sentences.push(sentence);
    start = end;
  }
  const rest = paragraph.slice(start).trim();
  if (rest) sentences.push(rest);
  return sentences;
}

function citationsOf(sentence: string): number[] {
  const numbers = [...sentence.matchAll(CITATION)].map((match) => Number(match[1]));
  return [...new Set(numbers)];
}

function stripCitations(sentence: string): string {
  return sentence.replace(/\s*\[\d+\]/g, "").replace(/\s+([.,;:!?])/g, "$1").trim();
}

/**
 * Alıntısız cümle (ör. bir girişin devamı) aynı paragraftaki bir sonraki alıntılı cümlenin
 * kaynağını paylaşır; sonrasında yoksa öncekininkini. Backend'in doğrulama kuralıyla aynıdır.
 */
function inheritCitations(rows: { text: string; citations: number[] }[]): void {
  for (let index = 0; index < rows.length; index += 1) {
    if (rows[index].citations.length > 0) continue;
    const next = rows.slice(index + 1).find((row) => row.citations.length > 0);
    const previous = rows
      .slice(0, index)
      .reverse()
      .find((row) => row.citations.length > 0);
    rows[index].citations = [...(next ?? previous)?.citations ?? []];
  }
}

/** Noktalamasız kısa satır (alıntılanan slaytın başlığı gibi) bir iddia değil, başlıktır. */
function isHeading(paragraph: string): boolean {
  if (citationsOf(paragraph).length > 0) return false;
  const text = stripCitations(paragraph);
  return text.length > 0 && text.length <= MAX_HEADING_LENGTH && !/[.!?…:;]$/.test(text) && !text.includes("\n");
}

export function structureAnswer(answer: string): StructuredAnswer {
  const rows: { text: string; citations: number[] }[] = [];
  for (const paragraph of paragraphsOf(answer)) {
    if (isHeading(paragraph)) continue;
    const paragraphRows = splitSentences(paragraph.replace(/\n/g, " "))
      .map((sentence) => ({ text: stripCitations(sentence), citations: citationsOf(sentence) }))
      .filter((row) => row.text.length >= MIN_CLAIM_LENGTH);
    inheritCitations(paragraphRows);
    rows.push(...paragraphRows);
  }
  // Listeyi açan "…şöyledir:" cümlesi kendi paragrafında alıntısız kalır; ilk maddenin kaynağını
  // paylaşır. Başlık olarak gösterilmez: cevabın kendisi değil, girişidir.
  rows.forEach((row, index) => {
    if (row.citations.length > 0 || !row.text.endsWith(":")) return;
    row.citations = [...(rows.slice(index + 1).find((next) => next.citations.length > 0)?.citations ?? [])];
  });
  const intro = rows[0]?.text.endsWith(":") ?? false;

  const hasLead = rows.length >= LEAD_MIN_SENTENCES && !intro;
  const [first, ...rest] = rows;
  const body = hasLead ? rest : rows;
  return {
    lead: hasLead && first ? { number: 0, ...first } : null,
    claims: body.map((row, index) => ({ number: index + 1, ...row })),
  };
}

/** LLM'siz cevabın ilk satırı ("…en uygun kısım:") yalnızca bir giriştir; iddia değildir. */
export function stripExtractiveIntro(answer: string): string {
  const [first, ...rest] = answer.split("\n\n");
  return rest.length > 0 && first.trimEnd().endsWith(":") ? rest.join("\n\n") : answer;
}

/** İddiaların dayandığı farklı belge sayısı (alıntı başlıklarına göre). */
export function distinctDocuments(titles: (string | null | undefined)[]): number {
  return new Set(titles.filter(Boolean)).size;
}
