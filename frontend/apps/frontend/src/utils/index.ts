export { default as compare } from 'lodash/isEqual.js';

/** 优先显示后端业务原因；错误码仅用于缺少具体原因时兜底。 */
export function getErrorMessage(
  error: unknown,
  fallback = '请求出现问题，请稍后重试',
  codeMessages: Partial<Record<number, string>> = {},
): string {
  const value = error as { response?: { data?: unknown }; code?: string; msg?: string; message?: string } | null;
  let data = value?.response?.data ?? value;
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch {
      // HTML、纯文本等非标准响应不作为业务错误展示。
      data = null;
    }
  }

  let localMessage: unknown;
  if (data && typeof data === 'object') {
    const body = data as { msg?: unknown; message?: unknown; err_code?: number };
    const codeMessage = typeof body.err_code === 'number' ? codeMessages[body.err_code] : undefined;
    for (const text of [body.msg, codeMessage]) {
      if (typeof text === 'string' && text.trim()) return text;
    }
    localMessage = body.message;
  }
  if (value?.code === 'ECONNABORTED' || value?.code === 'ETIMEDOUT') {
    return '请求超时，请稍后重试';
  }
  if (value?.code === 'ERR_NETWORK') return '无法连接服务，请检查网络或服务状态';
  if (typeof localMessage === 'string' && localMessage.trim()) return localMessage;
  return fallback;
}

/** 读取 JSON，仅还原 jsonStringify 保存的 /pattern/flags 正则字符串。 */
export const jsonParse = <T = any>(value: string): T => {
  return JSON.parse(value, (_key: string, entry: unknown) => {
    if (typeof entry !== 'string') {
      return entry;
    }

    try {
      const decoded = decodeURIComponent(entry);
      const separator = decoded.lastIndexOf('/');
      if (decoded.startsWith('/') && separator > 0) {
        return new RegExp(decoded.slice(1, separator), decoded.slice(separator + 1));
      }
    } catch {
      // 普通文本、损坏的编码及无效正则均保留原值。
    }

    return entry;
  });
};

/** 序列化配置，将 RegExp 编码为可由 jsonParse 还原的字符串。 */
export const jsonStringify = (value: Record<string, unknown>, type = 2): string => {
  return JSON.stringify(
    value,
    (_key: string, v: unknown) => {
      if (v instanceof RegExp) {
        return encodeURIComponent(v.toString());
      }
      return v;
    },
    type,
  );
};

export function downloadFromUrl(url: string, name?: string) {
  const link = document.createElement('a');
  link.href = url;

  if (name) {
    link.setAttribute('download', name);
  }

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
