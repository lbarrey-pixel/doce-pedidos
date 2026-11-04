import { type FormEvent, useState } from 'react';
import { mensagemDeErroDeLogin } from '../comum/mensagens';
import { irPara, ROTAS } from '../comum/rotas';
import { supabase } from '../comum/supabase';
import { Moldura } from './Moldura';

export function Entrar() {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [mostrar, setMostrar] = useState(false);
  const [erro, setErro] = useState('');
  const [entrando, setEntrando] = useState(false);

  async function entrar(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !senha) {
      setErro('Preencha o e-mail e a senha.');
      return;
    }
    setErro('');
    setEntrando(true);
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password: senha,
    });
    setEntrando(false);
    if (error) {
      setErro(mensagemDeErroDeLogin(error));
      return;
    }
    irPara(ROTAS.painel, true);
  }

  return (
    <Moldura titulo="Painel da Doce Ateliê">
      <p className="acesso__texto">Estoque, pedidos e vendas da loja, num lugar só.</p>
      <form className="formulario" onSubmit={entrar} noValidate>
        <label className="campo">
          <span className="campo__rotulo">E-mail</span>
          <input
            className="campo__entrada"
            type="email"
            inputMode="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="campo">
          <span className="campo__rotulo">Senha</span>
          <span className="campo__linha">
            <input
              className="campo__entrada"
              type={mostrar ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
            <button
              type="button"
              className="campo__mostrar"
              aria-pressed={mostrar}
              onClick={() => setMostrar((m) => !m)}
            >
              {mostrar ? 'Esconder' : 'Mostrar'}
            </button>
          </span>
        </label>
        <p className="formulario__erro" role="alert" aria-live="polite">
          {erro}
        </p>
        <button className="botao" type="submit" disabled={entrando}>
          {entrando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </Moldura>
  );
}
