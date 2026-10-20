import type { DocumentOut } from "../../api/types";
import { materialLabel } from "../../labels";
import { MATERIAL_SECTIONS } from "../courses/sections";

/** Komut paletindeki bir satır. */
export type Command =
  | { kind: "ask"; id: string; label: string; question: string }
  | { kind: "navigate"; id: string; label: string; hint: string; to: string }
  | { kind: "document"; id: string; label: string; hint: string; to: string };

export interface CommandGroup {
  title: string;
  commands: Command[];
}

const MAX_DOCUMENTS = 6;

/** Türkçe büyük/küçük harf ve aksan farkını yok sayan karşılaştırma anahtarı. */
export function searchKey(text: string): string {
  return text
    .toLocaleLowerCase("tr")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ı/g, "i")
    .replace(/\s+/g, " ")
    .trim();
}

function matches(haystack: string, needle: string): boolean {
  if (!needle) return true;
  const key = searchKey(haystack);
  return searchKey(needle)
    .split(" ")
    .every((word) => key.includes(word));
}

/** Belgenin hangi ders bölümünde listelendiği (OCW düzeni); bulunamazsa tüm materyaller. */
function sectionPathFor(document: DocumentOut, base: string): string {
  const section = MATERIAL_SECTIONS.find((item) => item.types.includes(document.material_type));
  return section ? `${base}/${section.path}` : `${base}/materials`;
}

/**
 * Yazılan metne göre palet satırları: önce "materyale sor", sonra eşleşen belgeler ve bölümler.
 * Metin boşken yalnızca gezinme ve son eklenen belgeler gösterilir.
 */
export function buildCommands(query: string, base: string, documents: DocumentOut[]): CommandGroup[] {
  const text = query.trim();
  const groups: CommandGroup[] = [];

  if (text) {
    groups.push({
      title: "Soru",
      commands: [{ kind: "ask", id: "ask", label: `Materyale sor: “${text}”`, question: text }],
    });
  }

  const found = documents
    .filter((document) => matches(`${document.title} ${document.filename}`, text))
    .slice(0, MAX_DOCUMENTS)
    .map<Command>((document) => ({
      kind: "document",
      id: `document-${document.id}`,
      label: document.title,
      hint: materialLabel(document.material_type),
      to: sectionPathFor(document, base),
    }));
  if (found.length > 0) groups.push({ title: "Belgeler", commands: found });

  const places: Command[] = [
    { kind: "navigate" as const, id: "overview", label: "Ders sayfası", hint: "Genel bakış", to: base },
    {
      kind: "navigate" as const,
      id: "materials",
      label: "Tüm materyaller",
      hint: "Liste",
      to: `${base}/materials`,
    },
    ...MATERIAL_SECTIONS.map((section) => ({
      kind: "navigate" as const,
      id: `section-${section.path}`,
      label: section.label,
      hint: "Bölüm",
      to: `${base}/${section.path}`,
    })),
  ].filter((command) => matches(command.label, text));
  if (places.length > 0) groups.push({ title: "Git", commands: places });

  return groups;
}

export function flatten(groups: CommandGroup[]): Command[] {
  return groups.flatMap((group) => group.commands);
}
