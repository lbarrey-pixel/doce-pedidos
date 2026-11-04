import { type FormEvent, useState } from 'react';
import { mensagemDeErroDeLogin, SENHA_MINIMA } from '../comum/mensagens';
import { irPara, ROTAS } from '../comum/rotas';
import { supabase } from '../comum/supabase';
import { Moldura } from './Moldura';

type Props = {
  titulo?: string;
  texto?: string;
  // Sem aoSalvar, vai ao painel. Com senha provisória, o painel avisa a API e segue.
  aoSalvar?: () => Promise<void>;
};

// Chega aqui pelo link do "esqueci minha senha" (o login veio no link) ou, logado com
// senha provisória, pelo painel.
export function CriarSenha({
  titulo = 'Crie sua senha',
  texto = 'Com ela você entra no painel deste e de outros aparelhos.',
  aoSalvar,
}: Props = {}) {
  const [senha, setSenha] = useState('');
  const [confirmacao, setConfirmacao] = useState('');
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);

  const curta = senha.length > 0 && senha.length < SENHA_MINIMA;
  const diferente = confirmacao.length > 0 && confirmacao !== senha;

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (senha.length < SENHA_MINIMA || senha !== confirmacao) return;
    setErro('');
    setSalvando(true);
    const { error } = await supabase.auth.updateUser({ password: senha });
    if (error) {
      setSalvando(false);
      setErro(
        error.message?.toLowerCase().includes('session')
          ? 'O link expirou. Peça um novo em "Esqueci minha senha".'
          : mensagemDeErroDeLogin(error),
      );
      return;
    }
    if (!aoSalvar) {
      irPara(ROTAS.painel, true);
      return;
    }
    try {
      await aoSalvar();
    } catch {
      setSalvando(false);
      setErro('A senha foi trocada, mas o painel não respondeu. Recarregue a página.');
    }
  }

  return (
    <Moldura titulo={titulo}>
      <p className="acesso__texto">{texto}</p>
      <form className="formulario" onSubmit={salvar} noValidate>
        <label className="campo">
          <span className="campo__rotulo">Senha nova</span>
          <input
            className="campo__entrada"
            type="password"
            autoComplete="new-password"
            minLength={SENHA_MINIMA}
            aria-invalid={curta}
            aria-describedby="dica-senha"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
          <span
            id="dica-senha"
            className={curta ? 'campo__dica campo__dica--alerta' : 'campo__dica'}
          >
            Pelo menos {SENHA_MINIMA} caracteres.
          </span>
        </label>
        <label className="campo">
          <span className="campo__rotulo">Repita a senha</span>
          <input
            className="campo__entrada"
            type="password"
            autoComplete="new-password"
            aria-invalid={diferente}
            value={confirmacao}
            onChange={(e) => setConfirmacao(e.target.value)}
          />
          {diferente && (
            <span className="campo__dica campo__dica--alerta">
              As duas senhas estão diferentes.
            </span>
          )}
        </label>
        <p className="formulario__erro" role="alert" aria-live="polite">
          {erro}
        </p>
        <button
          className="botao"
          type="submit"
          disabled={salvando || senha.length < SENHA_MINIMA || senha !== confirmacao}
        >
          {salvando ? 'Salvando…' : 'Salvar senha'}
        </button>
      </form>
    </Moldura>
  );
}
