// Small display helpers shared by the dashboard widgets.

// "author_affinity" -> "Author affinity"; "tharindu: author_affinity" -> "tharindu: Author affinity".
// The first letter is capitalised; labels that are already readable ("Behind the burndown") stay the same.
export function humanize(label) {
  if (typeof label !== 'string' || !label) return label;
  const nice = (s) => {
    const words = s.replace(/_/g, ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
  };
  const i = label.indexOf(': ');
  return i === -1 ? nice(label) : `${label.slice(0, i)}: ${nice(label.slice(i + 2))}`;
}

// Turns an evidence reference into a link when we know where it lives.
// "owner/repo#123" or "owner/repo#123:path" -> the GitHub pull request.
export function evidenceHref({ source, ref } = {}) {
  if (source === 'github' && typeof ref === 'string') {
    const m = ref.match(/^([\w.-]+\/[\w.-]+)#(\d+)/);
    if (m) return `https://github.com/${m[1]}/pull/${m[2]}`;
  }
  return null;
}

// Insight types where a higher prediction is worse (a risk), so upward pushes are shown in red.
export const RISK_TYPES = new Set(['quality-hotspot', 'sprint-risk']);

// Recommendations that are a fixed disclaimer rather than an action.
export const isDisclaimer = (text) => typeof text === 'string' && /^decision support only/i.test(text.trim());

// Lets long file paths wrap at "/" instead of in the middle of a word.
export function breakablePath(text) {
  if (typeof text !== 'string') return text;
  return text.split('/').flatMap((part, i) => (i === 0 ? [part] : ['/', { wbr: i }, part]));
}

// Sync result from the server -> "Synced Owner/repo: 9 pull requests, 1 developer."
const SYNC_LABELS = {
  repository: null,
  pullRequests: ['pull request', 'pull requests'],
  issues: ['issue', 'issues'],
  sprints: ['sprint', 'sprints'],
  developers: ['developer', 'developers'],
  files: ['file', 'files'],
  filesWithIssues: ['file with issues', 'files with issues'],
};
export function syncSummary(result = {}) {
  const parts = Object.entries(result)
    .filter(([k]) => SYNC_LABELS[k] !== null)
    .map(([k, v]) => {
      const label = SYNC_LABELS[k];
      if (!label || typeof v !== 'number') return `${k}: ${v}`;
      return `${v} ${v === 1 ? label[0] : label[1]}`;
    });
  const repo = result.repository ? `${result.repository}: ` : '';
  return `Synced ${repo}${parts.join(', ')}.`;
}

// A date -> "just now", "5 minutes ago", "2 hours ago", "3 days ago".
export function timeAgo(date) {
  if (!date) return 'never';
  const seconds = Math.round((Date.now() - new Date(date).getTime()) / 1000);
  if (seconds < 45) return 'just now';
  const units = [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60]];
  for (const [unit, size] of units) {
    const n = Math.floor(seconds / size);
    if (n >= 1) return `${n} ${unit}${n === 1 ? '' : 's'} ago`;
  }
  return 'just now';
}