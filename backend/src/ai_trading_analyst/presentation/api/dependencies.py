"""FastAPI-Dependencies. Lesen fertig verdrahtete Objekte aus ``app.state``,
statt selbst konkrete Infrastruktur zu konstruieren -- das Verdrahten
uebernimmt ausschliesslich der Composition Root (``ai_trading_analyst.bootstrap``,
bewusst ausserhalb der vier Schichten, siehe Doc 10 Paragraph 9)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import (
    MarketDataProvider,
    MarketDataUnavailableError,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.screening import CandidateRuleParameters

_logger = logging.getLogger(__name__)


def get_run_overview_use_case(request: Request) -> ReadRunOverviewUseCase:
    use_case: ReadRunOverviewUseCase = request.app.state.run_overview_use_case
    return use_case


def get_unit_of_work_factory(request: Request) -> Callable[[], UnitOfWork]:
    factory: Callable[[], UnitOfWork] = request.app.state.uow_factory
    return factory


def get_backtest_parameters(request: Request) -> BacktestParameters:
    """Die Schwellen der Stichprobengroesse -- dieselben wie im Messlauf.

    Sie stehen in der Konfiguration und nicht in der Oberflaeche: Eine
    Konfidenz, die die API anders einstuft als der Lauf, der die Zahlen
    erzeugt hat, waere schlimmer als gar keine.
    """
    params: BacktestParameters = request.app.state.backtest_parameters
    return params


def get_candidate_rule_parameters(request: Request) -> CandidateRuleParameters:
    params: CandidateRuleParameters = request.app.state.candidate_rule_parameters
    return params


def get_chart_market_data(request: Request) -> MarketDataProvider:
    """Der Anbieter fuer den Validierungschart -- **ausschliesslich aus dem
    Bestand**.

    Der Composition Root setzt ``market_data.source`` fuer diesen Anbieter
    fest auf ``stored``. Ein Webdienst, der die TWS-Client-ID belegt, waere
    gefaehrlicher als kein Chart (ADR 0052).

    ``app.state`` haelt eine **Fabrik**, keinen fertigen Anbieter: Er haengt
    an der Watchlist-Datei, und ein fehlendes Verzeichnis soll den Chart
    kosten und nicht den Start des Dienstes.

    Damit es wirklich nur den Chart kostet, wird der Ausfall hier abgefangen.
    Ungefangen waere er ein ``500`` aus einer Abhaengigkeit heraus -- also
    ein Fehler des Dienstes, obwohl der Dienst in Ordnung ist und nur eine
    Datei fehlt.
    """
    fabrik: Callable[[], MarketDataProvider] = request.app.state.chart_market_data
    try:
        return fabrik()
    except MarketDataUnavailableError as fehler:
        # Der Wortlaut bleibt drinnen: Er nennt Pfade auf dem Server.
        _logger.error("Chartanbieter nicht einsatzbereit: %s", fehler)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Der Kursbestand ist gerade nicht lesbar.",
        ) from fehler
