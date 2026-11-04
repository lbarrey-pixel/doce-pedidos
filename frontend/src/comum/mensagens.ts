// Mensagens de erro do login em linguagem do Operador: o que houve e o que fazer.
export function mensagemDeErroDeLogin(erro: { message?: string; status?: number } | null): string {
  if (!erro) return '';
  const texto = (erro.message ?? '').toLowerCase();
  if (texto.includes('invalid login credentials')) return 'E-mail ou senha não conferem.';
  if (texto.includes('email not confirmed'))
    return 'Confirme o e-mail pelo link que enviamos antes de entrar.';
  if (erro.status === 429 || texto.includes('rate limit'))
    return 'Muitas tentativas seguidas. Espere um minuto e tente de novo.';
  if (texto.includes('password should be at least') || texto.includes('weak'))
    return 'A senha precisa de pelo menos 8 caracteres.';
  if (texto.includes('fetch') || texto.includes('network'))
    return 'Sem conexão. Confira a internet e tente de novo.';
  return 'Não deu para concluir agora. Tente de novo em instantes.';
}

export const SENHA_MINIMA = 8;
