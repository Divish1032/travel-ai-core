/**
 * Error Section Component
 */
export default function ErrorSection({ message }) {
    if (!message) return null;

    return (
        <div className="error-section">
            <h3>⚠️ Error</h3>
            <p>{message}</p>
        </div>
    );
}
