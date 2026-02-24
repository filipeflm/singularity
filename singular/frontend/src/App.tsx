import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import ImportLesson from './pages/ImportLesson'
import LessonStatus from './pages/LessonStatus'
import Review from './pages/Review'
import Exercises from './pages/Exercises'
import Progress from './pages/Progress'
import { reviewApi, type ReviewStats } from './api/client'

const styles = `
  :root {
    --bg: #0f1117;
    --surface: #1a1d2e;
    --surface2: #252840;
    --border: #2d3148;
    --accent: #6c63ff;
    --accent-light: #8b85ff;
    --success: #48bb78;
    --error: #fc8181;
    --warning: #f6ad55;
    --text: #e2e8f0;
    --text-muted: #718096;
    --text-dim: #4a5568;
  }
  body { background: var(--bg); color: var(--text); }
  a { color: inherit; text-decoration: none; }
  button { cursor: pointer; border: none; font-family: inherit; }
  input, textarea { font-family: inherit; }
`

function Nav() {
  const loc = useLocation()
  const [stats, setStats] = useState<ReviewStats | null>(null)

  useEffect(() => {
    reviewApi.getStats().then(setStats).catch(() => {})
    const interval = setInterval(() => {
      reviewApi.getStats().then(setStats).catch(() => {})
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  const links = [
    { to: '/', label: 'Importar' },
    { to: '/review', label: `Revisar${stats && stats.total_pending > 0 ? ` (${stats.total_pending})` : ''}` },
    { to: '/exercises', label: 'Exercícios' },
    { to: '/progress', label: 'Progresso' },
  ]

  return (
    <nav style={{
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      padding: '0 24px',
      display: 'flex',
      alignItems: 'center',
      height: '56px',
      gap: '8px',
    }}>
      <span style={{
        fontWeight: 700,
        fontSize: '18px',
        color: 'var(--accent-light)',
        marginRight: '24px',
        letterSpacing: '-0.5px',
      }}>
        Singular
      </span>
      {links.map(link => (
        <Link
          key={link.to}
          to={link.to}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            fontSize: '14px',
            fontWeight: 500,
            color: loc.pathname === link.to ? 'var(--accent-light)' : 'var(--text-muted)',
            background: loc.pathname === link.to ? 'rgba(108, 99, 255, 0.12)' : 'transparent',
            transition: 'all 0.15s',
          }}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  )
}

export default function App() {
  return (
    <>
      <style>{styles}</style>
      <BrowserRouter>
        <Nav />
        <main style={{ maxWidth: '900px', margin: '0 auto', padding: '32px 24px' }}>
          <Routes>
            <Route path="/" element={<ImportLesson />} />
            <Route path="/lessons/:id" element={<LessonStatus />} />
            <Route path="/review" element={<Review />} />
            <Route path="/exercises" element={<Exercises />} />
            <Route path="/progress" element={<Progress />} />
          </Routes>
        </main>
      </BrowserRouter>
    </>
  )
}
