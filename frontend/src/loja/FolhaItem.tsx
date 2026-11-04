import { useEffect, useRef, useState } from 'react';
import { formatarCentavos } from '../comum/dinheiro';
import { Quantidade } from '../painel/Quantidade';
import { type VarianteLoja, urlDaFoto } from './tipos';

// Detalhe do item, aberto de baixo para cima: foto, descrição e quantidade.
export function FolhaItem({
  item,
  aoAdicionar,
  aoFechar,
}: {
  item: VarianteLoja;
  aoAdicionar: (quantidade: number) => void;
  aoFechar: () => void;
}) {
  const [quantidade, setQuantidade] = useState(1);
  const ref = useRef<HTMLDialogElement>(null);
  const foto = urlDaFoto(item.foto);

  useEffect(() => {
    const fechar = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', fechar);
    ref.current?.focus();
    return () => window.removeEventListener('keydown', fechar);
  }, [aoFechar]);

  return (
    <div className="folha__fundo" onClick={aoFechar}>
      <dialog
        open
        ref={ref}
        tabIndex={-1}
        className="folha"
        aria-label={item.produto}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="folha__fechar" aria-label="Fechar" onClick={aoFechar}>
          ×
        </button>
        {foto && <img className="prato prato--grande" src={foto} alt="" width={480} height={480} />}
        <h2 className="folha__nome">{item.produto}</h2>
        <p className="folha__tamanho">
          {[
            item.tamanho,
            item.peso_g && !item.tamanho.includes('g') ? `${item.peso_g} g` : '',
            /^\d+$/.test(item.porcoes)
              ? `${item.porcoes} ${item.porcoes === '1' ? 'porção' : 'porções'}`
              : item.porcoes,
          ]
            .filter(Boolean)
            .join(', ')}
        </p>
        {item.descricao && <p className="folha__texto">{item.descricao}</p>}
        {item.ingredientes && (
          <p className="folha__ingredientes">Ingredientes: {item.ingredientes}</p>
        )}
        {item.estado_disponibilidade === 'encomenda' && (
          <p className="folha__aviso">Sem pronta entrega agora: este item vai como Encomenda.</p>
        )}
        <div className="folha__acao">
          <Quantidade valor={quantidade} aoMudar={setQuantidade} />
          <button
            type="button"
            className="botao folha__adicionar"
            onClick={() => aoAdicionar(quantidade)}
          >
            Adicionar {formatarCentavos(item.preco_centavos * quantidade)}
          </button>
        </div>
      </dialog>
    </div>
  );
}
