"""Utilities for testing :mod:`~message_data.model.transport`."""
import logging
from contextlib import nullcontext
from pathlib import Path
from typing import Optional, Tuple

import pytest
from genno import Computer
from message_ix import Reporter, Scenario
from message_ix_models import Context, ScenarioInfo, testing

from message_data import reporting
from message_data.model import transport
from message_data.reporting.sim import add_simulated_solution
from message_data.tools import silence_log

from . import build
from .util import get_techs

log = logging.getLogger(__name__)

# Common marks for transport code
MARK = (
    pytest.mark.xfail(
        reason="Missing R14 input data/assumptions", raises=FileNotFoundError
    ),
    pytest.mark.skip(
        reason="Currently only possible with regions=R12 input data/assumptions",
    ),
    lambda t: pytest.mark.xfail(
        reason="Missing input data/assumptions for this node codelist", raises=t
    ),
)


def configure_build(
    test_context: Context, tmp_path: Path, regions: str, years: str, options=None
) -> Tuple[Computer, ScenarioInfo]:
    test_context.update(regions=regions, years=years, output_path=tmp_path)
    c = build.get_computer(test_context, options=options)
    return c, test_context["transport build info"]


def built_transport(
    request,
    context: Context,
    options: Optional[dict] = None,
    solved: bool = False,
    quiet: bool = True,
) -> Scenario:
    """Analogous to :func:`.testing.bare_res`, with transport detail added."""
    options = options or dict()

    # Retrieve (maybe generate) the bare RES with the same settings
    res = testing.bare_res(request, context, solved)

    # Derive the name for the transport scenario
    model_name = res.model.replace("-GLOBIOM", "-Transport")

    try:
        scenario = Scenario(context.get_platform(), model_name, "baseline")
    except ValueError:
        log.info(f"Create '{model_name}/baseline' for testing")

        # Optionally silence logs for code used via build.main()
        log_cm = (
            silence_log(["genno", "message_data.model.transport", "message_ix_models"])
            if quiet
            else nullcontext()
        )

        with log_cm:
            scenario = res.clone(model=model_name)
            transport.build.main(context, scenario, options, fast=True)
    else:
        # Loaded existing Scenario; ensure config files are loaded on `context`
        transport.Config.from_context(context, options=options)

    if solved and not scenario.has_solution():
        log.info(f"Solve '{scenario.model}/{scenario.scenario}'")
        scenario.solve(solve_options=dict(lpmethod=4))

    log.info(f"Clone to '{model_name}/{request.node.name}'")
    return scenario.clone(scenario=request.node.name, keep_solution=solved)


def simulated_solution(request, context) -> Reporter:
    """Return a :class:`.Reporter` with a simulated model solution.

    The contents allow for fast testing of reporting code, without solving an actual
    :class:`.Scenario`.
    """
    from .report import callback

    # Build the base model
    scenario = built_transport(request, context, solved=False)

    # Info about the built model
    info = ScenarioInfo(scenario)

    spec, technologies, t_info = get_techs(context)

    # Create a reporter
    rep = Reporter.from_scenario(scenario)

    # Add simulated solution data
    # TODO expand
    data = dict(
        ACT=dict(
            nl=info.N[-1],
            t=technologies,
            yv=2020,
            ya=2020,
            m="all",
            h="year",
            value=1.0,
        ),
        CAP=dict(
            nl=[info.N[-1]] * 2,
            t=["ELC_100", "ELC_100"],
            yv=[2020, 2020],
            ya=[2020, 2025],
            value=[1.0, 1.1],
        ),
    )
    add_simulated_solution(rep, info, data)

    # Register the callback to set up transport reporting
    reporting.register(callback)

    # Prepare the reporter
    with silence_log("genno", logging.CRITICAL):
        reporting.prepare_reporter(context, reporter=rep)

    return rep
