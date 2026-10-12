import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import DevHarness from './mock/DevHarness';

// Entrada de desarrollo (/game.html): monta GamePage sobre el simulador, sin pasar por App.tsx.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DevHarness />
  </StrictMode>,
);
