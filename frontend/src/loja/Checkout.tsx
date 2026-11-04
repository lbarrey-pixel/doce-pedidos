import { type FormEvent, useMemo, useRef, useState } from 'react';
import { chamarApi, ErroDaApi } from '../comum/api';
import { formatarCentavos } from '../comum/dinheiro';
import { Quantidade } from '../painel/Quantidade';
import type { Carrinho } from './carrinho';
import { diaLocal, horarios, horariosDeHoje, rotuloHorario } from './horarios';
import type { Cardapio, PedidoCriado, VarianteLoja } from './tipos';

type Recusa = { texto: string; whatsapp?: string };
type Cotacao = { taxa: number; endereco: string };
type Rua = { logradouro: string; bairro: string; cidade: string };

// Fechamento do pedido: itens, quem pede, entrega ou retirada, quando.
export function Checkout({
  cardapio,
  carrinho,
  aoMudar,
  aoCriar,
}: {
  cardapio: Cardapio;
  carrinho: Carrinho;
  aoMudar: (id: string, q: number) => void;
  aoCriar: (pedido: PedidoCriado) => void;
}) {
  const porId = useMemo(
    () =>
      new Map<string, VarianteLoja>(
        cardapio.categorias.flatMap((c) => c.variantes).map((v) => [v.id, v]),
      ),
    [cardapio],
  );
  const linhas = Object.entries(carrinho).filter(([id]) => porId.has(id));
  const subtotal = linhas.reduce((t, [id, q]) => t + porId.get(id)!.preco_centavos * q, 0);
  const falta = cardapio.pedido_minimo_centavos - subtotal;
  const hoje = useMemo(
    () => horariosDeHoje(cardapio.primeiro_agendamento, cardapio.fecha_as_hora),
    [cardapio],
  );
  const semPronta = linhas.some(([id, q]) => q > porId.get(id)!.pronta);
  // Loja fechada com tudo em pronta entrega agenda hoje a partir da abertura.
  const precisaEncomenda = semPronta || (!cardapio.loja_aberta && hoje.length === 0);
  const podeAgora = cardapio.loja_aberta && !semPronta;
  // Com pronta entrega, o cliente ainda pode agendar um horário de hoje.
  const [agendar, setAgendar] = useState(false);
  const escolheHorario = !podeAgora || agendar;

  const [recebimento, setRecebimento] = useState<'entrega' | 'retirada'>('entrega');
  const [nome, setNome] = useState('');
  const [telefone, setTelefone] = useState('');
  const [mascarado, setMascarado] = useState<string | null>(null);
  // Taxa até o endereço anterior, vinda junto com o reconhecimento.
  const [taxaAnterior, setTaxaAnterior] = useState<number | null>(null);
  const [usarAnterior, setUsarAnterior] = useState(false);
  const [cep, setCep] = useState('');
  const [numero, setNumero] = useState('');
  const [complemento, setComplemento] = useState('');
  // CEP primeiro: a rua aparece e só então o cliente informa número e complemento.
  const [rua, setRua] = useState<Rua | null>(null);
  const [ruaErro, setRuaErro] = useState<string | null>(null);
  const cepPedido = useRef('');
  // Detalhes da entrega: quem recebe, portaria, ponto de referência.
  const [observacao, setObservacao] = useState('');
  const [cotacao, setCotacao] = useState<Cotacao | null>(null);
  const [horario, setHorario] = useState('');
  const [recusa, setRecusa] = useState<Recusa | null>(null);
  const [enviando, setEnviando] = useState(false);
  const opcoes = useMemo(() => {
    const encomendas = horarios(
      cardapio.primeira_encomenda,
      cardapio.abre_as_hora,
      cardapio.fecha_as_hora,
    );
    if (precisaEncomenda || hoje.length === 0) return encomendas;
    const dia = diaLocal(hoje[0]);
    return [...hoje, ...encomendas.filter((d) => diaLocal(d) > dia)];
  }, [cardapio, hoje, precisaEncomenda]);
  // Horário que saiu da lista (ex.: o carrinho passou a precisar de Encomenda) volta a vazio.
  const escolhido = opcoes.some((d) => d.toISOString() === horario) ? horario : '';
  const agendadaHoje = !precisaEncomenda && hoje.some((d) => d.toISOString() === escolhido);
  const encomenda = escolheHorario && !agendadaHoje;

  function erro(e: unknown): Recusa {
    if (e instanceof ErroDaApi) {
      const url = e.extra.whatsapp_url;
      return { texto: e.message, whatsapp: typeof url === 'string' ? url : undefined };
    }
    return { texto: 'Sem conexão. Confira a internet e tente de novo.' };
  }

  async function reconhecer() {
    if (!nome.trim() || telefone.replace(/\D/g, '').length < 10) return;
    try {
      const r = await chamarApi<{
        endereco_mascarado?: string;
        taxa_entrega_centavos?: number;
      }>('/loja/cliente/reconhecer', {
        method: 'POST',
        corpo: { telefone, nome },
      });
      setMascarado(r.endereco_mascarado ?? null);
      setTaxaAnterior(r.taxa_entrega_centavos ?? null);
      setUsarAnterior(false);
    } catch {
      setMascarado(null);
      setTaxaAnterior(null);
    }
  }

  // CEP não encontrado ou serviço fora do ar: combinar pelo WhatsApp com CEP e itens escritos.
  function whatsappDoCep(): string | null {
    if (!cardapio.whatsapp_url) return null;
    const d = cep.replace(/\D/g, '');
    const itens = linhas.map(([id, q]) => {
      const v = porId.get(id)!;
      return `${q}× ${v.produto} ${v.tamanho}`;
    });
    const url = new URL(cardapio.whatsapp_url);
    url.searchParams.set(
      'text',
      [
        `Olá! Quero fazer um pedido para entrega, mas o app não achou meu CEP ${d.slice(0, 5)}-${d.slice(5)}.`,
        ...itens,
      ].join('\n'),
    );
    return url.toString();
  }

  async function mudarCep(texto: string) {
    setCep(texto);
    setCotacao(null);
    setRua(null);
    setRuaErro(null);
    const digitos = texto.replace(/\D/g, '');
    cepPedido.current = digitos;
    if (digitos.length !== 8) return;
    try {
      const r = await chamarApi<Rua>(`/loja/cep/${digitos}`);
      if (cepPedido.current === digitos) setRua(r);
    } catch (e) {
      if (cepPedido.current === digitos)
        setRuaErro(e instanceof ErroDaApi ? e.message : 'Sem conexão. Confira a internet.');
    }
  }

  async function cotar() {
    setRecusa(null);
    setCotacao(null);
    try {
      const r = await chamarApi<{
        taxa_entrega_centavos: number;
        endereco: { logradouro: string; numero: string; bairro: string };
      }>('/loja/entrega/cotacao', { method: 'POST', corpo: { cep, numero } });
      const e = r.endereco;
      setCotacao({
        taxa: r.taxa_entrega_centavos,
        endereco: `${e.logradouro}, ${e.numero}, ${e.bairro}`,
      });
    } catch (e) {
      setRecusa(erro(e));
    }
  }

  const enderecoPronto =
    recebimento === 'retirada' || usarAnterior || (cotacao !== null && cep && numero);
  const pode =
    linhas.length > 0 &&
    falta <= 0 &&
    nome.trim() !== '' &&
    telefone.replace(/\D/g, '').length >= 10 &&
    Boolean(enderecoPronto) &&
    (!escolheHorario || escolhido !== '');

  async function fazerPedido(e: FormEvent) {
    e.preventDefault();
    if (!pode) return;
    setEnviando(true);
    setRecusa(null);
    try {
      const pedido = await chamarApi<PedidoCriado>('/loja/pedidos', {
        method: 'POST',
        corpo: {
          cliente: { nome: nome.trim(), telefone },
          recebimento,
          endereco:
            recebimento === 'entrega' && !usarAnterior ? { cep, numero, complemento } : null,
          usar_endereco_anterior: recebimento === 'entrega' && usarAnterior,
          itens: linhas.map(([variante_id, quantidade]) => ({ variante_id, quantidade })),
          tipo_entrega: encomenda ? 'encomenda' : 'pronta_entrega',
          entrega_em: escolheHorario ? escolhido : null,
          observacao: observacao.trim() || null,
        },
      });
      aoCriar(pedido);
    } catch (e) {
      setRecusa(erro(e));
    } finally {
      setEnviando(false);
    }
  }

  const taxa =
    recebimento === 'retirada' ? 0 : usarAnterior ? taxaAnterior : (cotacao?.taxa ?? null);

  return (
    <form className="checkout" onSubmit={fazerPedido} noValidate>
      <h1 className="checkout__titulo">Seu pedido</h1>

      <ul className="checkout__itens">
        {linhas.map(([id, q]) => {
          const v = porId.get(id)!;
          return (
            <li key={id} className="venda__item" aria-label={`${v.produto} ${v.tamanho}`}>
              <span className="venda__nome">
                {v.produto}
                <small>
                  {v.tamanho} · {formatarCentavos(v.preco_centavos * q)}
                </small>
              </span>
              <Quantidade
                valor={q}
                aoMudar={(n) => aoMudar(id, n)}
                rotulo={`Quantidade de ${v.produto}`}
              />
              <button type="button" className="venda__tirar" onClick={() => aoMudar(id, 0)}>
                Tirar
              </button>
            </li>
          );
        })}
      </ul>
      {linhas.length === 0 && <p className="checkout__vazio">Seu pedido está vazio.</p>}
      {falta > 0 && linhas.length > 0 && (
        <p className="checkout__aviso">
          Faltam {formatarCentavos(falta)} para o pedido mínimo de{' '}
          {formatarCentavos(cardapio.pedido_minimo_centavos)}.
        </p>
      )}

      <fieldset className="lancar__acoes">
        <legend className="campo__rotulo">Como você quer receber</legend>
        {(
          [
            ['entrega', 'Entregar no meu endereço'],
            ['retirada', 'Retirar na loja (sem taxa)'],
          ] as const
        ).map(([valor, texto]) => (
          <label key={valor} className="chip">
            <input
              type="radio"
              name="recebimento"
              checked={recebimento === valor}
              onChange={() => setRecebimento(valor)}
            />
            <span>{texto}</span>
          </label>
        ))}
      </fieldset>

      <label className="campo">
        <span className="campo__rotulo">Seu nome</span>
        <input
          className="campo__entrada"
          autoComplete="name"
          value={nome}
          maxLength={80}
          onChange={(e) => setNome(e.target.value)}
          onBlur={reconhecer}
        />
      </label>
      <label className="campo">
        <span className="campo__rotulo">WhatsApp</span>
        <input
          className="campo__entrada"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="(11) 99999-9999"
          value={telefone}
          maxLength={20}
          onChange={(e) => setTelefone(e.target.value)}
          onBlur={reconhecer}
        />
      </label>

      {recebimento === 'entrega' && mascarado && (
        <fieldset className="lancar__acoes checkout__anterior">
          <legend className="campo__rotulo">{mascarado}</legend>
          <label className="chip">
            <input
              type="radio"
              name="anterior"
              checked={usarAnterior}
              onChange={() => setUsarAnterior(true)}
            />
            <span>Entregar no mesmo endereço</span>
          </label>
          <label className="chip">
            <input
              type="radio"
              name="anterior"
              checked={!usarAnterior}
              onChange={() => setUsarAnterior(false)}
            />
            <span>Outro endereço</span>
          </label>
        </fieldset>
      )}

      {recebimento === 'entrega' && !usarAnterior && (
        <div className="checkout__endereco">
          <label className="campo">
            <span className="campo__rotulo">CEP</span>
            <input
              className="campo__entrada"
              inputMode="numeric"
              autoComplete="postal-code"
              value={cep}
              maxLength={9}
              onChange={(e) => void mudarCep(e.target.value)}
            />
          </label>
          {ruaErro && (
            <p className="checkout__aviso">
              {ruaErro}{' '}
              {whatsappDoCep() && (
                <a
                  className="checkout__whatsapp"
                  href={whatsappDoCep()!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Combinar pelo WhatsApp
                </a>
              )}
            </p>
          )}
          {rua && (
            <>
              <p className="checkout__rua" aria-live="polite">
                <strong>{rua.logradouro}</strong>
                <span>
                  {rua.bairro}, {rua.cidade}
                </span>
              </p>
              <label className="campo">
                <span className="campo__rotulo">Número</span>
                <input
                  className="campo__entrada"
                  value={numero}
                  maxLength={10}
                  onChange={(e) => {
                    setNumero(e.target.value);
                    setCotacao(null);
                  }}
                />
              </label>
              <label className="campo checkout__complemento">
                <span className="campo__rotulo">Complemento (opcional)</span>
                <input
                  className="campo__entrada"
                  value={complemento}
                  maxLength={60}
                  onChange={(e) => setComplemento(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="botao botao--contorno"
                onClick={cotar}
                disabled={cep.replace(/\D/g, '').length !== 8 || !numero.trim()}
              >
                Calcular entrega
              </button>
            </>
          )}
          {cotacao && (
            <p className="checkout__cotacao">
              {cotacao.endereco}: entrega {formatarCentavos(cotacao.taxa)}
            </p>
          )}
        </div>
      )}

      <label className="campo">
        <span className="campo__rotulo">Observação (opcional)</span>
        <textarea
          className="campo__entrada checkout__observacao"
          rows={2}
          maxLength={300}
          placeholder="Ex.: é presente para outra pessoa; entregar na recepção do hospital, quarto 302"
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
        />
      </label>

      {podeAgora && (
        <fieldset className="lancar__acoes">
          <legend className="campo__rotulo">Quando</legend>
          {(
            [
              [false, 'Agora (até 40 min)'],
              [true, 'Agendar dia e hora'],
            ] as const
          ).map(([valor, texto]) => (
            <label key={texto} className="chip">
              <input
                type="radio"
                name="quando"
                checked={agendar === valor}
                onChange={() => setAgendar(valor)}
              />
              <span>{texto}</span>
            </label>
          ))}
        </fieldset>
      )}

      {escolheHorario && (
        <label className="campo">
          <span className="campo__rotulo">
            {!precisaEncomenda
              ? 'Escolha quando receber'
              : cardapio.loja_aberta
                ? 'Sem pronta entrega para tudo: escolha quando receber a Encomenda'
                : 'A loja está fechada: escolha quando receber a Encomenda'}
          </span>
          <select
            className="campo__entrada"
            value={escolhido}
            onChange={(e) => setHorario(e.target.value)}
          >
            <option value="">Escolha dia e hora</option>
            {opcoes.map((d) => (
              <option key={d.toISOString()} value={d.toISOString()}>
                {rotuloHorario(d)}
              </option>
            ))}
          </select>
        </label>
      )}

      <dl className="resumo">
        <div>
          <dt>Itens</dt>
          <dd>{formatarCentavos(subtotal)}</dd>
        </div>
        <div>
          <dt>Entrega</dt>
          <dd>
            {taxa === null ? 'calcule acima' : taxa === 0 ? 'grátis' : formatarCentavos(taxa)}
          </dd>
        </div>
        <div className="resumo__total">
          <dt>Total</dt>
          <dd>
            {formatarCentavos(subtotal + (taxa ?? 0))}
            {taxa === null ? ' + entrega' : ''}
          </dd>
        </div>
      </dl>

      {recusa && (
        <p className="formulario__erro" role="alert">
          {recusa.texto}{' '}
          {recusa.whatsapp && (
            <a
              className="checkout__whatsapp"
              href={recusa.whatsapp}
              target="_blank"
              rel="noreferrer"
            >
              Combinar pelo WhatsApp
            </a>
          )}
        </p>
      )}
      <button className="botao" type="submit" disabled={!pode || enviando}>
        {enviando ? 'Enviando…' : 'Fazer pedido e pagar com Pix'}
      </button>
    </form>
  );
}
