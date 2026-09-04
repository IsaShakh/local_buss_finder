import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { App } from '../app/App';
import { AppProviders } from '../app/providers';
import { authenticatedSessionHandler, testCsrfToken } from './handlers';
import { server } from './server';

export function renderApp(path = '/') {
  window.history.pushState({}, '', path);
  document.cookie = `csrftoken=${testCsrfToken}; Path=/`;

  return {
    user: userEvent.setup(),
    ...render(
      <AppProviders>
        <App />
      </AppProviders>,
    ),
  };
}

export function renderAuthenticatedApp(path = '/') {
  server.use(authenticatedSessionHandler);
  return renderApp(path);
}
