interface Props {
  page: number;
  taille: number;
  total: number;
  onPage: (page: number) => void;
}

export default function Pagination({ page, taille, total, onPage }: Props) {
  const nbPages = Math.max(1, Math.ceil(total / taille));
  if (nbPages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <button type="button" className="bouton bouton--sobre" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Précédent
      </button>
      <span>
        Page {page} sur {nbPages}
      </span>
      <button
        type="button"
        className="bouton bouton--sobre"
        disabled={page >= nbPages}
        onClick={() => onPage(page + 1)}
      >
        Suivant
      </button>
    </nav>
  );
}
