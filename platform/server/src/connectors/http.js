// Small fetch helper shared by connectors: JSON, auth headers, readable errors.
export async function getJson(url, headers = {}, { timeoutMs = 30000 } = {}) {
  let res;
  try {
    res = await fetch(url, { headers: { Accept: 'application/json', ...headers }, signal: AbortSignal.timeout(timeoutMs) });
  } catch (err) {
    throw new Error(`Could not reach ${new URL(url).host}: ${err.cause?.code || err.message}`);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    const err = new Error(`${res.status} ${res.statusText} from ${new URL(url).host}${new URL(url).pathname}: ${text.slice(0, 200)}`);
    err.status = res.status === 401 || res.status === 403 ? 502 : res.status === 404 ? 404 : 502;
    throw err;
  }
  return res.json();
}

// Run async work over items with limited concurrency (be polite to APIs).
export async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

// Upsert by (projectId, source, sourceId) so re-syncing never duplicates.
export async function upsertMany(Model, docs) {
  if (!docs.length) return 0;
  const ops = docs.map((doc) => ({
    updateOne: {
      filter: { projectId: doc.projectId, source: doc.source, sourceId: doc.sourceId },
      update: { $set: doc },
      upsert: true,
    },
  }));
  await Model.bulkWrite(ops, { ordered: false });
  return docs.length;
}
