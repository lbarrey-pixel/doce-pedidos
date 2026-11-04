// Assinatura visual do painel: a calda de caramelo escorrendo da borda. Uma única animação,
// só na abertura, e nenhuma com movimento reduzido.
export function Calda() {
  return (
    <svg
      className="calda calda--horizontal"
      viewBox="0 0 1000 120"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        className="calda__escorrida"
        d="M0 0H1000V36C960 36 948 58 924 58C896 58 892 36 860 36C820 36 812 92 776 92
           C742 92 744 40 702 40C664 40 660 64 628 64C598 64 600 40 560 40C520 40 516 104 478 104
           C442 104 446 44 404 44C366 44 362 70 330 70C298 70 300 42 262 42C222 42 218 86 184 86
           C152 86 152 40 112 40C80 40 76 60 48 60C24 60 18 38 0 38Z"
      />
    </svg>
  );
}
