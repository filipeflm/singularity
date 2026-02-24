/**
 * Tela 5 — Progresso
 * Exibe métricas reais de aprendizado e adaptações ativas.
 * Foca em retenção real, não em gamificação superficial (bigbang.md §11).
 */

import { useEffect, useState } from 'react'
import { progressApi, type AdaptationSummary, type ProgressStats } from '../api/client'

const patternLabel = (type: string) => ({
  vocab_weakness: 'Fraqueza em Vocabulário',
  grammar_confusion: 'Confusão Gramatical',
  structure_confusion: 'Confusão de Estrutura',
}[type] || type)

const patternIcon = (type: string) => ({
  vocab_weakness: '📚',
  grammar_confusion: '📝',
  structure_confusion: '🔀',
}[type] || '⚠')

const exerciseTypeLabel = (type: string | null) => ({
  translation: 'Tradução Ativa',
  fill_blank: 'Completar Lacuna',
  build_sentence: 'Construir Frase',
}[type || ''] || null)

const stateColors: Record<string, string> = {
  new: '#6c63ff',
  learning: '#f6ad55',
  review: '#48bb78',
  relearning: '#fc8181',
}

export default function Progress() {
  const [stats, setStats] = useState<ProgressStats | null>(null)
  const [adaptation, setAdaptation] = useState<AdaptationSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      progressApi.get(),
      progressApi.getAdaptation(),
    ]).then(([s, a]) => {
      setStats(s)
      setAdaptation(a)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: '48px', textAlign: 'center' }}>
      Carregando progresso...
    </div>
  }

  if (!stats || !adaptation) {
    return <div style={{ color: 'var(--error)', padding: '24px' }}>Erro ao carregar dados</div>
  }

  const totalCards = stats.total_cards || 1
  const stateEntries = Object.entries(stats.cards_by_state)
  const last7Days = Object.entries(stats.daily_reviews)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-7)

  const maxReviews = Math.max(...last7Days.map(([, v]) => v), 1)

  return (
    <div>
      <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '8px' }}>
        Progresso
      </h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '32px', fontSize: '15px' }}>
        Métricas reais de aprendizado — retenção, consistência, adaptação.
      </p>

      {/* Stats principais */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: '12px',
        marginBottom: '32px',
      }}>
        <StatCard label="Total de Cards" value={stats.total_cards} color="var(--accent-light)" />
        <StatCard label="Cards Dominados" value={stats.mastered_cards} color="var(--success)" />
        <StatCard label="Precisão (7 dias)" value={`${stats.accuracy_7d}%`}
          color={stats.accuracy_7d >= 70 ? 'var(--success)' : stats.accuracy_7d >= 50 ? 'var(--warning)' : 'var(--error)'} />
        <StatCard label="Retenção Est." value={`${stats.avg_retention_estimate}%`}
          color={stats.avg_retention_estimate >= 70 ? 'var(--success)' : 'var(--warning)'} />
        <StatCard label="Revisões (7d)" value={stats.reviews_7d} color="var(--text-muted)" />
        <StatCard label="Aulas" value={stats.total_lessons} color="var(--text-muted)" />
      </div>

      {/* Cards por estado */}
      <SectionTitle>Distribuição dos Cards</SectionTitle>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '20px',
        marginBottom: '24px',
      }}>
        {/* Barra de progresso empilhada */}
        <div style={{
          height: '12px',
          borderRadius: '6px',
          overflow: 'hidden',
          display: 'flex',
          marginBottom: '16px',
        }}>
          {stateEntries.map(([state, count]) => (
            <div
              key={state}
              style={{
                width: `${(count / totalCards) * 100}%`,
                background: stateColors[state] || '#718096',
                transition: 'width 0.5s',
              }}
            />
          ))}
        </div>

        {/* Legenda */}
        <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
          {stateEntries.map(([state, count]) => (
            <div key={state} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{
                width: '10px', height: '10px', borderRadius: '2px',
                background: stateColors[state] || '#718096',
              }} />
              <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                {{new:'Novo',learning:'Aprendendo',review:'Revisão',relearning:'Reaprendendo'}[state] || state}
              </span>
              <span style={{ fontSize: '13px', fontWeight: 600 }}>{count}</span>
            </div>
          ))}
        </div>

        {stats.cards_due_now > 0 && (
          <div style={{
            marginTop: '16px', padding: '10px 14px',
            background: 'rgba(246, 173, 85, 0.1)',
            border: '1px solid rgba(246, 173, 85, 0.3)',
            borderRadius: '6px', fontSize: '13px', color: 'var(--warning)',
          }}>
            ⏰ {stats.cards_due_now} card{stats.cards_due_now > 1 ? 's' : ''} pendente{stats.cards_due_now > 1 ? 's' : ''} para revisão agora
          </div>
        )}
      </div>

      {/* Gráfico de atividade */}
      <SectionTitle>Revisões nos Últimos 7 Dias</SectionTitle>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '20px',
        marginBottom: '24px',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', height: '80px' }}>
          {last7Days.map(([date, count]) => {
            const dayName = new Date(date + 'T00:00:00').toLocaleDateString('pt-BR', { weekday: 'short' })
            const height = count > 0 ? Math.max(8, (count / maxReviews) * 72) : 4
            return (
              <div key={date} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{count || ''}</div>
                <div style={{
                  width: '100%',
                  height: `${height}px`,
                  background: count > 0 ? 'var(--accent)' : 'var(--surface2)',
                  borderRadius: '3px 3px 0 0',
                  transition: 'height 0.3s',
                }} />
                <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{dayName}</div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Motor Adaptativo */}
      <SectionTitle>Motor de Adaptação</SectionTitle>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '20px',
        marginBottom: '24px',
      }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px',
        }}>
          <div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Novos cards/dia</div>
            <div style={{ fontSize: '20px', fontWeight: 700 }}>{adaptation.daily_new_cards_limit}</div>
          </div>
          {adaptation.recommended_exercise_type && (
            <div style={{
              padding: '8px 14px',
              background: 'rgba(108, 99, 255, 0.1)',
              border: '1px solid rgba(108, 99, 255, 0.3)',
              borderRadius: '8px',
            }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '2px' }}>
                Exercício recomendado
              </div>
              <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-light)' }}>
                {exerciseTypeLabel(adaptation.recommended_exercise_type)}
              </div>
            </div>
          )}
        </div>

        {adaptation.active_patterns.length === 0 ? (
          <div style={{
            padding: '16px', textAlign: 'center',
            color: 'var(--success)', fontSize: '14px',
          }}>
            ✓ Nenhum padrão de fraqueza ativo. Continue assim!
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {adaptation.active_patterns.map((pattern, i) => (
              <div key={i} style={{
                padding: '12px 14px',
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <span>{patternIcon(pattern.type)}</span>
                  <span style={{ fontSize: '14px', fontWeight: 500 }}>{patternLabel(pattern.type)}</span>
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: '4px' }}>
                    {Array.from({ length: 5 }).map((_, j) => (
                      <div key={j} style={{
                        width: '8px', height: '8px', borderRadius: '2px',
                        background: j < Math.ceil(pattern.severity * 5) ? 'var(--warning)' : 'var(--text-dim)',
                      }} />
                    ))}
                  </div>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{pattern.description}</p>
                <p style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
                  Detectado {pattern.count}x
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Princípio fundamental */}
      <div style={{
        padding: '16px 20px',
        background: 'transparent',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        fontSize: '13px',
        color: 'var(--text-dim)',
        lineHeight: 1.6,
      }}>
        <em>
          "Se o aluno usar o Singular por 90 dias, ele deve aprender mais do que
          YouTube + Anki + Caderno + Duolingo separados."
        </em>
        <br />— Princípio norteador do Singular
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{
      padding: '16px',
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: '10px',
    }}>
      <div style={{ fontSize: '24px', fontWeight: 700, color, marginBottom: '4px' }}>{value}</div>
      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{label}</div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      fontSize: '13px',
      color: 'var(--text-muted)',
      fontWeight: 500,
      marginBottom: '12px',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
    }}>
      {children}
    </h2>
  )
}
