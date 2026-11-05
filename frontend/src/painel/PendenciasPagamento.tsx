import { useCallback, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';

interface Pendencia {
  id: number;
  resultado: 'a_estornar' | 'a_decidir' | 'valor_recusado';
  numero: number | null; // número do pedido
  valor_cobrado_centavos: number | null;
  valor_pago_centavos: number | null;
  criado_em: string;
}

const NOME: Record<Pendencia['resultado'], string> = {
  a_estornar: 'A estornar',
  a_decidir: 'A decidir',
  valor_recusado: 'Valor recusado',
};
const ORIENTACAO: Record<Pendencia['resultado'], string> = {
  a_estornar: 'Faça o estorno no painel do gateway.',
  a_decidir:
    'Pagou depois de expirar e não há estoque: decida com o cliente (outro sabor, outro horário ou estorno).',
  valor_recusado:
    'O valor pago não confere com o do pedido; o pedido não foi confirmado. Confira no painel do gateway.',
};

// Pagamentos que pedem uma ação do operador: a estornar, a decidir e valor recusado. A seção
// some quando não há nada pendente.
export function PendenciasPagamento({ token, versao }: { token: string; versao: number }) {
  const [lista, setLista] = useState<Pendencia[]>([]);
  const [erro, setErro] = useState('');

  const carregar = useCallback(
    () =>
      chamarApi<{ pendencias: Pendencia[] }>('/painel/pagamentos/pendencias', { token })
        .then((r) => setLista(r.pendencias))
        .catch(() => undefined),
    [token],
  );
  useEffect(() => {
    carregar();
  }, [carregar, versao]);

  async function resolver(id: number) {
    setErro('');
    try {
      await chamarApi(`/painel/pagamentos/pendencias/${id}/resolver`, { method: 'POST', token });
      await carregar();
    } catch (e) {
      setErro(e instanceof ErroDaApi ? e.message : 'Não deu para salvar. Tente de novo.');
    }
  }

  if (lista.length === 0) return null;
  return (
    <section className="secao" aria-label="Pagamentos para conferir">
      <h2 className="secao__titulo">Pagamentos para conferir</h2>
      <ul className="pedido__itens">
        {lista.map((p) => (
          <li
            key={p.id}
            className="pedido__pendencia"
            aria-label={p.numero ? `Pedido nº ${p.numero}` : 'Pagamento sem pedido'}
          >
            <strong>{NOME[p.resultado] ?? p.resultado}</strong>
            {p.numero ? ` · Pedido nº ${p.numero}` : ' · sem pedido conhecido'}
            {p.valor_pago_centavos !== null && ` · pago ${formatarCentavos(p.valor_pago_centavos)}`}
            {p.valor_cobrado_centavos !== null &&
              p.valor_cobrado_centavos !== p.valor_pago_centavos &&
              ` · cobrado ${formatarCentavos(p.valor_cobrado_centavos)}`}
            <span className="obra__nota">{ORIENTACAO[p.resultado]}</span>
            <button type="button" className="botao botao--contorno" onClick={() => resolver(p.id)}>
              Resolvido
            </button>
          </li>
        ))}
      </ul>
      {erro && (
        <p className="formulario__erro" role="alert">
          {erro}
        </p>
      )}
    </section>
  );
}
