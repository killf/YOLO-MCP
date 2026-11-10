import { initReactI18next } from 'react-i18next';
import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import { resources } from './locales';

// 翻译资源使用字符串，运行配置与调用方类型都不返回 null。
declare module 'i18next' {
  interface CustomTypeOptions {
    returnNull: false;
  }
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh-CN',
    returnNull: false,
    interpolation: {
      escapeValue: false,
    },
  });

export { i18n };
export * from 'react-i18next';
