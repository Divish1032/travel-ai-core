/**
 * API Service for TravelAI Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Generate itinerary from query
 */
export async function generateItinerary(query, skipNarrative = false) {
    const response = await fetch(`${API_BASE_URL}/api/generate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: query,
            skip_narrative: skipNarrative
        })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Generation failed');
    }

    return await response.json();
}

/**
 * Check API health
 */
export async function checkHealth() {
    const response = await fetch(`${API_BASE_URL}/health`);

    if (!response.ok) {
        throw new Error('API health check failed');
    }

    return await response.json();
}
