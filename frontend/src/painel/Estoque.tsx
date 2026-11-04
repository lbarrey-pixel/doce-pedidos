import { useCallback, useEffect, useMemo, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import {
  ESTADOS_DO_CONTROLE,
  hora,
  NOME_DO_ESTADO,
  nomeDaVariante,
  type Saldo,
  type VarianteEstoque,
} from './estoque-tipos';
import { LancarMovimento } from './LancarMovimento';
import { Topo } from './Topo';

const SEM_ACENTO = (t: string) =>
  t
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();

// Estoque por variante, na loja e na cozinha. Cada cartão abre o lançamento.
export function Estoque({ token }: { token: string }) {
  const [variantes, setVariantes] = useState<VarianteEstoque[] | null>(null);
  const [erro, setErro] = useState('');
  const [busca, setBusca] = useState('');
  const [aberta, setAberta] = useState<string | null>(null);

  const carregar = useCallback(
    () =>
      chamarApi<{ variantes: VarianteEstoque[] }>('/painel/estoque', { token })
        .then((r) => setVariantes(r.variantes))
        .catch((e: unknown) =>
          setErro(
            e instanceof ErroDaApi && e.status !== 0
              ? e.message
              : 'O servidor está acordando. Recarregue a página em um minuto.',
          ),
        ),
    [token],
  );

  useEffect(() => {
    carregar();
  }, [carregar]);

  const grupos = useMemo(() => {
    const termo = SEM_ACENTO(busca.trim());
    const mapa = new Map<string, VarianteEstoque[]>();
    for (const v of variantes ?? []) {
      if (termo && !SEM_ACENTO(`${v.produto} ${v.tamanho} ${v.categoria}`).includes(termo))
        continue;
      mapa.set(v.categoria, [...(mapa.get(v.categoria) ?? []), v]);
    }
    return [...mapa.entries()];
  }, [variantes, busca]);

  function atualizar(id: string, saldo: Saldo, tipo: string) {
    if (tipo === 'inicio_descongelamento')
      carregar(); // traz a hora em que fica pronto
    else setVariantes((vs) => vs?.map((v) => (v.id === id ? { ...v, saldo } : v)) ?? vs);
  }

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        <section className="obra__abertura obra__abertura--curta">
          <h1 className="obra__titulo">Estoque</h1>
          <p className="obra__texto">
            Pronta entrega na loja; reserva congelada e estoque reserva na cozinha. O que começa a
            descongelar vira pronta entrega sozinho em 2 horas.
          </p>
          <input
            className="campo__entrada busca"
            type="search"
            placeholder="Buscar doce, bebida, sacola…"
            aria-label="Buscar no estoque"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </section>

        {erro && <p className="obra__aviso">{erro}</p>}
        {!variantes && !erro && (
          <p className="obra__aviso" role="status">
            Abrindo o estoque…
          </p>
        )}

        {grupos.map(([categoria, lista]) => (
          <section key={categoria} className="secao">
            <h2 className="secao__titulo">{categoria}</h2>
            {lista.map((v) => {
              const nome = nomeDaVariante(v);
              return (
                <article key={v.id} className="estoque" aria-label={nome}>
                  <div className="estoque__cabeca">
                    <h3 className="estoque__nome">{nome}</h3>
                    <button
                      type="button"
                      className="botao botao--contorno estoque__lancar"
                      aria-expanded={aberta === v.id}
                      onClick={() => setAberta(aberta === v.id ? null : v.id)}
                    >
                      Lançar
                    </button>
                  </div>
                  <dl className="estoque__saldos">
                    {ESTADOS_DO_CONTROLE[v.controle_estoque]
                      .filter((e) => e !== 'descongelando' || v.saldo.descongelando > 0)
                      .concat(v.saldo.separada > 0 ? ['separada'] : [])
                      .map((e) => (
                        <div key={e} className={`saldo saldo--${e}`}>
                          <dt>{NOME_DO_ESTADO[e]}</dt>
                          <dd>{v.saldo[e]}</dd>
                        </div>
                      ))}
                  </dl>
                  {v.descongelando.length > 0 && (
                    <p className="estoque__nota">
                      {v.descongelando
                        .map((l) => `${l.quantidade} pronto às ${hora(l.pronta_as)}`)
                        .join(' · ')}
                    </p>
                  )}
                  {aberta === v.id && (
                    <LancarMovimento
                      variante={v}
                      token={token}
                      aoLancar={(saldo, tipo) => atualizar(v.id, saldo, tipo)}
                    />
                  )}
                </article>
              );
            })}
          </section>
        ))}
      </main>
    </div>
  );
}
