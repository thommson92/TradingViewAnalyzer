"""``/api/v1/options-backtests`` -- die Messungen des Optionsbacktests.

Nur lesend. Ein Messlauf entsteht ueber ``cli options-backtest`` und nicht auf
Zuruf durch das Web: Er rechnet ueber die ganze Watchliste und ueber fuenf
Jahre, und ein Webdienst, der das auf Knopfdruck anstoesst, waere derselbe
Fehler wie ein Webdienst, der die TWS-Client-ID belegt (ADR 0052).

**Jede Zahl hier ist eine Modellzahl.** Die Praemie ist gerechnet, der
Verfallskalender konstruiert, das Strike-Raster angenommen. Die Annahmen
stehen deshalb an jeder Messung und nicht im Kleingedruckten.

Der Zusammenbau steht in ``..views`` -- derselbe Code, aus dem der
Exportschritt seinen Datenbaum schreibt (ADR 0060).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ai_trading_analyst.domain.analysis import UnitOfWork
from ai_trading_analyst.domain.backtesting import BacktestParameters

from .. import views
from ..dependencies import get_backtest_parameters, get_unit_of_work_factory
from ..schemas import OptionsMeasurementDetailResponse, OptionsMeasurementResponse

router = APIRouter(prefix="/api/v1/options-backtests", tags=["options-backtests"])


@router.get("", response_model=list[OptionsMeasurementResponse])
def list_measurements(
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
) -> list[OptionsMeasurementResponse]:
    """Alle Messungen, juengste zuerst.

    Eine leere Liste heisst: Es lief noch kein Messlauf. Das ist eine
    Auskunft und kein Fehler -- der Optionsbacktest ist ein Handlauf und
    haengt nicht am Tageslauf.
    """
    with uow_factory() as uow:
        return views.measurements(uow)


@router.get("/{measurement_id}", response_model=OptionsMeasurementDetailResponse)
def get_measurement(
    measurement_id: UUID,
    uow_factory: Callable[[], UnitOfWork] = Depends(get_unit_of_work_factory),
    backtest_params: BacktestParameters = Depends(get_backtest_parameters),
) -> OptionsMeasurementDetailResponse:
    """Eine Messung: die Kombinationen ueber alle Aktien und die Aktienzeilen.

    Die Aktienzeilen entstehen **aus den Einzeltrades** und nicht als Mittel
    der Kombinationszeilen -- ein Mittel von Mitteln gewichtete eine Aktie mit
    drei Trades so schwer wie eine mit dreissig.
    """
    with uow_factory() as uow:
        try:
            return views.measurement_detail(
                uow, measurement_id, backtest_params=backtest_params
            )
        except views.NotFoundError as fehler:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(fehler)
            ) from fehler
