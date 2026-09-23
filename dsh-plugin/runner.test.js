import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { runPython } from './runner.js';

const projectDir = fileURLToPath(new URL('../', import.meta.url));
const pythonPath = process.env.SF_DSH_PYTHON || join(projectDir,
  process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');

test('Node/Python bridge returns sanitized validation errors without calling SF', async () => {
  const result = await runPython({ projectDir, pythonPath }, {
    operation: 'create', payload: {}, environment: 'production', sign_mode: 'simple',
    partner_id: 'test-partner', checkword: 'private-test-secret',
  });
  assert.equal(result.error.code, 'INVALID_INPUT');
  assert.equal(JSON.stringify(result).includes('private-test-secret'), false);
});

test('missing Python executable rejects with an actionable error', async () => {
  await assert.rejects(runPython({ projectDir, pythonPath: join(projectDir, 'missing-python.exe') }, {}), /Python/);
});

test('an already cancelled call never starts a subprocess', async () => {
  await assert.rejects(runPython({ projectDir, pythonPath }, {}, AbortSignal.abort()), /取消/);
});
