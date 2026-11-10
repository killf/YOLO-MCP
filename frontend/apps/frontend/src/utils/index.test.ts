import assert from 'node:assert/strict';
import test from 'node:test';

import { compare, getErrorMessage, jsonParse, jsonStringify } from './index.ts';

test('training and inference preserve specific reasons instead of generic code messages', () => {
  const codes = { 30003: '请求错误' };
  for (const msg of ['训练集和测试集都需要至少一张已完成标注的图片', '模型下载失败，请检查网络']) {
    assert.equal(getErrorMessage({ msg, err_code: 30003 }, undefined, codes), msg);
    assert.equal(getErrorMessage({ response: { data: { msg, err_code: 30003 } } }, undefined, codes), msg);
  }
});

test('download text responses preserve JSON business errors and tolerate HTML', () => {
  assert.equal(getErrorMessage({ response: { data: '{"msg":"模型文件不存在","err_code":30003}' } }), '模型文件不存在');
  assert.equal(getErrorMessage({ response: { data: '<html>Bad Gateway</html>' } }, '下载失败'), '下载失败');
});

test('empty errors use one fallback and local validation messages remain readable', () => {
  assert.equal(getErrorMessage({ err_code: 0 }, undefined, { 0: '操作失败' }), '操作失败');
  assert.equal(getErrorMessage({ msg: ' ', err_code: 30003 }, undefined, { 30003: '请求错误' }), '请求错误');
  assert.equal(getErrorMessage({ message: '请选择标注工具' }), '请选择标注工具');
  for (const error of [null, undefined, {}, { msg: {} }]) {
    assert.equal(getErrorMessage(error, '请求失败'), '请求失败');
  }
});

test('network failures distinguish timeouts from unavailable services', () => {
  for (const code of ['ECONNABORTED', 'ETIMEDOUT']) {
    assert.equal(getErrorMessage({ code, message: 'timeout of 60000ms exceeded' }), '请求超时，请稍后重试');
  }
  assert.equal(getErrorMessage({ code: 'ERR_NETWORK' }), '无法连接服务，请检查网络或服务状态');
});

test('JSON keeps ordinary nested values intact', () => {
  const value = { name: 'a/b', values: [1, null, true, '%bad-escape'] };
  assert.deepEqual(jsonParse(JSON.stringify(value)), value);
});

test('regular expressions survive the supported JSON round trip', () => {
  const value = { rule: /a\/b\d+/gi, empty: /(?:)/, plain: 'new RegExp("x")' };
  assert.deepEqual(jsonParse(jsonStringify(value)), value);
});

test('invalid expressions and encoded text remain strings', () => {
  const value = { invalid: '/[/g', flags: '/x/gg', text: encodeURIComponent('a/b') };
  assert.deepEqual(jsonParse(JSON.stringify(value)), value);
});

test('code-like JSON strings are never executed', () => {
  const marker = globalThis as typeof globalThis & { labelsParserExecuted?: boolean };
  delete marker.labelsParserExecuted;
  const value = { text: '(globalThis.labelsParserExecuted = true)' };
  assert.deepEqual(jsonParse(JSON.stringify(value)), value);
  assert.equal(marker.labelsParserExecuted, undefined);
});

test('malformed JSON still reports the parse error', () => {
  assert.throws(() => jsonParse('{invalid}'), SyntaxError);
});

test('deep comparison handles primitives, null and nested arrays', () => {
  assert.equal(compare({ items: [1, null, { done: true }] }, { items: [1, null, { done: true }] }), true);
  assert.equal(compare({ items: [1, 2] }, { items: [2, 1] }), false);
  assert.equal(compare(null, {}), false);
});
