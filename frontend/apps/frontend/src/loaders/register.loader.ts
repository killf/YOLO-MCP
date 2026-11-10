import { redirect } from 'react-router';

import { goRegister } from '@/utils/sso';
import * as storage from '@/utils/storage';
import { getBootstrap } from '@/api/services/user';

export async function registerLoader() {
  if (storage.get('token')) {
    return redirect('/projects');
  }

  if (window.IS_ONLINE) {
    goRegister();

    return Promise.resolve();
  }

  return (await getBootstrap()).data.required ? null : redirect('/login');
}
