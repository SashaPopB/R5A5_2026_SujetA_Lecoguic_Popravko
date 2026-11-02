import type { ReactNode } from "react";

interface Props {
  type: "erreur" | "succes" | "info";
  children: ReactNode;
  onFermer?: () => void;
}

/** Message annoncé aux lecteurs d'écran (role="alert" pour les erreurs). */
export default function Message({ type, children, onFermer }: Props) {
  return (
    <div className={`message message--${type}`} role={type === "erreur" ? "alert" : "status"}>
      <span>{children}</span>
      {onFermer && (
        <button type="button" className="lien-nu" onClick={onFermer}>
          Masquer
        </button>
      )}
    </div>
  );
}
