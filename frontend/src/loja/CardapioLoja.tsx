import { useState } from 'react';
import { formatarCentavos } from '../comum/dinheiro';
import { FolhaItem } from './FolhaItem';
import { type Cardapio, type VarianteLoja, urlDaFoto } from './tipos';

function Prato({ item }: { item: VarianteLoja }) {
  const foto = urlDaFoto(item.foto);
  return foto ? (
    <img className="prato" src={foto} alt="" width={96} height={96} loading="lazy" />
  ) : (
    <span className="prato prato--vazio" aria-hidden="true">
      {item.produto.replace(/^(Bolo de Pote|Torta|Bolo|Brigadeiro) (de |do |da )?/, '').charAt(0)}
    </span>
  );
}

// Cardápio do app: categorias em abas, itens em linhas com o pratinho à direita.
export function CardapioLoja({
  cardapio,
  aoAdicionar,
}: {
  cardapio: Cardapio;
  aoAdicionar: (id: string, quantidade: number) => void;
}) {
  const [aberto, setAberto] = useState<VarianteLoja | null>(null);
  const ancora = (nome: string) => `cat-${nome.replace(/\W+/g, '-').toLowerCase()}`;

  return (
    <>
      <nav className="abas" aria-label="Categorias">
        {cardapio.categorias.map((c) => (
          <a key={c.nome} className="abas__item" href={`#${ancora(c.nome)}`}>
            {c.nome}
          </a>
        ))}
      </nav>
      {cardapio.categorias.map((c) => (
        <section key={c.nome} id={ancora(c.nome)} className="categoria">
          <h2 className="categoria__nome">{c.nome}</h2>
          <ul className="itens">
            {c.variantes.map((v) => (
              <li key={v.id}>
                <button type="button" className="item" onClick={() => setAberto(v)}>
                  <span className="item__texto">
                    <span className="item__nome">{v.produto}</span>
                    <span className="item__tamanho">{v.tamanho}</span>
                    {v.descricao && <span className="item__descricao">{v.descricao}</span>}
                    <span className="item__preco">
                      {formatarCentavos(v.preco_centavos)}
                      {v.estado_disponibilidade === 'encomenda' && (
                        <span className="item__selo">Só por Encomenda</span>
                      )}
                    </span>
                  </span>
                  <Prato item={v} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {aberto && (
        <FolhaItem
          item={aberto}
          aoFechar={() => setAberto(null)}
          aoAdicionar={(q) => {
            aoAdicionar(aberto.id, q);
            setAberto(null);
          }}
        />
      )}
    </>
  );
}
