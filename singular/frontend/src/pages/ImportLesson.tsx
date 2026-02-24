/**
 * Tela 1 — Importar Aula
 * Ponto de entrada do pipeline. O usuário cola uma URL do YouTube
 * ou ativa o modo mock para testar sem API.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { lessonsApi, type Lesson } from '../api/client'

export default function ImportLesson() {
  const [url, setUrl] = useState('')
  const [useMock, setUseMock] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [recentLessons, setRecentLessons] = useState<Lesson[]>([])
  const [loadingLessons, setLoadingLessons] = useState(false)
  const navigate = useNavigate()

  // Carrega aulas recentes ao montar
  useState(() => {
    setLoadingLessons(true)
    lessonsApi.list()
      .then(setRecentLessons)
      .catch(() => {})
      .finally(() => setLoadingLessons(false))
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!useMock && !url.trim()) {
      setError('Cole uma URL do YouTube ou ative o modo de teste.')
      return
    }

    setLoading(true)
    try {
      const lesson = await lessonsApi.create({
        url: useMock ? undefined : url.trim(),
        language: 'ja',
        use_mock: useMock,
      })
      navigate(`/lessons/${lesson.id}`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function deleteLesson(id: number) {
    try {
      await lessonsApi.delete(id)
      setRecentLessons(prev => prev.filter(l => l.id !== id))
    } catch {}
  }

  const statusColor = (status: string) => ({
    pending: '#f6ad55',
    processing: '#63b3ed',
    ready: '#48bb78',
    error: '#fc8181',
  }[status] || '#718096')

  const statusLabel = (status: string) => ({
    pending: 'Aguardando',
    processing: 'Processando...',
    ready: 'Pronto',
    error: 'Erro',
  }[status] || status)

  return (
    <div>
      <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '8px' }}>
        Importar Aula
      </h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '32px', fontSize: '15px' }}>
        Cole o link de um vídeo do YouTube. O Singular vai transcrever, extrair o conhecimento
        e criar seu sistema de revisão personalizado.
      </p>

      <form onSubmit={handleSubmit}>
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '24px',
        }}>
          {/* URL Input */}
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-muted)', marginBottom: '8px' }}>
              URL do YouTube
            </label>
            <input
              type="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              disabled={useMock || loading}
              style={{
                width: '100%',
                padding: '12px 16px',
                background: 'var(--surface2)',
                border: `1px solid ${useMock ? 'var(--text-dim)' : 'var(--border)'}`,
                borderRadius: '8px',
                color: useMock ? 'var(--text-dim)' : 'var(--text)',
                fontSize: '14px',
                outline: 'none',
              }}
            />
          </div>

          {/* Toggle mock */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '12px 16px',
            background: useMock ? 'rgba(108, 99, 255, 0.08)' : 'var(--surface2)',
            border: `1px solid ${useMock ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: '8px',
            cursor: 'pointer',
          }} onClick={() => setUseMock(!useMock)}>
            <div style={{
              width: '40px', height: '22px',
              background: useMock ? 'var(--accent)' : 'var(--text-dim)',
              borderRadius: '11px',
              position: 'relative',
              transition: 'background 0.2s',
              flexShrink: 0,
            }}>
              <div style={{
                position: 'absolute',
                top: '3px',
                left: useMock ? '21px' : '3px',
                width: '16px', height: '16px',
                background: 'white',
                borderRadius: '50%',
                transition: 'left 0.2s',
              }} />
            </div>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 500 }}>Modo de teste (mock)</div>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Usa dados de japonês pré-definidos — sem precisar de URL ou API key
              </div>
            </div>
          </div>

          {error && (
            <div style={{
              marginTop: '16px',
              padding: '12px',
              background: 'rgba(252, 129, 129, 0.1)',
              border: '1px solid rgba(252, 129, 129, 0.3)',
              borderRadius: '8px',
              color: 'var(--error)',
              fontSize: '14px',
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: '20px',
              width: '100%',
              padding: '13px',
              background: loading ? 'var(--text-dim)' : 'var(--accent)',
              color: 'white',
              borderRadius: '8px',
              fontSize: '15px',
              fontWeight: 600,
              transition: 'background 0.15s',
            }}
          >
            {loading ? '⏳ Iniciando pipeline...' : '→ Importar e Processar Aula'}
          </button>
        </div>
      </form>

      {/* Aulas recentes */}
      <div>
        <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-muted)' }}>
          Aulas Importadas
        </h2>

        {loadingLessons ? (
          <p style={{ color: 'var(--text-dim)', fontSize: '14px' }}>Carregando...</p>
        ) : recentLessons.length === 0 ? (
          <div style={{
            padding: '24px',
            textAlign: 'center',
            color: 'var(--text-dim)',
            background: 'var(--surface)',
            border: '1px dashed var(--border)',
            borderRadius: '8px',
            fontSize: '14px',
          }}>
            Nenhuma aula importada ainda. Use o modo mock para começar!
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {recentLessons.map(lesson => (
              <div
                key={lesson.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '14px 16px',
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  gap: '12px',
                  cursor: 'pointer',
                }}
                onClick={() => navigate(`/lessons/${lesson.id}`)}
              >
                <div style={{
                  width: '8px', height: '8px',
                  borderRadius: '50%',
                  background: statusColor(lesson.status),
                  flexShrink: 0,
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '14px', fontWeight: 500, marginBottom: '2px' }}>
                    {lesson.title || lesson.url || 'Aula sem título'}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {statusLabel(lesson.status)} · {lesson.cards_count} cards · {lesson.exercises_count} exercícios
                  </div>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); deleteLesson(lesson.id) }}
                  style={{
                    padding: '4px 10px',
                    background: 'transparent',
                    color: 'var(--text-dim)',
                    border: '1px solid var(--border)',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}
                >
                  Remover
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
