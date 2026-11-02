/**
 * Panneau latéral modal, accessible au clavier : le titre reçoit le focus à
 * l'ouverture, Échap ferme, et le focus revient sur l'élément qui l'a ouvert.
 */
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

interface Props {
  titre: string;
  sousTitre?: ReactNode;
  onFermer: () => void;
  children: ReactNode;
}

export default function PanneauLateral({ titre, sousTitre, onFermer, children }: Props) {
  const idTitre = useId();
  const refTitre = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const declencheur = document.activeElement as HTMLElement | null;
    refTitre.current?.focus();
    return () => declencheur?.focus();
  }, []);

  useEffect(() => {
    const surTouche = (evenement: KeyboardEvent) => {
      if (evenement.key === "Escape") onFermer();
    };
    window.addEventListener("keydown", surTouche);
    return () => window.removeEventListener("keydown", surTouche);
  }, [onFermer]);

  return (
    <>
      <div className="voile" onClick={onFermer} aria-hidden="true" />
      <section className="panneau" role="dialog" aria-modal="true" aria-labelledby={idTitre}>
        <header className="panneau__entete">
          <div>
            <h2 id={idTitre} ref={refTitre} tabIndex={-1}>
              {titre}
            </h2>
            {sousTitre && <p className="discret">{sousTitre}</p>}
          </div>
          <button type="button" className="bouton bouton--sobre" onClick={onFermer}>
            Fermer
          </button>
        </header>
        {children}
      </section>
    </>
  );
}
