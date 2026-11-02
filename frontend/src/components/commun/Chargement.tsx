export default function Chargement({ texte = "Chargement…" }: { texte?: string }) {
  return (
    <p className="chargement" role="status">
      {texte}
    </p>
  );
}
