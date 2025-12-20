/**
 * Loading Section Component
 */
export default function LoadingSection() {
    return (
        <div className="loading-section">
            <div className="spinner"></div>
            <p>Generating your personalized itinerary...</p>
            <p className="loading-note">This may take 30-60 seconds</p>
        </div>
    );
}
