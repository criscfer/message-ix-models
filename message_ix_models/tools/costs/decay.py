import numpy as np
import pandas as pd

from message_ix_models.util import package_data_path

from .config import Config
from .regional_differentiation import get_raw_technology_mapping, subset_module_map


def get_cost_reduction_data(module) -> pd.DataFrame:
    """Get cost reduction data from file.

    Raw data on cost reduction in 2100 for technologies are read from
    :file:`data/[module]/cost_reduction_[module].csv`, based on GEA data.

    Parameters
    ----------
    module : str
        Model module

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns:

        - message_technology: name of technology in MESSAGEix
        - reduction_rate: the cost reduction rate (either very_low, low, medium, high,
        or very_high)
        - cost_reduction: cost reduction in 2100 (%)
    """

    # Get full list of technologies from mapping
    tech_map = energy_map = get_raw_technology_mapping("energy")

    # if module is not energy, run subset_module_map
    if module != "energy":
        module_map = get_raw_technology_mapping(module)
        module_sub = subset_module_map(module_map)

        # Remove energy technologies that exist in module mapping
        energy_map = energy_map.query(
            "message_technology not in @module_sub.message_technology"
        )

        tech_map = pd.concat([energy_map, module_sub], ignore_index=True)

    # Read in raw data
    gea_file_path = package_data_path("costs", "energy", "cost_reduction.csv")
    energy_rates = (
        pd.read_csv(gea_file_path, header=8)
        .melt(
            id_vars=["message_technology", "technology_type"],
            var_name="reduction_rate",
            value_name="cost_reduction",
        )
        .assign(
            technology_type=lambda x: x.technology_type.fillna("NA"),
            cost_reduction=lambda x: x.cost_reduction.fillna(0),
        )
        .drop_duplicates()
        .reset_index(drop=1)
    ).reindex(["message_technology", "reduction_rate", "cost_reduction"], axis=1)

    # For module technologies with map_tech == energy, map to base technologies
    # and use cost reduction data
    module_rates_energy = (
        tech_map.query("reg_diff_source == 'energy'")
        .drop(columns=["reg_diff_source", "base_year_reference_region_cost"])
        .merge(
            energy_rates.rename(
                columns={"message_technology": "base_message_technology"}
            ),
            how="inner",
            left_on="reg_diff_technology",
            right_on="base_message_technology",
        )
        .drop(columns=["base_message_technology", "reg_diff_technology"])
        .drop_duplicates()
        .reset_index(drop=1)
    ).reindex(["message_technology", "reduction_rate", "cost_reduction"], axis=1)

    # Combine technologies that have cost reduction rates
    df_reduction_techs = pd.concat(
        [energy_rates, module_rates_energy], ignore_index=True
    )
    df_reduction_techs = df_reduction_techs.drop_duplicates().reset_index(drop=1)

    # Create unique dataframe of cost reduction rates
    # and make all cost_reduction values 0
    un_rates = pd.DataFrame(
        {
            "reduction_rate": ["none"],
            "cost_reduction": [0],
            "key": "z",
        }
    )
    # For remaining module technologies that are not mapped to energy technologies,
    # assume no cost reduction
    module_rates_noreduction = (
        tech_map.query(
            "message_technology not in @df_reduction_techs.message_technology"
        )
        .assign(key="z")
        .merge(un_rates, on="key")
        .drop(columns=["key"])
    ).reindex(["message_technology", "reduction_rate", "cost_reduction"], axis=1)

    # Concatenate base and module rates
    all_rates = pd.concat(
        [energy_rates, module_rates_energy, module_rates_noreduction],
        ignore_index=True,
    ).reset_index(drop=1)

    return all_rates


def get_technology_reduction_scenarios_data(
    first_year: int, module: str
) -> pd.DataFrame:
    """Read in technology first year and cost reduction scenarios.

    Raw data on technology first year and reduction scenarios are read from
    :file:`data/costs/[module]/first_year_[module]`. The first year the technology is
    available in MESSAGEix is adjusted to be the base year if the original first year is
    before the base year.

    Raw data on cost reduction scenarios are read from
    :file:`data/costs/[module]/scenarios_reduction_[module].csv`.

    Assumptions are made for the non-energy module for technologies' cost reduction
    scenarios that are not given.

    Parameters
    ----------
    base_year : int, optional
        The base year, by default set to global BASE_YEAR
    module : str
        Model module

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns:

        - message_technology: name of technology in MESSAGEix
        - scenario: scenario (SSP1, SSP2, SSP3, SSP4, SSP5, or LED)
        - first_technology_year: first year the technology is available in MESSAGEix.
        - reduction_rate: the cost reduction rate (either very_low, low, medium, high,
        or very_high)
    """

    energy_first_year_file = package_data_path("costs", "energy", "tech_map.csv")
    df_first_year = pd.read_csv(energy_first_year_file, skiprows=4)[
        ["message_technology", "first_year_original"]
    ]

    if module != "energy":
        module_first_year_file = package_data_path("costs", module, "tech_map.csv")
        module_first_year = pd.read_csv(module_first_year_file)[
            ["message_technology", "first_year_original"]
        ]
        df_first_year = pd.concat(
            [df_first_year, module_first_year], ignore_index=True
        ).drop_duplicates()

    tech_map = tech_energy = get_raw_technology_mapping("energy")

    if module != "energy":
        tech_module = subset_module_map(get_raw_technology_mapping(module))
        tech_energy = tech_energy.query(
            "message_technology not in @tech_module.message_technology"
        )
        tech_map = pd.concat([tech_energy, tech_module], ignore_index=True)

    tech_map = tech_map.reindex(
        ["message_technology", "reg_diff_source", "reg_diff_technology"], axis=1
    ).drop_duplicates()

    # Adjust first year:
    # - if first year is missing, set to base year
    # - if first year is after base year, then keep assigned first year
    all_first_year = (
        pd.merge(tech_map, df_first_year, on="message_technology", how="left")
        .assign(
            first_technology_year=lambda x: np.where(
                x.first_year_original.isnull(),
                first_year,
                x.first_year_original,
            )
        )
        .assign(
            first_technology_year=lambda x: np.where(
                x.first_year_original > first_year, x.first_year_original, first_year
            )
        )
        .drop(columns=["first_year_original"])
    )

    # Create new column for scenario_technology
    # - if reg_diff_source == weo, then scenario_technology = message_technology
    # - if reg_diff_source == energy, then scenario_technology = reg_diff_technology
    # - otherwise, scenario_technology = message_technology
    adj_first_year = (
        all_first_year.assign(
            scenario_technology=lambda x: np.where(
                x.reg_diff_source == "weo",
                x.message_technology,
                np.where(
                    x.reg_diff_source == "energy",
                    x.reg_diff_technology,
                    x.message_technology,
                ),
            )
        )
        .drop(columns=["reg_diff_source", "reg_diff_technology"])
        .drop_duplicates()
        .reset_index(drop=1)
    )

    # Merge with energy technologies that have given scenarios
    energy_scen_file = package_data_path("costs", "energy", "scenarios_reduction.csv")
    df_energy_scen = pd.read_csv(energy_scen_file).rename(
        columns={"message_technology": "scenario_technology"}
    )

    existing_scens = (
        pd.merge(
            adj_first_year,
            df_energy_scen,
            on=["scenario_technology"],
            how="inner",
        )
        .drop(columns=["scenario_technology"])
        .melt(
            id_vars=[
                "message_technology",
                "first_technology_year",
            ],
            var_name="scenario",
            value_name="reduction_rate",
        )
    )

    # Create dataframe of SSP1-SSP5 and LED scenarios with "none" cost reduction rate
    un_scens = pd.DataFrame(
        {
            "scenario": ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5", "LED"],
            "reduction_rate": "none",
            "key": "z",
        }
    )

    # Get remaining technologies that do not have given scenarios
    remaining_scens = (
        adj_first_year.query(
            "message_technology not in @existing_scens.message_technology.unique()"
        )
        .assign(key="z")
        .merge(un_scens, on="key")
        .drop(columns=["key", "scenario_technology"])
    )

    # Concatenate all technologies
    all_scens = (
        pd.concat([existing_scens, remaining_scens], ignore_index=True)
        .sort_values(by=["message_technology", "scenario"])
        .reset_index(drop=1)
    )

    return all_scens


def project_ref_region_inv_costs_using_reduction_rates(
    regional_diff_df: pd.DataFrame, config: Config
) -> pd.DataFrame:
    """Project investment costs for the reference region using cost reduction rates.

    This function uses the cost reduction rates for each technology under each scenario
    to project the capital costs for each technology in the reference region.

    The changing of costs is projected until the year 2100
    (hard-coded in this function), which might not be the same
    as :attr:`.Config.final_year` (:attr:`.Config.final_year` represents the final
    projection year instead). 2100 is hard coded because the cost reduction values are
    assumed to be reached by 2100.

    The returned data have the list of periods given by :attr:`.Config.seq_years`.

    Parameters
    ----------
    regional_diff_df : pandas.DataFrame
        Dataframe output from :func:`get_weo_region_differentiated_costs`
    config : .Config
        The function responds to, or passes on to other functions, the fields:
        :attr:`~.Config.base_year`,
        :attr:`~.Config.module`, and
        :attr:`~.Config.ref_region`.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns:

        - message_technology: name of technology in MESSAGEix
        - scenario: scenario (SSP1, SSP2, SSP3, SSP4, SSP5, or LED)
        - reference_region: reference region
        - first_technology_year: first year the technology is available in MESSAGEix.
        - year: year
        - inv_cost_ref_region_decay: investment cost in reference region in year.
    """

    # Get cost reduction data
    df_cost_reduction = get_cost_reduction_data(config.module)

    # Get scenarios data
    df_scenarios = get_technology_reduction_scenarios_data(config.y0, config.module)

    # Merge cost reduction data with cost reduction rates data
    df_cost_reduction = df_cost_reduction.merge(
        df_scenarios, on=["message_technology", "reduction_rate"], how="left"
    )

    # Filter for reference region, and merge with reduction scenarios and discount rates
    # Calculate cost in reference region in 2100
    df_ref = (
        regional_diff_df.query("region == @config.ref_region")
        .merge(df_cost_reduction, on="message_technology")
        .assign(
            cost_region_2100=lambda x: x.reg_cost_base_year
            - (x.reg_cost_base_year * x.cost_reduction),
            b=lambda x: (1 - config.pre_last_year_rate) * x.cost_region_2100,
            r=lambda x: (1 / (2100 - config.base_year))
            * np.log((x.cost_region_2100 - x.b) / (x.reg_cost_base_year - x.b)),
            reference_region=config.ref_region,
        )
    )

    for y in config.seq_years:
        df_ref = df_ref.assign(
            ycur=lambda x: np.where(
                y <= config.base_year,
                x.reg_cost_base_year,
                (x.reg_cost_base_year - x.b) * np.exp(x.r * (y - config.base_year))
                + x.b,
            )
        ).rename(columns={"ycur": y})

    df_inv_ref = (
        df_ref.drop(
            columns=[
                "b",
                "r",
                "reg_diff_source",
                "reg_diff_technology",
                "region",
                "base_year_reference_region_cost",
                "reg_cost_ratio",
                "reg_cost_base_year",
                "fix_ratio",
                "reduction_rate",
                "cost_reduction",
                "cost_region_2100",
            ]
        )
        .melt(
            id_vars=[
                "message_technology",
                "scenario",
                "reference_region",
                "first_technology_year",
            ],
            var_name="year",
            value_name="inv_cost_ref_region_decay",
        )
        .assign(year=lambda x: x.year.astype(int))
    ).drop_duplicates()

    return df_inv_ref
