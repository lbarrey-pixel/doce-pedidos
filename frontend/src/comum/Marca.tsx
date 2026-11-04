// Marca provisória: um doce em camadas desenhado em SVG, sem arquivo de imagem.
export function Marca({ className, tamanho = 96 }: { className?: string; tamanho?: number }) {
  return (
    <svg
      className={className}
      viewBox="0 0 96 96"
      width={tamanho}
      height={tamanho}
      role="img"
      aria-label="Doce Ateliê"
    >
      <circle cx="48" cy="48" r="46" fill="#f5eedc" />
      <path d="M22 54h52l-5 24a6 6 0 0 1-6 5H33a6 6 0 0 1-6-5z" fill="#953b1a" />
      <path d="M26 54c0-14 10-24 22-24s22 10 22 24z" fill="#d98b4a" />
      <path d="M31 46c4 4 8 4 12 0s9-4 13 0 8 4 9 0" fill="none" stroke="#f5eedc" strokeWidth="4" />
      <circle cx="48" cy="24" r="5" fill="#b3261e" />
    </svg>
  );
}
