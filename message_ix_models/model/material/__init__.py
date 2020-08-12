from typing import Mapping

import click
from message_ix_models import ScenarioInfo
from message_ix_models.model.build import apply_spec

from .data import gen_data
from .util import read_config


def build(scenario):
    """Set up materials accounting on `scenario`."""
    # Get the specification
    spec = get_spec()

    # Apply to the base scenario
    apply_spec(scenario, spec, gen_data)

    return scenario


def get_spec() -> Mapping[str, ScenarioInfo]:
    """Return the specification for materials accounting."""
    require = ScenarioInfo()
    add = ScenarioInfo()

    # Load configuration
    context = read_config()

    # Update the ScenarioInfo objects with required and new set elements
    for set_name, config in context["material"]["set"].items():
        # Required elements
        require.set[set_name].extend(config.get("require", []))

        # Elements to add
        add.set[set_name].extend(config.get("add", []))

    return dict(require=require, remove=ScenarioInfo(), add=add)


# Group to allow for multiple CLI subcommands under "material"
@click.group("material")
def cli():
    """Model with materials accounting."""


@cli.command("create-bare")
@click.option("--regions", type=click.Choice(["China", "R11", "R14"]))
@click.option('--dry_run', '-n', is_flag=True,
              help='Only show what would be done.')
@click.pass_obj
def create_bare(context, regions, dry_run):
    """Create the RES from scratch."""
    from .bare import create_res

    if regions:
        context.regions = regions

    scen = create_res(context)

    # Solve
    if not dry_run:
        scen.solve()

@cli.command()
@click.pass_obj
def solve(context):
    """Build and solve model.

    Use the --url option to specify the base scenario.
    """
    # Determine the output scenario name based on the --url CLI option. If the
    # user did not give a recognized value, this raises an error.
    output_scenario_name = {
        "baseline": "NoPolicy",
        "NPi2020-con-prim-dir-ncr": "NPi",
        "NPi2020_1000-con-prim-dir-ncr": "NPi2020_1000",
        "NPi2020_400-con-prim-dir-ncr": "NPi2020_400",
    }.get(context.scenario_info["scenario"])

    # Chnage this part - the model name ?? 

    if context.scenario_info["model"] != "CD_Links_SSP2":
        print("WARNING: this code is not tested with this base scenario!")

    # Clone and set up
    scenario = build(
        context.get_scenario()
        .clone(model="Material_test", scenario=output_scenario_name)
    )

    # Solve
    scenario.solve()
