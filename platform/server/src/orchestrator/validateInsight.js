// Validates component output against Contract 2 (shared/schemas/insight.schema.json).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';

const schemaPath = fileURLToPath(new URL('../../../../shared/schemas/insight.schema.json', import.meta.url));
const insightSchema = JSON.parse(readFileSync(schemaPath, 'utf8'));

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validate = ajv.compile(insightSchema);

export function validateInsight(insight) {
  const ok = validate(insight);
  if (ok) return { ok: true, errors: [] };
  const errors = validate.errors.map((e) => `${e.instancePath || '(root)'} ${e.message}`);
  return { ok: false, errors };
}
