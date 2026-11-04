import type { ReactNode } from 'react';
import { Marca } from '../comum/Marca';
import { Calda } from './Calda';

// Moldura das telas de acesso: campo de caramelo com o selo da loja e a calda escorrendo
// sobre o creme onde fica o formulário.
export function Moldura({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="acesso">
      <header className="acesso__caramelo">
        <Marca className="acesso__selo" tamanho={132} />
        <p className="acesso__assinatura">Doces artesanais, feitos por encomenda.</p>
        <Calda />
      </header>
      <main className="acesso__creme">
        <div className="acesso__conteudo">
          <h1 className="acesso__titulo">{titulo}</h1>
          {children}
        </div>
      </main>
    </div>
  );
}
