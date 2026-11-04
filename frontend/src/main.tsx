import '@fontsource-variable/figtree';
import '@fontsource-variable/fraunces/full.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { recarregarComVersaoNova } from './comum/atualizacao';
import './comum/identidade.css';
import './painel/painel.css';
import './painel/cartoes.css';
import './painel/estoque.css';
import './painel/gestao.css';
import './loja/loja.css';

recarregarComVersaoNova();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
