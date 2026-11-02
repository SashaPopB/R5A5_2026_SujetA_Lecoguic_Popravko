/**
 * Affiche une description mise en forme (A-02). Les éléments sont créés par
 * React à partir de l'arbre du Markdown : jamais de dangerouslySetInnerHTML.
 */
import { Fragment, useMemo } from "react";
import type { ReactNode } from "react";
import { analyserMarkdown } from "../../utils/markdown.ts";
import type { Inline } from "../../utils/markdown.ts";

function rendreEnLigne(elements: Inline[]): ReactNode[] {
  return elements.map((element, index) => {
    switch (element.type) {
      case "texte":
        return <Fragment key={index}>{element.valeur}</Fragment>;
      case "gras":
        return <strong key={index}>{rendreEnLigne(element.enfants)}</strong>;
      case "italique":
        return <em key={index}>{rendreEnLigne(element.enfants)}</em>;
      case "lien":
        return (
          <a key={index} href={element.url} target="_blank" rel="noopener noreferrer nofollow">
            {rendreEnLigne(element.enfants)}
          </a>
        );
    }
  });
}

export default function RenduDescription({ texte }: { texte: string }) {
  const blocs = useMemo(() => analyserMarkdown(texte), [texte]);
  return (
    <div className="description">
      {blocs.map((bloc, index) => {
        if (bloc.type === "paragraphe") {
          return (
            <p key={index}>
              {bloc.lignes.map((ligne, numero) => (
                <Fragment key={numero}>
                  {numero > 0 && <br />}
                  {rendreEnLigne(ligne)}
                </Fragment>
              ))}
            </p>
          );
        }
        const Liste = bloc.ordonnee ? "ol" : "ul";
        return (
          <Liste key={index}>
            {bloc.elements.map((element, numero) => (
              <li key={numero}>{rendreEnLigne(element)}</li>
            ))}
          </Liste>
        );
      })}
    </div>
  );
}
