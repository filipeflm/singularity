"""
API de Progresso — Singular
Rotas para métricas e adaptação do aluno.

GET /progress         → Estatísticas gerais de progresso
GET /progress/adaptation → Resumo das adaptações ativas
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.adaptation import get_adaptation_summary, resolve_pattern_if_improved
from app.services.review import get_progress_stats

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("")
def get_progress(db: Session = Depends(get_db)):
    """
    Retorna estatísticas completas de progresso do aluno.

    Inclui:
    - Cards por estado (new/learning/review/relearning)
    - Precisão nos últimos 7 dias
    - Cards dominados
    - Retenção estimada
    - Histórico diário de revisões
    """
    return get_progress_stats(user_id=1, db=db)


@router.get("/adaptation")
def get_adaptation(db: Session = Depends(get_db)):
    """
    Retorna resumo das adaptações ativas do motor adaptativo.

    Inclui:
    - Padrões de erro detectados e sua severidade
    - Tipo de exercício recomendado
    - Limite de novos cards por dia
    """
    # Tenta resolver padrões melhorados antes de retornar
    try:
        resolve_pattern_if_improved(user_id=1, db=db)
    except Exception:
        pass

    return get_adaptation_summary(user_id=1, db=db)
