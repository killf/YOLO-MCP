module.exports = {
  root: true,
  extends: [require.resolve('@shlab/fabric/dist/eslint')],
  globals: {
    JSX: true,
    React: true,
    NodeJS: true,
  },
  rules: {
    '@typescript-eslint/no-namespace': 0,
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
  },
};
