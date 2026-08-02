import { useState } from 'react';
import { useNavigate } from 'react-router';
import { submitReport } from '../lib/api';

const REPORT_TYPES = [
    { id: 'bug', label: '🐛 Bug report', hint: 'Something is broken or misbehaving' },
    { id: 'feature', label: '✨ Feature request', hint: 'Something you wish Clipo could do' },
    { id: 'feedback', label: '💬 Feedback', hint: 'General thoughts, ideas, or praise' },
];

export default function ReportScreen() {
    const [type, setType] = useState('bug');
    const [title, setTitle] = useState('');
    const [message, setMessage] = useState('');
    const [steps, setSteps] = useState('');
    const [expected, setExpected] = useState('');
    const [actual, setActual] = useState('');
    const [status, setStatus] = useState('editing'); // editing | submitting | sent | error
    const [issueUrl, setIssueUrl] = useState(null);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const valid = title.trim() || message.trim();

    const submit = async () => {
        setStatus('submitting');
        setError('');
        try {
            const res = await submitReport({
                type,
                title: title.trim(),
                message: message.trim(),
                steps: steps.trim(),
                expected: expected.trim(),
                actual: actual.trim(),
            });
            setIssueUrl(res.issue_url || null);
            setStatus('sent');
        } catch (err) {
            setStatus('error');
            setError(err.message || 'Something went wrong sending your report.');
        }
    };

    if (status === 'sent') {
        return (
            <div className="report-page">
                <div className="report-frame">
                    <header className="report-header">
                        <h1>Report submitted</h1>
                    </header>
                    <div className="report-body">
                        <div className="report-sent">
                            <h3>Thanks for reporting</h3>
                            <p>We received your {type} report and will review it shortly.</p>
                            {issueUrl && (
                                <p className="report-issue-link">
                                    It was filed as a GitHub issue —{' '}
                                    <a href={issueUrl} target="_blank" rel="noopener noreferrer">track it here</a>.
                                </p>
                            )}
                            <div className="report-actions">
                                <button className="ghost" onClick={() => navigate(-1)}>Back</button>
                                <button className="results-primary" onClick={() => navigate('/')}>Back to home</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="report-page">
            <div className="report-frame">
                <header className="report-header">
                    <button className="ghost" onClick={() => navigate(-1)}>← Back</button>
                    <h1>Send feedback</h1>
                </header>
                <div className="report-body">
                    <p>Tell us what went wrong or how we can improve — reports go straight to the maintainers.</p>

                    <div className="report-types" role="group" aria-label="Report type">
                        {REPORT_TYPES.map((t) => (
                            <button
                                key={t.id}
                                type="button"
                                className={`report-type${type === t.id ? ' active' : ''}`}
                                onClick={() => setType(t.id)}
                            >
                                <span className="report-type-label">{t.label}</span>
                                <span className="report-type-hint">{t.hint}</span>
                            </button>
                        ))}
                    </div>

                    <label className="report-field">
                        <span>Title</span>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder={type === 'feature' ? 'e.g. Support landscape mode in the player' : 'e.g. Captions burn onto the wrong frame'}
                        />
                    </label>

                    <label className="report-field">
                        <span>Description</span>
                        <textarea
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            placeholder="Describe what happened or what you'd like to see..."
                        />
                    </label>

                    {type === 'bug' && (
                        <>
                            <label className="report-field">
                                <span>Steps to reproduce <em className="report-opt">(optional)</em></span>
                                <textarea
                                    className="report-small"
                                    value={steps}
                                    onChange={(e) => setSteps(e.target.value)}
                                    placeholder="1. Upload a video\n2. Pick the Neon style\n3. ..."
                                />
                            </label>
                            <div className="report-row">
                                <label className="report-field">
                                    <span>Expected <em className="report-opt">(optional)</em></span>
                                    <textarea
                                        className="report-small"
                                        value={expected}
                                        onChange={(e) => setExpected(e.target.value)}
                                        placeholder="What should have happened?"
                                    />
                                </label>
                                <label className="report-field">
                                    <span>Actual <em className="report-opt">(optional)</em></span>
                                    <textarea
                                        className="report-small"
                                        value={actual}
                                        onChange={(e) => setActual(e.target.value)}
                                        placeholder="What actually happened?"
                                    />
                                </label>
                            </div>
                        </>
                    )}

                    {status === 'error' && (
                        <p className="report-error">⚠ {error}</p>
                    )}

                    <div className="report-actions">
                        <button className="results-quiet" onClick={() => navigate(-1)}>Cancel</button>
                        <button
                            className="results-primary"
                            onClick={submit}
                            disabled={!valid || status === 'submitting'}
                        >
                            {status === 'submitting' ? 'Sending…' : 'Send report'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
