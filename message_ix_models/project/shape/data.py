"""Tools for working with SHAPE data."""

import logging

from message_ix_models.tools.exo_data import (
    ExoDataSource,
    iamc_like_data_for_query,
    register_source,
)
from message_ix_models.util import path_fallback

log = logging.getLogger(__name__)

INFO = {
    "gdp": dict(latest="1.2", suffix=".mif", variable="GDP|PPP"),
    "gini": dict(
        latest="1.1",
        suffix=".csv",
        variable="Gini",
        drop=[
            "tgt.achieved",
            "Base gini imputed",
            "Share of final consumption among GDP imputed",
        ],
    ),
    "population": dict(latest="1.2", suffix=".mif", variable="Population"),
    "urbanisation": dict(
        latest="1.0", suffix=".csv", variable="Population|Urban|Share", drop=["Notes"]
    ),
}

# Convert unit forms appearing in files to pint-compatible expressions
UNITS = {
    "%": "",  # urbanisation
    "billion $2005/yr": "GUSD_2005 / year",  # gdp
    "NA": "dimensionless",  # gini
}


@register_source
class SHAPE(ExoDataSource):
    """Return SHAPE data.

    See :ref:`shape-data` for a description of the available data.

    Parameters
    ----------
    quantity : str
        Name of the quantity to load; one of "gdp", "gini", "population", or
        "urbanisation".
    version : str
        Version of the data to load.
    rtype : str
        Class of object to return:

        - "series": :class:`pandas.Series`
        - "quantity": :class:`genno.Quantity`

    Raises
    ------
    ValueError
        If invalid `quantity` is given.
    FileNotFoundError
        If invalid `version` is given.
    """

    id = "SHAPE"

    def __init__(self, source, source_kw):
        if source != self.id:
            raise ValueError(source)

        measure = source_kw.pop("measure", None)
        version = source_kw.pop("version", "latest")
        scenario = source_kw.pop("scenario", None)

        try:
            # Retrieve information about the `quantity`
            info = INFO[measure]
        except KeyError:
            raise ValueError(f"quantity must be one of {sorted(INFO.keys())}")

        self.raise_on_extra_kw(source_kw)

        # Choose the version: replace "latest" with the actual version
        version = version.replace("latest", info["latest"])

        # Construct path to data file
        self.path = path_fallback(
            "shape",
            f"{measure}_v{version.replace('.', 'p')}{info['suffix']}",
            where="private test",
        )
        if "test" in self.path.parts:
            log.warning(f"Reading random data from {self.path}")

        variable = info.get("variable", measure)
        self.query = " and ".join(
            [
                f"Scenario == {scenario!r}" if scenario else "True",
                f"Variable == {variable!r}",
            ]
        )

        self.to_drop = info.get("drop", [])
        if scenario:
            self.unique = "MODEL SCENARIO VARIABLE UNIT"
        else:
            self.unique = "MODEL VARIABLE UNIT"
            self.extra_dims = ("SCENARIO",)

    def __call__(self):
        # - Read the file. Use ";" for .mif files; set columns as index on load.
        # - Drop columns "Model" (meaningless); others from `info`.
        # - Drop empty columns (final column in .mif files).
        # - Convert column labels to integer.
        # - Stack to long format.
        # - Apply final column names.
        # data = shape_data_from_file(self.path, self.drop)
        return iamc_like_data_for_query(
            self.path,
            self.query,
            drop=self.to_drop,
            replace={"Unit": UNITS},
            unique=self.unique,
            # For pd.DataFrame.read_csv()
            na_values=[""],
            keep_default_na=False,
            sep=";" if self.path.suffix == ".mif" else ",",
        )
