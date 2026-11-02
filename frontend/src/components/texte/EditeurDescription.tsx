/**
 * Éditeur de description avec barre de mise en forme (A-02) : gras,
 * italique, listes et liens. Le texte produit est du Markdown restreint,
 * visible en aperçu avant l'envoi.
 */
import { useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { DESCRIPTION_LONGUEUR_MAX } from "../../config.ts";
import RenduDescription from "./RenduDescription.tsx";

interface Props {
  valeur: string;
  onChange: (valeur: string) => void;
  libelle: string;
  desactive?: boolean;
}

interface Edition {
  texte: string;
  debutSelection: number;
  finSelection: number;
}

type Transformation = (texte: string, debut: number, fin: number) => Edition;

function entourer(marque: string, exemple: string): Transformation {
  return (texte, debut, fin) => {
    const selection = texte.slice(debut, fin) || exemple;
    return {
      texte: texte.slice(0, debut) + marque + selection + marque + texte.slice(fin),
      debutSelection: debut + marque.length,
      finSelection: debut + marque.length + selection.length,
    };
  };
}

function prefixerLignes(prefixe: (numero: number) => string): Transformation {
  return (texte, debut, fin) => {
    const debutLigne = texte.lastIndexOf("\n", debut - 1) + 1;
    const lignes = texte.slice(debutLigne, fin).split("\n");
    const bloc = lignes.map((ligne, index) => prefixe(index + 1) + ligne).join("\n");
    return {
      texte: texte.slice(0, debutLigne) + bloc + texte.slice(fin),
      debutSelection: debutLigne,
      finSelection: debutLigne + bloc.length,
    };
  };
}

const insererLien: Transformation = (texte, debut, fin) => {
  const libelle = texte.slice(debut, fin) || "document de travail";
  const url = "https://";
  const lien = `[${libelle}](${url})`;
  const positionUrl = debut + libelle.length + 3;
  return {
    texte: texte.slice(0, debut) + lien + texte.slice(fin),
    debutSelection: positionUrl,
    finSelection: positionUrl + url.length,
  };
};

const OUTILS: { libelle: string; titre: string; transformation: Transformation; raccourci?: string }[] = [
  { libelle: "G", titre: "Gras (Ctrl+B)", transformation: entourer("**", "texte en gras"), raccourci: "b" },
  { libelle: "I", titre: "Italique (Ctrl+I)", transformation: entourer("*", "texte en italique"), raccourci: "i" },
  { libelle: "• Liste", titre: "Liste à puces", transformation: prefixerLignes(() => "- ") },
  { libelle: "1. Liste", titre: "Liste numérotée", transformation: prefixerLignes((n) => `${n}. `) },
  { libelle: "Lien", titre: "Lien vers un document", transformation: insererLien },
];

export default function EditeurDescription({ valeur, onChange, libelle, desactive = false }: Props) {
  const idChamp = useId();
  const idAide = useId();
  const zone = useRef<HTMLTextAreaElement>(null);
  const [apercu, setApercu] = useState(false);

  const appliquer = (transformation: Transformation) => {
    const element = zone.current;
    if (!element) return;
    const edition = transformation(valeur, element.selectionStart, element.selectionEnd);
    onChange(edition.texte);
    requestAnimationFrame(() => {
      element.focus();
      element.setSelectionRange(edition.debutSelection, edition.finSelection);
    });
  };

  const surTouche = (evenement: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(evenement.ctrlKey || evenement.metaKey)) return;
    const outil = OUTILS.find((o) => o.raccourci === evenement.key.toLowerCase());
    if (outil) {
      evenement.preventDefault();
      appliquer(outil.transformation);
    }
  };

  return (
    <div className="champ editeur">
      <div className="editeur__entete">
        <label htmlFor={idChamp}>{libelle}</label>
        <button type="button" className="lien-nu" aria-pressed={apercu} onClick={() => setApercu(!apercu)}>
          {apercu ? "Modifier" : "Aperçu"}
        </button>
      </div>

      {apercu ? (
        <div className="editeur__apercu" aria-live="polite">
          {valeur.trim() ? <RenduDescription texte={valeur} /> : <p className="discret">Rien à afficher.</p>}
        </div>
      ) : (
        <>
          <div className="editeur__outils" role="toolbar" aria-label="Mise en forme" aria-controls={idChamp}>
            {OUTILS.map((outil) => (
              <button
                key={outil.titre}
                type="button"
                title={outil.titre}
                aria-label={outil.titre}
                disabled={desactive}
                onClick={() => appliquer(outil.transformation)}
              >
                {outil.libelle}
              </button>
            ))}
          </div>
          <textarea
            id={idChamp}
            ref={zone}
            value={valeur}
            rows={5}
            maxLength={DESCRIPTION_LONGUEUR_MAX}
            disabled={desactive}
            aria-describedby={idAide}
            placeholder="Ex. : **Projet SAE** – préparation de la démo"
            onChange={(evenement) => onChange(evenement.target.value)}
            onKeyDown={surTouche}
          />
        </>
      )}
      <p id={idAide} className="aide-champ">
        **gras**, *italique*, « - » ou « 1. » en début de ligne pour une liste, [texte](https://…) pour un lien.{" "}
        {valeur.length}/{DESCRIPTION_LONGUEUR_MAX}
      </p>
    </div>
  );
}
