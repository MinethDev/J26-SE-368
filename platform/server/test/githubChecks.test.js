// Run with: npm test   (from platform/server)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeCi, summarizeConflicts } from '../src/connectors/github.js';

const run = (name, status, conclusion) => ({ name, status, conclusion });

test('no CI configured -> ci is null', () => {
  assert.equal(summarizeCi([], { statuses: [] }).ci, null);
  assert.equal(summarizeCi(null, null).ci, null);
});

test('all checks successful (or skipped/neutral) -> pass', () => {
  const r = summarizeCi([run('build', 'completed', 'success'), run('lint', 'completed', 'skipped')], { statuses: [{ context: 'cla', state: 'success' }] });
  assert.equal(r.ci, 'pass');
  assert.equal(r.total, 3);
});

test('any failing check run or status -> fail, and names the failing checks', () => {
  assert.deepEqual(summarizeCi([run('build', 'completed', 'failure'), run('lint', 'completed', 'success')], null).failing, ['build']);
  assert.equal(summarizeCi([], { statuses: [{ context: 'ci/legacy', state: 'error' }] }).ci, 'fail');
});

test('failure wins over pending; pending when something is still running', () => {
  assert.equal(summarizeCi([run('a', 'in_progress', null), run('b', 'completed', 'failure')], null).ci, 'fail');
  assert.equal(summarizeCi([run('a', 'queued', null), run('b', 'completed', 'success')], null).ci, 'pending');
});

test('merge conflicts follow GitHub mergeable (null = not computed yet)', () => {
  assert.equal(summarizeConflicts(true), 'pass');
  assert.equal(summarizeConflicts(false), 'fail');
  assert.equal(summarizeConflicts(null), null);
});