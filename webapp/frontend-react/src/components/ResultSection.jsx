/**
 * Result Section Component
 */
import { useEffect, useRef } from 'react';

export default function ResultSection({ result }) {
    const resultRef = useRef(null);

    useEffect(() => {
        if (result && resultRef.current) {
            setTimeout(() => {
                resultRef.current.scrollIntoView({ behavior: 'smooth' });
            }, 100);
        }
    }, [result]);

    if (!result) return null;

    return (
        <div ref={resultRef} className="result-section">
            <div className="metadata">
                <span>💰 Cost: {result.metadata.cost}</span>
                <span>⏱️ Time: {result.metadata.time}</span>
                <span>✅ Score: {result.metadata.validation_score}</span>
            </div>
            <div
                className="itinerary-content"
                dangerouslySetInnerHTML={{ __html: result.html_output }}
            />
        </div>
    );
}
