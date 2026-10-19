// Run with: npm test   (from platform/server)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateInsight } from '../src/orchestrator/validateInsight.js';

const valid = {
  component: 'pull-request',
  type: 'reviewer-recommendation',
  title: 'Recommended reviewers for PR #1',
  target: { type: 'pullRequest', id: '1' },
  prediction: { label: 'Top reviewers', value: ['alice', 'bob'] },
  confidence: 0.8,
  severity: 'info',
  explanation: [{ feature: 'author_affinity', value: 0.9, impact: 0.4 }],
  recommendations: ['Ask alice'],
  evidence: [{ source: 'github', ref: 'o/r#1' }],
  modelVersion: 'rr-v1',
  isStub: false,
};

test('accepts an insight that follows Contract 2', () => {
  assert.deepEqual(validateInsight(valid), { ok: true, errors: [] });
});

test('rejects missing required fields', () => {
  const { prediction, ...noPrediction } = valid;
  const result = validateInsight(noPrediction);
  assert.equal(result.ok, false);
  assert.match(result.errors.join(' '), /prediction/);
});

test('rejects unknown components, severities and target types', () => {
  assert.equal(validateInsight({ ...valid, component: 'security' }).ok, false);
  assert.equal(validateInsight({ ...valid, severity: 'urgent' }).ok, false);
  assert.equal(validateInsight({ ...valid, target: { type: 'commit', id: 'x' } }).ok, false);
});

test('rejects platform-managed fields sent by a component', () => {
  assert.equal(validateInsight({ ...valid, projectId: 'p' }).ok, false);
  assert.equal(validateInsight({ ...valid, feedback: { decision: 'accepted' } }).ok, false);
});

test('rejects confidence outside [0, 1] and non-numeric impact', () => {
  assert.equal(validateInsight({ ...valid, confidence: 1.5 }).ok, false);
  assert.equal(validateInsight({ ...valid, explanation: [{ feature: 'x', impact: 'high' }] }).ok, false);
});
