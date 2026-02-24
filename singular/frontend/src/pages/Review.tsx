/**
 * Tela 3 — Revisão de Cards (SRS)
 * Implementa a interface de revisão espaçada adaptativa.
 *
 * Fluxo:
 *   1. Mostra o front do card (estímulo)
 *   2. Usuário pensa na resposta
 *   3. Usuário clica "Ver resposta"
 *   4. Usuário avalia a qualidade (0-5)
 *   5. Sistema atualiza SRS e passa para o próximo card
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { reviewApi, type CardDue } from '../api/client'

type Phase = 'question' | 'answer' | 'complete'

const qualityButtons = [
  { q: 0, label: 'Não lembrei', color: '#fc8181', bg: 'rgba(252,129,129,0.1)' },
  { q: 1, label: 'Muito difícil', color: '#f6ad55', bg: 'rgba(246,173,85,0.1)' },
  { q: 2, label: 'Difícil', color: '#f6e05e', bg: 'rgba(246,224,94,0.1)' },
  { q: 3, label: 'Razoável', color: '#68d391', bg: 'rgba(104,211,145,0.1)' },
  { q: 4, label: 'Bom', color: '#48bb78', bg: 'rgba(72,187,120,0.1)' },
  { q: 5, label: 'Fácil!', color: '#38b2ac', bg: 'rgba(56,178,172,0.1)' },
]

const stateLabel = (state: string) => ({
  new: 'Novo',
  learning: 'Aprendendo',
  review: 'Revisão',
  relearning: 'Reaprendendo',
}[state] || state)

const stateColor = (state: string) => ({
  new: '#6c63ff',
  learning: '#f6ad55',
  review: '#48bb78',
  relearning: '#fc8181',
}[state] || '#718096')

const typeLabel = (type: string) => ({
  vocab: '語彙', phrase: '表現', grammar: '文法'
}[type] || type)

export default function Review() {
  const [cards, setCards] = useState<CardDue[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [phase, setPhase] = useState<Phase>('question')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [lastFeedback, setLastFeedback] = useState<string | null>(null)
  const [sessionStats, setSessionStats] = useState({ correct: 0, wrong: 0 })
  const startTime = useRef<number>(Date.now())
  const navigate = useNavigate()

  useEffect(() => {
    loadCards()
  }, [])

  async function loadCards() {
    setLoading(true)
    try {
      const data = await reviewApi.getDue(30)
      setCards(data.cards)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleQuality(quality: number) {
    if (submitting || !cards[currentIdx]) return
    setSubmitting(true)

    const responseTime = Date.now() - startTime.current
    const card = cards[currentIdx]

    try {
      const result = await reviewApi.submit(card.card_id, quality, responseTime)
      setLastFeedback(result.feedback)

      if (result.was_correct) {
        setSessionStats(s => ({ ...s, correct: s.correct + 1 }))
      } else {
        setSessionStats(s => ({ ...s, wrong: s.wrong + 1 }))
      }

      // Avança para o próximo card após pequena pausa
      setTimeout(() => {
        if (currentIdx + 1 >= cards.length) {
          setPhase('complete')
        } else {
          setCurrentIdx(i => i + 1)
          setPhase('question')
          startTime.current = Date.now()
          setLastFeedback(null)
        }
        setSubmitting(false)
      }, 600)
    } catch (e) {
      setSubmitting(false)
    }
  }

  function handleShowAnswer() {
    setPhase('answer')
    startTime.current = Date.now() // reseta timer para contar tempo de avaliação
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '48px', textAlign: 'center' }}>
      Carregando cards...
    </div>
  }

  if (cards.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>🎉</div>
        <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>Revisões em dia!</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: '32px' }}>
          Nenhum card pendente para revisão agora.
        </p>
        <button
          onClick={() => navigate('/exercises')}
          style={{
            padding: '12px 24px',
            background: 'var(--accent)',
            color: 'white',
            borderRadius: '8px',
            fontWeight: 600,
          }}
        >
          Praticar Exercícios
        </button>
      </div>
    )
  }

  if (phase === 'complete') {
    const total = sessionStats.correct + sessionStats.wrong
    const accuracy = total > 0 ? Math.round(sessionStats.correct / total * 100) : 0
    return (
      <div style={{ textAlign: 'center', padding: '64px 24px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>
          {accuracy >= 70 ? '✨' : '📖'}
        </div>
        <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>
          Sessão Concluída
        </h2>
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '32px',
          margin: '32px 0',
        }}>
          <Stat label="Acertos" value={sessionStats.correct} color="var(--success)" />
          <Stat label="Erros" value={sessionStats.wrong} color="var(--error)" />
          <Stat label="Precisão" value={`${accuracy}%`} color="var(--accent-light)" />
        </div>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
          <button onClick={loadCards} style={{
            padding: '12px 24px', background: 'var(--accent)', color: 'white',
            borderRadius: '8px', fontWeight: 600,
          }}>
            Continuar Revisando
          </button>
          <button onClick={() => navigate('/progress')} style={{
            padding: '12px 24px', background: 'var(--surface)',
            color: 'var(--text)', border: '1px solid var(--border)',
            borderRadius: '8px', fontWeight: 600,
          }}>
            Ver Progresso
          </button>
        </div>
      </div>
    )
  }

  const card = cards[currentIdx]
  const progress = ((currentIdx) / cards.length) * 100

  return (
    <div>
      {/* Header da sessão */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
        <div style={{ flex: 1, height: '4px', background: 'var(--surface2)', borderRadius: '2px' }}>
          <div style={{
            width: `${progress}%`,
            height: '100%',
            background: 'var(--accent)',
            borderRadius: '2px',
            transition: 'width 0.3s',
          }} />
        </div>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {currentIdx}/{cards.length}
        </span>
        <span style={{ fontSize: '12px', color: 'var(--success)' }}>✓{sessionStats.correct}</span>
        <span style={{ fontSize: '12px', color: 'var(--error)' }}>✗{sessionStats.wrong}</span>
      </div>

      {/* Card */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '16px',
        padding: '40px',
        textAlign: 'center',
        minHeight: '280px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        marginBottom: '20px',
      }}>
        {/* Badges */}
        <div style={{ position: 'absolute', top: '16px', left: '16px', display: 'flex', gap: '6px' }}>
          <span style={{
            fontSize: '11px', padding: '3px 8px', borderRadius: '4px',
            background: `${stateColor(card.state)}20`,
            color: stateColor(card.state),
          }}>
            {stateLabel(card.state)}
          </span>
          {card.item_type && (
            <span style={{
              fontSize: '11px', padding: '3px 8px', borderRadius: '4px',
              background: 'var(--surface2)', color: 'var(--text-muted)',
            }}>
              {typeLabel(card.item_type)}
            </span>
          )}
        </div>

        {/* Retention indicator */}
        <div style={{
          position: 'absolute', top: '16px', right: '16px',
          fontSize: '11px', color: card.retention_probability < 0.5 ? 'var(--warning)' : 'var(--text-dim)',
        }}>
          {card.lapses > 0 && `⚠ ${card.lapses} lapso${card.lapses > 1 ? 's' : ''}`}
        </div>

        {/* Front */}
        <div style={{ fontSize: '36px', fontWeight: 700, lineHeight: 1.4, marginBottom: '8px' }}>
          {card.front.split('\n')[0]}
        </div>
        {card.front.includes('\n') && (
          <div style={{ fontSize: '16px', color: 'var(--text-muted)' }}>
            {card.front.split('\n').slice(1).join(' ')}
          </div>
        )}

        {/* Hint */}
        {phase === 'question' && card.hint && (
          <div style={{ marginTop: '16px', fontSize: '13px', color: 'var(--text-dim)' }}>
            Dica: {card.hint}
          </div>
        )}

        {/* Answer reveal */}
        {phase === 'answer' && (
          <div style={{
            marginTop: '24px',
            paddingTop: '24px',
            borderTop: '1px solid var(--border)',
            width: '100%',
          }}>
            <div style={{ fontSize: '20px', color: 'var(--accent-light)', fontWeight: 600, marginBottom: '8px' }}>
              {card.back.split('\n')[0]}
            </div>
            {card.back.includes('\n') && (
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', whiteSpace: 'pre-line' }}>
                {card.back.split('\n').slice(1).join('\n').trim()}
              </div>
            )}
            {card.context_sentence && (
              <div style={{
                marginTop: '12px', padding: '10px', background: 'var(--surface2)',
                borderRadius: '6px', fontSize: '13px', color: 'var(--text-muted)',
              }}>
                {card.context_sentence}
              </div>
            )}
          </div>
        )}

        {/* Feedback momentâneo */}
        {lastFeedback && (
          <div style={{
            position: 'absolute', bottom: '16px',
            fontSize: '13px', color: 'var(--text-muted)',
          }}>
            {lastFeedback}
          </div>
        )}
      </div>

      {/* Ações */}
      {phase === 'question' ? (
        <button
          onClick={handleShowAnswer}
          style={{
            width: '100%',
            padding: '14px',
            background: 'var(--surface2)',
            border: '1px solid var(--border)',
            borderRadius: '10px',
            color: 'var(--text)',
            fontSize: '16px',
            fontWeight: 500,
          }}
        >
          Ver Resposta
        </button>
      ) : (
        <div>
          <p style={{ textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)', marginBottom: '12px' }}>
            Como foi?
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '8px' }}>
            {qualityButtons.map(({ q, label, color, bg }) => (
              <button
                key={q}
                onClick={() => handleQuality(q)}
                disabled={submitting}
                style={{
                  padding: '10px 6px',
                  background: bg,
                  border: `1px solid ${color}40`,
                  borderRadius: '8px',
                  color,
                  fontSize: '12px',
                  fontWeight: 500,
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ fontSize: '16px', marginBottom: '4px' }}>{q}</div>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '32px', fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{label}</div>
    </div>
  )
}
