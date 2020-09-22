import logging

from message_ix.reporting import Reporter
import pandas as pd

from message_data.tools import ScenarioInfo
from .plot import PLOTS
from .utils import read_config


log = logging.getLogger(__name__)


#: Reporting configuration for :func:`check`. Adds a single key,
#: 'transport check', that depends on others and returns a
#: :class:`pandas.Series` of :class:`bool`.
CONFIG = dict(
    general=[dict(
        key='transport check',
        comp='transport_check',
        inputs=['scenario', 'ACT']
    )],
)


def check(scenario):
    """Check that the transport model solution is complete.

    Parameters
    ----------
    scenario : message_ix.Scenario
        Scenario with solution.

    Returns
    -------
    pd.Series
        Index entries are str descriptions of checks. Values are the
        :obj:`True` if the respective check passes.
    """
    # NB this is here to avoid circular imports
    from message_data.reporting.core import prepare_reporter

    rep, key = prepare_reporter(scenario, CONFIG, 'transport check')
    return rep.get(key)


def check_computation(scenario, ACT):
    """Reporting computation for :func:`check`.

    Imported into :mod:`.reporting.computations`.
    """
    info = ScenarioInfo(scenario)

    # Mapping from check name → bool
    checks = {}

    # Correct number of outputs
    ACT_lf = ACT.sel(t=['transport freight load factor',
                        'transport pax load factor'])
    checks["'transport * load factor' technologies are active"] = \
        len(ACT_lf) == 2 * len(info.Y) * (len(info.N) - 1)

    # # Force the check to fail
    # checks['(fail for debugging)'] = False

    return pd.Series(checks)


def callback(rep: Reporter):
    """:meth:`.prepare_reporter` callback for MESSAGE-Transport.

    Adds:

    - ``{in,out}::transport``: with outputs aggregated by technology group or
      "mode".
    - ``transport plots``: the plots from :mod:`.transport.plot`.
    - ``transport all``: all of the above.
    """
    from message_data.reporting.util import infer_keys
    from .demand import prepare_reporter as prepare_demand

    # Read transport reporting configuration
    context = read_config()
    config = context["transport config"]["report"]

    if config["filter"]:
        # Include only technologies with "transport" in the name
        rep.set_filters(
            t=list(filter(lambda n: "transport" in n, rep.get("t")))
        )

    # Add configuration to the Reporter
    rep.graph["config"]["transport"] = config.copy()

    # Aggregate transport technologies
    t_groups = {}
    for tech in context["transport set"]["technology"]["add"]:
        if not len(tech.child):
            continue  # No children; not a group

        t_groups[tech.id] = [child.id for child in tech.child]

    all_keys = []

    for k in infer_keys(rep, ["in", "out"]):
        keys = rep.aggregate(k, 'transport', dict(t=t_groups), sums=True)
        all_keys.append(keys[0])
        log.info(f'Add {repr(keys[0])} + {len(keys)-1} partial sums')

    # Add ex-post mode and demand calculations
    prepare_demand(rep)

    # Add all plots
    plot_keys = []

    for plot in PLOTS:
        key = f"plot {plot.name}"
        comp = plot.computation()
        log.info(repr(comp))
        rep.add(key, comp)
        plot_keys.append(key)
        log.info(f"Add {repr(key)}")

    rep.add("transport plots", plot_keys)

    # Add key collecting all others
    rep.add("transport all", all_keys + plot_keys)
