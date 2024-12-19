from pathlib import Path
from typing import Literal


def load_pmids(input_data, load_from: Literal["string", "file"]):
    if input_data is None:
        return []
    input_data = str(input_data).strip()
    if load_from == "string":
        pmids = input_data.split(",")
    elif load_from == "file":
        pmids = []
        with open(input_data) as f:
            for line in f.readlines():
                pmids.extend(line.strip().split(","))

    pmids = drop_if_not_num(pmids)

    return pmids


def drop_if_not_num(id_list):
    checked_list = []
    for id in id_list:
        id = id.strip()
        try:
            _ = int(id)
            checked_list.append(id)
        except ValueError:
            pass

    return checked_list


def create_savepath(output_path, type, suffix):
    if output_path is None:
        if type == "query":
            savepath = Path(f"./query_{suffix}.pubtator")
        elif type == "pmids":
            savepath = Path(f"./pmids_{suffix}.pubtator")
    else:
        savepath = Path(output_path)
        savepath.parent.mkdir(parents=True, exist_ok=True)

    return savepath
