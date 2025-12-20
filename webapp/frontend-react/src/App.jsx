/**
 * Main App Component
 */
import { useState, useEffect } from 'react';
import Header from './components/Header';
import QueryForm from './components/QueryForm';
import LoadingSection from './components/LoadingSection';
import ErrorSection from './components/ErrorSection';
import ResultSection from './components/ResultSection';
import Footer from './components/Footer';
import { generateItinerary, checkHealth } from './services/api';
import './styles/App.css';

export default function App() {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [result, setResult] = useState(null);

    // Check API health on mount
    useEffect(() => {
        checkHealth()
            .then(data => {
                console.log('API Health:', data);
            })
            .catch(err => {
                console.error('Failed to connect to API:', err);
            });
    }, []);

    const handleSubmit = async (query, skipNarrative) => {
        setIsLoading(true);
        setError(null);
        setResult(null);

        try {
            const data = await generateItinerary(query, skipNarrative);
            setResult(data);
        } catch (err) {
            console.error('Generation error:', err);
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <>
            <div className="container">
                <Header />
                <QueryForm onSubmit={handleSubmit} isLoading={isLoading} />
                {isLoading && <LoadingSection />}
                <ErrorSection message={error} />
                <ResultSection result={result} />
            </div>
            <Footer />
        </>
    );
}
