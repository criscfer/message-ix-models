"""Reporting/postprocessing for MESSAGEix-Transport."""
import logging
from operator import attrgetter

from dask.core import quote
from message_ix.reporting import Key, Reporter
from message_ix_models import Context

from . import configure, computations
from .plot import PLOTS

log = logging.getLogger(__name__)


def check(scenario):
    """Check that the transport model solution is complete.

    Parameters
    ----------
    scenario : message_ix.Scenario
        Scenario with solution.

    Returns
    -------
    pd.Series
        Index entries are str descriptions of checks. Values are :obj:`True` if the
        respective check passes.
    """
    # NB this is here to avoid circular imports
    from message_data.reporting import prepare_reporter, register

    register(callback)
    rep, key = prepare_reporter(scenario, "global.yaml", "transport check")
    return rep.get(key)


def callback(rep: Reporter):
    """:meth:`.prepare_reporter` callback for MESSAGE-Transport.

    Adds:

    - ``{in,out}::transport``: with outputs aggregated by technology group or
      "mode".
    - ``transport plots``: the plots from :mod:`.transport.plot`.
    - ``transport all``: all of the above.
    """
    from . import build, demand

    if computations not in rep.modules:
        rep.modules.append(computations)

    try:
        solved = rep.graph["scenario"].has_solution()
    except KeyError:
        solved = False

    # Read transport reporting configuration onto the latest Context
    context = Context.get_instance(-1)
    configure(context)

    config = context["transport config"]["report"]
    config.update(context["transport config"])

    # Add configuration to the Reporter
    rep.graph["config"].setdefault("transport", {})
    rep.graph["config"]["transport"].update(config.copy())

    # Get a specification that describes this setting
    spec = build.get_spec(context)

    # Set of all transport technologies
    technologies = spec["add"].set["technology"]

    # Combine technologies from disutility formulation
    # TODO do this somewhere earlier, e.g. in build.get_spec()
    disutil_spec = build.get_disutility_spec(context)
    technologies.extend(disutil_spec["add"].set["technology"])

    rep.add("t:transport", quote(technologies))

    # Subsets of transport technologies for aggregation and filtering
    t_groups = dict(nonldv=[])
    for tech in filter(  # Only include those technologies with children
        lambda t: len(t.child), context["transport set"]["technology"]["add"]
    ):
        t_groups[tech.id] = list(c.id for c in tech.child)
        rep.add(f"t:transport {tech.id}", quote(dict(t=t_groups[tech.id])))
        # Store non-LDV technologies
        if tech.id != "LDV":
            t_groups["nonldv"].extend(t_groups[tech.id])

    rep.add("t:transport non-LDV", quote(dict(t=t_groups["nonldv"])))

    # Set of all transport commodities
    rep.add("c:transport", quote(spec["add"].set["commodity"]))

    # Apply filters if configured
    if config["filter"]:
        # Include only technologies with "transport" in the name
        log.info("Filter out non-transport technologies")
        rep.set_filters(t=list(map(str, sorted(technologies, key=attrgetter("id")))))

    # Queue of computations to add
    queue = []

    # Shorthands for queue of computations to add
    _s = dict(sums=True)
    _si = dict(sums=True, index=True)

    # Aggregate transport technologies
    for k in ("in", "out"):
        try:
            queue.append(
                (("aggregate", rep.full_key(k), "transport", dict(t=t_groups)), _s)
            )
        except KeyError:
            if solved:
                raise

    # Keys
    dist_ldv = Key("distance", "nl driver_type".split(), "ldv")
    dist_nonldv = Key("distance", "nl", "non-ldv")
    CAP = Key("CAP", "nl t ya".split())
    CAP_ldv = CAP.add_tag("ldv")
    CAP_nonldv = CAP.add_tag("non-ldv")

    # Vehicle stocks
    queue.extend(
        [
            (("select", CAP_ldv, CAP, "t:transport LDV"), _si),
            (("select", CAP_nonldv, CAP, "t:transport non-LDV"), _si),
            # Vehicle stocks for LDV
            ((dist_ldv, computations.distance_ldv, "config"), _si),
            (("ratio", "stock:nl-t-ya-driver_type:ldv", CAP_ldv, dist_ldv), _si),
            # Vehicle stocks for non-LDV technologies
            ((dist_nonldv, computations.distance_nonldv, "config"), _si),
            (("ratio", "stock:nl-t-ya:non-ldv", CAP_nonldv, dist_nonldv), _si),
        ]
    )

    # Only viable keys added
    rep.add_queue(queue)

    # Add key collecting all others
    # FIXME `added` includes all partial sums of in::transport etc.
    rep.add("transport all", ["transport plots"])

    # Configuration for :func:`check`. Adds a single key, 'transport check', that
    # depends on others and returns a :class:`pandas.Series` of :class:`bool`.
    rep.add(
        "transport check",
        computations.transport_check,
        "scenario",
        Key("ACT", "nl t yv ya m h".split()),
    )

    # Add ex-post mode and demand calculations
    demand.prepare_reporter(
        rep, context, configure=False, exogenous_data=not solved, info=spec["add"]
    )

    # Add plots
    add_plots(rep)


def add_plots(rep: Reporter):
    try:
        solved = rep.graph["scenario"].has_solution()
    except KeyError:
        solved = False

    queue = []

    for plot in PLOTS:
        key = f"plot {plot.basename}"
        queue.append(((key, plot.make_task()), dict()))

    added = rep.add_queue(queue, max_tries=2, fail="raise" if solved else logging.INFO)

    plots = list(k for k in added if str(k).startswith("plot"))

    key = "transport plots"
    log.info(f"Add {repr(key)} collecting {len(plots)} plots")
    rep.add(key, plots)
