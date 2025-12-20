/**
 * Query Form Component
 */
import { useState } from 'react';

export default function QueryForm({ onSubmit, isLoading }) {
    const [query, setQuery] = useState('');
    const [skipNarrative, setSkipNarrative] = useState(false);

    const exampleQueries = [
        '5 days Bangkok solo budget party',
        'romantic weekend in Phuket for couple',
        '3 days Chiang Mai family mid-range'
    ];

    const handleSubmit = (e) => {
        e.preventDefault();
        if (query.trim()) {
            onSubmit(query, skipNarrative);
        }
    };

    const setExampleQuery = (text) => {
        setQuery(text);
    };

    return (
        <div className="input-section">
            <form onSubmit={handleSubmit}>
                <div className="form-group">
                    <label htmlFor="query">Your Travel Query</label>
                    <input
                        type="text"
                        id="query"
                        name="query"
                        placeholder="e.g., 5 days Bangkok solo budget party"
                        required
                        autoComplete="off"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                    />
                </div>

                <div className="form-group checkbox">
                    <label>
                        <input
                            type="checkbox"
                            id="skipNarrative"
                            name="skipNarrative"
                            checked={skipNarrative}
                            onChange={(e) => setSkipNarrative(e.target.checked)}
                        />
                        Skip narrative (faster generation)
                    </label>
                </div>

                <button type="submit" disabled={isLoading}>
                    <span id="btnText">{isLoading ? 'Generating...' : 'Generate Itinerary'}</span>
                    {isLoading && <span className="loader"></span>}
                </button>
            </form>

            <div className="examples">
                <p><strong>Example queries:</strong></p>
                <div className="example-chips">
                    {exampleQueries.map((example, index) => (
                        <span
                            key={index}
                            className="chip"
                            onClick={() => setExampleQuery(example)}
                        >
                            {example}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
}
