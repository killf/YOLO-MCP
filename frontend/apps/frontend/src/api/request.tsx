import { notification } from 'antd';
import { get } from 'lodash-es';
import type { AxiosError, AxiosResponse } from 'axios';
import { create } from 'axios';

import commonController from '@/utils/common';
import { getErrorMessage } from '@/utils';
import { ErrorMessages } from '@/api/constant';
import { goLogin } from '@/utils/sso';

/**
 * 滑动续期：后端在响应头 `X-New-Token` 中返回新签发的 token 时，更新本地存储，
 * 使活跃用户的登录态自动延续，不会到点被强制登出。
 * @param response
 */
function applyRefreshedToken(response: AxiosResponse<any>) {
  const newToken = response?.headers?.['x-new-token'];
  if (newToken) {
    localStorage.token = newToken;
  }
}

/**
 * 后端返回的结构由 { data, meta_data } 包裹
 * @param response
 * @returns
 */
export function successHandler(response: AxiosResponse<any>) {
  applyRefreshedToken(response);
  return response.data;
}

async function errorHandler(error: AxiosError) {
  let data = get(error, 'response.data');

  if (data instanceof Blob) {
    try {
      data = await data.text();
    } catch {
      data = undefined;
    }
  }
  const userMessage = getErrorMessage({ ...error, response: { data } }, undefined, ErrorMessages);

  // 开发环境和开发自测环境显示报错信息
  if (window.DEV) {
    notification.error({
      message: `${userMessage}【${get(error, 'response.status', '无状态码')}】`,
      description: (
        <>
          <p>{error.message}</p>
          <p>{error.request?.responseURL}</p>
        </>
      ),
    });
  } else {
    commonController.notificationErrorMessage({ msg: userMessage }, 5);
  }

  return Promise.reject(error);
}

const authorizationBearerSuccess = (config: any) => {
  const token = localStorage.token;
  if (token) {
    config.headers.Authorization = localStorage.token;
  }
  return config;
};

const authorizationBearerFailed = (error: any) => {
  // 401一秒后跳转到登录页
  if (error?.response?.status === 401) {
    localStorage.removeItem('token');
    setTimeout(() => {
      if (window.IS_ONLINE) {
        goLogin();
      } else if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }, 1000);
  }

  return Promise.reject(error);
};

const requestConfig = {
  timeout: 60 * 1000,
  baseURL: '/api',
};

const request = create(requestConfig);

export const requestWithHeaders = create(requestConfig);

requestWithHeaders.interceptors.request.use(authorizationBearerSuccess, authorizationBearerFailed);
requestWithHeaders.interceptors.response.use((response) => {
  applyRefreshedToken(response);
  return response;
}, authorizationBearerFailed);
requestWithHeaders.interceptors.response.use(undefined, errorHandler);

request.interceptors.request.use(authorizationBearerSuccess, authorizationBearerFailed);
request.interceptors.response.use(successHandler, errorHandler);
request.interceptors.response.use(undefined, authorizationBearerFailed);

export default request;
