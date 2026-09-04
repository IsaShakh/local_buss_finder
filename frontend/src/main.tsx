import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';
import { AppProviders } from './app/providers';
import './styles/global.css';

const root = document.getElementById('root');

if (root === null) {
  throw new Error('Не найден корневой элемент приложения.');
}

createRoot(root).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
);
