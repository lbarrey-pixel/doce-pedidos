// Seletor de quantidade para uma mão: − número +. O máximo desativa o "+".
export function Quantidade({
  valor,
  aoMudar,
  maximo,
  rotulo = 'Quantidade',
}: {
  valor: number;
  aoMudar: (n: number) => void;
  maximo?: number;
  rotulo?: string;
}) {
  return (
    <div className="quantidade" role="group" aria-label={rotulo}>
      <button
        type="button"
        className="quantidade__botao"
        aria-label="Menos um"
        disabled={valor <= 1}
        onClick={() => aoMudar(valor - 1)}
      >
        −
      </button>
      <input
        className="quantidade__numero"
        inputMode="numeric"
        aria-label={rotulo}
        value={valor}
        onChange={(e) => {
          const n = Number(e.target.value.replace(/\D/g, ''));
          if (n >= 1) aoMudar(maximo ? Math.min(n, maximo) : n);
        }}
      />
      <button
        type="button"
        className="quantidade__botao"
        aria-label="Mais um"
        disabled={maximo !== undefined && valor >= maximo}
        onClick={() => aoMudar(valor + 1)}
      >
        +
      </button>
    </div>
  );
}
