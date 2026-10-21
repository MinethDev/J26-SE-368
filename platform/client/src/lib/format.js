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
