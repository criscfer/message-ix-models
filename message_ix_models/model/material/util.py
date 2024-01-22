from message_ix_models import Context
from message_ix_models.util import load_private_data
import pandas as pd
import yaml

# Configuration files
METADATA = [
    # ("material", "config"),
    ("material", "set"),
    # ("material", "technology"),
]


def read_config():
    """Read configuration from set.yaml."""
    # TODO this is similar to transport.utils.read_config; make a common
    #      function so it doesn't need to be in this file.
    context = Context.get_instance(-1)

    if "material set" in context:
        # Already loaded
        return context

    # Load material configuration
    for parts in METADATA:
        # Key for storing in the context
        key = " ".join(parts)

        # Actual filename parts; ends with YAML
        _parts = list(parts)
        _parts[-1] += ".yaml"

        context[key] = load_private_data(*_parts)

    # Read material.yaml
    # context.metadata_path=Path("C:/Users/unlu/Documents/GitHub/message_data/data")
    # context.load_config("material", "set")

    # Use a shorter name
    context["material"] = context["material set"]

    # Merge technology.yaml with set.yaml
    # context["material"]["steel"]["technology"]["add"] = (
    #     context.pop("transport technology")
    # )

    return context


def prepare_xlsx_for_explorer(filepath):
    df = pd.read_excel(filepath)

    def add_R12(str):
        if len(str) < 5:
            return "R12_" + str
        else:
            return str

    df = df[~df["Region"].isna()]
    df["Region"] = df["Region"].map(add_R12)
    df.to_excel(filepath, index=False)


def combine_df_dictionaries(*args):
    keys = set([key for tup in args for key in tup])
    comb_dict = {}
    for i in keys:
        comb_dict[i] = pd.concat([j.get(i) for j in args])
    return comb_dict


def read_yaml_file(file_path):
    with open(file_path, encoding="utf8") as file:
        try:
            data = yaml.safe_load(file)
            return data
        except yaml.YAMLError as e:
            print(f"Error while parsing YAML file: {e}")
            return None


def invert_dictionary(original_dict):
    inverted_dict = {}
    for key, value in original_dict.items():
        for array_element in value:
            if array_element not in inverted_dict:
                inverted_dict[array_element] = []
            inverted_dict[array_element].append(key)
    return inverted_dict
