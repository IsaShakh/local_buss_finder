import { expect, test } from '@playwright/test';

test('login → campaign → progress → preliminary records', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Имя пользователя').fill('owner');
  await page.getByLabel('Пароль').fill('e2e-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.getByRole('link', { name: 'Кампании' }).click();
  await page.getByRole('link', { name: 'Новая кампания' }).click();
  await page.getByLabel('Название кампании').fill('E2E — Аланья');
  await page.getByLabel('Область поиска').selectOption({ label: 'Аланья — пилот' });
  await page.getByRole('checkbox', { name: 'Overture Maps' }).check();
  await page.getByRole('checkbox', { name: 'OpenStreetMap' }).check();
  await page.getByRole('button', { name: 'Создать кампанию' }).click();
  await page.getByRole('button', { name: 'Запустить кампанию' }).click();
  await expect(page.getByText('Завершена')).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Бизнесы', exact: true }).click();
  await expect(page.getByText('Найдено записей: 4')).toBeVisible();
  await expect(page.getByRole('note')).toContainText('Дедупликация ещё не выполнена');
});
