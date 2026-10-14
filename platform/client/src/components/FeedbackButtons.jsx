import { useState } from 'react';
import { api } from '../lib/api.js';

// Human-in-the-loop: the user accepts or rejects a recommendation; stored on the insight.
export default function FeedbackButtons({ insight }) {
  const [feedback, setFeedback] = useState(insight.feedback);
  const [error, setError] = useState(null);

  async function send(decision) {
    setError(null);
    try {
      const d = await api(`/insights/${insight._id}/feedback`, { method: 'POST', body: { decision } });
      setFeedback(d.insight.feedback);
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="feedback">
      {feedback?.decision ? (
        <span className={`muted small feedback-${feedback.decision}`}>
          {feedback.decision === 'accepted' ? 'Accepted' : 'Rejected'} by {feedback.by}
        </span>
      ) : (
        <span className="muted small">Was this useful?</span>
      )}
      <button className="btn btn-small" onClick={() => send('accepted')} aria-pressed={feedback?.decision === 'accepted'}>Accept</button>
      <button className="btn btn-small" onClick={() => send('rejected')} aria-pressed={feedback?.decision === 'rejected'}>Reject</button>
      {error && <span className="error small">{error}</span>}
    </div>
  );
}
