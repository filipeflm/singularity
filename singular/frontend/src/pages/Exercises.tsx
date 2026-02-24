/**
 * Tela 4 — Exercícios Ativos
 * Interface de prática ativa com os 3 tipos de exercício.
 * Respostas são avaliadas e alimentam o motor adaptativo.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { exercisesApi, type Exercise, type ExerciseEvaluation } from '../api/client'

const typeConfig = {
  translation: {
    label: 'Tradução Ativa',
    icon: '↔',
    color: '#6c63ff',
    desc: 'Traduza para o idioma alvo',
  },
  fill_blank: {
    label: 'Completar Lacuna',
    icon: '___',
    color: '#48bb78',
    desc: 'Preencha o espaço em branco',
  },
  build_sentence: {
    label: 'Construir Frase',
    icon: '⬚⬚⬚',
    color: '#f6ad55',
    desc: 'Organize as palavras',
  },
}

export default function Exercises() {
  const [exercises, setExercises] = useState<Exercise[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [evaluation, setEvaluation] = useState<ExerciseEvaluation | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [sessionStats, setSessionStats] = useState({ correct: 0, wrong: 0 })
  const [activeFilter, setActiveFilter] = useState<string>('all')
  const [done, setDone] = useState(false)
  const startTime = useRef<number>(Date.now())
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    loadExercises()
  }, [activeFilter])

  async function loadExercises() {
    setLoading(true)
    setDone(false)
    setCurrentIdx(0)
    setAnswer('')
    setEvaluation(null)
    setSessionStats({ correct: 0, wrong: 0 })

    try {
      const params: any = { limit: 15 }
      if (activeFilter !== 'all') params.exercise_type = activeFilter
      const data = await exercisesApi.getAll(params)
      setExercises(data.exercises)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!answer.trim() || submitting || !exercises[currentIdx]) return
    setSubmitting(true)

    const responseTime = Date.now() - startTime.current
    const exercise = exercises[currentIdx]

    try {
      const result = await exercisesApi.submit(exercise.id, answer, responseTime)
      setEvaluation(result)

      if (result.is_correct) {
        setSessionStats(s => ({ ...s, correct: s.correct + 1 }))
      } else {
        setSessionStats(s => ({ ...s, wrong: s.wrong + 1 }))
      }
    } finally {
      setSubmitting(false)
    }
  }

  function handleNext() {
    if (currentIdx + 1 >= exercises.length) {
      setDone(true)
    } else {
      setCurrentIdx(i => i + 1)
      setAnswer('')
      setEvaluation(null)
      startTime.current = Date.now()
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '48px', textAlign: 'center' }}>
      Carregando exercícios...
    </div>
  }

  if (done || exercises.length === 0) {
    const total = sessionStats.correct + sessionStats.wrong
    const accuracy = total > 0 ? Math.round(sessionStats.correct / total * 100) : 0

    return (
      <div style={{ textAlign: 'center', padding: '64px 24px' }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>
          {exercises.length === 0 ? '📭' : accuracy >= 70 ? '🏆' : '💪'}
        </div>
        <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>
          {exercises.length === 0 ? 'Nenhum exercício disponível' : 'Sessão Concluída!'}
        </h2>
        {total > 0 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: '32px', margin: '32px 0' }}>
            <Stat label="Acertos" value={sessionStats.correct} color="var(--success)" />
            <Stat label="Erros" value={sessionStats.wrong} color="var(--error)" />
            <Stat label="Precisão" value={`${accuracy}%`} color="var(--accent-light)" />
          </div>
        )}
        <p style={{ color: 'var(--text-muted)', marginBottom: '24px', fontSize: '14px' }}>
          {exercises.length === 0
            ? 'Importe uma aula primeiro para gerar exercícios.'
            : 'Os erros foram registrados para adaptar seu aprendizado.'}
        </p>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
          <button onClick={loadExercises} style={{
            padding: '12px 24px', background: 'var(--accent)', color: 'white',
            borderRadius: '8px', fontWeight: 600,
          }}>
            Praticar Novamente
          </button>
          <button onClick={() => navigate('/review')} style={{
            padding: '12px 24px', background: 'var(--surface)',
            color: 'var(--text)', border: '1px solid var(--border)',
            borderRadius: '8px', fontWeight: 600,
          }}>
            Revisar Cards
          </button>
        </div>
      </div>
    )
  }

  const exercise = exercises[currentIdx]
  const config = typeConfig[exercise.type as keyof typeof typeConfig]
  const progress = (currentIdx / exercises.length) * 100

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
        <div style={{ flex: 1, height: '4px', background: 'var(--surface2)', borderRadius: '2px' }}>
          <div style={{
            width: `${progress}%`, height: '100%',
            background: 'var(--accent)', borderRadius: '2px', transition: 'width 0.3s',
          }} />
        </div>
        <span style={{ fontSize: '13px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {currentIdx}/{exercises.length}
        </span>
      </div>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {[
          { key: 'all', label: 'Todos' },
          { key: 'translation', label: '↔ Tradução' },
          { key: 'fill_blank', label: '___ Lacuna' },
          { key: 'build_sentence', label: '⬚ Montar' },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => setActiveFilter(f.key)}
            style={{
              padding: '6px 14px',
              background: activeFilter === f.key ? 'var(--accent)' : 'var(--surface)',
              border: `1px solid ${activeFilter === f.key ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: '6px',
              color: activeFilter === f.key ? 'white' : 'var(--text-muted)',
              fontSize: '13px',
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Exercício */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '16px',
        padding: '32px',
        marginBottom: '20px',
      }}>
        {/* Tipo */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          marginBottom: '20px',
        }}>
          <span style={{
            padding: '4px 10px', borderRadius: '4px',
            background: `${config.color}15`,
            color: config.color, fontSize: '12px', fontWeight: 600,
          }}>
            {config.icon} {config.label}
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>{config.desc}</span>
        </div>

        {/* Prompt */}
        <div style={{
          fontSize: '22px', fontWeight: 600, marginBottom: '8px',
          lineHeight: 1.5,
        }}>
          {exercise.prompt}
        </div>

        {exercise.context && (
          <div style={{
            padding: '10px 14px',
            background: 'var(--surface2)',
            borderRadius: '6px',
            fontSize: '13px',
            color: 'var(--text-muted)',
            marginBottom: '20px',
          }}>
            💡 {exercise.context}
          </div>
        )}

        {/* Input de resposta */}
        {!evaluation ? (
          <form onSubmit={handleSubmit}>
            <input
              ref={inputRef}
              value={answer}
              onChange={e => setAnswer(e.target.value)}
              placeholder="Sua resposta..."
              autoFocus
              style={{
                width: '100%',
                padding: '12px 16px',
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                color: 'var(--text)',
                fontSize: '16px',
                marginBottom: '12px',
                outline: 'none',
              }}
            />
            <button
              type="submit"
              disabled={!answer.trim() || submitting}
              style={{
                width: '100%',
                padding: '12px',
                background: answer.trim() ? 'var(--accent)' : 'var(--text-dim)',
                color: 'white',
                borderRadius: '8px',
                fontWeight: 600,
                fontSize: '15px',
              }}
            >
              {submitting ? 'Avaliando...' : 'Confirmar'}
            </button>
          </form>
        ) : (
          <EvaluationResult evaluation={evaluation} onNext={handleNext} />
        )}
      </div>

      {/* Stats da sessão */}
      <div style={{
        display: 'flex', gap: '16px',
        fontSize: '13px', color: 'var(--text-muted)',
        justifyContent: 'center',
      }}>
        <span>✓ {sessionStats.correct} corretos</span>
        <span>✗ {sessionStats.wrong} erros</span>
      </div>
    </div>
  )
}

function EvaluationResult({ evaluation, onNext }: {
  evaluation: ExerciseEvaluation
  onNext: () => void
}) {
  const isCorrect = evaluation.is_correct
  const borderColor = isCorrect ? 'var(--success)' : 'var(--error)'
  const bg = isCorrect ? 'rgba(72,187,120,0.08)' : 'rgba(252,129,129,0.08)'

  return (
    <div style={{
      padding: '16px',
      background: bg,
      border: `1px solid ${borderColor}40`,
      borderRadius: '8px',
    }}>
      <div style={{ fontSize: '16px', fontWeight: 600, color: borderColor, marginBottom: '8px' }}>
        {isCorrect ? '✓ Correto!' : '✗ Incorreto'}
      </div>
      <div style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: '4px' }}>
        {evaluation.feedback}
      </div>
      {!isCorrect && (
        <div style={{ marginTop: '10px', padding: '8px 12px', background: 'var(--surface)', borderRadius: '6px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Resposta correta: </span>
          <span style={{ fontSize: '14px', color: 'var(--text)', fontWeight: 500 }}>
            {evaluation.expected_answer}
          </span>
        </div>
      )}
      {evaluation.error_category && !isCorrect && (
        <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--warning)' }}>
          Categoria do erro: {evaluation.error_category}
        </div>
      )}
      <button
        onClick={onNext}
        style={{
          marginTop: '14px',
          width: '100%',
          padding: '10px',
          background: 'var(--accent)',
          color: 'white',
          borderRadius: '8px',
          fontWeight: 600,
          fontSize: '14px',
        }}
      >
        Próximo →
      </button>
    </div>
  )
}

function Stat({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '28px', fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{label}</div>
    </div>
  )
}
