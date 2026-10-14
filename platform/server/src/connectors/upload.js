// Requirement document upload (owner: Vidusini W. M. O.)
// Extracts text from an uploaded SRS/BRD so Requirement Intelligence can analyse it.
import { createHash } from 'node:crypto';
import pdfParse from 'pdf-parse/lib/pdf-parse.js';
import { Requirement } from '../models/index.js';
import { upsertMany } from './http.js';

export const ACCEPTED_TYPES = ['.pdf', '.txt', '.md'];

async function extractText(file) {
  const name = file.originalname.toLowerCase();
  if (name.endsWith('.pdf')) return (await pdfParse(file.buffer)).text;
  if (name.endsWith('.txt') || name.endsWith('.md')) return file.buffer.toString('utf8');
  throw Object.assign(new Error(`Unsupported file type. Accepted: ${ACCEPTED_TYPES.join(', ')}`), { status: 400 });
}

export async function saveRequirementDocument(project, file) {
  const rawText = (await extractText(file)).trim();
  if (!rawText) throw Object.assign(new Error('No text could be extracted from this file'), { status: 400 });
  const sourceId = createHash('sha256').update(file.buffer).digest('hex').slice(0, 16);
  await upsertMany(Requirement, [
    { projectId: project.key, source: 'upload', sourceId, fileName: file.originalname, mimeType: file.mimetype, rawText },
  ]);
  return { fileName: file.originalname, characters: rawText.length };
}
