/**
 * Footer Component
 */
export default function Footer() {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001/travelai';

    return (
        <footer>
            <p>
                Powered by TravelAI RAG Pipeline |{' '}
                <a href={`${API_URL}/health`} target="_blank" rel="noopener noreferrer">
                    API Health
                </a>
            </p>
        </footer>
    );
}
