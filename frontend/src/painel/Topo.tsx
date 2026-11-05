import { Marca } from '../comum/Marca';
import { irPara, ROTAS } from '../comum/rotas';
import { supabase } from '../comum/supabase';
import { Calda } from './Calda';

const ABAS = [
  [ROTAS.pedidos, 'Pedidos'],
  [ROTAS.producao, 'Produção'],
  [ROTAS.estoque, 'Estoque'],
  [ROTAS.vendas, 'Vendas'],
  [ROTAS.resumos, 'Resumos'],
  [ROTAS.configuracao, 'Configuração'],
] as const;

async function sair() {
  // Sai só deste aparelho: o padrão do Supabase (global) desconecta todos os celulares e abas.
  await supabase.auth.signOut({ scope: 'local' });
  irPara(ROTAS.entrar, true);
}

// Topo caramelo das telas internas, com a navegação entre elas e a saída.
export function Topo() {
  return (
    <header className="obra__topo">
      <Marca className="obra__selo" tamanho={52} />
      <nav className="obra__nav" aria-label="Painel">
        {ABAS.map(([caminho, nome]) => (
          <a
            key={caminho}
            className="obra__sair"
            href={caminho}
            aria-current={window.location.pathname === caminho ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault();
              irPara(caminho);
            }}
          >
            {nome}
          </a>
        ))}
        <button className="obra__sair" type="button" onClick={sair}>
          Sair
        </button>
      </nav>
      <Calda />
    </header>
  );
}
