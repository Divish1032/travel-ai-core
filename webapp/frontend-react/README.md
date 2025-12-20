# TravelAI React Frontend

Modern React frontend for the TravelAI itinerary generator.

## Tech Stack

- React 18
- Vite (build tool)
- CSS3 (no frameworks - keeping original styles)

## Development

### Prerequisites

- Node.js 18+
- npm or yarn

### Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` to set the API URL:
   ```
   VITE_API_URL=http://localhost:8000
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

   Open http://localhost:3000

### Build for Production

```bash
npm run build
```

Output will be in `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Docker Deployment

### Build Docker Image

```bash
docker build -t travelai-frontend .
```

### Run Docker Container

```bash
docker run -p 80:80 travelai-frontend
```

### Using Docker Compose

From the `webapp/` directory:

```bash
docker compose up -d --build
```

This will:
- Build the React app
- Serve it via Nginx
- Route traffic through Traefik

Access at: http://localhost/

## Project Structure

```
frontend-react/
├── src/
│   ├── components/         # React components
│   │   ├── Header.jsx
│   │   ├── QueryForm.jsx
│   │   ├── LoadingSection.jsx
│   │   ├── ErrorSection.jsx
│   │   ├── ResultSection.jsx
│   │   └── Footer.jsx
│   ├── services/           # API services
│   │   └── api.js
│   ├── styles/             # CSS styles
│   │   └── App.css
│   ├── App.jsx             # Main app component
│   └── main.jsx            # Entry point
├── index.html              # HTML template
├── vite.config.js          # Vite configuration
├── package.json            # Dependencies
├── Dockerfile              # Docker build
└── README.md               # This file
```

## Features

- Clean, responsive UI
- Real-time loading states
- Error handling
- Auto-scroll to results
- API health check on load
- Example query chips
- Skip narrative option

## API Integration

The app connects to the FastAPI backend at the URL specified in `VITE_API_URL`.

### Endpoints Used

- `POST /api/generate` - Generate itinerary
- `GET /health` - Health check

## Environment Variables

- `VITE_API_URL` - Backend API base URL (default: `http://localhost:8000`)

## Notes

- The UI is identical to the original HTML/CSS/JS version
- All styles are preserved in `src/styles/App.css`
- API calls are handled in `src/services/api.js`
- Components are kept simple and functional
