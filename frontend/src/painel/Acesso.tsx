import { type ReactNode, useEffect, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { CriarSenha } from './CriarSenha';
import { Topo } from './Topo';

type Estado =
  | { tipo: 'carregando' }
  | { tipo: 'ok' }
  | { tipo: 'trocar_senha'; nome: string }
  | { tipo: 'sem_acesso' }
  | { tipo: 'falhou'; mensagem: string };

// Porta das telas internas: confirma na API que o login é de um operador ativo e, com senha
// provisória, só abre a troca de senha.
export function Acesso({ token, children }: { token: string; children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'carregando' });

  useEffect(() => {
    let ativo = true;
    chamarApi<{ nome: string; trocar_senha?: boolean }>('/painel/eu', { token })
      .then(
        (eu) =>
          ativo &&
          setEstado(eu.trocar_senha ? { tipo: 'trocar_senha', nome: eu.nome } : { tipo: 'ok' }),
      )
      .catch((e: unknown) => {
        if (!ativo) return;
        if (e instanceof ErroDaApi && e.status === 403) setEstado({ tipo: 'sem_acesso' });
        else
          setEstado({
            tipo: 'falhou',
            mensagem:
              e instanceof ErroDaApi && e.status !== 0
                ? e.message
                : 'O servidor está acordando. Recarregue a página em um minuto.',
          });
      });
    return () => {
      ativo = false;
    };
  }, [token]);

  if (estado.tipo === 'ok') return <>{children}</>;

  if (estado.tipo === 'trocar_senha') {
    return (
      <CriarSenha
        titulo="Troque a senha provisória"
        texto={`${estado.nome.split(' ')[0]}, crie a sua senha. A provisória deixa de valer.`}
        aoSalvar={async () => {
          await chamarApi('/painel/senha-trocada', { method: 'POST', token });
          setEstado({ tipo: 'ok' });
        }}
      />
    );
  }

  return (
    <div className="obra">
      <Topo />
      <main className="obra__corpo">
        {estado.tipo === 'carregando' && (
          <p className="obra__aviso" role="status">
            Abrindo o painel…
          </p>
        )}
        {estado.tipo === 'sem_acesso' && (
          <section className="obra__abertura">
            <h1 className="obra__titulo">Seu acesso ainda não foi liberado</h1>
            <p className="obra__texto">
              Peça ao dono da loja para liberar o seu e-mail no painel e entre de novo.
            </p>
          </section>
        )}
        {estado.tipo === 'falhou' && (
          <section className="obra__abertura">
            <h1 className="obra__titulo">Não deu para abrir o painel</h1>
            <p className="obra__texto">{estado.mensagem}</p>
          </section>
        )}
      </main>
    </div>
  );
}
