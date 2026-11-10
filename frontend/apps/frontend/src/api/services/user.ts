import * as storage from '@/utils/storage';

import request from '../request';
import type {
  GetUsersApiV1UsersGetParams,
  ListResponseWithMeta,
  LoginCommand,
  OkRespLoginResponse,
  OkRespLogoutResponse,
  OkRespSignupResponse,
  OkRespUserInfo,
  SignupCommand,
  UserResponse,
} from '../types';

export async function login(params: LoginCommand): Promise<OkRespLoginResponse> {
  const result = await request.post('/v1/users/login', params);

  storage.set('token', result.data.token);

  return result;
}

export async function ssoLogin(code: string) {
  const result = await request.post(`/v1/users/token?code=${code}`);

  storage.set('token', result.data.token);

  return result;
}

export async function getUserInfo(): Promise<OkRespUserInfo> {
  return await request.get('/v1/users/me');
}

export async function getUsers(params: GetUsersApiV1UsersGetParams): Promise<ListResponseWithMeta<UserResponse>> {
  return await request.get('/v1/users', {
    params,
  });
}

export async function logout(): Promise<OkRespLogoutResponse> {
  localStorage.removeItem('token');
  localStorage.removeItem('username');
  localStorage.removeItem('userid');

  return await request.post('/v1/users/logout');
}

export async function signUp(params: SignupCommand): Promise<OkRespSignupResponse> {
  return await request.post('/v1/users/signup', params);
}

export async function getBootstrap(): Promise<{ data: { required: boolean } }> {
  return request.get('/v1/users/bootstrap');
}

export async function getUserDirectory(): Promise<{ data: UserResponse[] }> {
  return request.get('/v1/users/directory');
}

export async function createUser(params: SignupCommand & { is_admin: boolean }) {
  return request.post('/v1/users', params);
}

export async function updateUser(id: number, params: { is_admin?: boolean; is_active?: boolean; password?: string }) {
  return request.patch(`/v1/users/${id}`, params);
}

export interface PersonalToken {
  id: number;
  user_id: number;
  name: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
}

export async function getTokens(userId?: number): Promise<{ data: PersonalToken[] }> {
  return request.get('/v1/users/tokens', { params: { user_id: userId } });
}

export async function createToken(params: {
  name: string;
  expires_days: number | null;
}): Promise<{ data: PersonalToken & { token: string } }> {
  return request.post('/v1/users/tokens', params);
}

export async function revokeToken(id: number) {
  return request.delete(`/v1/users/tokens/${id}`);
}
