// Run with: npm test   (from platform/server)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { toChangelog } from '../src/connectors/jira.js';

const raw = {
  changelog: {
    histories: [
      { created: '2025-01-22T10:00:00.000+0000', items: [
        { field: 'status', from: '1', fromString: 'To Do', to: '3', toString: 'In Progress' },
        { field: 'assignee', from: null, to: 'abc' },
      ] },
      { created: '2025-01-21T09:00:00.000+0000', items: [
        { field: 'Sprint', from: '101', fromString: 'Sprint 1', to: '101, 102', toString: 'Sprint 1, Sprint 2' },
        { field: 'Story point estimate', fieldId: 'customfield_10016', from: null, fromString: null, to: null, toString: '5' },
      ] },
    ],
  },
};

test('keeps sprint, status and story point changes, oldest first', () => {
  assert.deepEqual(toChangelog(raw, 'customfield_10016'), [
    { field: 'Sprint', from: '101', to: '101, 102', at: '2025-01-21T09:00:00.000+0000' },
    { field: 'Story Points', from: null, to: '5', at: '2025-01-21T09:00:00.000+0000' },
    { field: 'status', from: '1', to: '3', at: '2025-01-22T10:00:00.000+0000' },
  ]);
});

test('story points are found by the configured custom field id', () => {
  const r = { changelog: { histories: [{ created: '2025-01-01T00:00:00.000+0000', items: [{ field: 'Points', fieldId: 'customfield_10028', fromString: '3', toString: '8' }] }] } };
  assert.deepEqual(toChangelog(r, 'customfield_10028'), [{ field: 'Story Points', from: '3', to: '8', at: '2025-01-01T00:00:00.000+0000' }]);
});

test('issues fetched without a changelog give an empty list', () => {
  assert.deepEqual(toChangelog({}, 'customfield_10016'), []);
});
